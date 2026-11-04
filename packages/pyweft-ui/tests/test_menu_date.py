"""Menu and DatePicker: opening, the keyboard, choosing, and limits."""

import datetime

from test_controls import app, cls, cycle, find, tag, text

D = datetime.date


def attr(name, value=None):
    return lambda n: name in n.attrs and (value is None or n.attrs[name] == value)


def focused(r, tree):
    """The element the latest focus request points at (the requests are
    carried out after the render, as a host would)."""
    r.after_render()
    commands = [c for c in r.take_commands() if c["op"] == "focus"]
    assert commands, "no focus request"
    node, nodes = None, tree
    for index in commands[-1]["path"]:
        node = nodes[index]
        nodes = node.children
    return node


def drain(r):
    r.after_render()
    r.take_commands()


def label_of(node):
    return text([node]).strip()


# ------------------------------------------------------------------ Menu

MENU = """<div><ui.Menu label="Actions" :items="items" @select="chosen.append(event)" /></div>"""
ITEMS = """
items: list = [
    "Edit",
    ("dup", "Duplicate"),
    {"value": "arch", "label": "Archive", "disabled": True},
    "-",
    {"value": "del", "label": "Delete", "icon": "trash", "danger": True},
]
chosen: list = []
"""


def test_menu_opens_moves_and_chooses(tmp_path):
    _, a, r, tree = app(tmp_path, MENU, ITEMS)
    trigger = find(tree, tag("button"))
    assert trigger.attrs["aria-expanded"] == "false" and trigger.attrs["aria-haspopup"] == "menu"
    assert find(tree, attr("role", "menu")) is None

    r.dispatch(trigger.events["click"], {})
    tree = cycle(r, tree)
    menu = find(tree, attr("role", "menu"))
    items = [n for n in menu.children if n.tag == "button"]
    assert [text([n]).strip() for n in items] == ["Edit", "Duplicate", "Archive", "Delete"]
    assert "disabled" in items[2].attrs and "danger" in items[3].attrs["class"]
    assert find(tree, attr("role", "separator")) is not None
    assert label_of(focused(r, tree)) == "Edit"  # the first item

    # Down skips the disabled item; it wraps at the end.
    for expected in ("Duplicate", "Delete", "Edit"):
        r.dispatch(menu.events["keydown.down.prevent"], {"key": "ArrowDown"})
        tree = cycle(r, tree)
        assert label_of(focused(r, tree)) == expected
    r.dispatch(menu.events["keydown.end.prevent"], {"key": "End"})
    tree = cycle(r, tree)
    assert label_of(focused(r, tree)) == "Delete"
    r.dispatch(menu.events["keydown.up.prevent"], {"key": "ArrowUp"})
    tree = cycle(r, tree)
    assert label_of(focused(r, tree)) == "Duplicate"  # up skips Archive too

    items = [n for n in find(tree, attr("role", "menu")).children if n.tag == "button"]
    r.dispatch(items[1].events["click"], {})
    tree = cycle(r, tree)
    assert a.chosen == ["dup"] and find(tree, attr("role", "menu")) is None
    assert focused(r, tree).attrs["aria-haspopup"] == "menu"  # back on the button


def test_menu_keyboard_open_and_close(tmp_path):
    _, a, r, tree = app(tmp_path, MENU, ITEMS)
    trigger = find(tree, tag("button"))
    r.dispatch(trigger.events["keydown.up.prevent"], {"key": "ArrowUp"})  # opens on the last
    tree = cycle(r, tree)
    assert label_of(focused(r, tree)) == "Delete"

    menu = find(tree, attr("role", "menu"))
    r.dispatch(menu.events["keydown.esc.stop"], {"key": "Escape"})
    tree = cycle(r, tree)
    assert find(tree, attr("role", "menu")) is None
    assert focused(r, tree).attrs["aria-haspopup"] == "menu"

    r.dispatch(trigger.events["keydown.down.prevent"], {"key": "ArrowDown"})
    tree = cycle(r, tree)
    menu = find(tree, attr("role", "menu"))
    r.dispatch(menu.events["keydown.tab"], {"key": "Tab"})  # Tab moves on: no refocus
    tree = cycle(r, tree)
    r.after_render()
    assert find(tree, attr("role", "menu")) is None and r.take_commands() == []
    assert a.chosen == []


