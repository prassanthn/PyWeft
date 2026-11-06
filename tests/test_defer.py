"""<Defer>: content rendered when the host says it's time (visible, idle)."""

import pytest

from pyweft import Renderer, component_from_source
from pyweft.check import check_app
from pyweft.parser import TDefer, TemplateError, parse_template
from pyweft.vdom import Element


def text(nodes):
    return "".join(text(n.children) if isinstance(n, Element) else n.text for n in nodes)


def placeholders(nodes):
    found = []
    for n in nodes:
        if isinstance(n, Element):
            if "defer" in n.events:
                found.append(n)
            found.extend(placeholders(n.children))
    return found


PAGE = """
<template>
  <main>
    <h1>top</h1>
    <Defer height="300px"><section>{{ heavy }}</section><Placeholder><p>loading...</p></Placeholder></Defer>
    <Defer when="idle"><section>second</section></Defer>
    <If cond="third"><Defer><section>third</section></Defer></If>
  </main>
</template>
<code>
heavy: str = "lots of controls"
third: bool = True
</code>
"""


def test_parse():
    (node,) = parse_template('<Defer when="idle" height="10px" :ready="go"><p>a</p><Placeholder>wait</Placeholder></Defer>')
    assert isinstance(node, TDefer) and (node.when, node.height, node.ready) == ("idle", "10px", "go")
    assert [c.tag for c in node.children] == ["p"] and node.placeholder
    for src, message in [
        ('<Defer when="soon">x</Defer>', "visible"),
        ('<Defer key="a">x</Defer>', "when="),
        ("<Defer><Placeholder>a</Placeholder><Placeholder>b</Placeholder></Defer>", "two"),
        ("<div><Placeholder>a</Placeholder></div>", "inside a <Defer>"),
    ]:
        with pytest.raises(TemplateError, match=message):
            parse_template(src)


def test_placeholders_first_then_content_on_the_hosts_word():
    app = component_from_source(PAGE, "Page")()
    r = Renderer(app)
    (main,) = r.render()
    assert text([main]) == "toploading..."
    first, second, third = placeholders(r._tree)
    assert first.attrs["data-pw-defer"] == "visible" and first.attrs["style"] == "min-height: 300px"
    assert second.attrs["data-pw-defer"] == "idle"
    # The host reports two at once: one dispatch, one render.
    r.dispatch(first.events["defer"], {"type": "defer", "also": [third.events["defer"]]})
    (main,) = r.render()
    assert text([main]) == "toplots of controlsthird"
    (second,) = placeholders(r._tree)
    r.dispatch(second.events["defer"], {"type": "defer", "also": []})
    (main,) = r.render()
    assert text([main]) == "toplots of controlssecondthird" and placeholders(r._tree) == []
    # Shown stays shown...
    r.render()
    assert placeholders(r._tree) == []
    # ...until it leaves the page: coming back, it defers again.
    app.third = False
    r.render()
    app.third = True
    r.render()
    assert len(placeholders(r._tree)) == 1


def test_ready_shows_it_at_once():
    app = component_from_source(
        "<template><div><Defer :ready='open'><b>in</b></Defer></div></template><code>\nopen: bool = False\n</code>",
        "App")()
    r = Renderer(app)
    r.render()
    assert len(placeholders(r._tree)) == 1
    app.open = True
    r.render()
    assert text(r._tree) == "in"
    app.open = False
    r.render()
    assert text(r._tree) == "in"  # once shown, it stays


def test_keyed_rows_each_defer():
    app = component_from_source(
        "<template><ul><For each='n in nums' key='n'><Defer><li>{{ n }}</li></Defer></For></ul></template>"
        "<code>\nnums: list = [1, 2, 3]\n</code>", "App")()
    r = Renderer(app)
    (ul,) = r.render()
    rows = placeholders(r._tree)
    assert [row.key for row in rows] == [1, 2, 3]
    r.dispatch(rows[1].events["defer"], {"type": "defer"})
    (ul,) = r.render()
    assert [c.tag for c in ul.children] == ["div", "li", "div"] and text([ul]) == "2"


def test_check_walks_both_parts(tmp_path):
    (tmp_path / "app.weft").write_text(
        "<template><div><Defer :ready='nope'><p>{{ missing }}</p><Placeholder>{{ also_missing }}</Placeholder></Defer></div></template>",
        encoding="utf-8")
    problems, _ = check_app(tmp_path, deps=False, a11y=False)
    names = sorted(p.message.split("unknown name ")[1].split()[0] for p in problems)
    assert names == ["'also_missing'", "'missing'", "'nope'"]
