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


def menu_items(menu):
    return [e.children[0] for e in menu.children if e.attrs.get("role") == "none"]


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
    items = menu_items(menu)
    assert [text([n]).strip() for n in items] == ["Edit", "Duplicate", "Archive", "Delete"]
    assert "disabled" in items[2].attrs and "danger" in items[3].attrs["class"]
    assert find(tree, attr("role", "separator")) is not None
    assert label_of(focused(r, tree)) == "Edit"  # the first item

    # Down skips the disabled item; it wraps at the end.
    for expected in ("Duplicate", "Delete", "Edit"):
        r.dispatch(menu.events["keydown.down.prevent.stop"], {"key": "ArrowDown"})
        tree = cycle(r, tree)
        assert label_of(focused(r, tree)) == expected
    r.dispatch(menu.events["keydown.end.prevent.stop"], {"key": "End"})
    tree = cycle(r, tree)
    assert label_of(focused(r, tree)) == "Delete"
    r.dispatch(menu.events["keydown.up.prevent.stop"], {"key": "ArrowUp"})
    tree = cycle(r, tree)
    assert label_of(focused(r, tree)) == "Duplicate"  # up skips Archive too

    items = menu_items(find(tree, attr("role", "menu")))
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
    r.dispatch(menu.events["keydown.tab.stop"], {"key": "Tab"})  # Tab moves on: no refocus
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
    assert find(tree, attr("role", "grid")).attrs["aria-label"] == "November 2026"
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
    assert find(tree, attr("role", "grid")).attrs["aria-label"] == "December 2026"
    assert focused(r, tree).attrs["aria-label"] == "Thursday 10 December 2026"
    grid = find(tree, attr("role", "grid"))  # December's grid: a new element
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
    assert find(tree, attr("role", "grid")).attrs["aria-label"] == "February 2026"
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


def test_months_and_years_views(tmp_path):
    _, a, r, tree = picker(
        tmp_path, day="datetime.date(2026, 11, 3)", low="datetime.date(2025, 3, 15)",
        high="datetime.date(2031, 6, 1)",
    )
    r.dispatch(find(tree, cls("control")).events["click"], {})
    tree = cycle(r, tree)
    drain(r)
    titles = [n for n in walk(find(tree, cls("month"))) if n.tag == "button"]
    assert [label_of(b) for b in titles] == ["November", "2026"]

    # The month name: a choice of the year's months, focus on the shown one.
    r.dispatch(titles[0].events["click"], {})
    tree = cycle(r, tree)
    months = [b for b in walk(find(tree, attr("role", "grid"))) if b.tag == "button"]
    assert [label_of(b) for b in months][:3] == ["Jan", "Feb", "Mar"] and len(months) == 12
    assert focused(r, tree).attrs["aria-label"] == "November 2026"
    assert months[10].attrs["aria-pressed"] == "true"  # the chosen date's month
    grid = find(tree, attr("role", "grid"))
    r.dispatch(grid.events["keydown.up.prevent"], {"key": "ArrowUp"})  # three back
    tree = cycle(r, tree)
    assert focused(r, tree).attrs["aria-label"] == "August 2026"
    r.dispatch(find(tree, attr("aria-label", "Next year")).events["click"], {})
    tree = cycle(r, tree)
    drain(r)
    months = [b for b in walk(find(tree, attr("role", "grid"))) if b.tag == "button"]
    assert find(tree, attr("role", "grid")).attrs["aria-label"] == "Months of 2027"
    r.dispatch(months[1].events["click"], {})  # February 2027: back to its days
    tree = cycle(r, tree)
    assert find(tree, attr("role", "grid")).attrs["aria-label"] == "February 2027"
    assert focused(r, tree).attrs["aria-label"] == "Wednesday 3 February 2027"

    # The year: twelve years; out-of-range ones can't be chosen; then months.
    year_button = [n for n in walk(find(tree, cls("month"))) if n.tag == "button"][1]
    r.dispatch(year_button.events["click"], {})
    tree = cycle(r, tree)
    years = {label_of(b): b for b in walk(find(tree, attr("role", "grid"))) if b.tag == "button"}
    assert list(years)[0] == "2016" and list(years)[-1] == "2027"
    assert "disabled" in years["2024"].attrs and "disabled" not in years["2025"].attrs
    assert label_of(find(tree, cls("title-text"))) == "2016 – 2027"
    assert focused(r, tree).attrs["aria-pressed"] == "false"  # 2027, not the chosen 2026
    r.dispatch(find(tree, attr("aria-label", "Next twelve years")).events["click"], {})
    tree = cycle(r, tree)
    years = {label_of(b): b for b in walk(find(tree, attr("role", "grid"))) if b.tag == "button"}
    assert list(years)[0] == "2028" and "disabled" in years["2032"].attrs
    assert "disabled" in find(tree, attr("aria-label", "Next twelve years")).attrs
    r.dispatch(years["2030"].events["click"], {})
    tree = cycle(r, tree)
    assert find(tree, attr("role", "grid")).attrs["aria-label"] == "Months of 2030"

    # Esc goes back a step: months -> days; then it closes.
    calendar = find(tree, cls("calendar"))
    r.dispatch(calendar.events["keydown.esc.stop"], {"key": "Escape"})
    tree = cycle(r, tree)
    assert find(tree, attr("role", "grid")).attrs["aria-label"] == "February 2030"
    r.dispatch(find(tree, cls("calendar")).events["keydown.esc.stop"], {"key": "Escape"})
    tree = cycle(r, tree)
    assert find(tree, attr("role", "dialog")) is None
    assert a.day == D(2026, 11, 3)  # browsing never changes the value


