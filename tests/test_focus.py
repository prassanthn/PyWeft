"""ref="..." and focus(): requests resolved against the render they follow."""

import pytest

from pyweft import Renderer, component_from_source, to_dicts
from pyweft.dommodel import _node_at

FIELD = component_from_source(
    '<template><label class="field">{{ label }}<input /></label></template>'
    '<code>\nlabel: str = ""\n</code>',
    "Field",
)
BOX = component_from_source('<template><div class="box"><Slot /></div></template>', "Box")

APP = """
<template>
  <form>
    <input ref="name" />
    <If cond="more"><input ref="email" class="email" /></If>
    <Field ref="city" label="City" />
    <ul><For each="i in range(3)" key="i"><li ref="row-{{ i }}" tabindex="-1">{{ i }}</li></For></ul>
    <Box><button ref="inside">x</button></Box>
  </form>
</template>
<code>
more: bool = False

def add_email(self):
    self.more = True
    self.focus("email")
</code>
"""


def mount():
    app = component_from_source(APP, "App", components={"Field": FIELD, "Box": BOX})()
    renderer = Renderer(app)
    return app, renderer, renderer.render()


def target(tree, command):
    return _node_at(to_dicts(tree), command["path"])


def test_focus_names_the_element_and_ref_is_not_an_attribute():
    app, r, tree = mount()
    app.focus("name")
    assert r.take_commands() == [{"op": "focus", "path": [0, 0]}]
    assert "ref" not in tree[0].children[0].attrs
    assert r.take_commands() == []  # taken once


def test_a_request_can_name_an_element_its_handler_creates():
    app, r, tree = mount()
    app.add_email()
    tree = r.render()
    (command,) = r.take_commands()
    assert target(tree, command)["attrs"]["class"] == "email"


def test_refs_on_component_tags_loops_and_slot_content():
    app, r, tree = mount()
    app.focus("city")
    app.scroll_to("row-2")
    app.focus_first("inside")
    city, row, inside = r.take_commands()
    assert target(tree, city)["attrs"]["class"] == "field"  # the component's root
    assert row["op"] == "scroll_to" and target(tree, row)["children"][0]["text"] == "2"
    assert inside["op"] == "focus_first" and target(tree, inside)["tag"] == "button"


def test_unknown_or_vanished_refs_are_dropped():
    app, r, tree = mount()
    app.focus("nope")
    app.focus("email")  # not rendered: more is False
    app.save_focus()
    app.restore_focus()
    assert r.take_commands() == [{"op": "save_focus"}, {"op": "restore_focus"}]


def test_a_request_outside_a_handler_asks_the_host_to_render():
    app, r, tree = mount()
    calls = []
    r.on_invalidate = lambda: calls.append(1)
    app.focus("name")
    assert calls == [1] and r.needs_render()


def test_refs_belong_to_the_component_that_wrote_them():
    app, r, tree = mount()
    box = next(i for i in r.instances.values() if type(i) is BOX)
    box.focus("inside")  # written by the parent, not by Box
    assert r.take_commands() == []


def test_focus_needs_a_rendered_component():
    with pytest.raises(RuntimeError, match=r"focus\(\) needs the component to be rendered"):
        FIELD().focus("x")


def test_keep_in_view_names_the_element():
    app, renderer, tree = mount()
    app.keep_in_view("city")
    app.scroll_to("name")
    commands = renderer.take_commands()
    assert [c["op"] for c in commands] == ["keep_in_view", "scroll_to"]
    assert _node_at(to_dicts(tree), commands[0]["path"])["attrs"]["class"] == "field"


def test_keep_in_view_vertically_on_request():
    app, renderer, tree = mount()
    app.keep_in_view("city", vertical=True)
    app.keep_in_view("city")
    first, second = renderer.take_commands()
    assert first["vertical"] is True and "vertical" not in second
    assert first["path"] == second["path"]
    app.keep_in_view("city", flip=True)
    (third,) = renderer.take_commands()
    assert third["flip"] is True and "vertical" not in third
