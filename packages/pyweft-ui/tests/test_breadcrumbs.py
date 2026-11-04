"""Breadcrumbs: items, links, select, folding, separators, auto from the router."""

import textwrap

import pytest

from pyweft import Renderer, load_component, navigate, routing
from pyweft.vdom import Element

from test_controls import app, cls, cycle, find, text


@pytest.fixture(autouse=True)
def history():
    routing.set_host(routing.MemoryHistory())
    yield
    routing.set_host(routing.MemoryHistory())


def every(tree, test):
    out = []

    def walk(nodes):
        for n in nodes:
            if isinstance(n, Element):
                if test(n):
                    out.append(n)
                walk(n.children)

    walk(tree)
    return out


def crumbs(tree):
    return every(tree, cls("crumb"))


def labels(tree):
    return [" ".join(text([c]).split()) for c in crumbs(tree)]


ITEMS = "picked: list = []\nTRAIL = [('/', 'Home'), {'to': '/orders', 'label': 'Orders', 'icon': 'list'}, 'Archive', ('https://example.org', 'Elsewhere'), 'Order #1041']\n"


def test_items_links_and_the_current_page(tmp_path):
    _, a, r, tree = app(tmp_path, '<div><ui.Breadcrumbs :items="TRAIL" /></div>', ITEMS)
    nav = find(tree, lambda n: n.tag == "nav")
    assert nav.attrs["aria-label"] == "Breadcrumb" and find([nav], lambda n: n.tag == "ol") is not None
    assert labels(tree) == ["Home", "Orders", "Archive", "Elsewhere", "Order #1041"]
    home, orders, archive, elsewhere, current = crumbs(tree)
    assert find([home], lambda n: n.tag == "a").attrs["href"] == "#/"         # through the router
    assert find([home], cls("sep")) is None and find([orders], cls("sep")).attrs["aria-hidden"] == "true"
    assert find([orders], cls("icon")) is not None
    assert find([archive], lambda n: n.tag == "a") is None                    # text: no link
    assert find([elsewhere], lambda n: n.tag == "a").attrs["href"] == "https://example.org"
    last = find([current], cls("text"))
    assert last.attrs["aria-current"] == "page" and find([current], lambda n: n.tag == "a") is None
    r.dispatch(find([orders], lambda n: n.tag == "a").events["click"], {"button": 0})
    assert routing.location().path == "/orders"


def test_select_makes_buttons(tmp_path):
    _, a, r, tree = app(tmp_path, '<div><ui.Breadcrumbs :items="TRAIL" @select="picked.append(event)" /></div>', ITEMS)
    buttons = every(tree, lambda n: n.tag == "button")
    assert [" ".join(text([b]).split()) for b in buttons] == ["Home", "Orders", "Elsewhere"]
    r.dispatch(buttons[1].events["click"], {})
    assert a.picked == ["/orders"] and routing.location().path == "/"


def test_long_trails_fold_into_a_menu(tmp_path):
    _, a, r, tree = app(tmp_path, '<div><ui.Breadcrumbs :items="TRAIL" max="3" separator="slash" /></div>', ITEMS)
    assert labels(tree)[0] == "Home" and labels(tree)[-1] == "/Order #1041"
    more = find(tree, cls("more"))
    trigger = find([more], lambda n: n.tag == "button")
    assert trigger.attrs["aria-label"] == "Show the levels in between"
    r.dispatch(trigger.events["click"], {})
    tree = cycle(r, tree)
    menu_items = every(tree, lambda n: n.attrs.get("role") == "menuitem")
    assert [" ".join(text([m]).split()) for m in menu_items] == ["Orders", "Archive", "Elsewhere"]
    r.dispatch(menu_items[0].events["click"], {})
    assert routing.location().path == "/orders"
    assert text([find(tree, cls("sep"))]).strip() == "/"


def test_custom_separator_and_item_fill(tmp_path):
    _, a, r, tree = app(tmp_path, '''<div><ui.Breadcrumbs :items="TRAIL[:2] + ['Here']" separator="›">
      <Fill name="item"><i class="mine">{{ item if isinstance(item, str) else item[1] if isinstance(item, tuple) else item['label'] }}{{ '!' if current else '' }}</i></Fill>
    </ui.Breadcrumbs></div>''', ITEMS)
    assert [text([i]) for i in every(tree, cls("mine"))] == ["Home", "Orders", "Here!"]
    assert text([find(tree, cls("sep"))]).strip() == "›"


APP = """
<template>
  <div><ui.Breadcrumbs auto="true" home_icon="true" /><Pages /></div>
</template>
<code>
from pyweft import router
from pyweft_ui import ui
Pages = router("pages")
</code>
"""
PAGES = {
    "index.weft": "<template><h1>Home</h1></template>",
    "orders.weft": '<template><h1>Orders</h1></template>\n<code>\ncrumb = "All orders"\n</code>',
    "order.weft": '<template><h1>One</h1></template>\n<code>\nroute = "/orders/{id}"\ncrumb = "Order #{id}"\nid: int = 0\n</code>',
}


def test_auto_follows_the_route(tmp_path):
    (tmp_path / "app.weft").write_text(textwrap.dedent(APP), encoding="utf-8")
    for name, src in PAGES.items():
        (tmp_path / "pages").mkdir(exist_ok=True)
        (tmp_path / "pages" / name).write_text(src, encoding="utf-8")
    renderer = Renderer(load_component(tmp_path / "app.weft")())
    renderer.init_root()
    tree = renderer.render()
    assert labels(tree) == ["Home"]                                       # at /: just the current page
    assert find([crumbs(tree)[0]], cls("text")).attrs["aria-current"] == "page"
    assert find(tree, cls("icon")) is not None                            # home_icon
    navigate("/orders/7")
    tree = cycle(renderer, tree)
    assert labels(tree) == ["Home", "All orders", "Order #7"]
    assert find([crumbs(tree)[1]], lambda n: n.tag == "a").attrs["href"] == "#/orders"
    navigate("/orders")
    tree = cycle(renderer, tree)
    assert labels(tree) == ["Home", "All orders"]
