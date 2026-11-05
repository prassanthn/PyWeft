"""Scatter and bubble charts (numbers on both axes) and sparklines."""

from __future__ import annotations

import math
from dataclasses import dataclass, field as _field

from .axes import value_axis, widest
from .data import _first_key, _keys, color_of, colors_list, field, label_text, number, readable, rows_of
from .scales import LinearScale, fmt_value
from .scene import LegendItem, Mark, Scene, Tip, n
from .stats import linear_fit


@dataclass
class Point:
    x: float
    y: float
    size: float | None = None
    name: str = ""
    row: object = None
    index: int = 0


@dataclass
class XYSeries:
    key: str
    label: str
    color: str
    points: list = _field(default_factory=list)


def xy_input(data, x="", y="", group="", size="", label="", colors=()):
    """([XYSeries], x field, [y fields]). One series per y field, or with
    ``group``, one per value of that field (plotting the first y)."""
    rows = rows_of(data)
    palette = colors_list(colors)
    x = x or _first_key(rows, want_number=True)
    ys = [s.strip() for s in y.split(",") if s.strip()] if isinstance(y, str) else list(y or [])
    if not ys and rows:
        ys = [k for k in _keys(rows[0]) if k not in (x, size, group, label)
              and number(field(rows[0], k)) is not None and not isinstance(field(rows[0], k), str)][:1]

    def own(i):
        return color_of(palette[i] if i < len(palette) else None, i)

    def point(i, row, key):
        xv, yv = number(field(row, x)), number(field(row, key))
        if xv is None or yv is None:
            return None
        return Point(xv, yv, number(field(row, size)) if size else None,
                     label_text(field(row, label)) if label else "", row, i)

    out = []
    if group and ys:
        buckets = {}
        for i, row in enumerate(rows):
            name = label_text(field(row, group))
            if name not in buckets:
                buckets[name] = XYSeries(name, name or "(none)", own(len(buckets)))
            p = point(i, row, ys[0])
            if p:
                buckets[name].points.append(p)
        out = list(buckets.values())
    else:
        for j, key in enumerate(ys):
            series = XYSeries(str(key), readable(key), own(j))
            series.points = [p for i, row in enumerate(rows) if (p := point(i, row, key))]
            out.append(series)
    return out, x, ys


