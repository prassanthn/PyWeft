"""Chips (choose from a row) and ChipInput (type to add)."""

from pyweft.vdom import Element

from test_controls import app, cycle, find, tag, text


def all_nodes(tree, test):
    out = []

    def walk(nodes):
        for n in nodes:
            if isinstance(n, Element):
                if test(n):
                    out.append(n)
                walk(n.children)

    walk(tree)
    return out


def has_class(name):
    return lambda n: name in n.attrs.get("class", "").split()


def label(n):
    return " ".join(text([n]).split())


def focused_attrs(r, tree):
    r.after_render()
    commands = [c for c in r.take_commands() if c["op"] == "focus"]
    assert commands, "no focus request"
    node, nodes = None, tree
    for index in commands[-1]["path"]:
        node = nodes[index]
        nodes = node.children
    return node.attrs


# ------------------------------------------------------------------ Chips

LANGS = "langs: list = []\nlang = None\nremoved: list = []\nopts: list = ['Python', 'Rust', {'value': 'go', 'label': 'Go', 'icon': 'star'}, {'value': 'cob', 'label': 'COBOL', 'disabled': True}]\n"


def chips(tmp_path, attrs, code=LANGS):
    return app(tmp_path, f'<div><ui.Chips label="Languages" :options="opts" {attrs} @remove="removed.append(event)" /></div>', code)


def mains(tree):
    return all_nodes(tree, has_class("main"))


def test_single_choice(tmp_path):
    _, a, r, tree = chips(tmp_path, '@bind="lang"')
    assert [label(m) for m in mains(tree)] == ["Python", "Rust", "Go", "COBOL"]
    assert all(m.attrs["aria-pressed"] == "false" for m in mains(tree))
    assert "disabled" in mains(tree)[3].attrs
    r.dispatch(mains(tree)[1].events["click"], {})
    tree = cycle(r, tree)
    assert a.lang == "Rust" and mains(tree)[1].attrs["aria-pressed"] == "true"
    assert "on" in all_nodes(tree, has_class("chip"))[1].attrs["class"]
    r.dispatch(mains(tree)[2].events["click"], {})
    assert a.lang == "go"                    # a dict's value
    tree = cycle(r, tree)
    r.dispatch(mains(tree)[2].events["click"], {})
    assert a.lang is None                    # clicked again: un-chosen


def test_required_keeps_one(tmp_path):
    _, a, r, tree = chips(tmp_path, '@bind="lang" required="true"', LANGS.replace("lang = None", "lang = 'Rust'"))
    r.dispatch(mains(tree)[1].events["click"], {})
    assert a.lang == "Rust"


def test_multiple_choice_keeps_option_order(tmp_path):
    _, a, r, tree = chips(tmp_path, '@bind="langs" multiple="true"')
    for i in (2, 0):
        r.dispatch(mains(tree)[i].events["click"], {})
        tree = cycle(r, tree)
    assert a.langs == ["Python", "go"]
    r.dispatch(mains(tree)[0].events["click"], {})
    assert a.langs == ["go"]


def test_removable_and_the_keyboard(tmp_path):
    _, a, r, tree = chips(tmp_path, '@bind="langs" multiple="true" removable="true" selectable="false"')
    assert "aria-pressed" not in mains(tree)[0].attrs
    assert [m.attrs["tabindex"] for m in mains(tree)] == ["0", "-1", "-1", "-1"]  # one Tab stop
    xs = all_nodes(tree, has_class("x"))
    assert xs[1].attrs["aria-label"] == "Remove Rust"
    r.dispatch(xs[1].events["click"], {})
    assert a.removed == ["Rust"]
    group = find(tree, lambda n: n.attrs.get("role") == "group")
    r.dispatch(group.events["keydown.right.prevent"], {})
    tree = cycle(r, tree)
    assert focused_attrs(r, tree)["tabindex"] == "0"
    r.dispatch(group.events["keydown.end.prevent"], {})
    tree = cycle(r, tree)
    r.dispatch(group.events["keydown.delete.prevent"], {})   # the focused one: COBOL,
    assert a.removed == ["Rust"]                              # disabled, so it stays
    r.dispatch(group.events["keydown.home.prevent"], {})
    tree = cycle(r, tree)
    r.dispatch(group.events["keydown.delete.prevent"], {})
    assert a.removed[-1] == "Python"


def test_custom_chip_text(tmp_path):
    code = LANGS
    _, a, r, tree = app(
        tmp_path,
        '<div><ui.Chips :options="opts" @bind="lang"><Fill name="option"><b class="mine">{{ option["label"].upper() }}</b><If cond="selected">!</If></Fill></ui.Chips></div>',
        code,
    )
    assert [label(n) for n in all_nodes(tree, has_class("mine"))][:2] == ["PYTHON", "RUST"]
    r.dispatch(mains(tree)[0].events["click"], {})
    tree = cycle(r, tree)
    assert label(mains(tree)[0]).endswith("!")