def test_menu_click_outside_and_icon_only(tmp_path):
    _, a, r, tree = app(
        tmp_path,
        '<div><ui.Menu label="More actions" icon="more" icon_only="true" align="end" :items="items" @select="chosen.append(event)" /></div>',
        ITEMS,
    )
    trigger = find(tree, tag("button"))
    assert trigger.attrs["aria-label"] == "More actions" and "icon-only" in trigger.attrs["class"]
    assert "align-end" in find(tree, cls("menu")).attrs["class"]
    r.dispatch(trigger.events["click"], {})
    tree = cycle(r, tree)
    r.dispatch(find(tree, cls("backdrop")).events["click"], {})
    tree = cycle(r, tree)
    assert find(tree, attr("role", "menu")) is None


# ------------------------------------------------------------------ DatePicker

PICKER = """<div><ui.DatePicker label="Check-in" @bind="day" :min="low" :max="high"
                  @blur="left.append(event)" /></div>"""


def picker(tmp_path, day="None", low="None", high="None", extra=""):
    return app(
        tmp_path,
        PICKER.replace("/>", f"{extra} />") if extra else PICKER,
        f"import datetime\nday = {day}\nlow = {low}\nhigh = {high}\nleft: list = []",
    )


def day_buttons(tree):
    grid = find(tree, attr("role", "grid"))
    return [] if grid is None else [n for n in walk(grid) if n.tag == "button"]


def walk(node):
    for child in node.children:
        if getattr(child, "tag", None):
            yield child
            yield from walk(child)


def test_date_picker_shows_the_value_or_a_placeholder(tmp_path):
    _, a, r, tree = picker(tmp_path)
    assert text([find(tree, cls("text"))]) == "Choose a date"
    a.day = D(2026, 11, 3)
    tree = cycle(r, tree)
    assert text([find(tree, cls("text"))]) == "3 Nov 2026"
    a.day = "2026-12-25"  # text works too
    tree = cycle(r, tree)
    assert text([find(tree, cls("text"))]) == "25 Dec 2026"


def test_date_picker_opens_on_the_chosen_day_and_picks(tmp_path):
    _, a, r, tree = picker(tmp_path, day="datetime.date(2026, 11, 3)")
    r.dispatch(find(tree, cls("control")).events["click"], {})
    tree = cycle(r, tree)
    assert text([find(tree, cls("month"))]) == "November 2026"
    days = day_buttons(tree)
    assert len(days) == 42  # six weeks, Monday first
    assert [text([th]) for th in walk(find(tree, tag("thead"))) if th.tag == "th"][:2] == ["Mo", "Tu"]
    target = focused(r, tree).attrs
    assert target["aria-label"] == "Tuesday 3 November 2026" and target["tabindex"] == "0"
    assert target["aria-pressed"] == "true"

    grid = find(tree, attr("role", "grid"))
    r.dispatch(grid.events["keydown.down.prevent"], {"key": "ArrowDown"})  # a week on
    tree = cycle(r, tree)
    assert focused(r, tree).attrs["aria-label"] == "Tuesday 10 November 2026"
    r.dispatch(grid.events["keydown.page-down.prevent"], {"key": "PageDown"})
    tree = cycle(r, tree)
    assert text([find(tree, cls("month"))]) == "December 2026"
    assert focused(r, tree).attrs["aria-label"] == "Thursday 10 December 2026"
    r.dispatch(grid.events["keydown.home.prevent"], {"key": "Home"})
    tree = cycle(r, tree)
    assert focused(r, tree).attrs["aria-label"] == "Monday 7 December 2026"

    pick = next(b for b in day_buttons(tree) if b.attrs["aria-label"] == "Friday 25 December 2026")
    r.dispatch(pick.events["click"], {})
    tree = cycle(r, tree)
    assert a.day == D(2026, 12, 25) and type(a.day) is D
    assert find(tree, attr("role", "grid")) is None and a.left == [D(2026, 12, 25)]
    assert focused(r, tree).attrs["aria-haspopup"] == "dialog"