def scatter(series, *, width, height, hidden=frozenset(), x_name="x", y_name="y", size_name="Size",
            x_label="", y_label="", x_min=None, x_max=None, y_min=None, y_max=None, grid=True, fmt=None,
            x_fmt=None, tick_fmt=None, x_tick_fmt=None, trend=False, radius=4.0, kind="Scatter",
            empty="No data") -> Scene:
    width, height = max(float(width), 160.0), max(float(height), 120.0)
    shown = [s for s in series if s.key not in hidden]
    pts = [(s, p) for s in shown for p in s.points]
    sized = any(p.size is not None for _, p in pts)
    scene = Scene(width, height)
    scene.legend = [LegendItem(s.key, s.label, s.color, s.key in hidden, "dot") for s in series]
    scene.head = ["Series", x_label or x_name, y_label or y_name] + ([size_name] if sized else [])
    scene.rows = [[s.label, fmt_value(p.x, x_fmt), fmt_value(p.y, fmt)] + ([fmt_value(p.size)] if sized else [])
                  for s, p in pts[:1000]]
    scene.summary = f"{kind} chart of {len(pts)} {'point' if len(pts) == 1 else 'points'}" + \
        (f" in {len(shown)} series" if len(shown) > 1 else "")

    def payload(i, key=None):
        s, p = pts[max(0, min(i, len(pts) - 1))]
        return {"index": p.index, "series": s.key, "x": p.x, "y": p.y, "size": p.size, "label": p.name,
                "row": p.row}

    scene.payload = payload
    if not pts:
        scene.marks.append(Mark("text", "empty", "empty", x=n(width / 2), y=n(height / 2), text=empty,
                                anchor="middle", baseline="middle"))
        return scene

    X = value_axis([p.x for _, p in pts], max(2, int(width / 90)), x_min, x_max, x_tick_fmt, pad=0.04)
    Y = value_axis([p.y for _, p in pts], max(2, int(height / 50)), y_min, y_max, tick_fmt, pad=0.06)
    px0 = widest(Y.texts) + 10 + (18 if y_label else 0)
    px1 = width - max(14.0, widest(X.texts[-1:]) / 2 + 4)
    py0, py1 = 10.0, height - 24 - (18 if x_label else 0)
    xs, ys = LinearScale((X.lo, X.hi), (px0, px1)), LinearScale((Y.lo, Y.hi), (py1, py0))
    marks = scene.marks
    for j, (v, text) in enumerate(zip(X.values, X.texts)):
        p = n(xs(v))
        if grid:
            marks.append(Mark("line", f"gx{j}", "grid", x1=p, x2=p, y1=n(py0), y2=n(py1)))
        marks.append(Mark("text", f"tx{j}", "tick", x=p, y=n(py1 + 15), text=text, anchor="middle"))
    for j, (v, text) in enumerate(zip(Y.values, Y.texts)):
        p = n(ys(v))
        if grid:
            marks.append(Mark("line", f"gy{j}", "grid", x1=n(px0), x2=n(px1), y1=p, y2=p))
        marks.append(Mark("text", f"ty{j}", "tick", x=n(px0 - 8), y=p, text=text, anchor="end", baseline="middle"))
    marks.append(Mark("line", "axis", "axis", x1=n(px0), x2=n(px1), y1=n(py1), y2=n(py1)))
    if x_label:
        marks.append(Mark("text", "title-bottom", "axis-title", x=n((px0 + px1) / 2), y=n(height - 6),
                          text=x_label, anchor="middle"))
    if y_label:
        mid = n((py0 + py1) / 2)
        marks.append(Mark("text", "title-side", "axis-title", x=12, y=mid, text=y_label, anchor="middle",
                          baseline="middle", transform=f"rotate(-90 12 {mid})"))

    top = max((p.size for _, p in pts if p.size is not None and p.size > 0), default=0.0)
    biggest = max(8.0, min(40.0, (px1 - px0) / 18))

    def r_of(p):
        if p.size is None or top <= 0:
            return float(radius)
        return 3.0 + math.sqrt(max(p.size, 0.0) / top) * (biggest - 3.0)  # area, not radius, shows size

    if trend:
        for s in shown:
            fit = linear_fit([p.x for p in s.points], [p.y for p in s.points])
            if not fit:
                continue
            a, b = min(p.x for p in s.points), max(p.x for p in s.points)
            x1, y1, x2, y2 = xs(a), ys.clamp(fit(a)), xs(b), ys.clamp(fit(b))
            marks.append(Mark("line", f"trend|{s.key}", "trend", style=f"stroke: {s.color}",
                              x1=n(x1), y1=n(y1), x2=n(x2), y2=n(y2)))
            marks.append(Mark("text", f"r2|{s.key}", "trend-label", style=f"fill: {s.color}", x=n(x2 - 2),
                              y=n(y2 - 6), text=f"R² {fit.r2:.2f}", anchor="end"))
    order = sorted(range(len(pts)), key=lambda i: -r_of(pts[i][1]))  # big bubbles below small ones
    for i in order:
        s, p = pts[i]
        style = f"fill: {s.color}; stroke: {s.color}"
        marks.append(Mark("circle", f"d{i}", "dot bubble hit" if sized else "dot hit", style=style,
                          cx=n(xs.clamp(p.x)), cy=n(ys.clamp(p.y)), r=n(r_of(p)), hit=i, series=s.key))
    for i, (s, p) in enumerate(pts):
        cx, cy, r = xs.clamp(p.x), ys.clamp(p.y), r_of(p)
        rows = [("x", s.color, x_label or x_name, fmt_value(p.x, x_fmt)),
                ("y", None, y_label or y_name, fmt_value(p.y, fmt))]
        if p.size is not None:
            rows.append(("size", None, size_name, fmt_value(p.size)))
        if p.name and len(shown) > 1:
            rows.append(("series", None, "Series", s.label))
        ring = Mark("circle", "hover-ring", "hover-ring", style=f"stroke: {s.color}", cx=n(cx), cy=n(cy), r=n(r + 4))
        right = cx < width / 2
        scene.tips.append(Tip(p.name or s.label, rows, n(cx + r if right else cx - r), n(cy),
                              "right mid" if right else "left mid", [ring]))
    return scene


