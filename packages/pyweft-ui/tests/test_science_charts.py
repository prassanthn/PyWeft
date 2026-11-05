"""Data-science charts and the statistics under them."""

import datetime as dt
import math
import random

import pytest

from pyweft_ui.charting import (
    boxplot, calendar, candles_input, candlestick, cartesian, cartesian_input, correlation, days_input, groups_input,
    heat_input, heatmap, histogram, kde, links_input, moving_average, pearson, quantile, sankey, spearman,
    squarify, summary, tree_input, treemap,
)
from pyweft_ui.charting.stats import bin_counts, bin_edges, ranks
from test_controls import app, cls, cycle, find, tag, text


def marks(scene, css):
    return [m for m in scene.marks if css in m.cls.split()]


# ------------------------------------------------------------------- stats
def test_quantiles_match_the_usual_method():
    data = sorted([7, 1, 3, 9, 4, 2])
    assert [quantile(data, q) for q in (0, 0.25, 0.5, 0.75, 1)] == [1, 2.25, 3.5, 6.25, 9]


def test_summary_finds_whiskers_and_outliers():
    s = summary([1, 2, 3, 4, 5, 6, 7, 8, 9, 100])
    assert (s.q1, s.median, s.q3, s.low, s.high, s.outliers) == (3.25, 5.5, 7.75, 1, 9, [100])
    assert s.mean == 14.5 and s.count == 10 and s.largest == 100


def test_kde_integrates_to_one():
    values = [random.Random(1).gauss(0, 1) for _ in range(200)]
    xs = [-6 + 12 * k / 599 for k in range(600)]
    area = sum(kde(values, xs)) * (12 / 599)
    assert area == pytest.approx(1, abs=0.01)


def test_bins_are_round_and_count_everything():
    values = [random.Random(2).uniform(3, 97) for _ in range(500)]
    edges = bin_edges(values)
    step = edges[1] - edges[0]
    assert all(math.isclose(b - a, step) for a, b in zip(edges, edges[1:]))
    assert edges[0] <= min(values) and edges[-1] >= max(values) and step in (1, 2, 5, 10, 20)
    assert sum(bin_counts(values, edges)) == 500
    assert bin_edges([1, 2, 3, 10], 3) == [0, 2, 4, 6, 8, 10] and bin_counts([0, 5, 10], [0, 5, 10]) == [1, 2]
    assert bin_edges([1, 9], "width:4") == [0, 4, 8, 12] and bin_edges([5, 5]) == [4.5, 5.5]


def test_correlations_and_ranks():
    xs = [1, 2, 3, 4, 5]
    assert pearson(xs, [2, 4, 6, 8, 10]) == pytest.approx(1)
    assert pearson(xs, [5, 4, 3, 2, 1]) == pytest.approx(-1)
    assert spearman(xs, [1, 4, 9, 16, 25]) == pytest.approx(1)      # rising, not straight
    assert pearson(xs, [1, 4, 9, 16, 25]) < 1
    assert ranks([10, 20, 20, None, 5]) == [2, 3.5, 3.5, None, 1]
    assert pearson([1, 1], [2, 3]) is None


def test_moving_average():
    assert moving_average([1, 2, 3, 4, None, 6], 2) == [None, 1.5, 2.5, 3.5, None, None]


# ---------------------------------------------------------- distributions
GROUPS = [{"team": "a", "t": v} for v in [3, 4, 4, 5, 5, 5, 6, 6, 7, 20]] + \
         [{"team": "b", "t": v} for v in [8, 9, 9, 10, 11, 12]]


def test_groups_from_every_shape():
    assert [(g.key, len(g.values)) for g in groups_input(GROUPS, "t", "team")] == [("a", 10), ("b", 6)]
    assert [g.label for g in groups_input({"x": [1, 2], "y": [3]})] == ["x", "y"]
    assert groups_input([1, 2, None, 3])[0].values == [1, 2, 3]


