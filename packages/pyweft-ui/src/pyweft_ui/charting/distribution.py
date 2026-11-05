"""How values are spread: histograms, box plots and violins."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field as _field

from .axes import category_labels, cut, empty, titles, value_axis, widest, x_ticks, y_ticks
from .data import _first_key, color_of, colors_list, field, label_text, number, readable, rows_of
from .scales import LinearScale, fmt_value
from .scene import LegendItem, Mark, Scene, Tip, n
from .stats import bin_counts, bin_edges, kde, mean, summary


@dataclass
class Group:
    key: str
    label: str
    color: str
    values: list = _field(default_factory=list)


def groups_input(data, y="", group="", colors=()) -> list[Group]:
    """Groups of numbers from a list of numbers, a {name: [numbers]} dict,
    or rows: one group per field in ``y``, or per value of ``group``."""
    palette = colors_list(colors)

    def paint(i):
        return color_of(palette[i] if i < len(palette) else None, i)

    if isinstance(data, Mapping) and data and all(not isinstance(v, (str, bytes, Mapping)) and hasattr(v, "__iter__")
                                                  for v in data.values()) and not y and not group:
        return [Group(str(k), str(k), paint(i), [number(v) for v in vals if number(v) is not None])
                for i, (k, vals) in enumerate(data.items())]
    rows = rows_of(data)
    if rows and all(isinstance(r, (int, float)) or r is None for r in rows):
        return [Group("values", "Values", paint(0), [float(r) for r in rows if r is not None])]
    fields = [s.strip() for s in y.split(",") if s.strip()] if isinstance(y, str) else list(y or [])
    fields = fields or [k for k in [_first_key(rows, want_number=True)] if k is not None]
    if group and fields:
        out = {}
        for row in rows:
            name = label_text(field(row, group))
            if name not in out:
                out[name] = Group(name, name or "(none)", paint(len(out)))
            v = number(field(row, fields[0]))
            if v is not None:
                out[name].values.append(v)
        return list(out.values())
    return [Group(str(f), readable(f), paint(i), [v for r in rows if (v := number(field(r, f))) is not None])
            for i, f in enumerate(fields)]


def histogram(groups, *, width, height, hidden=frozenset(), bins=None, density=False, cumulative=False,
              curve=False, show_mean=False, fmt=None, tick_fmt=None, x_tick_fmt=None, x_label="", y_label="",
              kind="Histogram", empty_text="No data") -> Scene:
    width, height = max(float(width), 160.0), max(float(height), 120.0)
    shown = [g for g in groups if g.key not in hidden and g.values]
    scene = Scene(width, height)
    scene.legend = [LegendItem(g.key, g.label, g.color, g.key in hidden) for g in groups] if len(groups) > 1 else []
    values = [v for g in shown for v in g.values]
    scene.summary = f"{kind} of {len(values)} values" + (f" in {len(shown)} groups" if len(shown) > 1 else "")
    if not values:
        scene.payload = lambda i, key=None: {"index": i}
        return empty(scene, empty_text)
    edges = bin_edges(values, bins)
    count = len(edges) - 1
    heights = {}
    for g in shown:
        counts = bin_counts(g.values, edges)
        if cumulative:
            run, acc = [], 0
            for c in counts:
                acc += c
                run.append(acc)
            counts = run
        if density:
            total = len(g.values)
            hs = [c / total if cumulative else c / (total * (edges[i + 1] - edges[i])) for i, c in enumerate(counts)]
        else:
            hs = [float(c) for c in counts]
        heights[g.key] = (counts, hs)
    curves = {}
    if curve and not cumulative:
        lo, hi = edges[0], edges[-1]
        xs_ = [lo + (hi - lo) * k / 119 for k in range(120)]
        avg_width = (hi - lo) / count
        for g in shown:
            dens = kde(g.values, xs_)
            curves[g.key] = list(zip(xs_, dens if density else [d * len(g.values) * avg_width for d in dens]))
    Y = value_axis([h for _, hs in heights.values() for h in hs] + [p[1] for c in curves.values() for p in c],
                   max(2, int((height - 50) / 45)), fmt=tick_fmt, zero=True)
    X = value_axis([edges[0], edges[-1]], max(2, int(width / 90)), edges[0], edges[-1], x_tick_fmt)
    px0 = widest(Y.texts) + 10 + (18 if y_label else 0)
    px1 = width - max(14.0, widest(X.texts[-1:]) / 2 + 4)
    py0, py1 = 10.0 + (14 if show_mean else 0), height - 24 - (18 if x_label else 0)
    xs, ys = LinearScale((edges[0], edges[-1]), (px0, px1)), LinearScale((Y.lo, Y.hi), (py1, py0))
    marks = scene.marks
    y_ticks(marks, Y, ys, px0, px1)
    x_ticks(marks, X, xs, py0, py1)
    marks.append(Mark("line", "axis", "axis", x1=n(px0), x2=n(px1), y1=n(py1), y2=n(py1)))
    titles(marks, width, height, px0, px1, py0, py1, x_label, y_label or ("Density" if density else "Count"))
    for i in range(count):
        a, b = xs(edges[i]), xs(edges[i + 1])
        marks.append(Mark("rect", f"h{i}", "hit band", x=n(a), y=n(py0), w=n(b - a), h=n(py1 - py0), hit=i))
    layered = len(shown) > 1
    for g in shown:
        for i, h in enumerate(heights[g.key][1]):
            if h <= 0:
                continue
            a, b = xs(edges[i]), xs(edges[i + 1])
            top = ys(h)
            marks.append(Mark("rect", f"b{i}|{g.key}", "bin layered" if layered else "bin",
                              style=f"fill: {g.color}", x=n(a + 0.5), y=n(top), w=n(max(b - a - 1, 0.5)),
                              h=n(py1 - top)))
    for g in shown:
        if g.key in curves:
            d = " ".join(("M" if k == 0 else "L") + f"{n(xs(x))},{n(ys.clamp(y))}" for k, (x, y) in enumerate(curves[g.key]))
            marks.append(Mark("path", f"kde|{g.key}", "line", style=f"stroke: {g.color}", d=d))
        if show_mean:
            m = mean(g.values)
            x = n(xs(m))
            marks.append(Mark("line", f"mean|{g.key}", "mean-line", style=f"stroke: {g.color}", x1=x, x2=x,
                              y1=n(py0), y2=n(py1)))
            marks.append(Mark("text", f"meant|{g.key}", "mean-label", style=f"fill: {g.color}", x=x, y=n(py0 - 4),
                              text=f"mean {fmt_value(round(m, 2), fmt)}", anchor="middle"))
    for i in range(count):
        a, b = edges[i], edges[i + 1]
        rows = []
        for g in shown:
            counts, hs = heights[g.key]
            text = f"{counts[i]:,}" + (f" ({counts[i] / len(g.values) * 100:.0f}%)" if not cumulative else "")
            if density:
                text = f"{hs[i]:.3g}"
            rows.append((g.key, g.color, g.label if layered else ("Density" if density else "Count"), text))
        light = [Mark("rect", "hover-band", "hover-band", x=n(xs(a)), y=n(py0), w=n(xs(b) - xs(a)), h=n(py1 - py0))]
        right = xs(b) < width / 2
        scene.tips.append(Tip(f"{fmt_value(a, fmt)} – {fmt_value(b, fmt)}", rows, n(xs(b) if right else xs(a)),
                              n(py0), "right" if right else "left", light))
    scene.head = ["From", "To", *[g.label for g in shown]]
    scene.rows = [[fmt_value(edges[i], fmt), fmt_value(edges[i + 1], fmt),
                   *[str(heights[g.key][0][i]) for g in shown]] for i in range(count)]
    scene.payload = lambda i, key=None: {"index": i, "start": edges[i], "end": edges[i + 1],
                                         "counts": {g.key: heights[g.key][0][i] for g in shown}}
    scene.summary += f", {count} bins from {fmt_value(edges[0], fmt)} to {fmt_value(edges[-1], fmt)}"
    return scene


def boxplot(groups, *, width, height, hidden=frozenset(), horizontal=False, violin=False, points="outliers",
            show_mean=True, fmt=None, tick_fmt=None, x_label="", y_label="", kind="Box plot",
            empty_text="No data") -> Scene:
    width, height = max(float(width), 160.0), max(float(height), 120.0)
    shown = [(g, summary(g.values)) for g in groups if g.key not in hidden and g.values]
    scene = Scene(width, height)
    scene.legend = []
    scene.head = ["", "n", "Min", "Q1", "Median", "Q3", "Max", "Mean"]
    scene.rows = [[g.label, str(s.count), *[fmt_value(round(v, 4), fmt) for v in
                   (s.smallest, s.q1, s.median, s.q3, s.largest, s.mean)]] for g, s in shown]
    scene.summary = f"{'Violin' if violin else 'Box'} plot of {len(shown)} {'group' if len(shown) == 1 else 'groups'}"

    def payload(i, key=None):
        g, s = shown[max(0, min(i, len(shown) - 1))]
        return {"index": i, "label": g.label, "count": s.count, "min": s.smallest, "q1": s.q1, "median": s.median,
                "q3": s.q3, "max": s.largest, "mean": s.mean, "outliers": list(s.outliers)}

    scene.payload = payload
    if not shown:
        return empty(scene, empty_text)
    names = [g.label for g, _ in shown]
    values = [v for g, _ in shown for v in g.values]
    V = value_axis(values, max(2, int(((width * 0.7) if horizontal else (height - 50)) / (90 if horizontal else 45))),
                   fmt=tick_fmt, pad=0.05)
    if horizontal:
        room = min(widest(names), width * 0.3)
        px0 = room + 12 + (18 if x_label else 0)
        px1 = width - max(14.0, widest(V.texts[-1:]) / 2 + 4)
        py0, py1 = 10.0, height - 24 - (18 if y_label else 0)
        vs = LinearScale((V.lo, V.hi), (px0, px1))
        c0, c1 = py0, py1
    else:
        px0 = widest(V.texts) + 10 + (18 if y_label else 0)
        px1 = width - 14
        py0, py1 = 10.0, height - 24 - (18 if x_label else 0)
        vs = LinearScale((V.lo, V.hi), (py1, py0))
        c0, c1 = px0, px1
    step = (c1 - c0) / len(shown)
    centers = [c0 + step * (i + 0.5) for i in range(len(shown))]
    box = min(step * 0.45, 56.0)
    reach = step * 0.42

    def at(u, v):
        return (vs(v), u) if horizontal else (u, vs(v))

    def line(key, cls, u0, v0, u1, v1, style=None):
        (x1, y1), (x2, y2) = at(u0, v0), at(u1, v1)
        return Mark("line", key, cls, style=style, x1=n(x1), y1=n(y1), x2=n(x2), y2=n(y2))

    def rect(key, cls, u0, u1, v0, v1, style=None, rx=None):
        (xa, ya), (xb, yb) = at(u0, v0), at(u1, v1)
        return Mark("rect", key, cls, style=style, x=n(min(xa, xb)), y=n(min(ya, yb)), w=n(abs(xb - xa)),
                    h=n(abs(yb - ya)), rx=rx)

    marks = scene.marks
    if horizontal:
        x_ticks(marks, V, vs, py0, py1, grid=True)
        chars = int(room / (11 * 0.58))
        for i, name in enumerate(names):
            marks.append(Mark("text", f"c{i}", "tick", x=n(px0 - 8), y=n(centers[i]), text=cut(name, chars),
                              anchor="end", baseline="middle"))
        titles(marks, width, height, px0, px1, py0, py1, y_label, x_label)
    else:
        y_ticks(marks, V, vs, px0, px1)
        marks.extend(category_labels(names, centers, step, py1 + 16))
        marks.append(Mark("line", "axis", "axis", x1=n(px0), x2=n(px1), y1=n(py1), y2=n(py1)))
        titles(marks, width, height, px0, px1, py0, py1, x_label, y_label)
    for i in range(len(shown)):
        a, b = c0 + step * i, c0 + step * (i + 1)
        marks.append(Mark("rect", f"h{i}", "hit band", x=n(px0), y=n(a), w=n(px1 - px0), h=n(b - a), hit=i)
                     if horizontal else
                     Mark("rect", f"h{i}", "hit band", x=n(a), y=n(py0), w=n(b - a), h=n(py1 - py0), hit=i))
    densest = 0.0
    shapes = {}
    if violin:
        for g, s in shown:
            grid = [s.smallest + (s.largest - s.smallest) * k / 59 for k in range(60)] if s.largest > s.smallest \
                else [s.smallest]
            dens = kde(g.values, grid)
            shapes[g.key] = list(zip(grid, dens))
            densest = max(densest, max(dens))
    for i, (g, s) in enumerate(shown):
        u = centers[i]
        paint = g.color
        if violin and densest > 0 and len(shapes[g.key]) > 1:
            pts = shapes[g.key]
            right = [at(u + reach * d / densest, v) for v, d in pts]
            left = [at(u - reach * d / densest, v) for v, d in reversed(pts)]
            d = " ".join(("M" if k == 0 else "L") + f"{n(x)},{n(y)}" for k, (x, y) in enumerate(right + left)) + " Z"
            marks.append(Mark("path", f"v{i}", "violin", style=f"fill: {paint}; stroke: {paint}", d=d))
            marks.append(line(f"w{i}", "whisker", u, s.low, u, s.high))
            marks.append(rect(f"b{i}", "violin-box", u - 4, u + 4, s.q1, s.q3, rx=2))
            mx, my = at(u, s.median)
            marks.append(Mark("circle", f"m{i}", "violin-median", cx=n(mx), cy=n(my), r=3))
        else:
            style = f"fill: {paint}; stroke: {paint}"
            marks.append(line(f"wl{i}", "whisker", u, s.low, u, s.q1))
            marks.append(line(f"wh{i}", "whisker", u, s.q3, u, s.high))
            marks.append(line(f"cl{i}", "whisker", u - box / 4, s.low, u + box / 4, s.low))
            marks.append(line(f"ch{i}", "whisker", u - box / 4, s.high, u + box / 4, s.high))
            marks.append(rect(f"b{i}", "box", u - box / 2, u + box / 2, s.q1, s.q3, style=style, rx=2))
            marks.append(line(f"m{i}", "median", u - box / 2, s.median, u + box / 2, s.median,
                              style=f"stroke: {paint}"))
        if show_mean:
            mx, my = at(u, s.mean)
            marks.append(Mark("circle", f"mean{i}", "mean-dot", style=f"stroke: {paint}", cx=n(mx), cy=n(my), r=3.5))
        dots = g.values if points == "all" else s.outliers if points != "none" else []
        spread = (reach * 0.6 if violin else box * 0.35) if points == "all" else 0.0
        for k, v in enumerate(dots):
            jitter = ((k * 0.618034) % 1 - 0.5) * 2 * spread
            x, y = at(u + jitter, v)
            marks.append(Mark("circle", f"o{i}|{k}", "point small", style=f"stroke: {paint}", cx=n(x), cy=n(y),
                              r=2.5))
    for i, (g, s) in enumerate(shown):
        rows = [(k, None, label, fmt_value(round(v, 4), fmt)) for k, label, v in
                (("max", "Max", s.largest), ("q3", "Q3", s.q3), ("median", "Median", s.median), ("q1", "Q1", s.q1),
                 ("min", "Min", s.smallest), ("mean", "Mean", s.mean))]
        rows.insert(0, ("n", g.color, "Values", f"{s.count:,}"))
        if s.outliers:
            rows.append(("out", None, "Outliers", str(len(s.outliers))))
        a, b = c0 + step * i, c0 + step * (i + 1)
        light = [Mark("rect", "hover-band", "hover-band", x=n(px0), y=n(a), w=n(px1 - px0), h=n(b - a))
                 if horizontal else
                 Mark("rect", "hover-band", "hover-band", x=n(a), y=n(py0), w=n(b - a), h=n(py1 - py0))]
        if horizontal:
            scene.tips.append(Tip(g.label, rows, n(px1 - 4), n(a), "left", light))
        else:
            right = centers[i] < width / 2
            scene.tips.append(Tip(g.label, rows, n(b if right else a), n(py0), "right" if right else "left", light))
    return scene
