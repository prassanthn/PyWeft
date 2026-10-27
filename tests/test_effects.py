"""@effect: dependency tracking, re-run rules, cleanup, state writes."""

import pytest

from pyweft import (
    EffectLoopError,
    Renderer,
    apply_patches,
    component_from_source,
    diff,
    to_dicts,
)
from pyweft.vdom import Element


def settle(renderer, tree):
    """What a host does after applying patches: run the after-render pass and
    apply follow-up renders until effects stop changing state."""
    while renderer.after_render():
        new_tree = renderer.render()
        assert apply_patches(to_dicts(tree), diff(tree, new_tree)) == to_dicts(new_tree)
        tree = new_tree
    return tree


def mount(cls, **params):
    comp = cls(**params)
    comp.on_init()
    renderer = Renderer(comp)
    tree = settle(renderer, renderer.render())
    return comp, renderer, tree


def update(comp, renderer, tree, **changes):
    """Simulate a handler: change state, re-render, settle."""
    for name, value in changes.items():
        setattr(comp, name, value)
    comp.state_has_changed()
    return settle(renderer, renderer.render())


def text_of(nodes):
    return "".join(
        n.text if not isinstance(n, Element) else text_of(n.children) for n in nodes
    )


COUNTER = """
<template><p>{{ count }} {{ other }}</p></template>
<code>
from pyweft import effect

count: int = 0
other: int = 0
runs: list = []

@effect
def track(self):
    self.runs.append(self.count)
</code>
"""


# ------------------------------------------------------------------ running


def test_effect_runs_after_first_render_not_before():
    Comp = component_from_source(COUNTER, "Comp")
    comp = Comp()
    renderer = Renderer(comp)
    renderer.render()
    assert comp.runs == []  # render alone does not run effects
    renderer.after_render()
    assert comp.runs == [0]


def test_effect_reruns_only_when_its_input_changes():
    Comp = component_from_source(COUNTER, "Comp")
    comp, renderer, tree = mount(Comp)
    assert comp.runs == [0]

    tree = update(comp, renderer, tree, other=5)
    assert comp.runs == [0]  # `other` was never read by the effect

    tree = update(comp, renderer, tree, count=1)
    assert comp.runs == [0, 1]

    tree = update(comp, renderer, tree, count=1)
    assert comp.runs == [0, 1]  # same value is not a change


def test_reads_through_properties_and_helpers_are_tracked():
    Comp = component_from_source(
        """
        <template><p>x</p></template>
        <code>
from pyweft import effect

first: str = "a"
last: str = "b"
unrelated: int = 0
seen: list = []

@property
def full(self):
    return f"{self.first} {self.last}"

def shout(self):
    return self.full.upper()

@effect
def log(self):
    self.seen.append(self.shout())
        </code>
        """,
        "Comp",
    )
    comp, renderer, tree = mount(Comp)
    assert comp.seen == ["A B"]
    tree = update(comp, renderer, tree, unrelated=1)
    assert comp.seen == ["A B"]
    tree = update(comp, renderer, tree, last="c")
    assert comp.seen == ["A B", "A C"]


def test_in_place_mutation_counts_as_change():
    Comp = component_from_source(
        """
        <template><p>{{ len(items) }}</p></template>
        <code>
from pyweft import effect

items: list = []
sizes: list = []

@effect
def watch_items(self):
    self.sizes.append(len(self.items))
        </code>
        """,
        "Comp",
    )
    comp, renderer, tree = mount(Comp)
    comp.items.append("x")
    comp.state_has_changed()
    settle(renderer, renderer.render())
    assert comp.sizes == [0, 1]


# ------------------------------------------------------------------ cleanup


def test_cleanup_runs_before_rerun():
    Comp = component_from_source(
        """
        <template><p>{{ n }}</p></template>
        <code>
from pyweft import effect

n: int = 0
log: list = []

@effect
def sub(self):
    n = self.n
    self.log.append(f"start {n}")
    return lambda: self.log.append(f"stop {n}")
        </code>
        """,
        "Comp",
    )
    comp, renderer, tree = mount(Comp)
    update(comp, renderer, tree, n=1)
    assert comp.log == ["start 0", "stop 0", "start 1"]


class _Log:
    """Not a list, so Component.__init__ shares it instead of copying it."""

    def __init__(self):
        self.items = []

    def append(self, item):
        self.items.append(item)


def test_cleanup_runs_when_child_is_disposed():
    log = _Log()
    Child = component_from_source(
        """
        <template><p>child</p></template>
        <code>
from pyweft import effect

@effect
def timer(self):
    LOG.append("start")
    return lambda: LOG.append("stop")

def on_dispose(self):
    LOG.append("disposed")
        </code>
        """.replace("LOG", "self.log"),
        "Child",
    )
    Child.log = log  # shared on purpose: the instance is gone afterwards
    Parent = component_from_source(
        """
        <template><div><If cond="show"><Child /></If></div></template>
        <code>
show: bool = True
        </code>
        """,
        "Parent",
        components={"Child": Child},
    )
    comp, renderer, tree = mount(Parent)
    assert log.items == ["start"]
    update(comp, renderer, tree, show=False)
    assert log.items == ["start", "stop", "disposed"]