def test_histogram_bins_tips_curve_and_mean():
    groups = groups_input(GROUPS, "t", "team")
    scene = histogram(groups, width=600, height=300, bins=4, curve=True, show_mean=True)
    assert len(scene.tips) == len(marks(scene, "band")) == 4
    assert sum(sum(c for c in scene.pick(i)["counts"].values()) for i in range(4)) == 16
    assert len(marks(scene, "line")) == 2 and len(marks(scene, "mean-line")) == 2
    assert all("layered" in b.cls for b in marks(scene, "bin"))
    first = scene.tips[0]
    assert first.title == "0 – 5" and first.rows[0][2:] == ("a", "3 (30%)")
    one = histogram(groups[:1], width=600, height=300, density=True, cumulative=True)
    assert one.tips[-1].rows[0][2:] == ("Density", "1")      # the running share ends at all of them


def test_box_and_violin():
    groups = groups_input(GROUPS, "t", "team")
    scene = boxplot(groups, width=600, height=300)
    assert len(marks(scene, "box")) == 2 and len(marks(scene, "median")) == 2
    assert len(marks(scene, "point")) == 1                   # the 20 in team a
    assert dict((r[2], r[3]) for r in scene.tips[0].rows)["Median"] == "5"
    assert scene.pick(1)["q3"] == quantile([8, 9, 9, 10, 11, 12], 0.75)
    violin = boxplot(groups, width=600, height=300, violin=True, points="all", horizontal=True)
    assert len(marks(violin, "violin")) == 2 and len(marks(violin, "point")) == 16


# ----------------------------------------------------------------- matrix
def test_heat_input_shapes():
    rows = [{"day": "Mon", "hour": "9", "n": 2}, {"day": "Mon", "hour": "9", "n": 3}, {"day": "Tue", "hour": "10", "n": 1}]
    assert heat_input(rows, "hour", "day", "n") == (["9", "10"], ["Mon", "Tue"], [[5, None], [None, 1]])
    assert heat_input({"r1": {"a": 1}, "r2": {"b": 2}}) == (["a", "b"], ["r1", "r2"], [[1, None], [None, 2]])
    assert heat_input([[1, 2], [3]], x_labels=["p", "q"])[2] == [[1, 2], [3, None]]


def test_heatmap_cells_scale_and_auto_height():
    scene = heatmap(["a", "b", "c"], ["x", "y"], [[0, 5, 10], [None, 2, 8]], width=400, height=0, labels=True)
    cells = marks(scene, "cell")
    assert len(cells) == 6 and len(scene.tips) == 6 and scene.height > 0
    assert "100%" in cells[2].style and "8%" in cells[0].style and "subtle" in cells[3].style
    assert scene.pick(4) == {"index": 4, "x": "b", "y": "y", "value": 2, "row": 1, "column": 1}
    assert len([m for m in scene.marks if m.key.startswith("lg") and m.kind == "rect"]) == 24


def test_correlation_matrix_is_diverging_and_masks_the_upper_half():
    rows = [{"a": i, "b": 2 * i, "c": -i} for i in range(10)]
    names, matrix = correlation(rows)
    assert names == ["A", "B", "C"] and matrix[0][1] == pytest.approx(1) and matrix[0][2] == pytest.approx(-1)
    scene = heatmap(names, names, matrix, width=300, height=0, diverging=True, lo=-1, hi=1, labels=True,
                    fmt=".2f", skip=lambda i, j: j > i)
    assert len(marks(scene, "cell")) == 6
    assert [m.text for m in marks(scene, "cell-label")][-1] == "1.00"
    assert "--ui-info" in marks(scene, "cell")[3].style      # -1: the low colour


