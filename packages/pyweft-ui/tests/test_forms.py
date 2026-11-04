"""Form and rules: checking a component's fields and showing what to fix."""

import pytest

from pyweft.component import declared_props
from pyweft_ui import Form, rules
from pyweft_ui.forms import BoundForm

from test_controls import app, cls, cycle, find, tag, text

# ------------------------------------------------------------------ rules


def test_required_and_accepted():
    req = rules.required("Fill it in")
    assert [req(v) for v in (None, "", "  ", [], {}, "x", 0, False)] == [
        "Fill it in", "Fill it in", "Fill it in", "Fill it in", "Fill it in", None, None, None
    ]
    acc = rules.accepted()
    assert acc(True) is None and acc(False) and acc(None)


@pytest.mark.parametrize("value, ok", [
    ("ada@example.com", True), (" ada@example.com ", True), ("ada@example", False),
    ("ada example.com", False), ("@example.com", False), ("", True),
])
def test_email(value, ok):
    assert (rules.email()(value) is None) is ok


def test_lengths_values_patterns_and_choices():
    assert rules.min_length(3)("ab") == "Use at least 3 characters"
    assert rules.min_length(2)(["a"]) == "Choose at least 2"
    assert rules.min_length(3)("abc") is None and rules.min_length(3)("") is None
    assert rules.max_length(2, "Too long")("abc") == "Too long"
    assert rules.min_value(1)(0) == "Must be at least 1" and rules.min_value(1)(None) is None
    assert rules.max_value(10)(11) == "Must be at most 10" and rules.max_value(10)(10) is None
    assert rules.pattern(r"[A-Z]{2}\d{2}")("AB12") is None
    assert rules.pattern(r"[A-Z]{2}\d{2}", "Like AB12")("AB123") == "Like AB12"
    assert rules.one_of(["S", "M"])("L") == "Choose one of: S, M"
    assert rules.url()("https://example.com/x") is None and rules.url()("example.com")
    assert rules.check(lambda v: v != "admin", "Taken")("admin") == "Taken"
    assert rules.check(lambda v: v != "admin", "Taken")("ada") is None


# ------------------------------------------------------------------ Form, alone


class Signup:
    """A stand-in component: Form only needs attributes and focus()."""

    form = Form(
        email=[rules.required(), rules.email()],
        password=[rules.required(), rules.min_length(8)],
        confirm=rules.same_as("password", "Type the same password"),
        agreed=rules.accepted(),
    )

    def __init__(self):
        self.email, self.password, self.confirm, self.agreed = "", "", "", False
        self.focused = []

    def focus(self, ref):
        self.focused.append(ref)


def test_nothing_shows_until_touched_or_checked():
    s = Signup()
    assert s.form.errors == {} and s.form.error("email") == ""
    assert not s.form.valid and s.form.problem("email") == "This is required"
    s.form.touch("email")
    assert s.form.errors == {"email": "This is required"}
    s.email = "ada@"
    assert s.form.error("email").startswith("Enter an email address")
    s.email = "ada@example.com"
    assert s.form.error("email") == ""  # fixed: the message goes as you type


def test_check_shows_everything_and_focuses_the_first():
    s = Signup()
    s.email = "ada@example.com"
    assert s.form.check() is False
    assert s.focused == ["password"]
    assert list(s.form.errors) == ["password", "agreed"]
    s.password, s.agreed = "long enough", True
    assert s.form.errors == {"confirm": "Type the same password"}
    s.confirm = "long enough"
    assert s.form.valid and s.form.check() is True and s.form.errors == {}
    assert s.focused == ["password"]  # valid: nothing to focus
    s.form.reset()
    s.password = ""
    assert s.form.errors == {} and not s.form.valid


def test_state_is_per_component_and_rules_take_the_form():
    first, second = Signup(), Signup()
    first.form.check(focus=False)
    assert first.form.errors and second.form.errors == {} and first.focused == []

    class Custom:
        form = Form(name=[lambda v: "Too short" if len(v) < 2 else None,
                          lambda v, f: "Same as nick" if v == f.value("nick") else None],
                    nick=rules.required())

        def __init__(self):
            self.name, self.nick = "x", "ab"

    c = Custom()
    assert c.form.problem("name") == "Too short"
    c.name = "ab"
    assert c.form.problem("name") == "Same as nick"


