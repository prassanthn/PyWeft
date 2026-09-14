"""Component composition: props, emit, lifecycle, state retention."""

import pytest

from pyweft import (
    Renderer,
    TemplateError,
    apply_patches,
    component_from_source,
    diff,
    load_component,
    to_dicts,
)
from pyweft.parser import rewrite_at_directives
from pyweft.vdom import Element

CHILD_SRC = """
<template>
  <div class="child">
    <p>{{ label }}: {{ n }}</p>
    <button @click="bump">+</button>
    <button @click="emit('poke', n)">poke</button>
  </div>
</template>

<code>
label: str = "child"
n: int = 0

def bump(self):
    self.n += 1
</code>
"""


def make_child(**extra_ns):
    return component_from_source(CHILD_SRC, "Child")


def render_cycle(renderer, old_tree):
    """Re-render, assert dommodel convergence, return the new tree."""
    old_dicts = to_dicts(old_tree)
    new_tree = renderer.render()
    ops = diff(old_tree, new_tree)
    assert apply_patches(old_dicts, ops) == to_dicts(new_tree)
    return new_tree


def find_first(nodes, tag):
    for node in nodes:
        if isinstance(node, Element):
            if node.tag == tag:
                return node
            found = find_first(node.children, tag)
            if found is not None:
                return found
    return None


def text_of(node):
    return "".join(
        c.text if not isinstance(c, Element) else text_of(c) for c in node.children
    )


# ------------------------------------------------------------------- parser


def test_colon_attr_rewritten():
    out = rewrite_at_directives('<Child :items="history" />')
    assert out == '<Child py-colon-items="history" />'


def test_colon_left_alone_in_values_and_text():
    src = '<a href="http://x/y">12:30 x:y</a>'
    assert rewrite_at_directives(src) == src


def test_namespaced_attr_not_rewritten():
    # ':' mid-name (no leading whitespace) is not the binding sugar
    src = '<div xml:lang="en" />'
    assert rewrite_at_directives(src) == src


# ------------------------------------------------------------------ rendering


def test_component_renders_with_props():
    Child = make_child()
    Parent = component_from_source(
        """
        <template><div><Child :label="title" /></div></template>
        <code>
title: str = "kid"
        </code>
        """,
        "Parent",
        components={"Child": Child},
    )
    renderer = Renderer(Parent())
    tree = renderer.render()
    p = find_first(tree, "p")
    assert text_of(p) == "kid: 0"


def test_expr_prop_passes_typed_value():
    Child = component_from_source(
        "<template><p>{{ len(items) }}</p></template><code>\nitems: list = []\n</code>",
        "Lister",
    )
    Parent = component_from_source(
        """
        <template><div><Lister :items="stuff" /></div></template>
        <code>
stuff: list = [1, 2, 3]
        </code>
        """,
        "Parent",
        components={"Lister": Child},
    )
    tree = Renderer(Parent()).render()
    assert text_of(find_first(tree, "p")) == "3"


def test_child_state_survives_parent_rerender():
    Child = make_child()
    Parent = component_from_source(
        """
        <template><div><h1>{{ title }}</h1><Child :label="title" /></div></template>
        <code>
title: str = "a"
        </code>
        """,
        "Parent",
        components={"Child": Child},
    )
    parent = Parent()
    renderer = Renderer(parent)
    tree = renderer.render()

    # bump the child twice through dispatch
    bump_id = find_first(tree, "button").events["click"]
    renderer.dispatch(bump_id)
    renderer.dispatch(bump_id)
    tree = render_cycle(renderer, tree)
    assert text_of(find_first(tree, "p")) == "a: 2"

    # parent state change re-renders everything; child keeps its counter
    parent.title = "b"
    parent.state_has_changed()
    tree = render_cycle(renderer, tree)
    assert text_of(find_first(tree, "p")) == "b: 2"


def test_emit_reaches_parent_expression():
    Child = make_child()
    Parent = component_from_source(
        """
        <template><div><Child @poke="record(event)" /></div></template>
        <code>
seen: list = []

def record(self, payload):
    self.seen.append(payload)
        </code>
        """,
        "Parent",
        components={"Child": Child},
    )
    parent = Parent()
    renderer = Renderer(parent)
    tree = renderer.render()

    buttons = find_first(tree, "div").children[0]  # child's root div
    poke_id = buttons.children[2].events["click"]  # second button
    renderer.dispatch(poke_id)
    assert parent.seen == [0]  # payload was the child's n