def test_calendar_days_levels_and_narrow_width():
    days = days_input([{"when": "2026-03-02", "n": 4}, {"when": dt.date(2026, 3, 2), "n": 1},
                       {"when": dt.datetime(2026, 3, 9, 14, 0), "n": 9}])
    assert days == {dt.date(2026, 3, 2): 5, dt.date(2026, 3, 9): 9}
    scene = calendar(days, width=900)
    assert len(scene.tips) == 365 and scene.tips[-1].title == "Mon 9 Mar 2026"
    assert scene.pick(len(scene.tips) - 1) == {"index": 364, "date": dt.date(2026, 3, 9), "value": 9}
    assert any(m.text == "Mar" for m in scene.marks)
    narrow = calendar(days, width=320)
    assert len(narrow.tips) < 365 and narrow.tips[-1].title == "Mon 9 Mar 2026"
    assert all(m.x + (m.w or 0) <= 320 for m in narrow.marks if m.kind == "rect")


# --------------------------------------------------------------- finance
def prices(count=30):
    rnd, out, price = random.Random(4), [], 100.0
    for i in range(count):
        close = price + rnd.uniform(-3, 3)
        out.append({"Date": f"d{i}", "Open": price, "High": max(price, close) + 1, "Low": min(price, close) - 1,
                    "Close": close, "Volume": 1000 + i})
        price = close
    return out


def test_candles_volume_and_averages():
    rows = prices()
    candles = candles_input(rows)
    assert candles[0].open == 100 and candles[0].volume == 1000
    scene = candlestick(candles, width=700, height=360, averages=[5])
    assert len(marks(scene, "candle")) == 30 and len(marks(scene, "volume")) == 30
    assert [i.key for i in scene.legend] == ["sma5", "volume"]
    rows_ = dict((r[0], r[3]) for r in scene.tips[10].rows)
    assert rows_["change"].endswith("%") and "sma5" in rows_
    rising = [c for c in candles if c.close >= c.open]
    assert {m.style.split(";")[0] for m in marks(scene, "candle")} == {"fill: var(--ui-success)", "fill: var(--ui-danger)"} \
        or not rising
    quiet = candlestick(candles, width=700, height=360, hidden={"volume"}, style="ohlc")
    assert not marks(quiet, "volume") and not marks(quiet, "candle") and len(marks(quiet, "wick")) == 90


# -------------------------------------------------------------- hierarchy
def test_squarify_fills_the_box_with_squarish_tiles():
    rects = squarify([6, 6, 4, 3, 2, 2, 1], 0, 0, 600, 400)
    assert sum(w * h for _, _, w, h in rects) == pytest.approx(600 * 400)
    assert max(max(w / h, h / w) for _, _, w, h in rects) < 3
    assert all(x >= -1e-9 and y >= -1e-9 and x + w <= 600 + 1e-6 and y + h <= 400 + 1e-6 for x, y, w, h in rects)


def test_treemap_from_paths_and_nested_dicts():
    rows = [{"region": "EU", "country": "FR", "v": 30}, {"region": "EU", "country": "DE", "v": 20},
            {"region": "AS", "country": "JP", "v": 50}, {"region": "EU", "country": "FR", "v": 10}]
    roots = tree_input(rows, value="v", path="region, country")
    assert [(r.label, [c.label for c in r.children]) for r in roots] == [("EU", ["FR", "DE"]), ("AS", ["JP"])]
    scene = treemap(roots, width=600, height=360)
    titles = [t.title for t in scene.tips]
    assert sorted(titles) == ["AS › JP", "EU › DE", "EU › FR"] and len(marks(scene, "tm-group")) == 2
    fr = titles.index("EU › FR")
    assert dict((r[2], r[3]) for r in scene.tips[fr].rows) == {"": "40", "Of all": "36.4%", "Of EU": "66.7%"}
    assert scene.pick(fr)["path"] == ["EU", "FR"]
    flat = treemap(tree_input({"a": 3, "b": {"c": 1, "d": 2}}), width=400, height=300, depth=1)
    assert sorted(t.title for t in flat.tips) == ["a", "b"]


