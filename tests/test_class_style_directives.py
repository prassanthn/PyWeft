"""class:name="expr" and style:prop="expr"."""

from pyweft import Renderer
from pyweft.component import component_from_source
from pyweft.parser import parse_template, rewrite_at_directives


def render(template, code=""):
    App = component_from_source(f"<template>{template}</template><code>\n{code}\n</code>")
    app = App()
    renderer = Renderer(app)
    return app, renderer, renderer.render()


def test_parsed_into_toggles():
    (div,) = parse_template('<div class="a" class:on="x > 1" style:width="w" style:--level="lvl">t</div>')
    assert div.class_toggles == {"on": "x > 1"} and div.style_props == {"width": "w", "--level": "lvl"}
    assert div.attrs.keys() == {"class"}


def test_only_attribute_names_are_rewritten():
    src = '<p title="class:x=1" data-y="style:a=b" class:big="n">class:x="1" in text</p>'
    out = rewrite_at_directives(src)
    assert 'title="class:x=1"' in out and 'data-y="style:a=b"' in out and 'class:x="1" in text' in out
    assert "py-class-big=" in out


def test_classes_add_to_static_and_bound_ones():
    app, r, (div,) = render('<div class="card" class:active="on" class:big="n > 2"><p :class="kind" class:y="on">a</p></div>',
                            "on: bool = True\nn: int = 3\nkind: str = 'note'")
    assert div.attrs["class"] == "card active big" and div.children[0].attrs["class"] == "note y"
    app.on, app.n = False, 1
    (div,) = r.render()
    assert div.attrs["class"] == "card" and div.children[0].attrs["class"] == "note"


def test_style_properties_add_and_drop():
    app, r, (div,) = render('<div style="color: red;" style:width="str(w) + \'px\'" style:--level="lvl" style:opacity="fade">x</div>',
                            "w: int = 30\nlvl: float = 0.5\nfade = None")
    assert div.attrs["style"] == "color: red; width: 30px; --level: 0.5"
    app.fade = 0.4
    (div,) = r.render()
    assert div.attrs["style"].endswith("opacity: 0.4")
    _, _, (span,) = render('<span style:display="None if True else \'x\'">y</span>')
    assert "style" not in span.attrs


def test_on_a_component_they_reach_its_root():
    Badge = component_from_source('<template><span class="badge">{{ text }}</span></template><code>\ntext: str = ""\n</code>')
    App = component_from_source('<template><div><Badge text="new" class:hot="hot" style:color="tint" /></div></template>'
                                '<code>\nhot: bool = True\ntint: str = "red"\n</code>', components={"Badge": Badge})
    (div,) = Renderer(App()).render()
    span = div.children[0]
    assert span.attrs["class"] == "badge hot" and span.attrs["style"] == "color: red"
