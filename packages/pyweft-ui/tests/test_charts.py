"""Charts: the layout (charting/) on its own, then the controls headless."""

import math
import re

import pytest

from pyweft_ui.charting import (
    cartesian, cartesian_input, fmt_tick, fmt_value, nice, pie, polar, radar, slices_input, ticks,
)
from pyweft_ui.charting.cartesian import _path, _tangents
from pyweft_ui.charting.radial import sector
from test_controls import app, cls, cycle, find, tag, text

ROWS = [
    {"month": "Jan", "online": 120, "store": 80},
    {"month": "Feb", "online": 150, "store": 95},
    {"month": "Mar", "online": None, "store": 70},
    {"month": "Apr", "online": 210, "store": -20},
]


def marks(scene, css):
    return [m for m in scene.marks if css in m.cls.split()]


# ------------------------------------------------------------------ scales
@pytest.mark.parametrize("lo, hi, count, expected", [
    (0, 213, 5, [0, 50, 100, 150, 200]),
    (0, 1, 5, [0, 0.2, 0.4, 0.6, 0.8, 1]),
    (-35, 72, 4, [-20, 0, 20, 40, 60]),
    (0.001, 0.0042, 3, [0.001, 0.002, 0.003, 0.004]),
])
def test_ticks_are_round_numbers(lo, hi, count, expected):
    assert ticks(lo, hi, count) == expected


def test_nice_widens_to_whole_steps():
    assert nice(3, 97, 5) == (0, 100)
    assert nice(0.13, 0.87, 4) == (0, 1)
    assert nice(5, 5) == (5, 5)


def test_formatting():
    assert [fmt_tick(v, 500) for v in (0, 2500, 12500)] == ["0", "2.5k", "12.5k"]
    assert fmt_tick(2_000_000, 1_000_000) == "2M" and fmt_tick(0.25, 0.05) == "0.25"
    assert fmt_value(1234.5) == "1,234.5" and fmt_value(3.0) == "3" and fmt_value(None) == "–"
    assert fmt_value(0.5, ".0%") == "50%" and fmt_value(9.5, "${:,.2f}") == "$9.50"
    assert fmt_value(2, lambda v: f"{v} kg") == "2 kg"


# -------------------------------------------------------------------- data
def test_data_shapes_all_give_the_same_series():
    columns = {"month": ["Jan", "Feb"], "online": [1, 2]}
    rows = [{"month": "Jan", "online": 1}, {"month": "Feb", "online": 2}]

    class Row:
        def __init__(self, month, online):
            self.month, self.online = month, online

    for data in (columns, rows, [Row("Jan", 1), Row("Feb", 2)]):
        cats, series, _ = cartesian_input(data)
        assert cats == ["Jan", "Feb"] and [(s.key, s.label, s.values) for s in series] == [("online", "Online", [1, 2])]


def test_series_settings_and_chartjs_data():
    cats, series, _ = cartesian_input(ROWS, "month", "online", [{"key": "store", "type": "line", "axis": "right",
                                                                 "dash": True, "color": "danger"}])
    store = series[1]
    assert (store.kind, store.axis, store.dash, store.color) == ("line", "right", "6 4", "var(--ui-danger)")
    assert series[0].color.startswith("var(--ui-chart-1")
    chartjs = {"labels": ["a", "b"], "datasets": [
        {"label": "X", "data": [1, 2], "type": "line", "tension": 0.4, "borderColor": "red", "fill": True},
        {"label": "Y", "data": [3], "yAxisID": "y1", "stepped": True}]}
    cats, series, _ = cartesian_input(chartjs)
    assert cats == ["a", "b"]
    assert [(s.label, s.kind, s.curve, s.axis, s.color) for s in series][0] == ("X", "area", "smooth", "left", "red")
    assert (series[1].axis, series[1].curve, series[1].values) == ("right", "step-after", [3, None])


def test_slices_from_dicts_rows_and_chartjs():
    assert [(s.label, s.value) for s in slices_input({"a": 1, "b": 2})] == [("a", 1), ("b", 2)]
    rows = [{"cat": "Rent", "amount": 900, "color": "#123"}, {"cat": "Food", "amount": "300"}]
    first, second = slices_input(rows)
    assert (first.label, first.value, first.color, second.value) == ("Rent", 900, "#123", 300)
    chartjs = {"labels": ["a", "b"], "datasets": [{"data": [5, 6], "backgroundColor": ["#f00", "#0f0"]}]}
    assert [s.color for s in slices_input(chartjs)] == ["#f00", "#0f0"]


