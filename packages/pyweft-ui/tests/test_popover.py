"""Popover (click and hover) and Tooltip."""

from pyweft.vdom import Element

from test_controls import app, cls, cycle, find, tag, text


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


def commands(r):
    r.after_render()
    return r.take_commands()


CODE = "shown: bool = False\nlog: list = []\nlink: str = 'https://example.org/x'\n"
POP = ('<div><ui.Popover label="Share" icon="send" title="Share link" @bind="shown" '
       '@open="log.append(\'open\')" @close="log.append(\'close\')">'
       '<input class="field" :value="link" /><button class="copy">Copy</button></ui.Popover></div>')


def test_click_popover_opens_focuses_and_closes(tmp_path):
    _, a, r, tree = app(tmp_path, POP, CODE)
    trigger = find(tree, cls("trigger"))
    assert trigger.attrs["aria-haspopup"] == "dialog" and trigger.attrs["aria-expanded"] == "false"
    assert text([trigger]).strip() == "Share" and find(tree, cls("panel")) is None
    r.dispatch(trigger.events["click"], {})
    tree = cycle(r, tree)
    assert a.shown is True and a.log == ["open"]
    panel = find(tree, cls("panel"))
    assert panel.attrs["role"] == "dialog" and panel.attrs["aria-label"] == "Share link"
    assert panel.attrs["style"] == "width: 20rem" and find([panel], cls("arrow")) is not None
    assert text([find([panel], cls("title"))]) == "Share link"
    assert find(tree, cls("trigger")).attrs["aria-expanded"] == "true"
    assert find(tree, cls("trigger")).attrs["aria-controls"] == panel.attrs["id"]
    ops = [c["op"] for c in commands(r)]
    assert ops == ["keep_in_view", "focus", "focus_first"]
    r.dispatch(panel.events["keydown.esc.stop"], {})
    tree = cycle(r, tree)
    assert a.shown is False and a.log == ["open", "close"] and find(tree, cls("panel")) is None
    assert [c["op"] for c in commands(r)] == ["focus"]                # back on the button


def test_click_outside_and_opening_from_code(tmp_path):
    _, a, r, tree = app(tmp_path, POP, CODE)
    a.shown = True                                                    # opened by the app
    tree = cycle(r, tree)
    assert find(tree, cls("panel")) is not None
    assert "focus_first" in [c["op"] for c in commands(r)]
    r.dispatch(find(tree, cls("backdrop")).events["click"], {})
    tree = cycle(r, tree)
    assert a.shown is False and find(tree, cls("panel")) is None
    assert commands(r) == []                                          # a click elsewhere keeps its focus


def test_unbound_toggles_itself_and_placement(tmp_path):
    _, a, r, tree = app(tmp_path, '<div><ui.Popover label="Info" position="above" align="end" arrow="false" '
                                  'width="14rem" caret="true"><p class="body">Hi</p></ui.Popover></div>')
    root = find(tree, cls("popover"))
    assert "pos-above" in root.attrs["class"] and "align-end" in root.attrs["class"]
    trigger = find(tree, cls("trigger"))
    assert find([trigger], tag("svg")) is not None                    # the caret
    r.dispatch(trigger.events["click"], {})
    tree = cycle(r, tree)
    assert find(tree, cls("body")) is not None and find(tree, cls("arrow")) is None
    assert find(tree, cls("panel")).attrs["style"] == "width: 14rem"
    r.dispatch(find(tree, cls("trigger")).events["click"], {})       # the button again closes it
    tree = cycle(r, tree)
    assert find(tree, cls("panel")) is None


def test_trigger_fill_and_disabled(tmp_path):
    _, a, r, tree = app(tmp_path, '<div><ui.Popover label="Account" variant="link">'
                                  '<Fill name="trigger"><span class="who">@ada</span></Fill>x</ui.Popover>'
                                  '<ui.Popover label="Off" disabled="true">y</ui.Popover></div>')
    first, second = every(tree, cls("trigger"))
    assert text([find([first], cls("who"))]) == "@ada" and first.attrs["aria-label"] == "Account"
    assert "btn-link" in first.attrs["class"] and "disabled" in second.attrs
    r.dispatch(second.events["click"], {})
    tree = cycle(r, tree)
    assert len(every(tree, cls("panel"))) == 0


def test_hover_card_is_always_there_for_css(tmp_path):
    _, a, r, tree = app(tmp_path, '<div><ui.Popover open_on="hover" label="Ada" variant="link" @bind="shown">'
                                  '<b class="card">Ada Lovelace</b></ui.Popover></div>', CODE)
    root = find(tree, cls("popover"))
    trigger = find(tree, cls("trigger"))
    panel = find(tree, cls("panel"))
    assert "hover" in root.attrs["class"] and panel is not None and "role" not in panel.attrs
    assert "aria-haspopup" not in trigger.attrs and "aria-expanded" not in trigger.attrs
    assert trigger.attrs["aria-controls"] == panel.attrs["id"]
    r.dispatch(trigger.events["click"], {})
    tree = cycle(r, tree)
    assert a.shown is False and find(tree, cls("backdrop")) is None    # clicks don't toggle it
    r.dispatch(find(tree, cls("popover")).events["keydown.esc"], {})
    tree = cycle(r, tree)
    assert "dismissed" in find(tree, cls("popover")).attrs["class"]
    r.dispatch(find(tree, cls("popover")).events["mouseleave"], {})
    tree = cycle(r, tree)
    assert "dismissed" not in find(tree, cls("popover")).attrs["class"]


# ------------------------------------------------------------------ Tooltip

def test_tooltip_wraps_and_names_itself(tmp_path):
    _, a, r, tree = app(tmp_path, '<div><ui.Tooltip text="Delete forever" tip_id="del-tip" position="below">'
                                  '<button class="del" aria-describedby="del-tip">x</button></ui.Tooltip>'
                                  '<ui.Tooltip text="Plain"><span class="s">y</span></ui.Tooltip>'
                                  '<ui.Tooltip text="Off" disabled="true"><i>z</i></ui.Tooltip></div>')
    hosts = every(tree, cls("tip-host"))
    first, plain, off = hosts
    tip = find([first], cls("tip"))
    assert tip.attrs["role"] == "tooltip" and tip.attrs["id"] == "del-tip" and text([tip]) == "Delete forever"
    assert find([first], cls("del")).attrs["aria-describedby"] == tip.attrs["id"]
    assert "pos-below" in first.attrs["class"] and "pos-above" in plain.attrs["class"]
    assert find([plain], cls("tip")).attrs["id"].startswith("ui-tooltip-")
    assert find([off], cls("tip")) is None and find([off], tag("i")) is not None


def test_tooltip_esc_hides_until_leaving(tmp_path):
    _, a, r, tree = app(tmp_path, '<div><ui.Tooltip text="Hi"><button>b</button></ui.Tooltip></div>')
    r.dispatch(find(tree, cls("tip-host")).events["keydown.esc"], {})
    tree = cycle(r, tree)
    assert "dismissed" in find(tree, cls("tip-host")).attrs["class"]
    r.dispatch(find(tree, cls("tip-host")).events["focusout"], {})
    tree = cycle(r, tree)
    assert "dismissed" not in find(tree, cls("tip-host")).attrs["class"]
