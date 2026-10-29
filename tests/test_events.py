"""Event specs and modifiers, the event object, and @bind."""

from typing import Optional

import pytest

from pyweft import Event, Renderer, TemplateError, component_from_source
from pyweft.binding import KEEP, convert, declared_type
from pyweft.events import parse_event_spec
from pyweft.vdom import Element


def make(src, **components):
    return component_from_source(src, "App", components=components or None)


def first(tree, tag):
    """The first element with this tag, depth first."""
    for node in tree:
        if isinstance(node, Element):
            if node.tag == tag:
                return node
            found = first(node.children, tag)
            if found:
                return found
    return None


# -------------------------------------------------------------- event specs


@pytest.mark.parametrize(
    "spec, normalised",
    [
        ("click", "click"),
        ("submit.prevent", "submit.prevent"),
        ("keydown.enter", "keydown.enter"),
        ("keydown.Enter.CTRL", "keydown.enter.ctrl"),
        ("keyup.page-down", "keyup.page-down"),
        ("keydown.a.exact.shift", "keydown.a.exact.shift"),
        ("click.right.prevent", "click.right.prevent"),
        ("click.ctrl.exact", "click.ctrl.exact"),
        ("scroll.passive", "scroll.passive"),
        ("click.once.stop.self.capture", "click.once.stop.self.capture"),
    ],
)
def test_valid_specs(spec, normalised):
    assert parse_event_spec(spec) == normalised


@pytest.mark.parametrize(
    "spec, message",
    [
        ("click.prevnt", "unknown modifier .prevnt"),
        ("click.enter", "key modifiers such as .enter only work on keydown/keyup"),
        ("wheel.passive.prevent", "contradict"),
        ("keydown.x_y", "unknown modifier"),
    ],
)
def test_invalid_specs(spec, message):
    with pytest.raises(ValueError, match=message):
        parse_event_spec(spec)


def test_typo_in_template_is_a_template_error():
    with pytest.raises(TemplateError, match=r"<form> @submit.prevnt: unknown modifier"):
        make('<template><form @submit.prevnt="save"></form></template><code>def save(self): pass</code>')


# ---------------------------------------------------------- events in vdom


KEYS = """
<template>
  <div>
    <input @keydown.enter="submit" @keydown.esc="cancel" @keydown="last = event.key" />
    <form @submit.prevent=""><button>go</button></form>
  </div>
</template>
<code>
log: list = []
last: str = ""
def submit(self, event):
    self.log.append(("submit", event.key, event["ctrlKey"]))
def cancel(self):
    self.log.append(("cancel",))
</code>
"""


def test_each_spec_is_its_own_event_key_and_handler():
    app = make(KEYS)()
    r = Renderer(app)
    tree = r.render()
    field = first(tree, "input")
    assert set(field.events) == {"keydown.enter", "keydown.esc", "keydown"}
    assert len(set(field.events.values())) == 3

    r.dispatch(field.events["keydown.enter"], {"type": "keydown", "key": "Enter", "ctrlKey": True})
    r.dispatch(field.events["keydown.esc"], {"type": "keydown", "key": "Escape"})
    r.dispatch(field.events["keydown"], {"type": "keydown", "key": "q"})
    assert app.log == [("submit", "Enter", True), ("cancel",)]
    assert app.last == "q"


def test_modifiers_only_has_no_handler():
    app = make(KEYS)()
    r = Renderer(app)
    form = first(r.render(), "form")
    assert form.events == {"submit.prevent": ""}
    assert not any(hid.endswith("#submit.prevent") for hid in r.handlers)


def test_modifiers_on_a_component_event_are_an_error():
    child = make("<template><p>c</p></template><code></code>")
    parent = make(
        '<template><div><Child @save.prevent="go" /></div></template>'
        "<code>def go(self): pass</code>",
        Child=child,
    )
    with pytest.raises(TemplateError, match="not to a component's own events"):
        Renderer(parent()).render()


def test_event_object():
    event = Event({"type": "keydown", "key": "a"})
    assert event.key == "a" and event["key"] == "a" and event == {"type": "keydown", "key": "a"}
    with pytest.raises(AttributeError, match="keydown event has no 'clientX'; it has key, type"):
        event.clientX


def test_emitted_payloads_are_not_wrapped():
    child = make('<template><button @click="emit(\'pick\', 0)">x</button></template><code></code>')
    parent = make(
        '<template><div><Child @pick="got = event" /></div></template><code>got = None</code>',
        Child=child,
    )
    app = parent()
    r = Renderer(app)
    r.dispatch(first(r.render(), "button").events["click"], {"type": "click"})
    assert app.got == 0 and type(app.got) is int


# --------------------------------------------------------------------- bind


def bound(template, code):
    app = make(f"<template>{template}</template><code>{code}</code>")()
    r = Renderer(app)
    return app, r, r.render()


