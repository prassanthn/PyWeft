import pytest

from pyweft import Element, Renderer, Text, component_from_source
from pyweft.parser import TemplateError

COUNTER = """
<template>
  <div class="counter">
    <h1>Count: {{ count }}</h1>
    <input @bind="name" placeholder="your name" />
    <button @click="increment">+1</button>
    <If cond="count > 2">
      <p>a lot, {{ name }}</p>
    </If>
    <Else>
      <p>keep going</p>
    </Else>
  </div>
</template>

<code>
count: int = 0
name: str = ""

def increment(self):
    self.count += 1
</code>
"""


def render(component):
    renderer = Renderer(component)
    return renderer, renderer.render()


def test_imported_functions_are_called_as_plain_functions(tmp_path, monkeypatch):
    (tmp_path / "helpers_for_test.py").write_text(
        "def shout(text):\n    return text.upper()\n\n"
        "def greeting(self):\n    return 'hi ' + self.name\n",
        encoding="utf-8",
    )
    monkeypatch.syspath_prepend(str(tmp_path))
    comp = component_from_source(
        """
        <template><p @click="said.append(shout('click'))">{{ shout(name) }} {{ greeting() }} {{ local() }}</p></template>
        <code>
        from helpers_for_test import shout, greeting
        name: str = "ada"
        said: list = []
        def local(self):
            return shout(self.name[::-1])
        </code>
        """
    )()
    renderer, tree = render(comp)
    assert tree[0].children[0].text == "ADA hi ada ADA"
    renderer.dispatch(tree[0].events["click"])
    assert comp.said == ["CLICK"]


def test_renders_interpolated_text():
    comp = component_from_source(COUNTER, "Counter")()
    _, tree = render(comp)
    heading = tree[0].children[0]
    assert heading.tag == "h1"
    assert heading.children[0].text == "Count: 0"


def test_click_handler_mutates_state_and_rerenders():
    comp = component_from_source(COUNTER, "Counter")()
    renderer, tree = render(comp)
    button = tree[0].children[2]
    renderer.dispatch(button.events["click"])
    assert comp.count == 1
    assert renderer.render()[0].children[0].children[0].text == "Count: 1"


def test_bind_sets_value_attribute_and_coerces_type():
    comp = component_from_source(COUNTER, "Counter")()
    renderer, tree = render(comp)
    field = tree[0].children[1]
    assert field.attrs["value"] == ""
    renderer.dispatch(field.events["input"], {"value": "Prassanth"})
    assert comp.name == "Prassanth"


def test_bind_coerces_to_existing_int_type():
    src = """
    <template><input @bind="n" /></template>
    <code>
    n: int = 0
    </code>
    """
    comp = component_from_source(src, "NumBox")()
    renderer, tree = render(comp)
    renderer.dispatch(tree[0].events["input"], {"value": "42"})
    assert comp.n == 42 and isinstance(comp.n, int)


def test_if_else_branches():
    cls = component_from_source(COUNTER, "Counter")
    comp = cls()
    _, tree = render(comp)
    assert tree[0].children[3].children[0].text == "keep going"
    comp.count = 5
    _, tree = render(comp)
    assert "a lot" in tree[0].children[3].children[0].text


def test_stale_handler_id_is_a_noop():
    comp = component_from_source(COUNTER, "Counter")()
    renderer, _ = render(comp)
    assert renderer.dispatch("nope#click") is None


LIST = """
<template>
  <ul>
    <For each="item in items" key="item['id']">
      <li @click="remove(item)">{{ item['label'] }}</li>
    </For>
  </ul>
</template>

<code>
items: list = []

def remove(self, item):
    self.items = [i for i in self.items if i['id'] != item['id']]
</code>
"""


def test_keyed_loop_assigns_keys_and_stable_handler_ids():
    cls = component_from_source(LIST, "List")
    comp = cls(items=[{"id": "a", "label": "A"}, {"id": "b", "label": "B"}])
    renderer, tree = render(comp)
    rows = tree[0].children
    assert [r.key for r in rows] == ["a", "b"]
    first_id = rows[0].events["click"]

    comp.items = list(reversed(comp.items))
    _, tree = render(comp)
    moved = [r for r in tree[0].children if r.key == "a"][0]
    assert moved.events["click"] == first_id  # id followed the key, not the slot


def test_loop_handler_receives_loop_variable():
    cls = component_from_source(LIST, "List")
    comp = cls(items=[{"id": "a", "label": "A"}, {"id": "b", "label": "B"}])
    renderer, tree = render(comp)
    renderer.dispatch(tree[0].children[0].events["click"])
    assert [i["id"] for i in comp.items] == ["b"]


def test_index_variable_available():
    src = """
    <template><ul><For each="x in xs" index="i"><li>{{ i }}-{{ x }}</li></For></ul></template>
    <code>
    xs: list = []
    </code>
    """
    comp = component_from_source(src, "Idx")(xs=["p", "q"])
    _, tree = render(comp)
    assert [li.children[0].text for li in tree[0].children] == ["0-p", "1-q"]


def test_keyed_loop_body_must_be_single_element():
    src = """
    <template><ul><For each="x in xs" key="x"><li>{{ x }}</li><li>extra</li></For></ul></template>
    <code>
    xs: list = []
    </code>
    """
    comp = component_from_source(src, "Bad")(xs=["a"])
    with pytest.raises(TemplateError):
        render(comp)


def test_mutable_class_defaults_are_not_shared_between_instances():
    cls = component_from_source(LIST, "List")
    a, b = cls(), cls()
    a.items.append({"id": "x", "label": "X"})
    assert b.items == []


def test_none_iterable_renders_nothing():
    src = """
    <template><ul><For each="x in xs"><li>{{ x }}</li></For></ul></template>
    <code>
    xs = None
    </code>
    """
    comp = component_from_source(src, "Empty")()
    _, tree = render(comp)
    assert tree[0].children == []


def test_state_has_changed_notifies_host():
    seen = []
    comp = component_from_source(COUNTER, "Counter")()
    comp._on_change = seen.append
    renderer, tree = render(comp)
    renderer.dispatch(tree[0].children[2].events["click"])
    assert seen == [comp]
