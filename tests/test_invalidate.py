"""state_has_changed() outside a handler must reach the host as a render request."""

from pyweft import Renderer, component_from_source, effect

COUNTER = """
<template><div><p>{{ n }}</p><button @click="n += 1">+</button></div></template>
<code>
n: int = 0

def tick(self):
    self.n += 1
    self.state_has_changed()
</code>
"""


def wired(cls):
    comp = cls()
    renderer = Renderer(comp)
    calls = []
    renderer.on_invalidate = lambda: calls.append(1)
    return comp, renderer, renderer.render(), calls


def test_change_outside_handler_requests_render():
    comp, renderer, tree, calls = wired(component_from_source(COUNTER, "Counter"))
    assert not renderer.needs_render()
    comp.tick()  # as a timer or JS callback would
    assert calls == [1]
    assert renderer.needs_render()
    renderer.render()
    assert not renderer.needs_render()


def test_handler_does_not_request_extra_render():
    comp, renderer, tree, calls = wired(component_from_source(COUNTER, "Counter"))
    renderer.dispatch(tree[0].children[1].events["click"])
    assert calls == []  # the host renders after every dispatch anyway
    assert comp.n == 1 and renderer.needs_render()


def test_child_change_outside_handler_requests_render():
    Child = component_from_source(COUNTER, "Child")
    Parent = component_from_source(
        "<template><div><Child /></div></template><code></code>",
        "Parent",
        components={"Child": Child},
    )
    comp, renderer, tree, calls = wired(Parent)
    child = next(iter(renderer.instances.values()))
    child.tick()
    assert calls == [1]
    assert renderer.needs_render()


def test_effect_state_change_is_not_an_extra_request():
    Comp = component_from_source(
        """
        <template><p>{{ doubled }}</p></template>
        <code>
from pyweft import effect

n: int = 1
doubled: int = 0

@effect
def double(self):
    self.doubled = self.n * 2
    self.state_has_changed()
        </code>
        """,
        "Comp",
    )
    comp, renderer, tree, calls = wired(Comp)
    assert renderer.after_render() is True  # after_render reports it instead
    assert calls == []


def test_disposed_child_stops_requesting_renders():
    Child = component_from_source(COUNTER, "Child")
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
    comp, renderer, tree, calls = wired(Parent)
    child = next(iter(renderer.instances.values()))
    comp.show = False
    renderer.render()
    child.tick()  # a timer the child forgot to cancel
    assert calls == []
    assert not renderer.needs_render()


def test_no_host_hook_is_harmless():
    comp = component_from_source(COUNTER, "Counter")()
    renderer = Renderer(comp)
    renderer.render()
    comp.tick()
    assert renderer.needs_render()


def test_existing_on_change_hook_still_called():
    seen = []
    comp, renderer, tree, calls = wired(component_from_source(COUNTER, "Counter"))
    comp._on_change = seen.append
    comp.tick()
    assert seen == [comp] and calls == [1]


def test_effect_import_is_public():
    assert callable(effect)