# ------------------------------------------------------------------ ChipInput

TAGS = "tags: list = []\nadded: list = []\ngone: list = []\nleft: list = []\n"


def chip_input(tmp_path, attrs="", code=TAGS):
    return app(
        tmp_path,
        f'''<div><ui.ChipInput label="Tags" @bind="tags" {attrs} @add="added.append(event)"
                 @remove="gone.append(event)" @blur="left.append(event)" /></div>''',
        code,
    )


def typing(r, tree, value):
    r.dispatch(find(tree, tag("input")).events["input"], {"value": value})
    return cycle(r, tree)


def press(r, tree, spec):
    r.dispatch(find(tree, tag("input")).events[spec], {})
    return cycle(r, tree)


def chip_labels(tree):
    return [label(n) for n in all_nodes(tree, has_class("text"))]


def test_enter_and_comma_add_backspace_removes(tmp_path):
    _, a, r, tree = chip_input(tmp_path)
    tree = typing(r, tree, "python")
    tree = press(r, tree, "keydown.enter.prevent")
    assert a.tags == ["python"] and find(tree, tag("input")).attrs.get("value", "") == ""
    tree = typing(r, tree, "rust, go, Python, ")   # pasted: three, one a duplicate
    assert a.tags == ["python", "rust", "go"] and a.added == ["python", "rust", "go"]
    assert chip_labels(tree) == ["python", "rust", "go"]
    tree = press(r, tree, "keydown.backspace")     # empty box: the last chip goes
    assert a.tags == ["python", "rust"] and a.gone == ["go"]
    tree = typing(r, tree, "x")
    tree = press(r, tree, "keydown.backspace")     # text in the box: nothing removed
    assert a.tags == ["python", "rust"]
    remove = all_nodes(tree, has_class("x"))[0]
    assert remove.attrs["aria-label"] == "Remove python"
    r.dispatch(remove.events["click"], {})
    assert a.tags == ["rust"]


def test_blur_adds_and_max_limits(tmp_path):
    _, a, r, tree = chip_input(tmp_path, 'max="2"')
    tree = typing(r, tree, "one, two, three")
    assert a.tags == ["one", "two"]                # max: the third doesn't fit
    assert "disabled" in find(tree, tag("input")).attrs
    _, b, r2, tree2 = chip_input(tmp_path / "b" if (tmp_path / "b").mkdir() is None else tmp_path)
    tree2 = typing(r2, tree2, "draft")
    r2.dispatch(find(tree2, tag("input")).events["blur"], {})
    assert b.tags == ["draft"] and b.left == [["draft"]]


def test_suggestions_values_and_custom_layout(tmp_path):
    code = TAGS + """people: list = [
    {"value": "ada", "label": "Ada Lovelace", "email": "ada@engine.org"},
    {"value": "alan", "label": "Alan Turing", "email": "alan@bletchley.uk"},
    {"value": "grace", "label": "Grace Hopper", "email": "grace@cobol.net"},
]
"""
    _, a, r, tree = app(
        tmp_path,
        '''<div><ui.ChipInput label="Invite" :options="people" free="false" @bind="tags">
             <Fill name="chip"><b class="who">{{ chip['data']['email'] }}</b></Fill>
             <Fill name="option"><i class="sug">{{ option['label'] }}</i></Fill>
           </ui.ChipInput></div>''',
        code,
    )
    tree = typing(r, tree, "a")
    assert [label(n) for n in all_nodes(tree, has_class("sug"))] == ["Ada Lovelace", "Alan Turing", "Grace Hopper"]
    tree = press(r, tree, "keydown.down.prevent")
    tree = press(r, tree, "keydown.enter.prevent")
    assert a.tags == ["alan"]
    assert [label(n) for n in all_nodes(tree, has_class("who"))] == ["alan@bletchley.uk"]
    tree = typing(r, tree, "a")                    # chosen ones aren't suggested again
    assert [label(n) for n in all_nodes(tree, has_class("sug"))] == ["Ada Lovelace", "Grace Hopper"]
    tree = typing(r, tree, "nobody")
    tree = press(r, tree, "keydown.enter.prevent")  # free="false": not an option, not added
    assert a.tags == ["alan"]
    tree = typing(r, tree, "grace hopper")
    tree = press(r, tree, "keydown.enter.prevent")  # typed in full: the option's value
    assert a.tags == ["alan", "grace"]


def test_with_a_form(tmp_path):
    code = TAGS + "from pyweft_ui import Form, rules\nform = Form(tags=rules.required('Add at least one tag'))\n"
    _, a, r, tree = chip_input(tmp_path, attrs=""":error="form.error('tags')" """, code=code)
    a.form.check(focus=False)
    tree = cycle(r, tree)
    assert "Add at least one tag" in text(tree)
    tree = typing(r, tree, "one,")
    assert "Add at least one tag" not in text(cycle(r, tree))
