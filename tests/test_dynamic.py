"""<Dynamic :is="..."> renders a component class chosen by an expression."""

import pytest

from pyweft import Renderer, TemplateError, apply_patches, component_from_source, diff, to_dicts
from pyweft.parser import parse_template

LOG: list = []

A = component_from_source(
    """
    <template><p class="a">A {{ label }} {{ count }}</p></template>
    <code>
    label: str = ""
    count: int = 0
    def on_init(self):
        LOG.append("init A " + self.label)
    def on_dispose(self):
        LOG.append("dispose A " + self.label)
    </code>
    """,
    "A",
)
A.on_init.__globals__["LOG"] = LOG
B = component_from_source(
    '<template><div class="b">B <Slot>no slot</Slot></div></template><code>\nsize: int = 1\n</code>',
    "B",
)

PARENT = """
<template>
  <section>
    <Dynamic :is="current" :props="extra" label="hi" key="ident" />
  </section>
</template>
<code>
current = None
extra = None
ident = "one"
</code>
"""


def mount(src=PARENT):
    LOG.clear()
    parent = component_from_source(src, "Parent", components={"A": A, "B": B})()
    renderer = Renderer(parent)
    return parent, renderer, renderer.render()


def cycle(renderer, old):
    new = renderer.render()
    assert apply_patches(to_dicts(old), diff(old, new)) == to_dicts(new)
    return new


def test_none_renders_nothing_then_a_class_renders():
    parent, r, tree = mount()
    assert tree[0].children == []
    parent.current = A
    tree = cycle(r, tree)
    assert tree[0].children[0].children[0].text == "A hi 0"
    assert LOG == ["init A hi"]


def test_changing_the_class_disposes_and_creates():
    parent, r, tree = mount()
    parent.current = A
    tree = cycle(r, tree)
    parent.current = B
    tree = cycle(r, tree)
    # label isn't a field of B, so it lands on B's root element.
    assert tree[0].children[0].attrs == {"class": "b", "label": "hi"}
    assert LOG == ["init A hi", "dispose A hi"]
    assert [type(i) for i in r.instances.values()] == [B]


def test_props_mapping_passes_declared_props_and_explicit_attrs_win():
    parent, r, tree = mount()
    parent.current = A
    parent.extra = {"count": 3, "label": "ignored", "title": "tip", "hidden": False}
    tree = cycle(r, tree)
    p = tree[0].children[0]
    assert p.children[0].text == "A hi 3"
    assert p.attrs["title"] == "tip" and "hidden" not in p.attrs


def test_a_new_key_means_a_new_instance_of_the_same_class():
    parent, r, tree = mount()
    parent.current = A
    tree = cycle(r, tree)
    instance = next(iter(r.instances.values()))
    instance.count = 5
    parent.ident = "two"
    tree = cycle(r, tree)
    assert tree[0].children[0].children[0].text == "A hi 0"
    assert LOG == ["init A hi", "init A hi", "dispose A hi"]


def test_same_class_and_key_keeps_state():
    parent, r, tree = mount()
    parent.current = A
    tree = cycle(r, tree)
    next(iter(r.instances.values())).count = 7
    parent.extra = {"title": "x"}
    tree = cycle(r, tree)
    assert tree[0].children[0].children[0].text == "A hi 7"
    assert LOG == ["init A hi"]


def test_slot_content_goes_to_the_dynamic_component():
    parent, r, tree = mount(
        '<template><div><Dynamic :is="components[\'B\']">filled</Dynamic></div></template>'
    )
    assert tree[0].children[0].children[1].text == "filled"


def test_not_a_component_is_an_error():
    parent, r, tree = mount()
    parent.current = "A"
    with pytest.raises(TemplateError, match="expected a component class, got 'A'"):
        r.render()


def test_is_is_required():
    with pytest.raises(TemplateError, match='needs :is="..."'):
        parse_template("<div><Dynamic /></div>")
