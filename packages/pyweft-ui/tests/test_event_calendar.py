"""EventCalendar: events laid out by month, week and agenda."""

import datetime
from types import SimpleNamespace

from test_controls import app, cycle, find, text
from pyweft.vdom import Element

D, T = datetime.date, datetime.datetime

EVENTS = """
import datetime
picked: list = []
days: list = []
shown: list = []
events: list = [
    {"id": 1, "title": "Standup", "start": datetime.datetime(2026, 11, 10, 10, 0),
     "end": datetime.datetime(2026, 11, 10, 10, 15), "color": "blue"},
    {"id": 2, "title": "1:1", "start": datetime.datetime(2026, 11, 10, 10, 0),
     "end": datetime.datetime(2026, 11, 10, 10, 30), "color": "green"},
    {"id": 3, "title": "Conference", "start": datetime.date(2026, 11, 8),
     "end": datetime.date(2026, 11, 11), "color": "purple"},
    {"id": 4, "title": "Release", "start": "2026-11-12", "color": "red"},
    {"id": 5, "title": "Extra", "start": datetime.date(2026, 11, 10)},
]
"""


def calendar(tmp_path, attrs="", code=EVENTS):
    return app(
        tmp_path,
        f'''<div><ui.EventCalendar :events="events" date="2026-11-10" {attrs}
                 @select="picked.append(event)" @navigate="shown.append(event)" /></div>''',
        code,
    )


def nodes(tree, cls):
    out = []

    def walk(ns):
        for n in ns:
            if isinstance(n, Element):
                if cls in n.attrs.get("class", "").split():
                    out.append(n)
                walk(n.children)

    walk(tree)
    return out


def label(n):
    """The visible text; separate pieces (a time, a name) joined by a space."""
    parts = [" ".join(text([c]).split()) for c in n.children if isinstance(c, Element)]
    parts = [p for p in parts if p]
    return " ".join(parts) if parts else " ".join(text([n]).split())


def test_month_lays_events_out_in_lanes(tmp_path):
    _, a, r, tree = calendar(tmp_path)
    assert label(nodes(tree, "title")[0]) == "November 2026"
    weeks = nodes(tree, "week")
    assert len(weeks) == 6  # 26 Oct to 6 Dec, Monday first
    bars = {label(b): b for b in nodes(tree, "event")}
    # The conference runs Sunday 8 into the next week: two bars, joined.
    conference = [b for b in nodes(tree, "event") if label(b) == "Conference"]
    assert len(conference) == 2
    assert "goes-on" in conference[0].attrs["class"] and "from-before" in conference[1].attrs["class"]
    assert "grid-column: 1 / span 3" in conference[1].attrs["style"]  # Mon 9 to Wed 11
    assert "dot" in bars["10:00 1:1"].attrs["class"]  # timed: a dot and the time
    assert "--ev: #16a34a" in bars["10:00 1:1"].attrs["style"]
    # Tuesday 10 has four events: three rows, then "+1 more".
    assert [label(m) for m in nodes(tree, "more")] == ["+1 more"]


def test_more_expands_the_week(tmp_path):
    _, a, r, tree = calendar(tmp_path)
    r.dispatch(nodes(tree, "more")[0].events["click"], {})
    tree = cycle(r, tree)
    assert nodes(tree, "more") == []
    names = [label(b) for b in nodes(tree, "event")]
    assert "10:00 Standup" in names and "10:00 1:1" in names
    r.dispatch(nodes(tree, "less")[0].events["click"], {})
    tree = cycle(r, tree)
    assert [label(m) for m in nodes(tree, "more")] == ["+1 more"]


def test_select_gives_back_your_event_and_days_only_click_when_listened_to(tmp_path):
    _, a, r, tree = calendar(tmp_path)
    release = next(b for b in nodes(tree, "event") if label(b) == "Release")
    assert release.attrs["aria-label"] == "Release, Thursday 12 November 2026, all day"
    r.dispatch(release.events["click"], {})
    assert a.picked == [a.events[3]]
    assert not any("clickable" in c.attrs["class"] for c in nodes(tree, "cell"))

    _, b, r2, tree2 = app(
        tmp_path / "x" if (tmp_path / "x").mkdir() is None else tmp_path,
        '<div><ui.EventCalendar :events="[]" date="2026-11-10" @day="days.append(event)" /></div>',
        "days: list = []",
    )
    cells = nodes(tree2, "cell")
    assert all("clickable" in c.attrs["class"] for c in cells)
    r2.dispatch(cells[15].events["click"], {})  # the third week's Tuesday
    assert b.days == [D(2026, 11, 10)]