# --------------------------------------------------------------- cartesian
def test_grouped_bars_tips_and_payload():
    cats, series, rows = cartesian_input(ROWS, "month")
    scene = cartesian(cats, series, width=600, height=300, rows=rows)
    bars = marks(scene, "bar")
    assert len(bars) == 7                                   # the missing value has no bar
    assert {b.hit for b in bars} == {0, 1, 2, 3} and len(scene.tips) == 4
    feb = [b for b in bars if b.hit == 1]
    assert feb[0].x < feb[1].x and feb[0].h > feb[1].h      # side by side, online taller
    negative = [b for b in bars if b.hit == 3 and b.series == "store"][0]
    zero = [m for m in scene.marks if m.cls == "grid zero"][0]
    assert negative.y == pytest.approx(zero.y1, abs=0.2)    # hangs down from zero
    assert scene.tips[1].rows == [("online", series[0].color, "Online", "150"), ("store", series[1].color, "Store", "95")]
    picked = scene.pick(1, "store")
    assert (picked["label"], picked["series"], picked["value"], picked["row"]) == ("Feb", "store", 95, ROWS[1])


def test_stacked_and_percent():
    cats, series, _ = cartesian_input(ROWS[:2], "month")
    scene = cartesian(cats, series, width=600, height=300, stacked="true")
    jan = sorted((b for b in marks(scene, "bar") if b.hit == 0), key=lambda b: b.series)
    assert jan[0].x == jan[1].x                             # one column
    assert jan[1].y + jan[1].h == pytest.approx(jan[0].y, abs=0.2)   # store sits on online
    assert scene.tips[0].rows[-1][2:] == ("Total", "200")
    scene = cartesian(cats, series, width=600, height=300, stacked="percent")
    assert scene.tips[0].rows[0][3] == "120 (60.0%)"
    assert [m.text for m in marks(scene, "tick")][:6] == ["0", "20", "40", "60", "80", "100"]


def test_horizontal_bars_and_labels():
    cats, series, _ = cartesian_input(ROWS[:2], "month", "online")
    scene = cartesian(cats, series, width=500, height=200, horizontal=True, labels=True)
    a, b = marks(scene, "bar")
    assert a.y < b.y and a.x == b.x and b.w > a.w            # categories down, values across
    assert [m.text for m in marks(scene, "value-label")] == ["120", "150"]


def test_hidden_series_rescale_and_legend_keeps_them():
    cats, series, _ = cartesian_input(ROWS[:2], "month")
    scene = cartesian(cats, series, width=600, height=300, hidden={"online"})
    assert {b.series for b in marks(scene, "bar")} == {"store"}
    assert [(i.key, i.hidden) for i in scene.legend] == [("online", True), ("store", False)]
    assert max(float(m.text) for m in marks(scene, "tick") if m.key.startswith("t")) == 100


def test_lines_gaps_curves_and_second_axis():
    cats, series, _ = cartesian_input(ROWS, "month", "online, store", [{"key": "store", "axis": "right"}], "line")
    scene = cartesian(cats, series, width=600, height=300)
    online = [m for m in marks(scene, "line") if m.key.endswith("|online")]
    assert len(online) == 2                                 # the gap in March splits it
    joined = cartesian(cats, series, width=600, height=300, connect_gaps=True)
    assert len([m for m in marks(joined, "line") if m.key.endswith("|online")]) == 1
    assert any(m.key.startswith("r") for m in marks(scene, "tick"))   # right-hand tick labels
    assert len(marks(scene, "point")) == 7
    smooth = cartesian(cats, series, width=600, height=300, curve="smooth", connect_gaps=True)
    assert " C" in [m for m in marks(smooth, "line")][0].d


def test_area_and_stacked_area():
    cats, series, _ = cartesian_input(ROWS[:3], "month", "online, store", (), "area")
    scene = cartesian(cats, series, width=600, height=300, stacked="true")
    areas = marks(scene, "area")
    assert len(areas) == 2 and all(a.d.endswith("Z") for a in areas)
    hover = scene.tips[0].marks
    assert [m.cls for m in hover] == ["hover-band", "hover-point", "hover-point"]


def test_monotone_curve_never_overshoots():
    pts = [(0, 10), (10, 10), (20, 50), (30, 50), (40, 0)]
    t = _tangents(pts)
    assert t[1] == 0 and t[3] == 0                          # flat runs stay flat
    d = _path(pts, "smooth", False)
    ys = [float(y) for y in re.findall(r",(-?[\d.]+)", d)]
    assert min(ys) >= 0 and max(ys) <= 50
    assert _path([(0, 0), (10, 5)], "step", False) == "M0.0,0.0 L5.0,0.0 L5.0,5.0 L10.0,5.0"
    assert _path([(0, 0), (10, 5)], "linear", True) == "M0.0,0.0 L10.0,5.0"


