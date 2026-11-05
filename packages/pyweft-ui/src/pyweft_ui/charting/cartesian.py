"""Bar, line and area charts over categories: the layout.

Categories run along one axis (x, or y for horizontal bars) and values
along the other; series on ``axis="right"`` get a second value axis.
Everything is computed in pixels for the width the chart really has.
"""

from __future__ import annotations

import math
from collections import defaultdict

from .data import label_text
from .scales import LinearScale, fmt_tick, fmt_value, nice, tick_step, ticks
from .scene import LegendItem, Mark, Scene, Tip, n, text_width

_STEPS = ("step", "step-before", "step-after")


def cartesian(categories, series, *, width, height, hidden=frozenset(), horizontal=False,
              stacked="", labels=False, fmt=None, tick_fmt=None, x_label="", y_label="",
              y2_label="", y_min=None, y_max=None, grid=True, curve="linear", points=None,
              connect_gaps=False, rows=(), kind="Bar", empty="No data") -> Scene:
    width, height = max(float(width), 160.0), max(float(height), 120.0)
    count = len(categories)
    for s in series:  # every series as long as the categories
        s.values = (list(s.values) + [None] * count)[:count]
    names = [label_text(c) for c in categories]
    shown = [s for s in series if s.key not in hidden]
    scene = Scene(width, height)
    scene.legend = [LegendItem(s.key, s.label, s.color, s.key in hidden, "line" if s.kind == "line" else "box")
                    for s in series]
    scene.head = [x_label, *[s.label for s in series]]
    scene.rows = [[names[i], *[fmt_value(s.values[i], fmt) for s in series]] for i in range(count)]
    what = ", ".join(s.label for s in shown)
    scene.summary = f"{kind} chart" + (f" of {what}" if what else "") + \
        f" over {count} {'category' if count == 1 else 'categories'}"

    def payload(i, key):
        i = max(0, min(i, count - 1))
        values = {s.key: s.values[i] for s in series}
        return {"index": i, "label": categories[i], "series": key,
                "value": values.get(key) if key else None, "values": values,
                "row": rows[i] if i < len(rows) else None}

    scene.payload = payload
    if not count or not shown:
        scene.marks.append(Mark("text", "empty", "empty", x=n(width / 2), y=n(height / 2),
                                text=empty, anchor="middle", baseline="middle"))
        return scene

    # ---------------------------------------------------------- stacking
    mode = str(stacked).strip().lower()
    percent = mode == "percent"
    stacking = mode in ("true", "1", "yes", "percent")

    def group(s):
        if s.stack:
            return s.stack
        return "_all" if stacking and s.kind in ("bar", "area") else None

    totals = defaultdict(lambda: [0.0] * count)
    if percent:
        for s in shown:
            if group(s):
                for i, v in enumerate(s.values):
                    totals[(s.axis, group(s))][i] += abs(v or 0.0)
    pos, neg = defaultdict(lambda: [0.0] * count), defaultdict(lambda: [0.0] * count)
    base, top = {}, {}
    for s in shown:
        g = group(s)
        b, t = [None] * count, [None] * count
        for i, v in enumerate(s.values):
            if v is None:
                if g is None or s.kind != "area":
                    continue
                v = 0.0  # a stacked area carries on through a gap
            if g is None:
                b[i], t[i] = (0.0 if s.kind in ("bar", "area") else None), v
                continue
            if percent:
                total = totals[(s.axis, g)][i]
                v = v / total * 100 if total else 0.0
            pile = pos if v >= 0 else neg
            b[i] = pile[(s.axis, g)][i]
            pile[(s.axis, g)][i] += v
            t[i] = pile[(s.axis, g)][i]
        base[s.key], top[s.key] = b, t

    # ------------------------------------------------------- value axes
    value_room = (width * 0.7) if horizontal else (height - 50)
    tick_count = max(2, int(value_room / (90 if horizontal else 45)))
    axes = {}
    for side, lo_fix, hi_fix in (("left", y_min, y_max), ("right", None, None)):
        members = [s for s in shown if s.axis == side]
        if not members:
            continue
        vals = [v for s in members for v in (*top[s.key], *base[s.key]) if v is not None] or [0.0, 1.0]
        lo, hi = min(vals), max(vals)
        if any(s.kind in ("bar", "area") for s in members):
            lo, hi = min(lo, 0.0), max(hi, 0.0)
        lo = float(lo_fix) if lo_fix is not None else lo
        hi = float(hi_fix) if hi_fix is not None else hi
        if lo == hi:
            lo, hi = (lo - abs(lo) * 0.5 - 1, hi + abs(hi) * 0.5 + 1) if lo else (0.0, 1.0)
        nlo, nhi = nice(lo, hi, tick_count)
        lo = lo if lo_fix is not None else nlo
        hi = hi if hi_fix is not None else nhi
        values = ticks(lo, hi, tick_count)
        step = tick_step(lo, hi, tick_count)
        axes[side] = (lo, hi, values, [fmt_tick(v, step, tick_fmt) for v in values])

    # ----------------------------------------------------------- margins
    bars_any = any(s.kind == "bar" for s in series)
    widest = lambda texts: max((text_width(t) for t in texts), default=0.0)  # noqa: E731
    value_labels = [fmt_value(v, fmt) for s in shown for v in s.values if v is not None] if labels else []
    if not horizontal:
        left = widest(axes["left"][3]) + 10 if "left" in axes else 12
        right = widest(axes["right"][3]) + 10 if "right" in axes else 14
        left += 18 if y_label else 0
        right += 18 if y2_label else 0
        top_m = 10 + (14 if labels else 0)
        bottom = 24 + (18 if x_label else 0)
        if not bars_any and count > 1:  # points sit on the edges: their labels mustn't spill out
            left = max(left, text_width(names[0]) / 2 + 4)
            right = max(right, text_width(names[-1]) / 2 + 4)
    else:
        cat_room = min(widest(names), width * 0.35)
        left = cat_room + 12 + (18 if x_label else 0)
        right = max(16.0, widest(axes[next(iter(axes))][3][-1:]) / 2 + 4) + \
            (widest(value_labels) + 4 if labels and not stacking else 0)
        top_m = 10 + ((22 + (18 if y2_label else 0)) if "right" in axes else 0)
        bottom = 24 + (18 if y_label else 0)
    px0, px1 = left, max(left + 20, width - right)
    py0, py1 = top_m, max(top_m + 20, height - bottom)

    # -------------------------------------------------------- categories
    c0, c1 = (py0, py1) if horizontal else (px0, px1)
    if bars_any or count == 1:
        step = (c1 - c0) / count
        centers = [c0 + step * (i + 0.5) for i in range(count)]
        edges = [(c0 + step * i, c0 + step * (i + 1)) for i in range(count)]
        band = step * 0.8
    else:
        step = (c1 - c0) / (count - 1)
        centers = [c0 + step * i for i in range(count)]
        edges = [(max(c0, c - step / 2), min(c1, c + step / 2)) for c in centers]
        band = step * 0.8
    scales = {side: LinearScale(axes[side][:2], (px0, px1) if horizontal else (py1, py0)) for side in axes}

    def at(i, v, side):
        u, w = centers[i], scales[side].clamp(v)
        return (w, u) if horizontal else (u, w)

    marks = scene.marks

    # ---------------------------------------------------- grid and axes
    main = "left" if "left" in axes else "right"
    lo, hi, values, texts = axes[main]
    for j, (v, text) in enumerate(zip(values, texts)):
        p = n(scales[main](v))
        if grid or v == 0:
            cls = "grid zero" if v == 0 and lo < 0 else "grid"
            marks.append(Mark("line", f"g{j}", cls, x1=p, x2=p, y1=n(py0), y2=n(py1)) if horizontal else
                         Mark("line", f"g{j}", cls, x1=n(px0), x2=n(px1), y1=p, y2=p))
        marks.append(Mark("text", f"t{j}", "tick", x=p, y=n(py1 + 15), text=text, anchor="middle") if horizontal
                     else Mark("text", f"t{j}", "tick", x=n(px0 - 8), y=p, text=text, anchor="end",
                               baseline="middle"))
    if "right" in axes:
        for j, (v, text) in enumerate(zip(axes["right"][2], axes["right"][3])):
            p = n(scales["right"](v))
            marks.append(Mark("text", f"r{j}", "tick", x=p, y=n(py0 - 8), text=text, anchor="middle")
                         if horizontal else
                         Mark("text", f"r{j}", "tick", x=n(px1 + 8), y=p, text=text, anchor="start",
                              baseline="middle"))
    marks.append(Mark("line", "axis", "axis", x1=n(px0), x2=n(px0), y1=n(py0), y2=n(py1)) if horizontal else
                 Mark("line", "axis", "axis", x1=n(px0), x2=n(px1), y1=n(py1), y2=n(py1)))

    if horizontal:
        every = max(1, math.ceil(16 / max(step, 1)))
        room = int((cat_room - 2) / (11 * 0.58))
        for i, name in enumerate(names):
            if i % every == 0:
                marks.append(Mark("text", f"c{i}", "tick", x=n(px0 - 8), y=n(centers[i]), text=_cut(name, room),
                                  anchor="end", baseline="middle"))
    else:
        shortened = [_cut(name, 24) for name in names]
        every = max(1, math.ceil((widest(shortened) + 8) / max(step, 1)))
        for i, name in enumerate(shortened):
            if i % every == 0:
                marks.append(Mark("text", f"c{i}", "tick", x=n(centers[i]), y=n(py1 + 16), text=name,
                                  anchor="middle"))

    mid_x, mid_y = n((px0 + px1) / 2), n((py0 + py1) / 2)
    side_title = x_label if horizontal else y_label
    bottom_title = y_label if horizontal else x_label
    if side_title:
        marks.append(Mark("text", "title-side", "axis-title", x=12, y=mid_y, text=side_title, anchor="middle",
                          baseline="middle", transform=f"rotate(-90 12 {mid_y})"))
    if bottom_title:
        marks.append(Mark("text", "title-bottom", "axis-title", x=mid_x, y=n(height - 6), text=bottom_title,
                          anchor="middle"))
    if y2_label and "right" in axes:
        if horizontal:
            marks.append(Mark("text", "title-top", "axis-title", x=mid_x, y=14, text=y2_label, anchor="middle"))
        else:
            x = n(width - 12)
            marks.append(Mark("text", "title-right", "axis-title", x=x, y=mid_y, text=y2_label, anchor="middle",
                              baseline="middle", transform=f"rotate(90 {x} {mid_y})"))

    # ------------------------------------------------- hover/click bands
    for i, (a, b) in enumerate(edges):
        marks.append(Mark("rect", f"h{i}", "hit band", x=n(px0), y=n(a), w=n(px1 - px0), h=n(b - a), hit=i)
                     if horizontal else
                     Mark("rect", f"h{i}", "hit band", x=n(a), y=n(py0), w=n(b - a), h=n(py1 - py0), hit=i))

    # -------------------------------------------------------------- bars
    bar_series = [s for s in shown if s.kind == "bar"]
    slots = []
    for s in bar_series:
        if (group(s) or s.key) not in slots:
            slots.append(group(s) or s.key)
    texts_after = []
    if slots:
        slot = band / len(slots)
        thick = min(slot * (0.88 if len(slots) > 1 else 1.0), 80.0)
        for s in bar_series:
            j = slots.index(group(s) or s.key)
            scale = scales[s.axis]
            for i in range(count):
                v0, v1 = base[s.key][i], top[s.key][i]
                if v1 is None:
                    continue
                c = centers[i] - band / 2 + slot * (j + 0.5)
                a, b = scale.clamp(v0), scale.clamp(v1)
                lo_p, hi_p = min(a, b), max(a, b)
                length = hi_p - lo_p
                rx = n(max(0.0, min(3.0, thick / 4, length / 2)))
                if horizontal:
                    box = dict(x=n(lo_p), y=n(c - thick / 2), w=n(length), h=n(thick))
                else:
                    box = dict(x=n(c - thick / 2), y=n(lo_p), w=n(thick), h=n(length))
                marks.append(Mark("rect", f"b{i}|{s.key}", "bar hit", style=f"fill: {s.color}", rx=rx, hit=i,
                                  series=s.key, **box))
                if not labels:
                    continue
                text = f"{v1 - v0:.0f}%" if percent and group(s) else fmt_value(s.values[i], fmt)
                if group(s):  # inside its segment, when it fits
                    fits = length >= (text_width(text) + 6 if horizontal else 15)
                    if fits and thick >= (15 if horizontal else text_width(text) + 4):
                        x, y = (n((lo_p + hi_p) / 2), n(c)) if horizontal else (n(c), n((lo_p + hi_p) / 2))
                        texts_after.append(Mark("text", f"l{i}|{s.key}", "value-label inside", x=x, y=y,
                                                text=text, anchor="middle", baseline="middle"))
                    continue
                up = (s.values[i] or 0) >= 0
                if horizontal:
                    texts_after.append(Mark("text", f"l{i}|{s.key}", "value-label", x=n(hi_p + 4 if up else lo_p - 4),
                                            y=n(c), text=text, anchor="start" if up else "end",
                                            baseline="middle"))
                else:
                    texts_after.append(Mark("text", f"l{i}|{s.key}", "value-label", x=n(c),
                                            y=n(lo_p - 5 if up else hi_p + 13), text=text, anchor="middle"))

    # ----------------------------------------------------- areas, lines
    drawn = [s for s in shown if s.kind in ("line", "area")]
    for s in drawn:
        if s.kind != "area":
            continue
        for k, seg in enumerate(_segments(top[s.key], connect_gaps)):
            edge = [at(i, top[s.key][i], s.axis) for i in seg]
            floor_ = [at(i, base[s.key][i] or 0.0, s.axis) for i in reversed(seg)]
            how = s.curve or curve
            d = _path(edge, how, horizontal) + " " + _path(floor_, how, horizontal, start="L") + " Z"
            marks.append(Mark("path", f"a{k}|{s.key}", "area", style=f"fill: {s.color}", d=d))
    for s in drawn:
        style = f"stroke: {s.color}"
        if s.dash:
            style += f"; stroke-dasharray: {s.dash}"
        if s.width:
            style += f"; stroke-width: {s.width}"
        for k, seg in enumerate(_segments(top[s.key], connect_gaps)):
            d = _path([at(i, top[s.key][i], s.axis) for i in seg], s.curve or curve, horizontal)
            marks.append(Mark("path", f"p{k}|{s.key}", "line", style=style, d=d))
    for s in drawn:
        show = s.points if s.points is not None else points if points is not None else count <= 40
        for i in range(count):
            if top[s.key][i] is None:
                continue
            x, y = at(i, top[s.key][i], s.axis)
            if show and str(show).lower() != "false":
                marks.append(Mark("circle", f"o{i}|{s.key}", "point", style=f"stroke: {s.color}",
                                  cx=n(x), cy=n(y), r=3))
            if labels:
                texts_after.append(Mark("text", f"l{i}|{s.key}", "value-label", x=n(x + 7) if horizontal else n(x),
                                        y=n(y) if horizontal else n(y - 8), text=fmt_value(s.values[i], fmt),
                                        anchor="start" if horizontal else "middle",
                                        baseline="middle" if horizontal else None))
    marks.extend(texts_after)

    # ------------------------------------------------------------- tips
    grouped = [s for s in shown if group(s)]
    for i in range(count):
        tip_rows = []
        for s in shown:
            v = s.values[i]
            if v is None:
                continue
            text = fmt_value(v, fmt)
            if percent and group(s):
                text += f" ({top[s.key][i] - base[s.key][i]:.1f}%)"
            tip_rows.append((s.key, s.color, s.label, text))
        if stacking and len(grouped) > 1:
            total = sum(s.values[i] or 0.0 for s in grouped)
            tip_rows.append(("_total", None, "Total", fmt_value(total, fmt)))
        a, b = edges[i]
        if horizontal:
            light = [Mark("rect", "hover-band", "hover-band", x=n(px0), y=n(a), w=n(px1 - px0), h=n(b - a))]
        else:
            light = [Mark("rect", "hover-band", "hover-band", x=n(a), y=n(py0), w=n(b - a), h=n(py1 - py0))]
        for s in drawn:
            if top[s.key][i] is not None:
                x, y = at(i, top[s.key][i], s.axis)
                light.append(Mark("circle", f"hover|{s.key}", "hover-point", style=f"fill: {s.color}",
                                  cx=n(x), cy=n(y), r=5))
        if horizontal:
            ends = [scales[s.axis].clamp(top[s.key][i]) for s in shown if top[s.key][i] is not None] or [px0]
            x = max(ends) + 8
            tip = Tip(names[i], tip_rows, n(x), n(a), "right") if x < width * 0.5 else \
                Tip(names[i], tip_rows, n(x - 16), n(a), "left")
        else:
            right_side = centers[i] < width * 0.5
            tip = Tip(names[i], tip_rows, n(b if right_side else a), n(py0), "right" if right_side else "left")
        tip.marks = light
        scene.tips.append(tip)
    return scene


