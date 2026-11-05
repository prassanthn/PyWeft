"""<Html :content=...>: markup parsed into vdom nodes, sanitized by default."""

import pytest

from pyweft import Renderer, component_from_source
from pyweft.parser import THtml, TemplateError, parse_template
from pyweft.rawhtml import html_nodes, parse_html, safe_url
from pyweft.vdom import Element, Text


def html(markup, trusted=False):
    """The nodes back as HTML text, for compact assertions."""
    def out(nodes):
        parts = []
        for node in nodes:
            if isinstance(node, Text):
                parts.append(node.text)
            else:
                attrs = "".join(f' {k}="{v}"' for k, v in node.attrs.items())
                parts.append(f"<{node.tag}{attrs}>{out(node.children)}</{node.tag}>")
        return "".join(parts)
    return out(html_nodes(markup, trusted))


def test_markdown_like_output_round_trips():
    src = ('<h2 id="intro">Intro</h2>\n<p>Some <strong>bold</strong> &amp; <em>em</em> '
           '<a href="https://x.org/a?b=1&amp;c=2" title="t">link</a></p>\n'
           '<ul>\n<li>one</li>\n<li>two</li>\n</ul>\n<pre><code class="language-py">x &lt; 1\n</code></pre>')
    assert html(src) == (
        '<h2 id="intro">Intro</h2>\n<p>Some <strong>bold</strong> &amp; <em>em</em> '
        '<a href="https://x.org/a?b=1&c=2" title="t">link</a></p>\n'
        '<ul>\n<li>one</li>\n<li>two</li>\n</ul>\n<pre><code class="language-py">x < 1\n</code></pre>'
    ).replace("&amp; <em>", "& <em>")


@pytest.mark.parametrize("src, expected", [
    ("<script>alert(1)</script><p>ok</p>", "<p>ok</p>"),
    ('<img src="x.png" onerror="alert(1)">', '<img src="x.png"></img>'),
    ('<a href="javascript:alert(1)">x</a>', "<a>x</a>"),
    ('<a href=" jAvA\tscript:alert(1)">x</a>', "<a>x</a>"),
    ('<a href="data:text/html,x">x</a>', "<a>x</a>"),
    ('<img src="data:image/png;base64,AAA">', '<img src="data:image/png;base64,AAA"></img>'),
    ('<a href="/relative#frag">x</a>', '<a href="/relative#frag">x</a>'),
    ('<a href="mailto:a@b.c">x</a>', '<a href="mailto:a@b.c">x</a>'),
    ("<iframe src='https://x'><p>inside</p></iframe>after", "after"),
    ("<style>body{}</style><svg><script>1</script></svg>ok", "ok"),
    ("<font color=red>kept text</font>", "kept text"),
    ("<form action='/x'><input name=q><button>Go</button></form>", "Go"),
    ('<div data-pw-in="fade" data-x="1" aria-label="ok">x</div>', '<div aria-label="ok">x</div>'),
    ('<td style="text-align: center">x</td>', '<td style="text-align: center">x</td>'),
    ('<p style="position: fixed; top: 0">x</p>', "<p>x</p>"),
    ('<p style="background: url(https://t/x)">x</p>', "<p>x</p>"),
    ('<p style="b\\61 ckground: u\\72 l(x)">x</p>', "<p>x</p>"),
    ('<img srcset="a.png 1x, javascript:x 2x">', "<img></img>"),
    ("<!-- note --><p>a</p>", "<p>a</p>"),
])
def test_sanitizing(src, expected):
    assert html(src) == expected


@pytest.mark.parametrize("src, expected", [
    ("<p>a<p>b", "<p>a</p><p>b</p>"),
    ("<ul><li>a<li>b</ul>", "<ul><li>a</li><li>b</li></ul>"),
    ("<p>a<div>b</div>", "<p>a</p><div>b</div>"),
    ("<table><tr><td>1<td>2<tr><td>3</table>",
     "<table><tr><td>1</td><td>2</td></tr><tr><td>3</td></tr></table>"),
    ("<b>bold <i>both</b> after", "<b>bold <i>both</i></b> after"),
    ("</div>stray", "stray"),
    ("a<br>b<br/>c", "a<br></br>b<br></br>c"),
    ("<dl><dt>a<dd>b<dt>c</dl>", "<dl><dt>a</dt><dd>b</dd><dt>c</dt></dl>"),
])
def test_loose_html_is_closed_like_a_browser(src, expected):
    assert html(src) == expected


def test_trusted_keeps_more_but_never_script():
    src = ('<iframe src="https://www.youtube.com/embed/x" allowfullscreen></iframe>'
           '<svg viewBox="0 0 2 2"><linearGradient id="g"></linearGradient></svg>'
           '<button onclick="x()">b</button><script>alert(1)</script>')
    assert html(src, trusted=True) == (
        '<iframe src="https://www.youtube.com/embed/x" allowfullscreen=""></iframe>'
        '<svg viewBox="0 0 2 2"><linearGradient id="g"></linearGradient></svg>'
        '<button>b</button>'
    )


def test_safe_url():
    assert safe_url("https://x") and safe_url("x/y") and safe_url("#a") and safe_url("?q=1")
    assert not safe_url("vbscript:x") and not safe_url("javascript:x")
    assert safe_url("data:image/gif;base64,x", "src", "img")
    assert not safe_url("data:image/gif;base64,x", "href", "a")


def test_parse_is_cached_and_nodes_are_fresh():
    assert parse_html("<p>x</p>") is parse_html("<p>x</p>")
    first, second = html_nodes("<p>x</p>"), html_nodes("<p>x</p>")
    assert first == second and first[0] is not second[0]


def test_markup_objects_and_none():
    class Markup(str):
        def __html__(self):
            return "<b>m</b>"
    assert html(Markup("ignored")) == "<b>m</b>"
    assert html_nodes(None) == []
    assert html(42) == "42"


def test_parser():
    (node,) = parse_template('<Html :content="body" />')
    assert node == THtml(content="body", trusted=False)
    (node,) = parse_template('<Html :content="body" trusted="true" />')
    assert node.trusted
    for src, message in [
        ('<Html content="x" />', ":content="),
        ('<Html :content="x">text</Html>', "no content"),
        ('<Html :content="x" class="a" />', "only :content= and trusted="),
        ('<Html :content="x" trusted="maybe" />', "trusted="),
    ]:
        with pytest.raises(TemplateError, match=message):
            parse_template(src)


POST = """
<template>
  <article class="post">
    <h1>{{ title }}</h1>
    <Html :content="body" />
    <button @click="edit">edit</button>
  </article>
</template>
<code>
title: str = "Hi"
body: str = "<p>first <em>post</em></p>"

def edit(self):
    self.body = "<p>changed</p><p>twice</p>"
</code>
<style>
.post p { margin: 0 }
</style>
"""


def test_renders_in_place_with_the_scope_marker():
    cls = component_from_source(POST, "Post")
    cls.__scope__ = "post"  # what the loader sets for a file with a <style>
    r = Renderer(cls())
    (article,) = r.render()
    tags = [c.tag for c in article.children if isinstance(c, Element)]
    assert tags == ["h1", "p", "button"]
    (p,) = [c for c in article.children if isinstance(c, Element) and c.tag == "p"]
    assert "data-w-post" in p.attrs and "data-w-post" in p.children[1].attrs
    (click,) = [c.events["click"] for c in article.children if isinstance(c, Element) and c.events]
    r.dispatch(click, {})
    (article,) = r.render()
    assert [c.tag for c in article.children if isinstance(c, Element)] == ["h1", "p", "p", "button"]