# ------------------------------------------------------------------- flow
def test_sankey_columns_widths_and_payloads():
    links = links_input([("Pay", "Budget", 5000), ("Budget", "Rent", 2000), ("Budget", "Saved", 3000),
                         ("Saved", "Stocks", 1000), ("x", "x", 5)])
    assert len(links) == 4                                    # a self-loop is left out
    scene = sankey(links, width=700, height=300)
    nodes = {m.key: m for m in marks(scene, "node")}
    xs = sorted({m.x for m in nodes.values()})
    assert len(xs) == 4 and nodes["n0"].x == xs[0] and nodes["n2"].x == xs[2] and nodes["n4"].x == xs[3]
    justified = {m.key: m for m in marks(sankey(links, width=700, height=300, align="justify"), "node")}
    assert justified["n2"].x == justified["n4"].x == xs[3]  # every end on the right
    assert nodes["n1"].h == pytest.approx(nodes["n0"].h, abs=0.2)  # Budget passes on all it gets
    assert scene.pick(1) == {"kind": "node", "index": 1, "label": "Budget", "value": 5000, "in": 5000, "out": 5000}
    assert scene.pick(5)["source"] == "Pay" and scene.tips[5 + 2].title == "Budget → Saved"
    assert all(0 <= m.y and m.y + m.h <= 300.5 for m in nodes.values())


# --------------------------------------------- bands, error bars, trends
def test_bands_error_bars_and_trends():
    rows = [{"m": i, "v": 10 + i, "lo": 8 + i, "hi": 13 + i, "e": 2} for i in range(5)]
    cats, series, _ = cartesian_input(rows, "m", "v", [{"key": "v", "lower": "lo", "upper": "hi", "trend": True}],
                                      "line")
    scene = cartesian(cats, series, width=600, height=300)
    assert len(marks(scene, "band-fill")) == 1 and len(marks(scene, "trend")) == 1
    assert scene.tips[0].rows[0][3] == "10 (8 – 13)"
    cats, series, _ = cartesian_input(rows, "m", "v", [{"key": "v", "error": "e"}])
    bars = cartesian(cats, series, width=600, height=300)
    assert len(marks(bars, "whisker")) == 15 and bars.tips[1].rows[0][3] == "11 (9 – 13)"
    cats, series, _ = cartesian_input(rows, "m", "v", [{"key": "v", "error": 0.5}])
    assert cartesian(cats, series, width=600, height=300).tips[0].rows[0][3] == "10 (9.5 – 10.5)"


# --------------------------------------------------------------- controls
def test_science_controls_render(tmp_path):
    code = (f"groups = {GROUPS!r}\nprices = {prices(12)!r}\npicked: list = []\n"
            "days = {'2026-01-05': 3, '2026-01-06': 1}\n")
    _, a, r, tree = app(tmp_path, """<div>
      <ui.Histogram :data="groups" y="t" group="team" curve="true" />
      <ui.BoxPlot :data="groups" y="t" group="team" violin="true" @select="picked.append(event)" />
      <ui.Heatmap :data="[[1, 2], [3, 4]]" :x_labels="['a', 'b']" :y_labels="['x', 'y']" labels="true" />
      <ui.CorrelationMatrix :data="[{'p': 1, 'q': 2}, {'p': 2, 'q': 5}, {'p': 3, 'q': 5.5}]" triangle="lower" />
      <ui.CandlestickChart :data="prices" averages="3" />
      <ui.Treemap :data="{'EU': {'FR': 3, 'DE': 2}, 'AS': 4}" />
      <ui.SankeyChart :data="[('a', 'b', 3), ('a', 'c', 1)]" />
      <ui.CalendarHeatmap :data="days" />
    </div>""", code)
    figures = tree[0].children
    assert len(figures) == 8 and all(find([f], tag("svg")) is not None for f in figures)
    band = find([figures[1]], cls("band"))
    r.dispatch(band.events["click"], {"type": "click"})
    assert a.picked[0]["label"] == "a" and a.picked[0]["median"] == 5
    assert "Correlation matrix" in find([figures[3]], cls("plot")).attrs["aria-label"]
    r.dispatch(find([figures[7]], cls("day")).events["mouseenter"], {"type": "mouseenter"})
    tree = cycle(r, tree)
    assert find([tree[0].children[7]], cls("tip")) is not None