def test_months_outside_the_limits(tmp_path):
    _, a, r, tree = picker(
        tmp_path, day="datetime.date(2026, 5, 20)", low="datetime.date(2026, 3, 15)",
        high="datetime.date(2026, 8, 1)",
    )
    r.dispatch(find(tree, cls("control")).events["click"], {})
    tree = cycle(r, tree)
    title = [n for n in walk(find(tree, cls("month"))) if n.tag == "button"][0]
    r.dispatch(title.events["click"], {})
    tree = cycle(r, tree)
    months = [b for b in walk(find(tree, attr("role", "grid"))) if b.tag == "button"]
    allowed = [label_of(b) for b in months if "disabled" not in b.attrs]
    assert allowed == ["Mar", "Apr", "May", "Jun", "Jul", "Aug"]
    assert "disabled" in find(tree, attr("aria-label", "Previous year")).attrs
    r.dispatch(months[2].events["click"], {})  # March: the 20th is fine
    tree = cycle(r, tree)
    assert focused(r, tree).attrs["aria-label"] == "Friday 20 March 2026"


# ------------------------------------------------------------------ Calendar and ranges


def days_by_label(tree):
    return {b.attrs["aria-label"]: b for b in day_buttons_all(tree)}


def day_buttons_all(tree):
    out = []

    def walk_all(nodes):
        for node in nodes:
            if getattr(node, "tag", None):
                if node.tag == "button" and "day" in node.attrs.get("class", "").split():
                    out.append(node)
                walk_all(node.children)

    walk_all(tree)
    return out


def test_calendar_on_a_page(tmp_path):
    _, a, r, tree = app(
        tmp_path, '<div><ui.Calendar @bind="day" min="2030-01-01" max="2030-12-31" /></div>',
        "day = None",
    )
    r.after_render()
    assert r.take_commands() == []  # on a page it doesn't take the keyboard
    assert find(tree, attr("role", "grid")).attrs["aria-label"] == "January 2030"
    r.dispatch(days_by_label(tree)["Friday 4 January 2030"].events["click"], {})
    tree = cycle(r, tree)
    assert a.day == D(2030, 1, 4)
    assert days_by_label(tree)["Friday 4 January 2030"].attrs["aria-pressed"] == "true"


RANGE = """<div><ui.DateRangePicker label="Stay" @bind="stay" min="2030-01-10" max="2030-06-30"
                 @blur="left.append(event)" /></div>"""


def ranged(tmp_path, extra="", stay="None"):
    return app(tmp_path, RANGE.replace("/>", f"{extra} />") if extra else RANGE,
               f"import datetime\nstay = {stay}\nleft: list = []")


def test_a_range_is_chosen_first_day_then_last(tmp_path):
    _, a, r, tree = ranged(tmp_path)
    assert text([find(tree, cls("text"))]) == "Choose dates"
    r.dispatch(find(tree, cls("control")).events["click"], {})
    tree = cycle(r, tree)
    titles = [g.attrs["aria-label"] for g in [n for n in walk_tree(tree) if n.attrs.get("role") == "grid"]]
    assert titles == ["January 2030", "February 2030"]  # two months, from min
    assert find(tree, cls("blank")) is not None  # the neighbour's days are left out
    assert focused(r, tree).attrs["aria-label"] == "Thursday 10 January 2030"

    days = days_by_label(tree)
    r.dispatch(days["Saturday 12 January 2030"].events["click"], {})
    tree = cycle(r, tree)
    assert text([find(tree, cls("status"))]) == "Now choose the last day"
    r.dispatch(days_by_label(tree)["Tuesday 15 January 2030"].events["mouseenter"], {})
    tree = cycle(r, tree)
    preview = [b.attrs["aria-label"].split()[1] for b in day_buttons_all(tree)
               if "preview" in b.attrs["class"].split()]
    assert preview == ["12", "13", "14", "15"]
    assert a.stay is None  # nothing is chosen until the last day is

    r.dispatch(days_by_label(tree)["Tuesday 15 January 2030"].events["click"], {})
    tree = cycle(r, tree)
    assert a.stay == (D(2030, 1, 12), D(2030, 1, 15)) and type(a.stay) is tuple
    assert find(tree, attr("role", "dialog")) is None and a.left == [a.stay]
    assert text([find(tree, cls("text"))]) == "12 – 15 Jan 2030"
    assert focused(r, tree).attrs["aria-haspopup"] == "dialog"


