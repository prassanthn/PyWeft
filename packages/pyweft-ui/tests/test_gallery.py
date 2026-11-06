"""The gallery app loads and renders every section: a mistake in it shows
here, not only in a browser."""

from pathlib import Path

from pyweft import Renderer, load_component
from pyweft.vdom import Element

GALLERY = Path(__file__).parent.parent / "gallery" / "app.weft"


def test_the_gallery_renders_every_section():
    App = load_component(GALLERY)
    app = App()
    renderer = Renderer(app)
    renderer.init_root()
    tree = renderer.render()

    ids = set()

    def walk(nodes):
        for node in nodes:
            if isinstance(node, Element):
                if "id" in node.attrs:
                    ids.add(node.attrs["id"])
                walk(node.children)

    walk(tree)
    for section in App.SECTIONS:
        assert section.lower().replace(" ", "-") in ids, section


def _nav(tree):
    """The sidebar's tree (the gallery's Tree demo has rows too)."""
    stack = list(tree)
    while stack:
        node = stack.pop()
        if isinstance(node, Element):
            if node.attrs.get("id") == "gallery-nav":
                return node.children
            stack.extend(node.children)
    return []


def _links(tree):
    """The sidebar's sections: the tree's second-level rows."""
    tree = _nav(tree)
    out = []

    def walk(nodes):
        for node in nodes:
            if isinstance(node, Element):
                if node.attrs.get("role") == "treeitem" and node.attrs.get("aria-level") == "2":
                    out.append(node)
                walk(node.children)

    walk(tree)
    return out


def _groups(tree):
    tree = _nav(tree)
    out = []

    def walk(nodes):
        for node in nodes:
            if isinstance(node, Element):
                if node.attrs.get("role") == "treeitem" and node.attrs.get("aria-level") == "1":
                    out.append(_text(node))
                walk(node.children)

    walk(tree)
    return out


def _text(node):
    return " ".join(
        " ".join(c.text if not isinstance(c, Element) else _text(c) for c in node.children).split()
    )


def test_the_section_list_searches_controls_too():
    from pyweft.differ import diff
    from pyweft.dommodel import apply_patches
    from pyweft.vdom import to_dicts

    App = load_component(GALLERY)
    app = App()
    renderer = Renderer(app)
    renderer.init_root()
    tree = renderer.render()
    assert len(_links(tree)) == len(App.SECTIONS)
    # Every section is linked to an anchor and has a ref for Enter to jump to.
    assert all(s in App.SECTION_CONTROLS for s in App.SECTIONS)

    def search(text):
        nonlocal tree
        app.nav_query = text
        new = renderer.render()
        assert apply_patches(to_dicts(tree), diff(tree, new)) == to_dicts(new)
        tree = new
        return [_text(a) for a in _links(tree)]

    assert search("date picker") == ["Dates and menus DatePicker"]
    assert search("picker") == ["Dates and menus DatePicker, DateRangePicker"]
    assert search("switch") == ["Choices Switch"]
    assert search("MENU") == ["Menus", "Dates and menus"]   # a name match needs no hints
    assert _groups(tree) == ["Buttons and menus", "Form fields"]  # groups with a match only
    assert search("zzz") == []
    app.nav_query = "slider"
    renderer.render()
    app.jump_to_first()
    commands = renderer.take_commands()
    assert [(c["op"], c.get("align")) for c in commands] == [("scroll_to", "start")]


def test_the_sidebar_tree_groups_sections_in_page_order():
    App = load_component(GALLERY)
    flat = [name for _, _, names in App.GROUPS for name in names]
    assert flat == App.SECTIONS and len(set(flat)) == len(flat)
    app = App()
    renderer = Renderer(app)
    renderer.init_root()
    tree = renderer.render()
    assert _groups(tree) == [g for g, _, _ in App.GROUPS]
    # Each group has a heading on the page, in the same order as the cards.
    ids = []

    def walk(nodes):
        for node in nodes:
            if isinstance(node, Element):
                if node.attrs.get("id", "").startswith("group-") or node.attrs.get("id") in {
                        s.lower().replace(" ", "-") for s in App.SECTIONS}:
                    ids.append(node.attrs["id"])
                walk(node.children)
    walk(tree)
    expected = []
    for group, _, names in App.GROUPS:
        expected.append("group-" + group.lower().replace(" ", "-"))
        expected += [n.lower().replace(" ", "-") for n in names]
    assert [i for i in ids if i in expected] == expected
    # Picking a section in the tree selects it and scrolls to its card.
    row = [r for r in _links(tree) if _text(r) == "Charts"][0]
    renderer.dispatch(row.events["click"], {"type": "click"})
    renderer.render()
    assert app.nav_selected == "charts"
    assert [(c["op"], c.get("align")) for c in renderer.take_commands()] == [("scroll_to", "start")]