def test_empty_data_says_so():
    scene = cartesian([], [], width=400, height=200, empty="Nothing yet")
    assert [m.text for m in scene.marks] == ["Nothing yet"] and scene.tips == []


@pytest.mark.parametrize("seed", range(40))
def test_random_data_stays_inside_the_plot(seed):
    import random

    rnd = random.Random(seed)
    count = rnd.randint(1, 30)
    data = [{"c": f"c{i}", **{k: rnd.choice([None, rnd.uniform(-1e4, 1e5)]) for k in "abc"}} for i in range(count)]
    kind = rnd.choice(["bar", "line", "area"])
    cats, series, _ = cartesian_input(data, "c", "a, b, c", (), kind)
    width, height = rnd.randint(160, 1200), rnd.randint(120, 500)
    scene = cartesian(cats, series, width=width, height=height, stacked=rnd.choice(["", "true", "percent"]),
                      horizontal=kind == "bar" and rnd.random() < 0.3, curve=rnd.choice(["linear", "smooth", "step"]))
    for m in scene.marks:
        for v in (m.x, m.y, m.cx, m.cy, m.x1, m.x2, m.y1, m.y2):
            assert v is None or (-1 <= v <= width + 1 or v <= height + 1)
            assert v is None or math.isfinite(v)
        if m.kind == "rect":
            assert m.w >= 0 and m.h >= 0
    assert len(scene.tips) == count


# ------------------------------------------------------------------ radial
def test_pie_slices_shares_and_center():
    slices = slices_input({"a": 1, "b": 3, "c": 0})
    scene = pie(slices, width=300, height=300, hole=0.6, center="total", center_label="items")
    assert len(marks(scene, "slice")) == 2                  # nothing to draw for zero
    assert [m.text for m in scene.marks if m.cls.startswith("center")] == ["4", "items"]
    assert scene.tips[1].title == "b" and scene.tips[1].rows[0][3] == "3 · 75%"
    assert scene.pick(1)["percent"] == 75 and scene.rows[2] == ["c", "0", ""]
    hidden = pie(slices, width=300, height=300, hidden={"1"})
    assert len(marks(hidden, "slice")) == 1 and hidden.tips[0].rows[0][3] == "1 · 100%"


def test_sector_paths():
    assert sector(0, 0, 0, 10, 0, math.pi / 2) == "M10.0,0.0 A10.0,10.0 0 0 1 0.0,10.0 L0.0,0.0 Z"
    ring = sector(0, 0, 5, 10, 0, 2 * math.pi)
    assert ring.count("Z") == 2 and "0 1 0" in ring        # a whole ring with its hole
    assert " 0 1 1 " in sector(0, 0, 0, 10, 0, 4)           # more than half: the large arc


def test_polar_and_radar():
    scene = polar(slices_input({"a": 2, "b": 8}), width=300, height=300)
    a, b = marks(scene, "polar")
    assert len(marks(scene, "hit")) == 2 and len(a.d) and b.d != a.d
    cats, series, _ = cartesian_input([{"k": c, "x": v, "y": 5 - v} for c, v in zip("ABCDE", [1, 2, 3, 4, 5])])
    scene = radar(cats, series, width=400, height=320)
    assert len(marks(scene, "radar-area")) == 2 and len(marks(scene, "hit")) == 5
    assert scene.tips[4].rows[0][2:] == ("X", "5")
    few = radar(cats[:2], series, width=400, height=320)
    assert "three or more" in few.marks[0].text


# ---------------------------------------------------------------- controls
CODE = """
rows = [{"month": "Jan", "online": 120, "store": 80}, {"month": "Feb", "online": 150, "store": 95}]
picked: list = []
"""


def test_bar_chart_renders_hovers_and_selects(tmp_path):
    _, a, r, tree = app(tmp_path, '<div><ui.BarChart :data="rows" x="month" title="Sales" class="wide"'
                                  ' @select="picked.append(event)" /></div>', CODE)
    figure = find(tree, tag("figure"))
    assert "wide" in figure.attrs["class"] and "clickable" in figure.attrs["class"]
    assert text([find(tree, cls("title"))]) == "Sales"
    plot = find(tree, cls("plot"))
    assert plot.attrs["role"] == "img" and plot.attrs["aria-label"].startswith("Bar chart of Online, Store")
    assert len([n for n in find(tree, tag("svg")).children if n.tag == "rect"]) == 6   # 2 bands + 4 bars
    band = find(tree, cls("band"))
    r.dispatch(band.events["mouseenter"], {"type": "mouseenter"})
    tree = cycle(r, tree)
    tip = find(tree, cls("tip"))
    assert text([find([tip], cls("tip-title"))]) == "Jan" and "120" in text([tip])
    assert find(tree, cls("hover-band")) is not None
    bar = find(tree, cls("bar"))
    r.dispatch(bar.events["click"], {"type": "click"})
    assert a.picked[0]["label"] == "Jan" and a.picked[0]["series"] == "online" and a.picked[0]["value"] == 120
    r.dispatch(plot.events["mouseleave"], {"type": "mouseleave"})
    tree = cycle(r, tree)
    assert find(tree, cls("tip")) is None