def test_dispose_called_when_component_leaves():
    disposed = []
    Child = make_child()

    class Tracked(Child):
        def on_dispose(self):
            disposed.append(self)

    Parent = component_from_source(
        """
        <template>
          <div>
            <If cond="show"><Tracked /></If>
            <Else><p>gone</p></Else>
          </div>
        </template>
        <code>
show: bool = True
        </code>
        """,
        "Parent",
        components={"Tracked": Tracked},
    )
    parent = Parent()
    renderer = Renderer(parent)
    tree = renderer.render()
    assert len(renderer.instances) == 1

    parent.show = False
    parent.state_has_changed()
    render_cycle(renderer, tree)
    assert len(renderer.instances) == 0
    assert len(disposed) == 1


def test_keyed_components_keep_state_across_reorder():
    Child = make_child()
    Parent = component_from_source(
        """
        <template>
          <ul>
            <For each="name in names" key="name">
              <Child :label="name" />
            </For>
          </ul>
        </template>
        <code>
names: list = ["x", "y"]
        </code>
        """,
        "Parent",
        components={"Child": Child},
    )
    parent = Parent()
    renderer = Renderer(parent)
    tree = renderer.render()

    # bump only x's counter
    ul = find_first(tree, "ul")
    x_bump = ul.children[0].children[1].events["click"]
    renderer.dispatch(x_bump)
    tree = render_cycle(renderer, tree)

    parent.names = ["y", "x"]
    parent.state_has_changed()
    tree = render_cycle(renderer, tree)

    ul = find_first(tree, "ul")
    assert text_of(ul.children[0].children[0]) == "y: 0"
    assert text_of(ul.children[1].children[0]) == "x: 1"


def test_component_children_rejected_until_slots():
    Child = make_child()
    Parent = component_from_source(
        "<template><div><Child><p>slot?</p></Child></div></template><code></code>",
        "Parent",
        components={"Child": Child},
    )
    with pytest.raises(TemplateError, match="slots"):
        Renderer(Parent()).render()


def test_expr_attr_on_plain_element():
    Comp = component_from_source(
        """
        <template>
          <span :class="'done' if done else None" :data-n="count">x</span>
        </template>
        <code>
done: bool = True
count: int = 7
        </code>
        """,
        "Comp",
    )
    comp = Comp()
    tree = Renderer(comp).render()
    span = find_first(tree, "span")
    assert span.attrs == {"class": "done", "data-n": "7"}

    comp.done = False
    tree = Renderer(comp).render()
    assert "class" not in find_first(tree, "span").attrs


# --------------------------------------------------------------------- loader


def test_loader_autoresolves_sibling_files(tmp_path):
    (tmp_path / "app.weft").write_text(
        "<template><div><TodoItem :item=\"first\" /></div></template>"
        "<code>\nfirst: dict = {'text': 'hi'}\n</code>",
        encoding="utf-8",
    )
    (tmp_path / "todo_item.weft").write_text(
        "<template><li>{{ item['text'] }}</li></template><code>\nitem: dict = {}\n</code>",
        encoding="utf-8",
    )
    App = load_component(tmp_path / "app.weft")
    tree = Renderer(App()).render()
    assert text_of(find_first(tree, "li")) == "hi"


def test_loader_missing_component_errors(tmp_path):
    (tmp_path / "app.weft").write_text(
        "<template><div><Missing /></div></template><code></code>", encoding="utf-8"
    )
    with pytest.raises(TemplateError, match="Missing"):
        load_component(tmp_path / "app.weft")


def test_loader_detects_cycles(tmp_path):
    (tmp_path / "a.weft").write_text(
        "<template><div><B /></div></template><code></code>", encoding="utf-8"
    )
    (tmp_path / "b.weft").write_text(
        "<template><div><A /></div></template><code></code>", encoding="utf-8"
    )
    with pytest.raises(TemplateError, match="circular"):
        load_component(tmp_path / "a.weft")
