import pytest

from pyweft.parser import (
    TElement,
    TFor,
    TIf,
    TStatic,
    TemplateError,
    parse_template,
    rewrite_at_directives,
    split_source,
)


def test_split_source_separates_code_from_template():
    template, code, _style = split_source(
        "<template><p>hi</p></template>\n<code>\nx = 1\n</code>\n"
    )
    assert "<p>hi</p>" in template
    assert code.strip() == "x = 1"


def test_code_block_with_angle_brackets_does_not_break_parsing():
    src = """
    <template><p>{{ n }}</p></template>
    <code>
    n = 0

    def bump(self):
        if self.n < 10 and self.n > -1:
            self.n += 1
    </code>
    """
    template, code, _style = split_source(src)
    assert "self.n < 10" in code
    parse_template(template)  # must not raise


def test_markup_code_and_template_elements_stay_in_the_template():
    src = (
        "<template>\n  <p>Run <code>pyweft run</code> or <code>build</code>.</p>\n"
        "  <template><b>inert</b></template>\n</template>\n"
        "<code>\nx = 1\n</code>\n"
    )
    template, code, _ = split_source(src)
    assert "<code>pyweft run</code>" in template and "<b>inert</b></template>" in template
    assert code.strip() == "x = 1"


def test_closing_tags_inside_python_strings_stay_in_the_code():
    src = '<template><p/></template>\n<code>\nHTML = "<code>x</code> and </code>!"\ny = 2\n</code>\n<style>p {}</style>'
    _, code, style = split_source(src)
    assert 'HTML = "<code>x</code> and </code>!"' in code and "y = 2" in code
    assert style == "p {}"


def test_blocks_in_any_order_and_comments_skipped():
    src = "<!-- a <code> example -->\n<code>\nz = 3\n</code>\n<template><i/></template>"
    template, code, _ = split_source(src)
    assert template == "<i/>" and code.strip() == "z = 3"


def test_unclosed_block_raises():
    with pytest.raises(TemplateError, match="<code> block is not closed"):
        split_source("<template><p/></template><code>x = 1")


def test_missing_template_block_raises():
    with pytest.raises(TemplateError):
        split_source("<code>x = 1</code>")


def test_at_directive_rewriting_only_touches_tags():
    src = '<button @click="go" title="mail me @ x">a@b.com @notattr</button>'
    out = rewrite_at_directives(src)
    assert 'py-at-click="go"' in out
    assert "mail me @ x" in out
    assert "a@b.com @notattr" in out


def test_comments_are_left_alone():
    # An apostrophe in a comment once opened a "quote" that swallowed the
    # rest of the template, so later @click attributes stayed unrewritten.
    src = ('<div><!-- the box\'s children; <b @click="no"> --><b @click="go">y</b>'
           '<!-- unclosed')
    out = rewrite_at_directives(src)
    assert '<!-- the box\'s children; <b @click="no"> -->' in out
    assert '<b py-at-click="go">' in out and out.endswith("<!-- unclosed")
    nodes = parse_template('<div><!-- it\'s fine --><button @click="go">a</button></div>')
    assert list(nodes[0].children[0].events) == ["click"]


def test_element_directives_and_interpolation():
    nodes = parse_template(
        '<div class="row {{ cls }}"><button @click="go" key="item.id">'
        "{{ label }}</button></div>"
    )
    div = nodes[0]
    assert isinstance(div, TElement) and div.tag == "div"
    assert div.attrs["class"] == [
        ("static", "row "),
        ("expr", "cls"),
    ]
    button = div.children[0]
    assert button.events == {"click": "go"}
    assert button.key_expr == "item.id"
    assert isinstance(button.children[0], TStatic)


def test_bind_directive():
    nodes = parse_template('<input @bind="name" />')
    assert nodes[0].bind == "name"


def test_bind_rejects_non_identifier():
    with pytest.raises(TemplateError):
        parse_template('<input @bind="a.b" />')


def test_if_elseif_else_fold_into_one_node():
    nodes = parse_template(
        '<div><If cond="a"><p>A</p></If>'
        '<ElseIf cond="b"><p>B</p></ElseIf>'
        "<Else><p>C</p></Else></div>"
    )
    branch_node = nodes[0].children[0]
    assert isinstance(branch_node, TIf)
    assert [c for c, _ in branch_node.branches] == ["a", "b", None]


def test_dangling_else_raises():
    with pytest.raises(TemplateError):
        parse_template("<div><Else><p>C</p></Else></div>")


def test_if_without_cond_raises():
    with pytest.raises(TemplateError):
        parse_template("<div><If><p>A</p></If></div>")


def test_for_parsing():
    nodes = parse_template(
        '<ul><For each="item in items" key="item.id" index="i">'
        "<li>{{ i }}: {{ item.name }}</li></For></ul>"
    )
    loop = nodes[0].children[0]
    assert isinstance(loop, TFor)
    assert (loop.var, loop.iter_src, loop.index_var, loop.key_expr) == (
        "item",
        "items",
        "i",
        "item.id",
    )


def test_bad_each_expression_raises():
    with pytest.raises(TemplateError):
        parse_template('<For each="nonsense"><li>x</li></For>')


def test_malformed_xml_raises_template_error():
    with pytest.raises(TemplateError):
        parse_template("<div><p>unclosed</div>")


def test_formatting_whitespace_is_dropped():
    nodes = parse_template("<div>\n  <span>a</span>\n</div>")
    assert all(not isinstance(n, TStatic) for n in nodes[0].children)


def test_nodes_know_their_file_line():
    nodes = parse_template(
        "<div>\n  <p>a</p>\n  <For each=\"x in xs\" key=\"x\"><b>{{ x }}</b></For>\n"
        "  <If cond=\"x\"><i/></If>\n</div>",
        first_line=5,
    )
    div = nodes[0]
    loop, branch = div.children[1], div.children[2]
    assert (div.line, div.children[0].line, loop.line, loop.children[0].line, branch.line) == (5, 6, 7, 7, 8)
    # Positions don't take part in equality: the same template elsewhere is equal.
    assert parse_template("<p>a</p>") == parse_template("\n\n<p>a</p>")


def test_xml_errors_name_the_file_line_and_column():
    with pytest.raises(TemplateError, match=r"mismatched tag: line 11, column 10"):
        parse_template("<div>\n<p>oops</div>", first_line=10)
    with pytest.raises(TemplateError, match=r"not well-formed \(invalid token\): line 1, column 9"):
        parse_template('<p a="1 < 2">x</p>')


def test_loaded_components_count_lines_from_the_top_of_the_file():
    from pyweft import component_from_source

    cls = component_from_source("<code>\nx = 1\n</code>\n\n<template>\n  <div>\n    <p>{{ x }}</p>\n  </div>\n</template>\n")
    div = cls.__template__[0]
    assert (div.line, div.children[0].line) == (6, 7)
    with pytest.raises(TemplateError, match=r"mismatched tag: line 5, column 3"):
        component_from_source("<template>\n<div>\n\n\n</span>\n</template>")
