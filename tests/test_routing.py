"""router(): a folder of pages, Link, navigate, and the location."""

import textwrap

import pytest

from pyweft import Renderer, TemplateError, apply_patches, diff, load_component, navigate, to_dicts
from pyweft import routing
from pyweft.hotreload import hot_swap
from pyweft.vdom import Element

APP = """
<template>
  <div>
    <nav><Link to="/">Home</Link><Link to="/orders" class="nav">Orders</Link><Link to="/orders" exact="true">Exact</Link></nav>
    <main><Pages /></main>
  </div>
</template>
<code>
from pyweft import Link, router
Pages = router("pages")
</code>
"""

PAGES = {
    "index.weft": "<template><h1>Home</h1></template>",
    "orders.weft": """
        <template><h1>Orders {{ status }} p{{ page }}</h1></template>
        <code>
        status: str = "all"
        page: int = 1
        </code>
    """,
    "order.weft": """
        <template><h1 @click="clicks += 1">Order {{ id + 1 }} ({{ clicks }})</h1></template>
        <code>
        route = "/orders/{id}"
        id: int = 0
        clicks: int = 0
        inits: list = []
        def on_init(self):
            type(self).inits.append(self.id)
        </code>
    """,
    "orders/new.weft": "<template><h1>New order</h1></template>",
    "settings/user_profile.weft": "<template><h1>Profile</h1></template>",
    "_parts/row.weft": "<template><p>not a page</p></template>",
    "not_found.weft": """
        <template><h1>Lost: {{ path }}</h1></template>
        <code>
        path: str = ""
        </code>
    """,
}


@pytest.fixture(autouse=True)
def history():
    host = routing.MemoryHistory()
    routing.set_host(host)
    yield host
    routing.set_host(routing.MemoryHistory())


def write_app(tmp_path, pages=PAGES, app=APP):
    (tmp_path / "app.weft").write_text(textwrap.dedent(app), encoding="utf-8")
    for name, src in pages.items():
        path = tmp_path / "pages" / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(textwrap.dedent(src), encoding="utf-8")
    return tmp_path / "app.weft"


def mount(tmp_path, **kw):
    App = load_component(write_app(tmp_path, **kw))
    renderer = Renderer(App())
    renderer.init_root()
    return App, renderer, renderer.render()


def walk(nodes):
    for node in nodes:
        if isinstance(node, Element):
            yield node
            yield from walk(node.children)


def text(node):
    return "".join(text(c) if isinstance(c, Element) else c.text for c in node.children)


def heading(tree):
    return text(next(n for n in walk(tree) if n.tag == "h1"))


def cycle(renderer, old):
    new = renderer.render()
    assert apply_patches(to_dicts(old), diff(old, new)) == to_dicts(new)
    return new


def go(renderer, tree, to, **kw):
    navigate(to, **kw)
    return cycle(renderer, tree)


def test_file_names_become_urls(tmp_path):
    _, r, tree = mount(tmp_path)
    assert heading(tree) == "Home"
    for to, expected in [
        ("/orders", "Orders all p1"),
        ("/orders/new", "New order"),  # a fixed segment wins over {id}
        ("/orders/41", "Order 42 (0)"),  # id arrives as an int
        ("/settings/user-profile", "Profile"),
        ("/orders/abc", "Lost: /orders/abc"),  # not an int: no such page
        ("/parts/row", "Lost: /parts/row"),
        ("/", "Home"),
    ]:
        tree = go(r, tree, to)
        assert heading(tree) == expected, to


def test_query_parameters_fill_declared_props(tmp_path):
    _, r, tree = mount(tmp_path)
    tree = go(r, tree, "/orders", query={"status": "paid", "page": "3", "other": "x"})
    assert heading(tree) == "Orders paid p3"
    assert routing.location().query == {"status": "paid", "page": "3", "other": "x"}
    tree = go(r, tree, "/orders?page=oops")  # a bad value leaves the default
    assert heading(tree) == "Orders all p1"  # and status is back to its default


def test_every_url_is_a_fresh_page(tmp_path):
    App, r, tree = mount(tmp_path)
    Order = App.components["Pages"].components["route:/orders/{id}"]
    tree = go(r, tree, "/orders/1")
    r.dispatch(next(n for n in walk(tree) if n.tag == "h1").events["click"])
    tree = cycle(r, tree)
    assert heading(tree) == "Order 2 (1)"
    tree = go(r, tree, "/orders/1?tab=notes")
    assert heading(tree) == "Order 2 (0)"
    tree = go(r, tree, "/orders/2")
    assert heading(tree) == "Order 3 (0)"
    assert Order.inits == [1, 1, 2]
    assert len(r.instances) == 5  # the old pages were disposed


def test_links_navigate_and_show_where_you_are(tmp_path, history):
    _, r, tree = mount(tmp_path)
    home, orders, exact = [n for n in walk(tree) if n.tag == "a"]
    assert home.attrs == {"href": "#/", "class": "active", "aria-current": "page"}
    assert orders.attrs == {"href": "#/orders", "class": "nav"}
    r.dispatch(orders.events["click"], {"button": 0})
    tree = cycle(r, tree)
    assert heading(tree) == "Orders all p1" and history.entries == ["/", "/orders"]
    tree = go(r, tree, "/orders/7")
    home, orders, exact = [n for n in walk(tree) if n.tag == "a"]
    assert "class" not in home.attrs and orders.attrs["class"] == "active nav"
    assert "class" not in exact.attrs  # exact: only /orders itself