def test_month_end_and_the_arrow_buttons(tmp_path):
    _, a, r, tree = picker(tmp_path, day="datetime.date(2026, 1, 31)")
    r.dispatch(find(tree, cls("control")).events["click"], {})
    tree = cycle(r, tree)
    drain(r)
    next_month = find(tree, attr("aria-label", "Next month"))
    r.dispatch(next_month.events["click"], {})
    tree = cycle(r, tree)
    assert text([find(tree, cls("month"))]) == "February 2026"
    r.after_render()
    assert r.take_commands() == []  # the arrow buttons keep focus where it is
    focus_day = next(b for b in day_buttons(tree) if b.attrs["tabindex"] == "0")
    assert focus_day.attrs["aria-label"] == "Saturday 28 February 2026"


def test_limits(tmp_path):
    _, a, r, tree = picker(
        tmp_path, low="datetime.date(2026, 11, 10)", high="'2026-11-20'"
    )
    a.day = D(2026, 11, 12)
    tree = cycle(r, tree)
    r.dispatch(find(tree, cls("control")).events["click"], {})
    tree = cycle(r, tree)
    days = {b.attrs["aria-label"]: b for b in day_buttons(tree)}
    assert "disabled" in days["Monday 9 November 2026"].attrs
    assert "disabled" not in days["Tuesday 10 November 2026"].attrs
    assert "disabled" in days["Saturday 21 November 2026"].attrs
    assert "disabled" in find(tree, attr("aria-label", "Previous month")).attrs
    assert "disabled" in find(tree, attr("aria-label", "Next month")).attrs
    drain(r)
    grid = find(tree, attr("role", "grid"))
    r.dispatch(grid.events["keydown.up.prevent"], {"key": "ArrowUp"})  # the 5th: out of range
    tree = cycle(r, tree)
    r.after_render()
    assert r.take_commands() == []
    r.dispatch(days["Monday 9 November 2026"].events["click"], {})
    assert a.day == D(2026, 11, 12)  # a disabled day can't be picked


def test_sunday_weeks_clear_today_and_escape(tmp_path):
    _, a, r, tree = picker(tmp_path, day="datetime.date(2026, 11, 3)", extra=' week_start="sunday"')
    r.dispatch(find(tree, cls("control")).events["click"], {})
    tree = cycle(r, tree)
    assert [text([th]) for th in walk(find(tree, tag("thead"))) if th.tag == "th"][:2] == ["Su", "Mo"]
    clear = find(tree, lambda n: n.tag == "button" and text([n]).strip() == "Clear")
    r.dispatch(clear.events["click"], {})
    tree = cycle(r, tree)
    assert a.day is None

    r.dispatch(find(tree, cls("control")).events["click"], {})
    tree = cycle(r, tree)
    assert find(tree, lambda n: n.tag == "button" and text([n]).strip() == "Clear") is None
    today = find(tree, lambda n: n.tag == "button" and text([n]).strip() == "Today")
    r.dispatch(today.events["click"], {})
    assert a.day == datetime.date.today()

    tree = cycle(r, tree)
    r.dispatch(find(tree, cls("control")).events["click"], {})
    tree = cycle(r, tree)
    r.dispatch(find(tree, attr("role", "dialog")).events["keydown.esc.stop"], {"key": "Escape"})
    tree = cycle(r, tree)
    assert find(tree, attr("role", "grid")) is None and a.left[-1] == datetime.date.today()


def test_date_picker_with_a_form(tmp_path):
    _, a, r, tree = app(
        tmp_path,
        """<div><ui.DatePicker ref="when" label="When" @bind="when" required="true"
                 :error="form.error('when')" @blur="form.touch('when')" /></div>""",
        "from pyweft_ui import Form, rules\nwhen = None\nform = Form(when=rules.required('Choose a day'))",
    )
    control = find(tree, cls("control"))
    r.dispatch(control.events["click"], {})
    tree = cycle(r, tree)
    r.dispatch(find(tree, cls("backdrop")).events["click"], {})  # closed without choosing
    tree = cycle(r, tree)
    assert text([find(tree, cls("error"))]) == "Choose a day"
    assert find(tree, cls("control")).attrs["aria-invalid"] == "true"
    a.when = D(2026, 1, 1)
    tree = cycle(r, tree)
    assert find(tree, cls("error")) is None
