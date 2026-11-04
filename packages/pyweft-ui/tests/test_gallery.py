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


def _links(tree):
    out = []

    def walk(nodes):
        for node in nodes:
            if isinstance(node, Element):
                if "nav-link" in node.attrs.get("class", "").split():
                    out.append(node)
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
    assert search("MENU") == ["Dates and menus", "Menus"]   # a name match needs no hints
    assert search("zzz") == []
    app.nav_query = "slider"
    renderer.render()
    app.jump_to_first()
    commands = renderer.take_commands()
    assert [(c["op"], c.get("align")) for c in commands] == [("scroll_to", "start")]
