"""Autocomplete: suggestions as you type, picking, custom items."""

from pyweft.vdom import Element

from test_controls import app, cycle, find, tag, text

COUNTRIES = """
picked: list = []
searched: list = []
entered: list = []
countries: list = [("in", "India"), ("id", "Indonesia"), ("nl", "Netherlands"),
                   ("nz", "New Zealand"), ("us", "United States")]
"""


def auto(tmp_path, attrs="", code=COUNTRIES, value="None", inner=""):
    return app(
        tmp_path,
        f'''<div><ui.Autocomplete label="Country" :options="countries" @bind="country" {attrs}
                 @select="picked.append(event)" @search="searched.append(event)"
                 @enter="entered.append(event)">{inner}</ui.Autocomplete></div>''',
        code + f"\ncountry = {value}\n",
    )


def options(tree):
    out = []

    def walk(nodes):
        for n in nodes:
            if isinstance(n, Element):
                if n.attrs.get("role") == "option":
                    out.append(n)
                walk(n.children)

    walk(tree)
    return out


def label(n):
    return "".join(text([n]).split())


def type_in(r, tree, value):
    r.dispatch(find(tree, tag("input")).events["input"], {"value": value})
    return cycle(r, tree)


def key(r, tree, spec):
    r.dispatch(find(tree, tag("input")).events[spec], {})
    return cycle(r, tree)


def test_typing_filters_and_highlights(tmp_path):
    _, a, r, tree = auto(tmp_path)
    field = find(tree, tag("input"))
    assert field.attrs["role"] == "combobox" and field.attrs["aria-expanded"] == "false"
    tree = type_in(r, tree, "ne")
    assert [label(o) for o in options(tree)] == ["Indonesia", "Netherlands", "NewZealand"]
    first = options(tree)[0]
    assert text([find([first], tag("mark"))]) == "ne"      # In-do-NE-sia
    assert first.attrs["aria-selected"] == "true"
    assert find(tree, tag("input")).attrs["aria-activedescendant"] == first.attrs["id"]
    assert a.searched == ["ne"] and a.country is None


def test_keyboard_picks_and_shows_the_label(tmp_path):
    _, a, r, tree = auto(tmp_path)
    tree = type_in(r, tree, "n")
    tree = key(r, tree, "keydown.down.prevent")
    tree = key(r, tree, "keydown.down.prevent")
    assert options(tree)[2].attrs["aria-selected"] == "true"
    tree = key(r, tree, "keydown.enter.prevent")
    assert a.country == "nl" and a.picked == [("nl", "Netherlands")]
    assert find(tree, tag("input")).attrs["value"] == "Netherlands"
    assert options(tree) == []
    tree = key(r, tree, "keydown.enter.prevent")  # closed: Enter is the parent's
    assert a.entered == ["nl"]


def test_escape_and_leaving_put_the_label_back(tmp_path):
    _, a, r, tree = auto(tmp_path, value='"us"')
    assert find(tree, tag("input")).attrs["value"] == "United States"
    tree = type_in(r, tree, "xyz")
    assert text([find(tree, tag("li"))]).strip() == "No matches"
    tree = key(r, tree, "keydown.esc")          # first: close
    assert options(tree) == [] and find(tree, tag("input")).attrs["value"] == "xyz"
    tree = key(r, tree, "keydown.esc")          # then: back to the chosen label
    assert find(tree, tag("input")).attrs["value"] == "United States"
    tree = type_in(r, tree, "Ind")
    r.dispatch(find(tree, tag("input")).events["blur"], {})
    tree = cycle(r, tree)
    assert find(tree, tag("input")).attrs["value"] == "United States" and a.country == "us"


def test_clicking_a_suggestion(tmp_path):
    _, a, r, tree = auto(tmp_path, attrs='match="starts"')
    tree = type_in(r, tree, "in")
    assert [label(o) for o in options(tree)] == ["India", "Indonesia"]  # starts with
    r.dispatch(options(tree)[1].events["mouseenter"], {})
    tree = cycle(r, tree)
    assert options(tree)[1].attrs["aria-selected"] == "true"
    r.dispatch(options(tree)[1].events["click"], {})
    tree = cycle(r, tree)
    assert a.country == "id"


def test_free_text(tmp_path):
    _, a, r, tree = auto(tmp_path, attrs='free="true"')
    tree = type_in(r, tree, "Atlantis")
    assert a.country == "Atlantis"
    r.dispatch(find(tree, tag("input")).events["blur"], {})
    tree = cycle(r, tree)
    assert find(tree, tag("input")).attrs["value"] == "Atlantis"  # kept, not reverted


def test_custom_items_and_empty_text(tmp_path):
    code = """
picked: list = []
searched: list = []
entered: list = []
countries: list = [
    {"value": "ada", "label": "Ada Lovelace", "email": "ada@engine.org"},
    {"value": "grace", "label": "Grace Hopper", "email": "grace@cobol.net"},
]
"""
    inner = """
      <Fill name="option"><b class="who">{{ option['label'] }}</b><small class="mail">{{ option['data']['email'] }}</small><If cond="active"><i class="here">*</i></If></Fill>
      <Fill name="empty">Nobody called "{{ query }}"</Fill>"""
    _, a, r, tree = auto(tmp_path, code=code, inner=inner)
    tree = type_in(r, tree, "a")
    first, second = options(tree)
    assert text([find([first], lambda n: n.attrs.get("class") == "mail")]) == "ada@engine.org"
    assert find([first], lambda n: n.attrs.get("class") == "here") is not None
    assert find([second], lambda n: n.attrs.get("class") == "here") is None
    tree = type_in(r, tree, "zed")
    assert text([find(tree, tag("li"))]).strip() == 'Nobody called "zed"'
    tree = type_in(r, tree, "gra")
    r.dispatch(options(tree)[0].events["click"], {})
    assert a.country == "grace" and a.picked[0]["email"] == "grace@cobol.net"


def test_server_suggestions(tmp_path):
    code = COUNTRIES.replace('countries: list = [', 'countries: list = []\nunused: list = [')
    _, a, r, tree = auto(tmp_path, attrs='match="none" :loading="busy"', code=code + "busy: bool = False\n")
    a.busy = True
    tree = type_in(r, tree, "zz")
    assert text([find(tree, tag("li"))]).strip() == "Searching…"
    a.busy, a.countries = False, [("x", "Xanadu"), ("y", "Yonder")]   # results arrive
    tree = cycle(r, tree)
    assert [label(o) for o in options(tree)] == ["Xanadu", "Yonder"]  # shown as given
    r.dispatch(options(tree)[1].events["click"], {})
    tree = cycle(r, tree)
    a.countries = []                     # the next search cleared them
    tree = cycle(r, tree)
    assert find(tree, tag("input")).attrs["value"] == "Yonder"  # the label stays


def test_with_a_form(tmp_path):
    code = COUNTRIES + "from pyweft_ui import Form, rules\nform = Form(country=rules.required('Choose a country'))\n"
    _, a, r, tree = auto(tmp_path, code=code,
                         attrs=""":error="form.error('country')" @blur="form.touch('country')" """)
    r.dispatch(find(tree, tag("input")).events["blur"], {})
    tree = cycle(r, tree)
    assert "Choose a country" in text(tree)