def test_modified_clicks_are_left_to_the_browser(tmp_path, history):
    _, r, tree = mount(tmp_path)
    orders = [n for n in walk(tree) if n.tag == "a"][1]
    r.dispatch(orders.events["click"], {"button": 0, "ctrlKey": True})
    assert history.entries == ["/"]


def test_back_and_replace(tmp_path, history):
    _, r, tree = mount(tmp_path)
    tree = go(r, tree, "/orders")
    tree = go(r, tree, "/orders/5", replace=True)
    assert history.entries == ["/", "/orders/5"]
    routing.back()
    assert heading(cycle(r, tree)) == "Home"


def test_location_changes_from_the_host_render(tmp_path):
    _, r, tree = mount(tmp_path)
    renders = []
    r.on_invalidate = lambda: renders.append(1)
    routing.location_changed("/orders%2F9")  # as a browser might encode it
    assert renders and r.needs_render()  # the host coalesces these into one
    assert heading(cycle(r, tree)) == "Order 10 (0)"
    renders.clear()
    routing.location_changed("/orders/9/")  # the same place: nothing to do
    assert renders == []


def test_redirect_from_on_init(tmp_path, history):
    pages = dict(PAGES)
    pages["admin.weft"] = """
        <template><h1>Admin</h1></template>
        <code>
        from pyweft import navigate
        def on_init(self):
            navigate("/", replace=True)
        </code>
    """
    _, r, tree = mount(tmp_path, pages=pages)
    tree = go(r, tree, "/admin")
    assert r.after_render() is True  # the host renders again
    assert heading(cycle(r, tree)) == "Home"
    assert history.entries == ["/", "/"]  # /admin was replaced, not kept


def test_default_not_found_page(tmp_path):
    pages = {k: v for k, v in PAGES.items() if k != "not_found.weft"}
    _, r, tree = mount(tmp_path, pages=pages)
    tree = go(r, tree, "/nowhere")
    assert text(next(n for n in walk(tree) if n.tag == "p")) == "There is no page at /nowhere."


@pytest.mark.parametrize(
    "pages, message",
    [
        ({"a.weft": '<template><p/></template><code>\nroute = "/x/{id}"\n</code>'}, "declare it"),
        ({"a.weft": '<template><p/></template><code>\nroute = "x"\n</code>'}, 'must start with "/"'),
        (
            {"a.weft": '<template><p/></template><code>\nroute = "/b"\n</code>', "b.weft": "<template><p/></template>"},
            "both want the URL",
        ),
    ],
)
def test_route_mistakes_are_errors(tmp_path, pages, message):
    with pytest.raises(TemplateError, match=message):
        mount(tmp_path, pages=pages)


def test_navigate_takes_absolute_paths():
    with pytest.raises(ValueError, match="starting with /"):
        navigate("orders")


def test_hot_reload_keeps_page_state(tmp_path):
    App, r, tree = mount(tmp_path)
    tree = go(r, tree, "/orders/1")
    r.dispatch(next(n for n in walk(tree) if n.tag == "h1").events["click"])
    tree = cycle(r, tree)
    page = tmp_path / "pages" / "order.weft"
    page.write_text(page.read_text(encoding="utf-8").replace("Order ", "Order #"), encoding="utf-8")
    changed = hot_swap(r, load_component(tmp_path / "app.weft"))
    assert changed == [str(page.resolve())]
    assert heading(cycle(r, tree)) == "Order #2 (1)"


def test_pages_get_scoped_styles_under_the_app_root(tmp_path):
    pages = {"index.weft": "<template><h1>x</h1></template><style>h1 { color: red; }</style>"}
    App, r, tree = mount(tmp_path, pages=pages)
    assert "data-w-pages-index" in next(n for n in walk(tree) if n.tag == "h1").attrs


def test_trail_names_each_level(tmp_path):
    pages = dict(PAGES)
    pages["orders.weft"] = pages["orders.weft"].replace("status: str", 'crumb = "All orders"\n        status: str')
    pages["order.weft"] = pages["order.weft"].replace('route = "/orders/{id}"', 'route = "/orders/{id}"\n        crumb = "Order #{id}"')
    App, renderer, tree = mount(tmp_path, pages=pages)
    crumbs = lambda path: [(c.to, c.label) for c in routing.trail(path)]  # noqa: E731
    assert crumbs("/") == [("/", "Home")]
    assert crumbs("/orders") == [("/", "Home"), ("/orders", "All orders")]
    assert crumbs("/orders/7") == [("/", "Home"), ("/orders", "All orders"), ("/orders/7", "Order #7")]
    assert crumbs("/orders/new") == [("/", "Home"), ("/orders", "All orders"), ("/orders/new", "New")]
    # /settings has no page of its own: a crumb with no link.
    assert crumbs("/settings/user-profile") == [("/", "Home"), (None, "Settings"), ("/settings/user-profile", "User profile")]
    assert [c.label for c in routing.trail("/", home="Start")] == ["Start"]
    navigate("/orders/3")
    assert [c.label for c in routing.trail()] == ["Home", "All orders", "Order #3"]