def sparkline(data, *, width, height, y="", x="", kind="line", color=None, fmt=None, points="last",
              name="Trend") -> Scene:
    """A word-sized chart: no axes, no legend, just the shape of the values."""
    width, height = max(float(width), 40.0), max(float(height), 16.0)
    rows = rows_of(data)
    if rows and all(isinstance(r, (int, float)) or r is None for r in rows):
        values, labels = [number(r) for r in rows], [""] * len(rows)
    else:
        y = y or _first_key(rows, want_number=True)
        values = [number(field(r, y)) for r in rows]
        labels = [label_text(field(r, x)) if x else "" for r in rows]
    color = color_of(color, 0)
    count = len(values)
    defined = [v for v in values if v is not None]
    scene = Scene(width, height)
    scene.head, scene.rows = ["", "Value"], [[labels[i] or str(i + 1), fmt_value(v, fmt)] for i, v in enumerate(values)]
    if not defined:
        scene.summary = f"{name}: no data"
        return scene
    lo, hi = min(defined), max(defined)
    scene.summary = (f"{name} over {count} values: from {fmt_value(defined[0], fmt)} to "
                     f"{fmt_value(defined[-1], fmt)}, low {fmt_value(lo, fmt)}, high {fmt_value(hi, fmt)}")
    scene.payload = lambda i, key=None: {"index": i, "label": labels[i] or None, "value": values[i]}
    bars = kind == "bar"
    if bars:
        lo, hi = min(lo, 0.0), max(hi, 0.0)
    if lo == hi:
        lo, hi = lo - 1, hi + 1
    pad = 4.0
    ys = LinearScale((lo, hi), (height - pad, pad))
    if bars or count == 1:
        step = (width - 2) / count
        xs = [1 + step * (i + 0.5) for i in range(count)]
    else:
        step = (width - 2 * pad) / (count - 1)
        xs = [pad + step * i for i in range(count)]
    marks = scene.marks
    for i in range(count):
        marks.append(Mark("rect", f"h{i}", "hit band", x=n(xs[i] - step / 2), y=0, w=n(step), h=n(height), hit=i))
    if bars:
        zero = ys(0.0)
        for i, v in enumerate(values):
            if v is None:
                continue
            top_, bottom = sorted((ys(v), zero))
            fill = color if v >= 0 else "var(--ui-danger, #d1242f)"
            marks.append(Mark("rect", f"b{i}", "bar", style=f"fill: {fill}", x=n(xs[i] - step * 0.4),
                              y=n(top_), w=n(step * 0.8), h=n(max(bottom - top_, 1.0)), rx=1))
    else:
        runs, run = [], []
        for i, v in enumerate(values):
            if v is None:
                if run:
                    runs.append(run)
                run = []
            else:
                run.append(i)
        if run:
            runs.append(run)
        for k, run in enumerate(runs):
            line = " ".join(("M" if j == 0 else "L") + f"{n(xs[i])},{n(ys(values[i]))}" for j, i in enumerate(run))
            if kind == "area":
                floor = ys(max(lo, 0.0) if lo >= 0 else lo)
                marks.append(Mark("path", f"a{k}", "area", style=f"fill: {color}",
                                  d=f"{line} L{n(xs[run[-1]])},{n(floor)} L{n(xs[run[0]])},{n(floor)} Z"))
            marks.append(Mark("path", f"p{k}", "line spark", style=f"stroke: {color}", d=line))
        wanted = {"last": [_last(values)], "all": [i for i, v in enumerate(values) if v is not None],
                  "minmax": [values.index(min(defined)), values.index(max(defined)), _last(values)]}.get(points, [])
        for i in dict.fromkeys(wanted):
            marks.append(Mark("circle", f"o{i}", "spark-dot", style=f"fill: {color}", cx=n(xs[i]),
                              cy=n(ys(values[i])), r=2.5))
    for i, v in enumerate(values):
        light = []
        if v is not None and not bars:
            light.append(Mark("circle", "hover", "hover-point", style=f"fill: {color}", cx=n(xs[i]),
                              cy=n(ys(v)), r=3.5))
        elif bars:
            light.append(Mark("rect", "hover-band", "hover-band", x=n(xs[i] - step / 2), y=0, w=n(step), h=n(height)))
        right = xs[i] < width / 2
        scene.tips.append(Tip(labels[i], [("v", color, "", fmt_value(v, fmt))], n(xs[i] + (4 if right else -4)),
                              n(height / 2), "right mid" if right else "left mid", light))
    return scene


def _last(values):
    return max(i for i, v in enumerate(values) if v is not None)
