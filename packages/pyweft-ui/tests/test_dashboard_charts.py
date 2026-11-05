"""Scatter/bubble, sparkline, gauge, funnel and waterfall."""

import math
import random

import pytest

from pyweft_ui.charting import (
    funnel, gauge, linear_fit, scatter, slices_input, sparkline, waterfall, xy_input,
)
from test_controls import app, cls, cycle, find, tag, text


def marks(scene, css):
    return [m for m in scene.marks if css in m.cls.split()]


PEOPLE = [{"name": f"p{i}", "h": 150 + i * 5, "w": 50 + i * 3 + (i % 3), "sex": "ab"[i % 2], "pop": i + 1}
          for i in range(8)]


# ----------------------------------------------------------------- scatter
def test_linear_fit():
    fit = linear_fit([0, 1, 2, 3], [1, 3, 5, 7])
    assert (fit.slope, fit.intercept, fit.r2) == (2, 1, 1)
    assert linear_fit([1, 1], [2, 3]) is None and linear_fit([1], [2]) is None
    noisy = linear_fit([0, 1, 2, 3], [0, 2, 1, 3])
    assert 0 < noisy.r2 < 1


def test_series_from_fields_or_groups():
    series, x, ys = xy_input(PEOPLE, "h", "w")
    assert (x, ys, [s.key for s in series], len(series[0].points)) == ("h", ["w"], ["w"], 8)
    series, _, _ = xy_input(PEOPLE, "h", "w", group="sex", label="name")
    assert [(s.key, len(s.points)) for s in series] == [("a", 4), ("b", 4)]
    assert series[1].points[0].name == "p1" and series[1].points[0].index == 1
    assert xy_input(PEOPLE)[1] == "h"                        # the first number field


def test_scatter_points_tips_trend_and_payload():
    series, _, _ = xy_input(PEOPLE, "h", "w", group="sex", label="name")
    scene = scatter(series, width=500, height=320, trend=True, x_name="Height", y_name="Weight")
    dots = marks(scene, "dot")
    assert len(dots) == 8 and len(scene.tips) == 8 and all(d.hit is not None for d in dots)
    assert len(marks(scene, "trend")) == 2 and marks(scene, "trend-label")[0].text.startswith("R² ")
    tip = scene.tips[1]
    assert tip.title == "p2" and tip.rows[0][2:] == ("Height", "160") and tip.rows[-1][2:] == ("Series", "a")
    assert scene.pick(1) == {"index": 2, "series": "a", "x": 160, "y": 58, "size": None, "label": "p2",
                             "row": PEOPLE[2]}
    hidden = scatter(series, width=500, height=320, hidden={"a"})
    assert len(marks(hidden, "dot")) == 4 and hidden.legend[0].hidden


def test_bubbles_scale_by_area_and_draw_big_ones_first():
    series, _, _ = xy_input(PEOPLE, "h", "w", size="pop")
    scene = scatter(series, width=600, height=320)
    dots = marks(scene, "dot")
    assert all("bubble" in d.cls for d in dots)
    radii = [d.r for d in dots]
    assert radii == sorted(radii, reverse=True)
    big, small = dots[0], dots[-1]
    assert (big.r - 3) / (small.r - 3) == pytest.approx(math.sqrt(8), rel=0.02)
    assert scene.head[-1] == "Size" and "Bubble" not in scene.summary


def test_scatter_with_nothing():
    scene = scatter([], width=300, height=200)
    assert [m.text for m in scene.marks] == ["No data"]


# --------------------------------------------------------------- sparkline
def test_sparkline_line_gaps_dots_and_summary():
    scene = sparkline([3, 5, None, 4, 8, 6], width=120, height=32, points="minmax")
    assert len(marks(scene, "line")) == 2                   # broken at the gap
    assert len(marks(scene, "spark-dot")) == 3              # min, max, last
    assert scene.summary == "Trend over 6 values: from 3 to 6, low 3, high 8"
    assert scene.tips[4].rows[0][3] == "8" and len(scene.tips) == 6
    rows = [{"day": "Mon", "v": 2}, {"day": "Tue", "v": 4}]
    scene = sparkline(rows, width=100, height=30, x="day", y="v", kind="area", points="none")
    assert marks(scene, "area") and scene.tips[1].title == "Tue" and not marks(scene, "spark-dot")


def test_sparkline_bars_show_negatives():
    scene = sparkline([3, -2, 4], width=90, height=30, kind="bar")
    bars = marks(scene, "bar")
    assert len(bars) == 3 and "danger" in bars[1].style
    assert sparkline([], width=90, height=30).summary == "Trend: no data"


# ------------------------------------------------------------------- gauge
def test_gauge_value_bands_and_clamping():
    g = gauge(72, 0, 100, bands="60:success, 85:warning, 100:danger")
    assert g["dash"] == "72.0 100" and g["color"] == "var(--ui-warning)" and len(g["bands"]) == 3
    assert gauge(150, 0, 100)["frac"] == 1 and gauge(-5, 0, 100)["frac"] == 0
    assert gauge(None)["text"] == "–"
    g = gauge(5, 0, 10, bands=[{"to": 4, "color": "red"}, (10, "#0a0")])
    assert g["color"] == "#0a0" and g["max_text"] == "10"
    half = gauge(50, half=True)
    assert half["view"] == "0 0 200 124.0" and half["min_xy"] == (20.0, 118.0)


