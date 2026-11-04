"""Stepper: steps one at a time, Back/Next, validation, linear mode."""

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


def heads(tree):
    return every(tree, lambda n: n.attrs.get("role") == "tab")


def panel_text(tree):
    return " ".join(text(every(tree, cls("body-text"))).split())


def buttons(tree):
    """The Back/Next row's buttons, by their text."""
    row = find(tree, cls("actions"))
    return {text([b]).strip(): b for b in every([row], lambda n: n.tag == "button")}


def press(r, tree, name):
    r.dispatch(buttons(tree)[name].events["click"], {"type": "click"})
    return cycle(r, tree)


def focus_target(r, tree):
    r.after_render()
    found = [c for c in r.take_commands() if c["op"] == "focus"]
    assert found, "no focus request"
    node, nodes = None, tree
    for index in found[-1]["path"]:
        node = nodes[index]
        nodes = node.children
    return node


CODE = """
step = None
email: str = ""
finished: list = []
log: list = []
STEPS = [("account", "Account"), {"value": "extras", "label": "Extras", "optional": True},
         {"value": "address", "label": "Address", "description": "Where to send it"}, ("review", "Review")]

def check(self, which):
    self.log.append(which)
    return which != "account" or "@" in self.email
"""


def stepper(tmp_path, attrs='@bind="step"', code=CODE):
    return app(tmp_path, f'''<div><ui.Stepper label="Sign up" :steps="STEPS" {attrs}
        @next="check(event)" @finish="finished.append(event)">
      <p class="body-text">Body {{{{ step }}}} {{{{ index }}}}</p>
    </ui.Stepper></div>''', code)


def test_headers_and_first_step(tmp_path):
    _, a, r, tree = stepper(tmp_path)
    hs = heads(tree)
    assert [text(every([h], cls("label"))) for h in hs] == ["Account", "Extras", "Address", "Review"]
    assert hs[0].attrs["aria-selected"] == "true" and hs[0].attrs["tabindex"] == "0"
    assert hs[1].attrs["aria-label"] == "Step 2 of 4: Extras, optional"
    assert text(every([hs[1]], cls("desc"))) == "Optional"
    assert text(every([hs[2]], cls("desc"))) == "Where to send it"
    assert panel_text(tree) == "Body account 0"
    assert list(buttons(tree)) == ["Next"]          # no Back on the first step
    (tablist,) = every(tree, lambda n: n.attrs.get("role") == "tablist")
    assert tablist.attrs["aria-label"] == "Sign up"
    panel = every(tree, lambda n: n.attrs.get("role") == "tabpanel")[0]
    assert panel.attrs["aria-labelledby"] == hs[0].attrs["id"] and hs[0].attrs["aria-controls"] == panel.attrs["id"]


def test_next_validates_then_moves_and_marks_done(tmp_path):
    _, a, r, tree = stepper(tmp_path)
    tree = press(r, tree, "Next")
    assert a.log == ["account"] and a.step is None and panel_text(tree) == "Body account 0"
    a.email = "ada@engine.org"
    tree = cycle(r, tree)
    tree = press(r, tree, "Next")
    assert a.step == "extras" and panel_text(tree) == "Body extras 1"
    assert "done" in heads(tree)[0].attrs["class"]
    assert text(every([heads(tree)[0]], cls("dot"))).strip() == ""   # a check mark, not "1"
    assert heads(tree)[0].attrs["aria-label"] == "Step 1 of 4: Account, completed"
    assert focus_target(r, tree).attrs["role"] == "tabpanel"   # focus moves to the new step
    assert list(buttons(tree)) == ["Back", "Next"]
    tree = press(r, tree, "Back")
    assert a.step == "account"
    assert "forward" not in find(tree, cls("panel")).attrs["class"]


def test_finish_on_the_last_step(tmp_path):
    _, a, r, tree = stepper(tmp_path, '@bind="step"', CODE.replace("step = None", "step = 'review'"))
    assert list(buttons(tree)) == ["Back", "Finish"]
    tree = press(r, tree, "Finish")
    assert a.finished == ["review"] and a.log == ["review"] and a.step == "review"


def test_linear_blocks_steps_ahead_but_not_past_optional_ones(tmp_path):
    _, a, r, tree = stepper(tmp_path, 'linear="true" @bind="step"')
    assert ["disabled" in h.attrs for h in heads(tree)] == [False, True, True, True]
    a.email = "a@b"
    tree = cycle(r, tree)
    tree = press(r, tree, "Next")
    # Account done; Extras is optional, so Address opens too; Review waits.
    assert ["disabled" in h.attrs for h in heads(tree)] == [False, False, False, True]
    r.dispatch(heads(tree)[2].events["click"], {})
    tree = cycle(r, tree)
    assert a.step == "address"


