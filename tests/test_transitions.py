"""transition= / in= / out= / animate=: carried as data-pw-* attributes for
the runtime, which plays them (see static/runtime.js, "transitions")."""

from pyweft import Renderer
from pyweft.component import component_from_source
from pyweft.parser import parse_template


def test_motion_attributes_become_data_attributes():
    (div,) = parse_template('<div><p transition="fly y=-8" animate="flip">x</p><b in="fade" :out="spec">y</b></div>')
    p, b = div.children
    assert p.attrs.keys() == {"data-pw-in", "data-pw-out", "data-pw-animate"}
    assert b.attrs.keys() == {"data-pw-in"} and b.expr_attrs == {"data-pw-out": "spec"}


def test_svg_filters_keep_their_in_attribute():
    (svg,) = parse_template('<svg><feBlend in="SourceGraphic" mode="multiply" /></svg>')
    assert "in" in svg.children[0].attrs


def test_a_component_passes_them_to_its_root():
    Row = component_from_source("<template><li>{{ text }}</li></template><code>\ntext: str = ''\n</code>")
    App = component_from_source(
        """<template><ul><For each="t in items" key="t"><Row :text="t" transition="slide" animate="flip" /></For></ul></template>
<code>
items: list = ["a", "b"]
</code>""", components={"Row": Row})
    (ul,) = Renderer(App()).render()
    li = ul.children[0]
    assert (li.attrs["data-pw-in"], li.attrs["data-pw-out"], li.attrs["data-pw-animate"]) == ("slide", "slide", "flip")


def test_a_bound_transition_follows_state():
    App = component_from_source("""<template><p :transition="'fade' if smooth else None">x</p></template>
<code>
smooth: bool = True
</code>""")
    app = App()
    r = Renderer(app)
    assert r.render()[0].attrs["data-pw-in"] == "fade"
    app.smooth = False
    assert "data-pw-in" not in r.render()[0].attrs