def test_chart_width_comes_from_resize(tmp_path):
    _, a, r, tree = app(tmp_path, '<div><ui.LineChart :data="rows" x="month" /></div>', CODE)
    svg = find(tree, tag("svg"))
    assert svg.attrs["viewBox"] == "0 0 640.0 300.0"
    r.dispatch(find(tree, cls("plot")).events["resize"], {"type": "resize", "width": 360, "height": 300})
    tree = cycle(r, tree)
    assert find(tree, tag("svg")).attrs["viewBox"] == "0 0 360.0 300.0"


def test_legend_toggles_and_keyboard_reads_values(tmp_path):
    _, a, r, tree = app(tmp_path, '<div><ui.BarChart :data="rows" x="month" /></div>', CODE)
    online, store = [n for n in find(tree, cls("legend")).children]
    assert online.attrs["aria-pressed"] == "true"
    r.dispatch(online.events["click"], {"type": "click"})
    tree = cycle(r, tree)
    assert find(tree, cls("legend")).children[0].attrs["aria-pressed"] == "false"
    assert {n.attrs.get("style") for n in [find(tree, cls("bar"))]} == {"fill: var(--ui-chart-2, #14b8a6)"}
    plot = find(tree, cls("plot"))
    r.dispatch(plot.events["keydown.right.prevent"], {"type": "keydown", "key": "ArrowRight"})
    tree = cycle(r, tree)
    live = [n for n in tree[0].children[0].children if n.attrs.get("aria-live")][0]
    assert text([live]) == "Jan. Store: 80"
    r.dispatch(plot.events["keydown.end.prevent"], {"type": "keydown", "key": "End"})
    tree = cycle(r, tree)
    assert text([find(tree, cls("tip-title"))]) == "Feb"


def test_no_select_handler_means_not_clickable(tmp_path):
    _, a, r, tree = app(tmp_path, '<div><ui.PieChart :data="{\'a\': 1, \'b\': 2}" donut="true" center="total" /></div>')
    assert "clickable" not in find(tree, tag("figure")).attrs["class"]
    slice_ = find(tree, cls("slice"))
    r.dispatch(slice_.events["click"], {"type": "click"})   # nothing to tell: no error
    assert text([find(tree, cls("center-value"))]) == "3"
    table = find(tree, tag("table"))
    assert [text([td]) for td in find([table], tag("tbody")).children[1].children] == ["b", "2", "67%"]


def test_every_chart_renders(tmp_path):
    _, a, r, tree = app(tmp_path, """<div>
      <ui.LineChart :data="rows" x="month" fill="true" stacked="true" curve="smooth" />
      <ui.PolarAreaChart :data="{'x': 1, 'y': 3, 'z': 2}" />
      <ui.RadarChart :data="rows + rows[:1]" x="month" />
      <ui.BarChart :data="[]" empty="Nothing yet" />
    </div>""", CODE + 'rows.append({"month": "Mar", "online": 90, "store": 60})\n')
    figures = [n for n in tree[0].children]
    assert len(figures) == 4
    assert find([figures[0]], cls("area")) is not None and find([figures[1]], cls("polar")) is not None
    assert find([figures[2]], cls("radar-area")) is not None
    assert text([find([figures[3]], cls("empty"))]) == "Nothing yet"



def test_hiding_a_series_hides_it_in_that_chart_only(tmp_path):
    _, a, r, tree = app(tmp_path, '<div><ui.BarChart :data="rows" x="month" /><ui.BarChart :data="rows" x="month" /></div>',
                        CODE)
    r.dispatch(find([tree[0].children[0]], cls("legend")).children[0].events["click"], {"type": "click"})
    tree = cycle(r, tree)
    first, second = [find([chart], cls("legend")).children[0] for chart in tree[0].children]
    assert first.attrs["aria-pressed"] == "false" and second.attrs["aria-pressed"] == "true"
    _, a, r, tree = app(tmp_path, '<div><ui.BarChart :data="rows" x="month" /></div>', CODE)
    assert find(tree, cls("legend")).children[0].attrs["aria-pressed"] == "true"   # a new chart too
