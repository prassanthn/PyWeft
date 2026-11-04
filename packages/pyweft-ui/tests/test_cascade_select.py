"""CascadeSelect: nested options, one level at a time."""

import asyncio

from pyweft.vdom import Element

from test_controls import app, cls, cycle, find, text


def every(tree, test):
    out = []

    def walk(nodes):
        for n in nodes:
            if isinstance(n, Element):
                if test(n):
                    out.append(n)
                walk(n.children)

    walk(tree)
    return out


def menus(tree):
    return every(tree, lambda n: n.attrs.get("role") == "menu")


def items(menu):
    return [e.children[0] for e in menu.children if e.attrs.get("role") == "none" and e.children]


def label(n):
    return " ".join(text(every([n], cls("label"))).split()) or " ".join(text([n]).split())


CODE = """
city = None
paths: list = []
blurs: list = []
loads: list = []
PLACES = [
    {"value": "au", "label": "Australia", "children": [
        {"value": "nsw", "label": "New South Wales", "children": [
            {"value": "syd", "label": "Sydney"}, {"value": "new", "label": "Newcastle"}]},
        {"value": "qld", "label": "Queensland", "children": [{"value": "bne", "label": "Brisbane"}]},
    ]},
    {"value": "ca", "label": "Canada", "children": None},
    {"value": "nz", "label": "New Zealand", "disabled": True},
]

def load(self, value):
    self.loads.append(value)
"""
FIELD = ('<div><ui.CascadeSelect label="City" :options="PLACES" @bind="city" @select="paths.append(event)" '
         '@blur="blurs.append(event)" @load="load(event)" {extra} /></div>')


def field(tmp_path, extra="", code=CODE):
    return app(tmp_path, FIELD.replace("{extra}", extra), code)


def open_field(r, tree):
    r.dispatch(find(tree, cls("control")).events["click"], {})
    return cycle(r, tree)


def test_choose_a_leaf_through_the_levels(tmp_path):
    _, a, r, tree = field(tmp_path)
    trigger = find(tree, cls("control"))
    assert trigger.attrs["aria-haspopup"] == "menu" and text(every(tree, cls("shown"))) == "Choose…"
    assert find(tree, cls("label")).attrs["for"] == trigger.attrs["id"]
    tree = open_field(r, tree)
    (top,) = menus(tree)
    assert [label(i) for i in items(top)] == ["Australia", "Canada", "New Zealand"]
    assert "disabled" in items(top)[2].attrs and items(top)[1].attrs["aria-haspopup"] == "menu"
    r.dispatch(items(top)[0].events["click"], {})              # a group: opens beside it
    tree = cycle(r, tree)
    r.dispatch(items(menus(tree)[1])[0].events["click"], {})
    tree = cycle(r, tree)
    third = menus(tree)[2]
    assert [label(i) for i in items(third)] == ["Sydney", "Newcastle"]
    r.dispatch(items(third)[0].events["click"], {})
    tree = cycle(r, tree)
    assert a.city == "syd" and a.paths == [["au", "nsw", "syd"]] and menus(tree) == []
    assert text(every(tree, cls("shown"))) == "Sydney"


def test_show_path_chosen_marks_and_clear(tmp_path):
    _, a, r, tree = field(tmp_path, 'show_path="true" clearable="true"', CODE.replace("city = None", "city = 'bne'"))
    assert text(every(tree, cls("shown"))) == "Australia / Queensland / Brisbane"
    tree = open_field(r, tree)
    top = menus(tree)[0]
    assert "chosen" in items(top)[0].attrs["class"] and "chosen" not in items(top)[1].attrs["class"]
    r.dispatch(find(tree, cls("backdrop")).events["click"], {})
    tree = cycle(r, tree)
    assert a.blurs == ["bne"]                                   # closed without a choice
    r.dispatch(find(tree, cls("clear")).events["click"], {})
    tree = cycle(r, tree)
    assert a.city is None and a.paths == [[]] and find(tree, cls("clear")) is None


def test_load_on_demand_once(tmp_path):
    _, a, r, tree = field(tmp_path)
    tree = open_field(r, tree)
    r.dispatch(items(menus(tree)[0])[1].events["mouseenter"], {})   # Canada: not loaded yet
    tree = cycle(r, tree)
    assert a.loads == ["ca"] and find(tree, cls("busy")) is not None
    a.PLACES = a.PLACES[:1] + [{"value": "ca", "label": "Canada", "children": [{"value": "tor", "label": "Toronto"}]}] + a.PLACES[2:]
    tree = cycle(r, tree)
    assert [label(i) for i in items(menus(tree)[1])] == ["Toronto"] and find(tree, cls("busy")) is None
    r.dispatch(items(menus(tree)[0])[0].events["mouseenter"], {})
    tree = cycle(r, tree)
    r.dispatch(items(menus(tree)[0])[1].events["mouseenter"], {})
    tree = cycle(r, tree)
    assert a.loads == ["ca"]


def test_any_level_lets_a_group_be_chosen(tmp_path):
    _, a, r, tree = field(tmp_path, 'any_level="true"')
    tree = open_field(r, tree)
    r.dispatch(items(menus(tree)[0])[0].events["click"], {})       # the group itself
    tree = cycle(r, tree)
    assert a.city == "au" and a.paths == [["au"]]
    tree = open_field(r, tree)
    more = find([items(menus(tree)[0])[0]], cls("more"))
    r.dispatch(more.events["click.stop"], {})                      # its arrow opens it
    tree = cycle(r, tree)
    assert len(menus(tree)) == 2 and a.city == "au"


def test_keyboard_and_drill_rows(tmp_path):
    _, a, r, tree = field(tmp_path)
    r.dispatch(find(tree, cls("control")).events["keydown.down.prevent"], {})
    tree = cycle(r, tree)
    top = menus(tree)[0]
    assert "drill" in top.attrs["class"] and find([top], cls("back")) is None   # no way back at the top
    r.dispatch(top.events["keydown.right.prevent.stop"], {})
    tree = cycle(r, tree)
    sub = menus(tree)[1]
    back = find([sub], cls("back"))
    assert text([back]).strip() == "Australia"
    r.dispatch(back.events["click"], {})                           # (shown on narrow screens)
    tree = cycle(r, tree)
    assert len(menus(tree)) == 1
    r.dispatch(menus(tree)[0].events["keydown.esc.stop"], {})
    tree = cycle(r, tree)
    assert menus(tree) == [] and a.city is None


def test_field_props_and_option_fill(tmp_path):
    _, a, r, tree = app(tmp_path, '''<div><ui.CascadeSelect :options="PLACES" @bind="city" name="city" required="true"
        error="Pick one" placeholder="Where?">
      <Fill name="option"><b class="mine">{{ option['label'].upper() }}{{ '*' if chosen else '' }}</b></Fill>
    </ui.CascadeSelect></div>''', CODE.replace("city = None", "city = 'syd'"))
    trigger = find(tree, cls("control"))
    assert trigger.attrs["aria-invalid"] == "true" and trigger.attrs["aria-required"] == "true"
    hidden = find(tree, lambda n: n.tag == "input")
    assert (hidden.attrs["type"], hidden.attrs["name"], hidden.attrs["value"]) == ("hidden", "city", "syd")
    assert text(every(tree, cls("error"))) == "Pick one"
    tree = open_field(r, tree)
    assert [text([b]) for b in every(tree, cls("mine"))] == ["AUSTRALIA*", "CANADA", "NEW ZEALAND"]
