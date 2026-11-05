"""<Head>: title, meta, link and style for the page's head."""

import json
import textwrap

import pytest

from pyweft import Renderer, compiler, component_from_source
from pyweft.parser import THead, TemplateError, parse_template
from pyweft.prerender import head_html, prerender, to_html
from pyweft.vdom import Element, Text

PAGE = """
<template>
  <article>
    <Head>
      <title>{{ name }} - Shop</title>
      <meta name="description" :content="summary" />
      <If cond="image">
        <meta property="og:image" :content="image" />
      </If>
    </Head>
    <h1>{{ name }}</h1>
    <button @click="rename">rename</button>
  </article>
</template>
<code>
name: str = "Order 7"
summary: str = "Seven things"
image = None
def rename(self):
    self.name = "Order 8"
</code>
"""


def test_parse():
    (node,) = parse_template('<Head><title>x</title><meta name="a" content="b" /></Head>')
    assert isinstance(node, THead) and [c.tag for c in node.children] == ["title", "meta"]


@pytest.mark.parametrize("src, message", [
    ("<Head><script src='x.js'></script></Head>", "not <script>"),
    ("<Head>some text</Head>", "not text"),
    ("<Head><meta @click='x' /></Head>", "no event handlers"),
    ("<Head><title><b>x</b></title></Head>", "text only"),
    ("<Head><link rel='x'>a</link></Head>", "no content"),
    ("<Head lang='en'><title>x</title></Head>", "no attributes"),
])
def test_parse_errors(src, message):
    with pytest.raises(TemplateError, match=message):
        parse_template(src)


@pytest.mark.parametrize("enabled", [True, False])
def test_rendered_into_head_not_in_place_and_sent_on_change(enabled, monkeypatch):
    monkeypatch.setattr(compiler, "ENABLED", enabled)
    r = Renderer(component_from_source(PAGE, "Page")())
    (article,) = r.render()
    assert [c.tag for c in article.children if isinstance(c, Element)] == ["h1", "button"]
    (cmd,) = r.take_commands()
    assert cmd["op"] == "head"
    assert [(n["tag"], n["attrs"]) for n in cmd["nodes"]] == [
        ("title", {}), ("meta", {"name": "description", "content": "Seven things"}),
    ]
    assert cmd["nodes"][0]["children"] == [{"type": "text", "text": "Order 7 - Shop"}]
    assert r.head == cmd["nodes"]

    r.render()
    assert r.take_commands() == []  # unchanged: nothing to send

    (click,) = r.handlers
    r.dispatch(click, {})
    r.render()
    (cmd,) = r.take_commands()
    assert cmd["nodes"][0]["children"][0]["text"] == "Order 8 - Shop"


def test_children_and_disposal_add_and_remove_tags():
    child = component_from_source(
        '<template><p><Head><link rel="canonical" href="/x" /></Head>x</p></template>', "Child")
    app = component_from_source(
        "<template><div><Head><title>App</title></Head><If cond='shown'><Child /></If></div></template>"
        "<code>\nshown: bool = True\n</code>", "App", components={"Child": child})
    root = app()
    r = Renderer(root)
    r.render()
    assert [n["tag"] for n in r.take_commands()[0]["nodes"]] == ["title", "link"]
    root.shown = False
    r.render()
    assert [n["tag"] for n in r.take_commands()[0]["nodes"]] == ["title"]


def test_resend_only_when_there_is_something():
    r = Renderer(component_from_source("<template><p>x</p></template>", "App")())
    r.render()
    r.resend_head()
    r.render()
    assert r.take_commands() == []
    r = Renderer(component_from_source(PAGE, "Page")())
    r.render()
    r.take_commands()
    r.resend_head()
    r.render()
    assert [c["op"] for c in r.take_commands()] == ["head"]


def test_head_html_marks_tags_and_takes_out_the_title():
    nodes = [
        Element("title", {}, {}, [Text("A & B")]),
        Element("meta", {"name": "description", "content": "x \"y\""}),
        Element("style", {}, {}, [Text("a > b { color: red }")]),
    ]
    tags, title = head_html(nodes)
    assert title == "A & B"
    assert tags == ('<meta name="description" content="x &quot;y&quot;" data-pyweft-head>'
                    '<style data-pyweft-head>a > b { color: red }</style>')
    assert to_html([Element("style", {}, {}, [Text("</style><script>")])]) == "<style><\\/style><script></style>"


def test_prerender_and_the_shell(tmp_path):
    from pyweft.cli import render_shell

    (tmp_path / "app.weft").write_text(textwrap.dedent(PAGE), encoding="utf-8")
    result = prerender(tmp_path)
    assert result["title"] == "Order 7 - Shop"
    assert result["head"] == '<meta name="description" content="Seven things" data-pyweft-head>'
    page = render_shell(tmp_path, prerender=True)
    title = f'<title data-pyweft-title="{tmp_path.name}">Order 7 - Shop</title>'
    assert title in page
    assert '<meta name="description" content="Seven things" data-pyweft-head>' in page
    assert page.index("data-pyweft-head") < page.index("</head>")


def test_desktop_window_title(tmp_path):
    from pyweft.desktop import DesktopApp

    class Window:
        title = None

        def set_title(self, title):
            self.title = title

        def evaluate_js(self, script):
            self.last = script

    (tmp_path / "app.weft").write_text(textwrap.dedent(PAGE), encoding="utf-8")
    window = Window()
    app = DesktopApp(tmp_path, window)
    app.start()
    try:
        app.call(lambda: app.mount("/"))
        app.call(app.settle)
        assert window.title == "Order 7 - Shop"
        assert json.loads(window.last[len("pyweftDesktop.commands("):-1])[0]["op"] == "head"
    finally:
        app.stop()