def _cut(text: str, room: int) -> str:
    room = max(room, 4)
    return text if len(text) <= room else text[: room - 1].rstrip() + "…"


def _segments(values, connect: bool) -> list[list[int]]:
    """Runs of indices with a value: a gap (None) breaks the line unless
    ``connect`` joins across it."""
    if connect:
        run = [i for i, v in enumerate(values) if v is not None]
        return [run] if run else []
    out, run = [], []
    for i, v in enumerate(values):
        if v is None:
            if run:
                out.append(run)
            run = []
        else:
            run.append(i)
    if run:
        out.append(run)
    return out


def _path(points, curve: str, horizontal: bool, start: str = "M") -> str:
    """An SVG path through points, in order, shaped by ``curve``: linear,
    smooth (monotone: never overshoots the data), step, step-before or
    step-after. Worked out along the category axis, so horizontal charts
    curve the same way."""
    uv = [(p[1], p[0]) if horizontal else (p[0], p[1]) for p in points]

    def xy(u, v):
        return f"{n(v)},{n(u)}" if horizontal else f"{n(u)},{n(v)}"

    out = [start + xy(*uv[0])]
    if curve == "smooth" and len(uv) > 2:
        t = _tangents(uv)
        for (u0, v0), (u1, v1), t0, t1 in zip(uv, uv[1:], t, t[1:]):
            d = (u1 - u0) / 3
            out.append(f"C{xy(u0 + d, v0 + d * t0)} {xy(u1 - d, v1 - d * t1)} {xy(u1, v1)}")
    elif curve in _STEPS:
        for (u0, v0), (u1, v1) in zip(uv, uv[1:]):
            if curve == "step":
                m = (u0 + u1) / 2
                out.append(f"L{xy(m, v0)} L{xy(m, v1)} L{xy(u1, v1)}")
            elif curve == "step-after":
                out.append(f"L{xy(u1, v0)} L{xy(u1, v1)}")
            else:
                out.append(f"L{xy(u0, v1)} L{xy(u1, v1)}")
    else:
        out.extend("L" + xy(u, v) for u, v in uv[1:])
    return " ".join(out)


def _tangents(uv) -> list[float]:
    """Monotone cubic tangents (Fritsch-Carlson, as d3's curveMonotoneX)."""
    def sign(x):
        return (x > 0) - (x < 0)

    size = len(uv)
    t = [0.0] * size
    for i in range(1, size - 1):
        (u0, v0), (u1, v1), (u2, v2) = uv[i - 1], uv[i], uv[i + 1]
        h0, h1 = u1 - u0, u2 - u1
        if not h0 or not h1:
            continue
        s0, s1 = (v1 - v0) / h0, (v2 - v1) / h1
        p = (s0 * h1 + s1 * h0) / (h0 + h1)
        t[i] = (sign(s0) + sign(s1)) * min(abs(s0), abs(s1), 0.5 * abs(p))

    def end(a, b, other):
        h = b[0] - a[0]
        return (3 * (b[1] - a[1]) / h - other) / 2 if h else other

    t[0] = end(uv[0], uv[1], t[1])
    t[-1] = end(uv[-2], uv[-1], t[-2])
    return t