def test_gauge_control_is_a_meter(tmp_path):
    _, a, r, tree = app(tmp_path, '<div><ui.Gauge :value="cpu" label="CPU" format="{:.0f}%" needle="true" /></div>',
                        "cpu: float = 70")
    meter = find(tree, lambda node: node.attrs.get("role") == "meter")
    assert (meter.attrs["aria-valuenow"], meter.attrs["aria-valuemax"], meter.attrs["aria-valuetext"]) == \
        ("70", "100", "70%")
    assert find(tree, cls("fill")).attrs["stroke-dasharray"] == "70.0 100"
    assert "rotate(" in find(tree, cls("needle")).attrs["style"]
    a.cpu = 95.5
    tree = cycle(r, tree)
    assert find(tree, cls("fill")).attrs["stroke-dasharray"] == "95.5 100"


# ------------------------------------------------------------------ funnel
STAGES = {"Visited": 1000, "Signed up": 420, "Trial": 150, "Paid": 48}


@pytest.mark.parametrize("shape", ["bars", "funnel"])
def test_funnel_stages_shares_and_conversion(shape):
    scene = funnel(slices_input(STAGES), width=500, height=0, shape=shape)
    stages = marks(scene, "stage")
    assert len(stages) == 4 and scene.height == 4 * 44 + 12
    assert len(marks(scene, "neck")) == (3 if shape == "bars" else 0)
    assert [m.text for m in marks(scene, "stage-value")][1] == "420 · 42%"
    assert [r[2:] for r in scene.tips[2].rows] == [("", "150"), ("Of first", "15%"), ("From previous", "36%"),
                                                   ("Lost", "270")]
    picked = scene.pick(3)
    assert (picked["label"], picked["percent"], picked["conversion"]) == ("Paid", 4.8, 32.0)
    widths = [s.w for s in stages] if shape == "bars" else None
    assert widths is None or widths == sorted(widths, reverse=True)


# --------------------------------------------------------------- waterfall
BRIDGE = [{"label": "Start", "value": 1000, "total": True}, {"label": "Sales", "value": 400},
          {"label": "Costs", "value": -650}, {"label": "Tax", "value": -50}, {"label": "End", "value": None}]


def test_waterfall_running_totals_colours_and_connectors():
    scene = waterfall(slices_input(BRIDGE), width=500, height=300, totals=["End"])
    bars = marks(scene, "bar")
    assert [b.style for b in bars][1:3] == ["fill: var(--ui-success)", "fill: var(--ui-danger)"]
    assert scene.rows == [["Start", "", "1,000"], ["Sales", "+400", "1,400"], ["Costs", "−650", "750"],
                          ["Tax", "−50", "700"], ["End", "", "700"]]
    assert bars[0].y + bars[0].h == pytest.approx(bars[4].y + bars[4].h)   # totals stand on zero
    assert bars[2].y == pytest.approx(bars[1].y, abs=0.2)                  # costs fall from the sales peak
    assert len(marks(scene, "connector")) == 4
    assert [m.text for m in marks(scene, "value-label")] == ["1,000", "+400", "−650", "−50", "700"]
    assert scene.tips[2].rows[1][2:] == ("Running total", "750")
    assert scene.pick(4) == {"index": 4, "label": "End", "value": 700, "total": 700, "is_total": True,
                             "row": BRIDGE[4]}


@pytest.mark.parametrize("seed", range(20))
def test_random_waterfalls_and_funnels_stay_inside(seed):
    rnd = random.Random(seed)
    rows = [{"label": f"s{i}", "value": rnd.uniform(-500, 800), "total": rnd.random() < 0.2}
            for i in range(rnd.randint(1, 15))]
    width, height = rnd.randint(160, 900), rnd.randint(120, 400)
    for scene in (waterfall(slices_input(rows), width=width, height=height),
                  funnel(slices_input([{"label": r["label"], "value": abs(r["value"])} for r in rows]),
                         width=width, height=height)):
        for m in scene.marks:
            for v in (m.x, m.cx, m.x1, m.x2):
                assert v is None or -1 <= v <= width + 1
            for v in (m.y, m.cy, m.y1, m.y2):
                assert v is None or -1 <= v <= scene.height + 1
            assert m.kind != "rect" or (m.w >= 0 and m.h >= 0)


# ---------------------------------------------------------------- controls
def test_dashboard_controls_render_and_select(tmp_path):
    _, a, r, tree = app(tmp_path, """<div>
      <ui.ScatterChart :data="people" x="h" y="w" size="pop" label="name" @select="picked.append(event)" />
      <ui.Sparkline :data="[1, 3, 2, 5]" kind="area" />
      <ui.FunnelChart :data="stages" shape="funnel" />
      <ui.WaterfallChart :data="bridge" totals="End" />
    </div>""", f"people = {PEOPLE!r}\nstages = {STAGES!r}\nbridge = {BRIDGE!r}\npicked: list = []\n")
    scatter_fig, spark_fig, funnel_fig, water_fig = tree[0].children
    dot = find([scatter_fig], cls("dot"))
    r.dispatch(dot.events["click"], {"type": "click"})
    assert a.picked[0]["label"] == "p7" and a.picked[0]["size"] == 8          # biggest drawn first
    plot = find([spark_fig], cls("plot"))
    assert plot.attrs["aria-label"] == "Trend over 4 values: from 1 to 5, low 1, high 5"
    assert find([spark_fig], cls("legend")) is None and find([spark_fig], cls("head")) is None
    assert len([n for n in find([funnel_fig], tag("svg")).children if "stage" in n.attrs.get("class", "").split()]) == 4
    r.dispatch(find([water_fig], cls("band")).events["mouseenter"], {"type": "mouseenter"})
    tree = cycle(r, tree)
    assert "Start" in text([find([tree[0].children[3]], cls("tip"))])