def test_mistakes_are_reported():
    with pytest.raises(TypeError):
        Form()
    with pytest.raises(TypeError):
        Form(email="required")
    with pytest.raises(KeyError, match="no field 'nope'"):
        Signup().form.touch("nope")
    with pytest.raises(AttributeError):
        Signup().form = None  # a computed value, like @property


# ------------------------------------------------------------------ in a page

PAGE = """
<form novalidate="" @submit.prevent="submit">
  <ui.TextField ref="email" label="Email" @bind="email"
                :error="form.error('email')" @blur="form.touch('email')" />
  <ui.Select ref="size" label="Size" placeholder="Pick" options="S, M" @bind="size"
             :error="form.error('size')" />
  <ui.Checkbox @bind="agreed" :error="form.error('agreed')">I agree</ui.Checkbox>
  <ui.RadioGroup label="Plan" options="Free, Pro" @bind="plan" :error="form.error('plan')" />
  <ui.Switch label="Opt in" @bind="opt" :error="form.error('opt')" />
  <ui.Button type="submit" :disabled="not form.valid">Go</ui.Button>
</form>
"""

CODE = """
from pyweft_ui import Form, rules
email: str = ""
size = None
agreed: bool = False
plan = None
opt: bool = False
sent: int = 0
form = Form(
    email=[rules.required(), rules.email()],
    size=rules.required("Pick a size"),
    agreed=rules.accepted("Agree first"),
    plan=rules.required("Pick a plan"),
    opt=rules.accepted("Opt in"),
)

def submit(self):
    if self.form.check():
        self.sent += 1
"""


def errors_in(tree):
    found = []

    def walk(nodes):
        for node in nodes:
            if getattr(node, "tag", None):
                if "error" in node.attrs.get("class", "").split():
                    found.append(text([node]))
                walk(node.children)

    walk(tree)
    return found


def test_a_form_in_a_page(tmp_path):
    App, a, r, tree = app(tmp_path, PAGE, CODE)
    assert "form" not in declared_props(App)  # never a prop
    assert errors_in(tree) == []
    assert "disabled" in find(tree, tag("button")).attrs

    # Leaving the email field shows its message; typing fixes it.
    email = find(tree, tag("input"))
    r.dispatch(email.events["blur"], {})
    tree = cycle(r, tree)
    assert errors_in(tree) == ["This is required"]
    assert find(tree, tag("input")).attrs["aria-invalid"] == "true"
    r.dispatch(email.events["input"], {"value": "ada@example.com"})
    tree = cycle(r, tree)
    assert errors_in(tree) == []

    # Submitting shows the rest, on every kind of field, and focuses the first.
    form = find(tree, tag("form"))
    r.dispatch(form.events["submit.prevent"], {})
    tree = cycle(r, tree)
    assert errors_in(tree) == ["Pick a size", "Agree first", "Pick a plan", "Opt in"]
    r.after_render()
    assert [c["op"] for c in r.take_commands()] == ["focus"]
    assert a.sent == 0

    a.size, a.agreed, a.plan, a.opt = "M", True, "Pro", True
    tree = cycle(r, tree)
    assert errors_in(tree) == [] and "disabled" not in find(tree, tag("button")).attrs
    r.dispatch(find(tree, tag("form")).events["submit.prevent"], {})
    assert a.sent == 1
    assert isinstance(a.form, BoundForm)


def test_fields_emit_blur(tmp_path):
    _, a, r, tree = app(
        tmp_path,
        """<div>
          <ui.TextArea @bind="t" @blur="left.append('area')" />
          <ui.NumberField @bind="n" @blur="left.append('number')" />
          <ui.Select options="A, B" @bind="s" @blur="left.append('select')" />
        </div>""",
        "t: str = ''\nn = None\ns = None\nleft: list = []",
    )
    for name in ("textarea", "input", "select"):
        r.dispatch(find(tree, tag(name)).events["blur"], {})
    assert a.left == ["area", "number", "select"]
    assert find(tree, cls("error")) is None