def test_free_order_by_header_and_unbound(tmp_path):
    _, a, r, tree = stepper(tmp_path, "")
    assert not any("disabled" in h.attrs for h in heads(tree))
    r.dispatch(heads(tree)[3].events["click"], {})
    tree = cycle(r, tree)
    assert panel_text(tree) == "Body review 3" and a.step is None
    assert "back" not in find(tree, cls("panel")).attrs["class"]


def test_step_dicts_set_error_done_and_disabled(tmp_path):
    code = CODE + """
at = "b"
STEPS2 = [{"value": "a", "label": "A", "done": True}, {"value": "b", "label": "B", "error": "Card declined"},
          {"value": "c", "label": "C", "disabled": True}, ("d", "D")]
"""
    _, a, r, tree = app(tmp_path, '<div><ui.Stepper :steps="STEPS2" @bind="at"><p>x</p></ui.Stepper></div>', code)
    hs = heads(tree)
    assert "done" in hs[0].attrs["class"] and "error" in hs[1].attrs["class"]
    assert text(every([hs[1]], cls("err"))) == "Card declined"
    assert hs[1].attrs["aria-label"] == "Step 2 of 4: B, error: Card declined"
    assert "disabled" in hs[2].attrs
    r.dispatch(buttons(tree)["Next"].events["click"], {})
    tree = cycle(r, tree)
    assert heads(tree)[3].attrs["aria-selected"] == "true"     # skips the disabled step


def test_arrow_keys_roam_the_headers(tmp_path):
    _, a, r, tree = stepper(tmp_path, 'linear="true" @bind="step"')
    a.email = "a@b"
    tree = press(r, cycle(r, tree), "Next")
    r.after_render(); r.take_commands()
    hs = heads(tree)
    r.dispatch(hs[1].events["keydown.right.prevent"], {})
    tree = cycle(r, tree)
    assert focus_target(r, tree) is heads(tree)[2] and heads(tree)[2].attrs["tabindex"] == "0"
    r.dispatch(heads(tree)[2].events["keydown.right.prevent"], {})   # Review isn't reachable: wraps
    tree = cycle(r, tree)
    assert focus_target(r, tree) is heads(tree)[0]
    r.dispatch(heads(tree)[0].events["keydown.end.prevent"], {})
    tree = cycle(r, tree)
    assert focus_target(r, tree) is heads(tree)[2]
    assert a.step == "extras"                                         # moving focus doesn't open


def test_vertical_shows_content_under_its_header(tmp_path):
    _, a, r, tree = stepper(tmp_path, 'orientation="vertical" @bind="step"')
    items = every(tree, cls("v-item"))
    assert len(items) == 4 and find([items[0]], cls("body-text")) is not None
    assert all(find([i], cls("body-text")) is None for i in items[1:])
    assert "keydown.down.prevent" in heads(tree)[0].events
    a.email = "a@b"
    tree = press(r, cycle(r, tree), "Next")
    items = every(tree, cls("v-item"))
    assert find([items[1]], cls("body-text")) is not None and find([items[0]], cls("body-text")) is None


def test_labels_bottom_and_custom_actions(tmp_path):
    _, a, r, tree = app(tmp_path, '''<div><ui.Stepper :steps="STEPS" label_position="bottom" @bind="step">
      <p class="body-text">{{ step }}</p>
      <Fill name="actions">
        <button class="mine-back" @click="go_back()">Previous</button>
        <button class="mine-next" @click="go_next()">{{ 'Done' if last else 'Continue' }} {{ index }}</button>
      </Fill>
    </ui.Stepper></div>''', CODE)
    assert "labels-bottom" in find(tree, cls("stepper")).attrs["class"] and find(tree, cls("line")) is None
    assert text([find(tree, cls("mine-next"))]) == "Continue 0"
    r.dispatch(find(tree, cls("mine-next")).events["click"], {})
    tree = cycle(r, tree)
    assert a.step == "extras" and text([find(tree, cls("mine-next"))]) == "Continue 1"
    r.dispatch(find(tree, cls("mine-back")).events["click"], {})
    tree = cycle(r, tree)
    assert a.step == "account"