def test_navigation(tmp_path):
    _, a, r, tree = calendar(tmp_path)
    nav = {n.attrs.get("aria-label"): n for n in nodes(tree, "nav")}
    r.dispatch(nav["Next month"].events["click"], {})
    tree = cycle(r, tree)
    assert label(nodes(tree, "title")[0]) == "December 2026"
    assert a.shown[-1] == (D(2026, 11, 30), D(2027, 1, 3))
    views = {label(v): v for v in nodes(tree, "view")}
    r.dispatch(views["Week"].events["click"], {})
    tree = cycle(r, tree)
    assert label(nodes(tree, "title")[0]) == "30 Nov – 6 Dec 2026"  # the week of the 1st
    r.dispatch(nodes(tree, "today-btn")[0].events["click"], {})
    tree = cycle(r, tree)
    today = datetime.date.today()
    first = today - datetime.timedelta(days=today.weekday())
    assert a.shown[-1] == (first, first + datetime.timedelta(days=6))


def test_week_places_timed_events_side_by_side(tmp_path):
    _, a, r, tree = calendar(tmp_path, attrs='view="week" day_start="9" day_end="13"')
    assert label(nodes(tree, "title")[0]) == "9 – 15 Nov 2026"
    timed = {label(t).split(" ")[0]: t for t in nodes(tree, "timed")}
    standup, one = timed["Standup"].attrs["style"], timed["1:1"].attrs["style"]
    # 10:00 is a quarter of the way through 9-13; both start then, half width each.
    assert "top: 25.000%" in standup and "width: 50.000%" in standup
    assert "height: 6.250%" in standup and "height: 12.500%" in one
    assert "left: 0.000%" in standup and "left: 50.000%" in one  # by start, then the earlier end
    all_day = [label(b) for b in nodes(tree, "event")]
    assert all_day == ["Conference", "Extra", "Release"]
    assert [label(h) for h in nodes(tree, "hour")] == ["09:00", "10:00", "11:00", "12:00"]


def test_several_months_and_the_agenda(tmp_path):
    _, a, r, tree = calendar(tmp_path, attrs='months="3"')
    assert label(nodes(tree, "title")[0]) == "November 2026 – January 2027"
    assert [label(h) for h in nodes(tree, "month-name")] == [
        "November 2026", "December 2026", "January 2027"]
    nav = {n.attrs.get("aria-label"): n for n in nodes(tree, "nav")}
    r.dispatch(nav["Next month"].events["click"], {})
    tree = cycle(r, tree)
    assert label(nodes(tree, "title")[0]) == "December 2026 – February 2027"

    _, b, r2, tree2 = calendar(tmp_path, attrs='view="agenda"')
    days = [label(h) for h in nodes(tree2, "ag-date")]
    assert days == ["Sunday 8 November", "Monday 9 November", "Tuesday 10 November",
                    "Wednesday 11 November", "Thursday 12 November"]
    tuesday = [label(e) for e in nodes(tree2, "ag-event")][2:6]
    assert tuesday == ["All day Conference", "All day Extra", "10:00 – 10:30 1:1",
                       "10:00 – 10:15 Standup"]


def test_objects_strings_and_nothing_planned(tmp_path):
    code = """
import datetime
from types import SimpleNamespace
picked: list = []
shown: list = []
events: list = [SimpleNamespace(title="Dentist", start="2026-11-20T09:00", end="2026-11-20T09:45", color="#ff00aa")]
"""
    _, a, r, tree = calendar(tmp_path, attrs='view="agenda"', code=code)
    (event,) = nodes(tree, "ag-event")
    assert label(event) == "09:00 – 09:45 Dentist" and "--ev: #ff00aa" in event.attrs["style"]
    r.dispatch(event.events["click"], {})
    assert a.picked[0].title == "Dentist"
    nav = {n.attrs.get("aria-label"): n for n in nodes(tree, "nav")}
    r.dispatch(nav["Next month"].events["click"], {})
    tree = cycle(r, tree)
    assert label(nodes(tree, "empty")[0]) == "Nothing planned."
