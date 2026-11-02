"""Store: state shared by components, re-rendering every page that shows it."""

import asyncio
import sys
import textwrap

import pytest

from pyweft import Renderer, Store, apply_patches, component_from_source, diff, to_dicts
from pyweft.component import declared_props

STORE = '''
import asyncio
from pyweft import Store

class Cart(Store):
    items: list = []
    owner: str = ""

    @property
    def count(self):
        return len(self.items)

    def add(self, item):
        self.items.append(item)

    async def load(self):
        await asyncio.sleep(0)
        self.items.extend(["saved"])

    def _secret(self):
        return "not wrapped"

cart = Cart()
'''

@pytest.fixture(autouse=True)
def cart_module(tmp_path, monkeypatch):
    (tmp_path / "cart_store.py").write_text(textwrap.dedent(STORE), encoding="utf-8")
    monkeypatch.syspath_prepend(str(tmp_path))
    sys.modules.pop("cart_store", None)
    yield
    sys.modules.pop("cart_store", None)


def app():
    App = component_from_source(
        """
        <template>
          <div>
            <Badge />
            <button @click="cart.add('apple')">Add</button>
            <p>{{ ', '.join(cart.items) }}</p>
          </div>
        </template>
        <code>
        from cart_store import cart
        </code>
        """,
        "App",
        components={"Badge": component_from_source(
            '<template><span class="badge">{{ cart.count }}</span></template>'
            "<code>\nfrom cart_store import cart\n</code>",
            "Badge",
        )},
    )
    renderer = Renderer(App())
    return App, renderer, renderer.render()


def cycle(renderer, old):
    new = renderer.render()
    assert apply_patches(to_dicts(old), diff(old, new)) == to_dicts(new)
    return new


def text_of(tree):
    badge, _, p = tree[0].children
    return badge.children[0].text, p.children[0].text


def test_a_change_in_one_component_shows_in_another():
    App, r, tree = app()
    r.dispatch(tree[0].children[1].events["click"])
    assert text_of(cycle(r, tree)) == ("1", "apple")


def test_changes_from_outside_a_handler_ask_the_host_to_render():
    from cart_store import cart

    App, r, tree = app()
    calls = []
    r.on_invalidate = lambda: calls.append(1)
    cart.owner = "ada"  # setting a field
    assert calls and r.needs_render()
    tree = cycle(r, tree)
    calls.clear()
    cart.add("pear")  # a method changing a list in place
    assert calls
    assert text_of(cycle(r, tree)) == ("1", "pear")
    calls.clear()
    cart.items.append("fig")  # behind the store's back: say so
    assert not calls
    cart.changed()
    assert calls and text_of(cycle(r, tree)) == ("2", "pear, fig")


def test_async_methods_notify_when_they_finish():
    from cart_store import cart

    App, r, tree = app()
    calls = []
    r.on_invalidate = lambda: calls.append(1)
    asyncio.run(cart.load())
    assert calls and cart.items == ["saved"]


def test_methods_called_while_rendering_only_read():
    from cart_store import cart

    App = component_from_source(
        "<template><p>{{ cart.add('x') or len(cart.items) }}</p></template>"
        "<code>\nfrom cart_store import cart\n</code>",
        "Reader",
    )
    r = Renderer(App())
    r.render()
    assert not r.needs_render() and not r.after_render()


def test_private_methods_and_properties_are_left_alone():
    from cart_store import Cart, cart

    assert cart._secret() == "not wrapped"
    assert isinstance(vars(Cart)["count"], property)


def test_mutable_defaults_are_per_store_and_values_can_be_given():
    from cart_store import Cart

    a, b = Cart(), Cart(owner="grace", items=["x"])
    a.add("y")
    assert a.items == ["y"] and b.items == ["x"] and b.owner == "grace"


def test_a_store_is_not_a_prop_and_is_shared_not_copied():
    from cart_store import cart

    App, r, tree = app()
    assert "cart" not in declared_props(App)
    badge = next(iter(r.instances.values()))
    assert badge.cart is cart and r.component.cart is cart


def test_effects_rerun_when_a_store_they_read_changes():
    from cart_store import cart

    seen = []
    App = component_from_source(
        "<template><p>x</p></template><code>\n"
        "from pyweft import effect\nfrom cart_store import cart\n"
        "@effect\ndef track(self):\n    SEEN.append(self.cart.count)\n</code>",
        "Watcher",
    )
    App.track.__globals__["SEEN"] = seen
    r = Renderer(App())
    r.render()
    r.after_render()
    cart.add("kiwi")
    r.render()
    r.after_render()
    r.render()
    r.after_render()  # nothing changed since: no third run
    assert seen == [0, 1]


def test_equality_and_repr():
    from cart_store import Cart

    a, b = Cart(owner="x"), Cart(owner="x")
    assert a == b and a != Cart(owner="y") and a != object()
    assert repr(a) == "Cart(items=[], owner='x')"
    assert len({a, b}) == 2  # hashed by identity, so stores can go in sets
