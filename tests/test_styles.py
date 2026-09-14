"""Component-scoped <style> blocks: selector rewriting, marker stamping,
and collection across the component tree."""

import pytest

from pyweft import Renderer, collect_styles, component_from_source, scope_css
from pyweft.parser import split_source


# ------------------------------------------------------------ selector rewrite

A = "[data-w-x]"


@pytest.mark.parametrize(
    "selector, expected",
    [
        (".a", f".a{A}"),
        ("div", f"div{A}"),
        ("*", f"*{A}"),
        ("#id.cls[href]", f"#id.cls[href]{A}"),
        (".a .b", f".a .b{A}"),
        ("ul > li", f"ul > li{A}"),
        ("h1 + p", f"h1 + p{A}"),
        ("h1 ~ p", f"h1 ~ p{A}"),
        ("ul>li", f"ul>li{A}"),
        ("a:hover", f"a:hover{A}"),
        ("a::before", f"a{A}::before"),
        ("a:before", f"a{A}:before"),
        ("li:nth-child(2n + 1)", f"li:nth-child(2n + 1){A}"),
        (":is(.a, .b) span", f":is(.a, .b) span{A}"),
        (":not(.done)::after", f":not(.done){A}::after"),
        ('[data-x="a b"]', f'[data-x="a b"]{A}'),
        ("input::placeholder", f"input{A}::placeholder"),
    ],
)
def test_marker_lands_on_the_last_compound(selector, expected):
    assert scope_css(f"{selector} {{ color: red }}", "x") == f"{expected} {{ color: red }}"


def test_selector_lists_are_scoped_individually():
    out = scope_css(".a, .b > .c,\n.d::before { x: y }", "x")
    assert out == f".a{A}, .b > .c{A}, .d{A}::before {{ x: y }}"


def test_conditional_at_rules_are_descended_into():
    css = "@media (max-width: 40rem) { .a { x: y } @supports (display: grid) { .b { z: w } } }"
    assert scope_css(css, "x") == (
        f"@media (max-width: 40rem) {{ .a{A} {{ x: y }} "
        f"@supports (display: grid) {{ .b{A} {{ z: w }} }} }}"
    )


def test_keyframes_and_font_face_pass_through():
    css = "@keyframes spin { from { r: 0 } to { r: 1 } } @font-face { font-family: F } .a { animation: spin 1s }"
    assert scope_css(css, "x") == (
        f"@keyframes spin {{ from {{ r: 0 }} to {{ r: 1 }} }} "
        f"@font-face {{ font-family: F }} .a{A} {{ animation: spin 1s }}"
    )


def test_import_statement_before_a_rule_is_left_alone():
    assert scope_css("@import url(x.css); .a { b: c }", "x") == f"@import url(x.css); .a{A} {{ b: c }}"


def test_comments_are_stripped_and_braces_in_strings_ignored():
    css = "/* .z { } */ .a::before { content: \"}\"; } .b { c: d }"
    assert scope_css(css, "x") == f" .a{A}::before {{ content: \"}}\"; }} .b{A} {{ c: d }}"


def test_scope_id_is_used_verbatim():
    assert scope_css(".a { }", "todo_item") == ".a[data-w-todo_item] { }"


# ---------------------------------------------------------------- parsing

def test_split_source_returns_style_block():
    template, code, style = split_source(
        "<template><p/></template>\n<style>\n  .p { color: red }\n</style>\n<code>\nx = 1\n</code>"
    )
    assert template == "<p/>"
    assert code.strip() == "x = 1"
    assert style.strip() == ".p { color: red }"


def test_style_block_may_contain_child_combinators():
    template, _, style = split_source("<style>ul > li { x: y }</style><template><ul/></template>")
    assert template == "<ul/>"
    assert "ul > li" in style


# -------------------------------------------------------------- rendering

CHILD = """
<template>
  <li class="row"><span>{{ label }}</span></li>
</template>
<style>
.row { display: flex }
</style>
<code>
label: str = ""
</code>
"""

PARENT = """
<template>
  <div class="box">
    <Child label="one" />
    <p>plain</p>
  </div>
</template>
<style>
.box { padding: 1rem }
.row { margin: 0 }
</style>
"""

UNSTYLED = """
<template><section><b>hi</b></section></template>
"""


def test_component_class_carries_scoped_style():
    Child = component_from_source(CHILD, "Child")
    assert Child.__scope__ == "child"
    assert Child.__style__ == ".row[data-w-child] { display: flex }"


def test_no_style_block_means_no_scope_and_no_markers():
    Plain = component_from_source(UNSTYLED, "Plain")
    assert Plain.__scope__ is None and Plain.__style__ == ""
    section = Renderer(Plain()).render()[0]
    assert not any(k.startswith("data-w-") for k in section.attrs)
    assert not any(k.startswith("data-w-") for k in section.children[0].attrs)


def test_every_element_of_a_styled_component_is_marked():
    Child = component_from_source(CHILD, "Child")
    li = Renderer(Child()).render()[0]
    assert li.attrs["data-w-child"] == ""
    assert li.children[0].attrs["data-w-child"] == ""


def test_child_root_gets_parent_marker_but_child_internals_do_not():
    Child = component_from_source(CHILD, "Child")
    Parent = component_from_source(PARENT, "Parent", components={"Child": Child})
    div = Renderer(Parent()).render()[0]
    assert div.attrs["data-w-parent"] == ""
    li = div.children[0]
    assert li.tag == "li"
    assert li.attrs["data-w-child"] == "" and li.attrs["data-w-parent"] == ""
    span = li.children[0]
    assert "data-w-child" in span.attrs and "data-w-parent" not in span.attrs
    p = div.children[1]
    assert "data-w-parent" in p.attrs and "data-w-child" not in p.attrs


def test_markers_survive_a_rerender_and_diff_is_empty():
    from pyweft import diff

    Child = component_from_source(CHILD, "Child")
    r = Renderer(Child())
    first = r.render()
    second = r.render()
    assert diff(first, second) == []


def test_collect_styles_walks_the_tree_once_per_class():
    Child = component_from_source(CHILD, "Child")
    Parent = component_from_source(PARENT, "Parent", components={"Child": Child, "Again": Child})
    css = collect_styles(Parent)
    assert css.count(".row[data-w-child]") == 1
    assert ".box[data-w-parent]" in css
    assert ".row[data-w-parent]" in css
    assert css.index("[data-w-parent]") < css.index("[data-w-child]")


def test_loader_uses_file_stem_as_scope(tmp_path):
    from pyweft import load_component

    (tmp_path / "app.weft").write_text(
        "<template><TodoItem /></template>", encoding="utf-8"
    )
    (tmp_path / "todo_item.weft").write_text(
        "<template><li>x</li></template><style>li { a: b }</style>", encoding="utf-8"
    )
    App = load_component(tmp_path / "app.weft")
    assert App.__scope__ is None
    Item = App.components["TodoItem"]
    assert Item.__scope__ == "todo_item"
    assert collect_styles(App) == "li[data-w-todo_item] { a: b }"
    li = Renderer(App()).render()[0]
    assert li.attrs == {"data-w-todo_item": ""}