def test_a_range_backwards_across_months_and_reopened(tmp_path):
    _, a, r, tree = ranged(tmp_path)
    r.dispatch(find(tree, cls("control")).events["click"], {})
    tree = cycle(r, tree)
    r.dispatch(days_by_label(tree)["Sunday 3 February 2030"].events["click"], {})
    tree = cycle(r, tree)
    r.dispatch(days_by_label(tree)["Monday 28 January 2030"].events["click"], {})
    tree = cycle(r, tree)
    assert a.stay == (D(2030, 1, 28), D(2030, 2, 3))
    assert text([find(tree, cls("text"))]) == "28 Jan – 3 Feb 2030"

    # Open again: the range shows as a band, its ends chosen.
    r.dispatch(find(tree, cls("control")).events["click"], {})
    tree = cycle(r, tree)
    days = days_by_label(tree)
    assert "start" in days["Monday 28 January 2030"].attrs["class"]
    assert "end" in days["Sunday 3 February 2030"].attrs["class"]
    assert days["Wednesday 30 January 2030"].attrs["aria-pressed"] == "true"
    assert text([find(tree, cls("length"))]) == "7 days"


def test_range_length_limits_and_escape(tmp_path):
    _, a, r, tree = ranged(tmp_path, extra=' min_days="2" max_days="5"')
    r.dispatch(find(tree, cls("control")).events["click"], {})
    tree = cycle(r, tree)
    r.dispatch(days_by_label(tree)["Saturday 12 January 2030"].events["click"], {})
    tree = cycle(r, tree)
    days = days_by_label(tree)
    assert "disabled" in days["Sunday 13 January 2030"].attrs     # 1 day: too short
    assert "disabled" not in days["Monday 14 January 2030"].attrs
    assert "disabled" not in days["Thursday 17 January 2030"].attrs
    assert "disabled" in days["Friday 18 January 2030"].attrs     # 6 days: too long

    # Esc drops the half-chosen range first, then closes.
    r.dispatch(find(tree, cls("calendar")).events["keydown.esc.stop"], {"key": "Escape"})
    tree = cycle(r, tree)
    assert text([find(tree, cls("status"))]) == "Choose the first day"
    assert find(tree, attr("role", "dialog")) is not None
    assert "disabled" not in days_by_label(tree)["Friday 18 January 2030"].attrs
    r.dispatch(find(tree, cls("calendar")).events["keydown.esc.stop"], {"key": "Escape"})
    tree = cycle(r, tree)
    assert find(tree, attr("role", "dialog")) is None and a.stay is None


def test_keyboard_moves_the_range_preview(tmp_path):
    _, a, r, tree = ranged(tmp_path, stay="(datetime.date(2030, 3, 4), datetime.date(2030, 3, 6))")
    assert text([find(tree, cls("text"))]) == "4 – 6 Mar 2030"
    r.dispatch(find(tree, cls("control")).events["click"], {})
    tree = cycle(r, tree)
    assert focused(r, tree).attrs["aria-label"] == "Monday 4 March 2030"
    focus_day = days_by_label(tree)["Monday 4 March 2030"]
    r.dispatch(focus_day.events["click"], {})  # Enter on the focused day: the first day
    tree = cycle(r, tree)
    grid = [n for n in walk_tree(tree) if n.attrs.get("role") == "grid"][0]
    r.dispatch(grid.events["keydown.right.prevent"], {"key": "ArrowRight"})
    r.dispatch(grid.events["keydown.right.prevent"], {"key": "ArrowRight"})
    tree = cycle(r, tree)
    preview = [b.attrs["aria-label"].split()[1] for b in day_buttons_all(tree)
               if "preview" in b.attrs["class"].split()]
    assert preview == ["4", "5", "6"]
    r.dispatch(days_by_label(tree)["Wednesday 6 March 2030"].events["click"], {})
    assert a.stay == (D(2030, 3, 4), D(2030, 3, 6))


def walk_tree(nodes):
    for node in nodes:
        if getattr(node, "tag", None):
            yield node
            yield from walk_tree(node.children)


def test_a_range_with_a_form(tmp_path):
    _, a, r, tree = app(
        tmp_path,
        """<div><ui.DateRangePicker label="Stay" @bind="stay" required="true"
                 :error="form.error('stay')" @blur="form.touch('stay')" /></div>""",
        "from pyweft_ui import Form, rules\nstay = None\nform = Form(stay=rules.required('Choose your dates'))",
    )
    r.dispatch(find(tree, cls("control")).events["click"], {})
    tree = cycle(r, tree)
    r.dispatch(find(tree, cls("backdrop")).events["click"], {})
    tree = cycle(r, tree)
    assert text([find(tree, cls("error"))]) == "Choose your dates"
