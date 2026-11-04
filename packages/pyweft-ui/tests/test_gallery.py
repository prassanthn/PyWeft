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
