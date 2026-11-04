"""ButtonToggle: a joined row of buttons, one choice or several."""

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


def btns(tree):
    return every(tree, cls("btn"))


def click(r, tree, index):
    r.dispatch(btns(tree)[index].events["click"], {})
    return cycle(r, tree)


def focused(r, tree):
    r.after_render()
    found = [c for c in r.take_commands() if c["op"] == "focus"]
    assert found, "no focus request"
    node, nodes = None, tree
    for index in found[-1]["path"]:
        node = nodes[index]
        nodes = node.children
    return node


CODE = """
view: str = "week"
styles: list = ["italic"]
align = None
VIEWS = [("day", "Day"), ("week", "Week"), {"value": "month", "label": "Month", "disabled": True}, ("year", "Year")]
STYLES = [{"value": "bold", "label": "Bold", "icon": "bold", "icon_only": True},
          {"value": "italic", "label": "Italic", "icon": "italic", "icon_only": True},
          {"value": "underline", "label": "Underline", "icon": "underline"}]
"""


def test_single_choice_is_a_radio_group(tmp_path):
    _, a, r, tree = app(tmp_path, '<div><ui.ButtonToggle label="View" :options="VIEWS" @bind="view" /></div>', CODE)
    group = find(tree, cls("group"))
    assert group.attrs["role"] == "radiogroup" and group.attrs["aria-labelledby"] == find(tree, cls("label")).attrs["id"]
    bs = btns(tree)
    assert [text(every([b], cls("text"))) for b in bs] == ["Day", "Week", "Month", "Year"]
    assert [b.attrs["aria-checked"] for b in bs] == ["false", "true", "false", "false"]
    assert [b.attrs["role"] for b in bs] == ["radio"] * 4 and "aria-pressed" not in bs[0].attrs
    assert [b.attrs["tabindex"] for b in bs] == ["-1", "0", "-1", "-1"]
    assert "disabled" in bs[2].attrs and "selected" in bs[1].attrs["class"]
    tree = click(r, tree, 0)
    assert a.view == "day"
    tree = click(r, tree, 0)          # clicking the chosen one keeps it
    assert a.view == "day"


def test_check_mark_and_allow_none(tmp_path):
    _, a, r, tree = app(tmp_path, '<div><ui.ButtonToggle :options="VIEWS" allow_none="true" @bind="view" />'
                                  '<ui.ButtonToggle :options="VIEWS" check="false" :value="\'day\'" /></div>', CODE)
    first, second = every(tree, cls("group"))
    chosen = every([first], cls("btn"))[1]
    assert find([chosen], cls("icon")) is not None                  # the check mark
    assert find([every([first], cls("btn"))[0]], cls("icon")) is None
    assert find([every([second], cls("btn"))[0]], cls("icon")) is None   # check="false"
    tree = click(r, tree, 1)
    assert a.view is None and not any("selected" in b.attrs["class"] for b in btns(tree)[:4])


def test_arrows_choose_in_a_radio_group_skipping_disabled(tmp_path):
    _, a, r, tree = app(tmp_path, '<div><ui.ButtonToggle :options="VIEWS" @bind="view" /></div>', CODE)
    group = find(tree, cls("group"))
    r.dispatch(group.events["keydown.right.prevent"], {})
    tree = cycle(r, tree)
    assert a.view == "year" and text(every([focused(r, tree)], cls("text"))) == "Year"
    r.dispatch(find(tree, cls("group")).events["keydown.down.prevent"], {})   # wraps
    tree = cycle(r, tree)
    assert a.view == "day"
    r.dispatch(find(tree, cls("group")).events["keydown.end.prevent"], {})
    tree = cycle(r, tree)
    assert a.view == "year"
    r.dispatch(find(tree, cls("group")).events["keydown.up.prevent"], {})
    tree = cycle(r, tree)
    assert a.view == "week"


def test_multiple_binds_a_list_in_order_with_icon_only_buttons(tmp_path):
    _, a, r, tree = app(tmp_path, '<div><ui.ButtonToggle aria_label="Text style" multiple="true" '
                                  ':options="STYLES" @bind="styles" /></div>', CODE)
    group = find(tree, cls("group"))
    assert group.attrs["role"] == "group" and group.attrs["aria-label"] == "Text style"
    bs = btns(tree)
    assert [b.attrs["aria-pressed"] for b in bs] == ["false", "true", "false"]
    assert "role" not in bs[0].attrs and "aria-checked" not in bs[0].attrs
    assert bs[0].attrs["aria-label"] == "Bold" and bs[0].attrs["title"] == "Bold"
    assert find([bs[0]], cls("text")) is None and text(every([bs[2]], cls("text"))) == "Underline"
    assert find([bs[1]], cls("icon")) is not None       # an icon-only button keeps its icon, no check
    tree = click(r, tree, 2)
    tree = click(r, tree, 0)
    assert a.styles == ["bold", "italic", "underline"]
    tree = click(r, tree, 1)
    assert a.styles == ["bold", "underline"]


def test_multiple_arrows_move_focus_only(tmp_path):
    _, a, r, tree = app(tmp_path, '<div><ui.ButtonToggle multiple="true" :options="STYLES" @bind="styles" /></div>', CODE)
    assert [b.attrs["tabindex"] for b in btns(tree)] == ["0", "-1", "-1"]
    r.dispatch(find(tree, cls("group")).events["keydown.right.prevent"], {})
    tree = cycle(r, tree)
    assert focused(r, tree) is btns(tree)[1] and a.styles == ["italic"]
    assert [b.attrs["tabindex"] for b in btns(tree)] == ["-1", "0", "-1"]


def test_field_props_and_hidden_inputs(tmp_path):
    _, a, r, tree = app(tmp_path, '<div><ui.ButtonToggle label="Align" required="true" name="align" size="sm" '
                                  'full_width="true" orientation="vertical" error="Pick one" '
                                  'options="Left, Center, Right" @bind="align" />'
                                  '<ui.ButtonToggle multiple="true" name="s" :options="STYLES" @bind="styles" '
                                  'hint="Any" disabled="true" /></div>', CODE)
    first, second = every(tree, cls("group"))
    assert all(c in first.attrs["class"] for c in ("size-sm", "full", "vertical", "invalid"))
    assert first.attrs["aria-required"] == "true" and first.attrs["aria-invalid"] == "true"
    assert first.attrs["aria-orientation"] == "vertical"
    assert text(every(tree, cls("error"))) == "Pick one" and text(every(tree, cls("hint"))) == "Any"
    hidden = every(tree, lambda n: n.tag == "input")
    assert [(h.attrs["name"], h.attrs["value"]) for h in hidden] == [("s", "italic")]
    assert all("disabled" in b.attrs for b in every([second], cls("btn")))
    r.dispatch(every([second], cls("btn"))[0].events["click"], {})
    assert a.styles == ["italic"]
    tree = click(r, tree, 1)
    hidden = every(tree, lambda n: n.tag == "input")
    assert [(h.attrs["name"], h.attrs["value"]) for h in hidden] == [("align", "Center"), ("s", "italic")]
