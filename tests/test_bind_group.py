"""@bind on checkboxes bound to a list: a checkbox group."""

from pyweft import Renderer, component_from_source
from pyweft.binding import collection_type
from pyweft.check import check_app
from pyweft.vdom import Element


def boxes(nodes):
    found = []
    for node in nodes:
        if isinstance(node, Element):
            if node.tag == "input":
                found.append(node)
            found.extend(boxes(node.children))
    return found


PIZZA = """
<template>
  <div>
    <For each="t in options">
      <label><input type="checkbox" value="{{ t }}" @bind="toppings" /> {{ t }}</label>
    </For>
    <p>{{ ', '.join(toppings) }}</p>
  </div>
</template>
<code>
options: list = ["cheese", "olives", "basil"]
toppings: list[str] = ["cheese"]
</code>
"""


def test_checked_follows_membership_and_clicks_add_and_remove():
    app = component_from_source(PIZZA, "App")()
    r = Renderer(app)
    inputs = boxes(r.render())
    assert ["checked" in i.attrs for i in inputs] == [True, False, False]
    original = app.toppings
    r.dispatch(inputs[2].events["change"], {"checked": True, "value": "basil"})
    assert app.toppings == ["cheese", "basil"]
    assert original == ["cheese"]  # a new list: effects and == see the change
    r.dispatch(inputs[0].events["change"], {"checked": False})
    assert app.toppings == ["basil"]
    inputs = boxes(r.render())
    assert ["checked" in i.attrs for i in inputs] == [False, False, True]
    # Checking an already-present value doesn't add it twice.
    r.dispatch(inputs[2].events["change"], {"checked": True})
    assert app.toppings == ["basil"]


def test_typed_values_and_sets():
    app = component_from_source("""
<template>
  <div>
    <For each="row in rows" key="row['id']">
      <input type="checkbox" :value="row['id']" @bind="picked" aria-label="pick" />
    </For>
  </div>
</template>
<code>
rows: list = [{"id": 1}, {"id": 2}, {"id": 3}]
picked: set[int] | None = None
</code>
""", "App")()
    r = Renderer(app)
    inputs = boxes(r.render())
    assert inputs[1].attrs["value"] == "2"
    r.dispatch(inputs[1].events["change"], {"checked": True})
    r.dispatch(inputs[2].events["change"], {"checked": True})
    assert app.picked == {2, 3}
    inputs = boxes(r.render())
    assert ["checked" in i.attrs for i in inputs] == [False, True, True]
    r.dispatch(inputs[1].events["change"], {"checked": False})
    assert app.picked == {3}


def test_single_checkbox_still_binds_a_bool():
    app = component_from_source(
        '<template><input type="checkbox" @bind="agree" /></template><code>\nagree: bool = False\n</code>', "App",
    )()
    r = Renderer(app)
    (box,) = boxes(r.render())
    r.dispatch(box.events["change"], {"checked": True})
    assert app.agree is True


def test_own_change_handler_runs_after_the_list_updates():
    app = component_from_source("""
<template><input type="checkbox" value="a" @bind="tags" @change="seen = list(tags)" /></template>
<code>
tags: tuple = ()
seen: list = []
</code>""", "App")()
    r = Renderer(app)
    (box,) = boxes(r.render())
    r.dispatch(box.events["change"], {"checked": True})
    assert app.tags == ("a",) and app.seen == ["a"]


def test_collection_type():
    cls = component_from_source("""
<template><p /></template>
<code>
a: list[int] = []
b: set[str] | None = None
c = frozenset()
d: int = 0
e: str | None = None
</code>""", "App")
    assert [collection_type(cls, n) for n in "abcde"] == [list, set, frozenset, None, None]


def test_check_accepts_a_group(tmp_path):
    (tmp_path / "app.weft").write_text(PIZZA, encoding="utf-8")
    problems, _ = check_app(tmp_path, deps=False)
    assert problems == []