# ------------------------------------------------------------- state writes


def test_effect_writing_state_triggers_follow_up_render():
    Comp = component_from_source(
        """
        <template><p>{{ doubled }}</p></template>
        <code>
from pyweft import effect

count: int = 1
doubled: int = 0

@effect
def double(self):
    self.doubled = self.count * 2
        </code>
        """,
        "Comp",
    )
    comp, renderer, tree = mount(Comp)
    assert text_of(tree) == "2"  # follow-up render showed the effect's write
    tree = update(comp, renderer, tree, count=5)
    assert text_of(tree) == "10"
    assert renderer.after_render() is False  # settled


def test_effect_writing_its_own_input_settles():
    Comp = component_from_source(
        """
        <template><p>{{ n }}</p></template>
        <code>
from pyweft import effect

n: int = 0
runs: int = 0

@effect
def bump(self):
    self.runs += 1
    self.n = self.n + 1
        </code>
        """,
        "Comp",
    )
    comp, renderer, tree = mount(Comp)
    assert comp.runs == 1
    assert text_of(tree) == "1"


def test_effects_feeding_each_other_raise():
    Comp = component_from_source(
        """
        <template><p>{{ a }} {{ b }}</p></template>
        <code>
from pyweft import effect

a: int = 0
b: int = 0

@effect
def a_to_b(self):
    self.b = self.a + 1

@effect
def b_to_a(self):
    self.a = self.b + 1
        </code>
        """,
        "Comp",
    )
    comp = Comp()
    renderer = Renderer(comp)
    with pytest.raises(EffectLoopError):
        settle(renderer, renderer.render())


def test_state_has_changed_in_effect_requests_render():
    Comp = component_from_source(
        """
        <template><p>{{ len(log) }}</p></template>
        <code>
from pyweft import effect

trigger: int = 0
log: list = []

@effect
def record(self):
    self.log.append(self.trigger)
    self.state_has_changed()
        </code>
        """,
        "Comp",
    )
    comp, renderer, tree = mount(Comp)
    assert text_of(tree) == "1"


# ---------------------------------------------------------- components / hooks


def test_on_after_render_fires_for_children_with_first_flag():
    Child = component_from_source(
        """
        <template><p>c</p></template>
        <code>
calls: list = []

def on_after_render(self, first):
    self.calls.append(first)
        </code>
        """,
        "Child",
    )
    Parent = component_from_source(
        """
        <template><div><Child /><b>{{ n }}</b></div></template>
        <code>
n: int = 0
        </code>
        """,
        "Parent",
        components={"Child": Child},
    )
    comp, renderer, tree = mount(Parent)
    update(comp, renderer, tree, n=1)
    child = next(iter(renderer.instances.values()))
    assert child.calls == [True, False]


def test_child_effect_tracks_its_props():
    Child = component_from_source(
        """
        <template><p>{{ label }}</p></template>
        <code>
from pyweft import effect

label: str = ""
seen: list = []

@effect
def watch_label(self):
    self.seen.append(self.label)
        </code>
        """,
        "Child",
    )
    Parent = component_from_source(
        """
        <template><div><Child :label="title" /><b>{{ n }}</b></div></template>
        <code>
title: str = "a"
n: int = 0
        </code>
        """,
        "Parent",
        components={"Child": Child},
    )
    comp, renderer, tree = mount(Parent)
    tree = update(comp, renderer, tree, n=1)
    tree = update(comp, renderer, tree, title="b")
    child = next(iter(renderer.instances.values()))
    assert child.seen == ["a", "b"]


def test_effects_are_inherited():
    Base = component_from_source(COUNTER, "Base")

    class Derived(Base):
        pass

    comp, renderer, tree = mount(Derived)
    assert comp.runs == [0]


def test_emit_inside_effect_is_not_a_dependency():
    Child = component_from_source(
        """
        <template><p>{{ value }}</p></template>
        <code>
from pyweft import effect

value: int = 0

@effect
def announce(self):
    self.emit("changed", self.value)
        </code>
        """,
        "Child",
    )
    Parent = component_from_source(
        """
        <template><div><Child :value="v" @changed="got.append(event)" /></div></template>
        <code>
v: int = 1
got: list = []
        </code>
        """,
        "Parent",
        components={"Child": Child},
    )
    comp, renderer, tree = mount(Parent)
    # on_changed is a fresh callback every render; if it were tracked the
    # effect would re-run on every parent render.
    assert comp.got == [1]
    tree = update(comp, renderer, tree, v=1)
    assert comp.got == [1]
    update(comp, renderer, tree, v=2)
    assert comp.got == [1, 2]
