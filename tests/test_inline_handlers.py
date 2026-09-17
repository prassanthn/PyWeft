"""Inline statement handlers: ``@click="count += 1"`` and friends."""

import pytest

from pyweft import ExpressionError, Renderer, component_from_source


def _click(src, *, text=None, tag="button", **params):
    cls = component_from_source(src, "Inline")
    inst = cls(**params)
    renderer = Renderer(inst)
    tree = renderer.render()

    def find(nodes):
        for n in nodes:
            if getattr(n, "tag", None) == tag and (
                text is None or any(getattr(c, "text", "") == text for c in n.children)
            ):
                return n
            hit = find(getattr(n, "children", []))
            if hit:
                return hit
        return None

    node = find(tree)
    assert node is not None, "button not found"
    renderer.dispatch(node.events["click"])
    return inst, renderer


def test_augmented_assignment_updates_state():
    inst, _ = _click(
        '<template><button @click="count += 1">+</button></template>'
        "<code>\ncount: int = 0\n</code>"
    )
    assert inst.count == 1


def test_plain_assignment_and_expression_rhs():
    inst, _ = _click(
        '<template><button @click="show = not show">t</button></template>'
        "<code>\nshow: bool = False\n</code>"
    )
    assert inst.show is True


def test_multiple_statements():
    inst, _ = _click(
        '<template><button @click="count += 1; history.append(count)">+</button></template>'
        "<code>\ncount: int = 0\nhistory: list = []\n</code>"
    )
    assert inst.count == 1 and inst.history == [1]


def test_self_is_available_in_handlers_and_interpolation():
    inst, renderer = _click(
        '<template><p>{{ self.count }}</p><button @click="self.count += 2">+</button></template>'
        "<code>\ncount: int = 0\n</code>"
    )
    assert inst.count == 2
    assert renderer.render()[0].children[0].text == "2"


def test_loop_variable_can_be_stored_into_state():
    inst, _ = _click(
        '<template><For each="item in items" key="item"><button @click="selected = item">{{ item }}</button></For></template>'
        "<code>\nitems: list = ['a', 'b']\nselected: str = ''\n</code>",
        text="b",
    )
    assert inst.selected == "b"


def test_assigning_a_loop_variable_does_not_leak_into_state():
    inst, _ = _click(
        '<template><For each="item in items"><button @click="item = 99">x</button></For></template>'
        "<code>\nitems: list = [1]\n</code>"
    )
    assert not hasattr(inst, "item")
    assert inst.items == [1]


def test_expression_handlers_still_return_their_value():
    cls = component_from_source(
        '<template><button @click="total(2)">x</button></template>'
        "<code>\ndef total(self, n):\n    return n * 21\n</code>",
        "Expr",
    )
    renderer = Renderer(cls())
    button = renderer.render()[0]
    assert renderer.dispatch(button.events["click"]) == 42


def test_statement_handlers_return_none_and_rerender():
    cls = component_from_source(
        '<template><p>{{ count }}</p><button @click="count += 1">x</button></template>'
        "<code>\ncount: int = 0\n</code>",
        "Stmt",
    )
    renderer = Renderer(cls())
    tree = renderer.render()
    assert renderer.dispatch(tree[1].events["click"]) is None
    assert renderer.render()[0].children[0].text == "1"


def test_inline_handler_in_child_targets_the_child():
    child = component_from_source(
        '<template><button @click="n += 1">{{ n }}</button></template><code>\nn: int = 0\n</code>',
        "Child",
    )
    parent = component_from_source(
        "<template><div><Child /></div></template><code>\nn: int = 100\n</code>",
        "Parent",
        components={"Child": child},
    )
    inst = parent()
    renderer = Renderer(inst)
    button = renderer.render()[0].children[0]
    renderer.dispatch(button.events["click"])
    assert inst.n == 100
    assert renderer.instances["i:0/i:0"].n == 1


def test_syntax_error_is_reported_as_expression_error():
    cls = component_from_source(
        '<template><button @click="count +== 1">x</button></template><code>\ncount: int = 0\n</code>',
        "Bad",
    )
    renderer = Renderer(cls())
    button = renderer.render()[0]
    with pytest.raises(ExpressionError, match="bad handler"):
        renderer.dispatch(button.events["click"])


def test_runtime_error_is_reported_as_expression_error():
    cls = component_from_source(
        '<template><button @click="count += \'x\'">x</button></template><code>\ncount: int = 0\n</code>',
        "Boom",
    )
    renderer = Renderer(cls())
    button = renderer.render()[0]
    with pytest.raises(ExpressionError, match="error running handler"):
        renderer.dispatch(button.events["click"])
