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
    template, code = split_source(
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
    template, code = split_source(src)
    assert "self.n < 10" in code
    parse_template(template)  # must not raise


def test_missing_template_block_raises():
    with pytest.raises(TemplateError):
        split_source("<code>x = 1</code>")


def test_at_directive_rewriting_only_touches_tags():
    src = '<button @click="go" title="mail me @ x">a@b.com @notattr</button>'
    out = rewrite_at_directives(src)
    assert 'py-at-click="go"' in out
    assert "mail me @ x" in out
    assert "a@b.com @notattr" in out


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