def test_bind_and_own_input_handler_both_run_bind_first():
    app, r, tree = bound(
        '<input @bind="name" @input="seen.append(name)" />', 'name: str = ""\nseen: list = []'
    )
    field = first(tree, "input")
    assert list(field.events) == ["input"]
    r.dispatch(field.events["input"], {"value": "Ada"})
    assert app.name == "Ada" and app.seen == ["Ada"]


def test_bind_lazy_uses_change_and_trim():
    app, r, tree = bound('<input @bind.lazy.trim="name" />', 'name: str = ""')
    field = first(tree, "input")
    assert list(field.events) == ["change"]
    r.dispatch(field.events["change"], {"value": "  Ada  "})
    assert app.name == "Ada"


def test_bind_unknown_modifier():
    with pytest.raises(TemplateError, match=r"@bind.lazzy: unknown modifier .lazzy"):
        make('<template><input @bind.lazzy="x" /></template><code>x = ""</code>')


def test_cleared_number_box_keeps_the_type():
    app, r, tree = bound('<input @bind="number" />', "number: int = 0")
    hid = first(tree, "input").events["input"]
    r.dispatch(hid, {"value": "12"})
    r.dispatch(hid, {"value": ""})
    assert app.number == 12  # kept while the box is empty
    r.dispatch(hid, {"value": "42"})
    assert app.number == 42 and type(app.number) is int
    r.dispatch(hid, {"value": "4x"})
    assert app.number == 42


def test_optional_number_box_becomes_none_when_cleared():
    app, r, tree = bound('<input @bind="number" />', "number: int | None = 5")
    hid = first(tree, "input").events["input"]
    r.dispatch(hid, {"value": ""})
    assert app.number is None
    r.dispatch(hid, {"value": "7"})
    assert app.number == 7


def test_bind_number_on_untyped_field():
    app, r, tree = bound('<input @bind.number="x" />', 'x = ""')
    hid = first(tree, "input").events["input"]
    r.dispatch(hid, {"value": "3"})
    assert app.x == 3
    r.dispatch(hid, {"value": "2.5"})
    assert app.x == 2.5


def test_checkbox_binds_checked_both_ways():
    app, r, tree = bound('<input type="checkbox" @bind="done" />', "done: bool = False")
    box = first(tree, "input")
    assert "checked" not in box.attrs and list(box.events) == ["change"]
    r.dispatch(box.events["change"], {"value": "on", "checked": True})
    assert app.done is True
    assert "checked" in first(r.render(), "input").attrs
    r.dispatch(box.events["change"], {"value": "on", "checked": False})
    assert app.done is False
    assert "checked" not in first(r.render(), "input").attrs


def test_radio_group_binds_choice_with_its_type():
    app, r, tree = bound(
        '<div><input type="radio" value="1" @bind="size" />'
        '<input type="radio" value="2" @bind="size" /></div>',
        "size: int = 2",
    )
    one, two = first(tree, "div").children
    assert "checked" not in one.attrs and "checked" in two.attrs
    r.dispatch(one.events["change"], {"value": "1", "checked": True})
    assert app.size == 1 and type(app.size) is int
    one, two = first(r.render(), "div").children
    assert "checked" in one.attrs and "checked" not in two.attrs


def test_select_binds_value_with_its_type():
    app, r, tree = bound(
        '<select @bind="flag"><option value="True">yes</option>'
        '<option value="False">no</option></select>',
        "flag: bool = True",
    )
    select = first(tree, "select")
    assert select.attrs["value"] == "True"
    r.dispatch(select.events["input"], {"value": "False"})
    assert app.flag is False


# ------------------------------------------------------------ conversions


class Fields:
    a: int = 0
    b: Optional[float] = None
    c: str = "x"
    d = 1.5
    e = None
    f: "int" = 3  # a string annotation the field's own module can resolve
    g: list = []


@pytest.mark.parametrize(
    "field, expected",
    [
        ("a", (int, False)),
        ("b", (float, True)),
        ("c", (str, False)),
        ("d", (float, False)),
        ("e", (None, True)),
        ("f", (int, False)),
        ("g", (None, False)),
    ],
)
def test_declared_type(field, expected):
    assert declared_type(Fields, field) == expected


@pytest.mark.parametrize(
    "text, target, allows_none, number, expected",
    [
        ("5", int, False, False, 5),
        ("5.0", int, False, False, KEEP),
        ("", int, False, False, KEEP),
        ("", int, True, False, None),
        (" 2.5 ", float, False, False, 2.5),
        ("abc", float, False, False, KEEP),
        ("yes", bool, False, False, True),
        ("off", bool, False, False, False),
        ("maybe", bool, False, False, KEEP),
        ("hi", str, False, False, "hi"),
        ("", None, True, False, None),
        ("7", None, False, True, 7),
        ("7", str, False, True, 7),
    ],
)
def test_convert(text, target, allows_none, number, expected):
    assert convert(text, target, allows_none, number) == expected or (
        expected is KEEP and convert(text, target, allows_none, number) is KEEP
    )
