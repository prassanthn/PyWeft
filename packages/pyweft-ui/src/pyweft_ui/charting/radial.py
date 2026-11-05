"""Pie, doughnut, polar area and radar charts: the layout.

Angles are in radians, clockwise from the positive x axis as the page
draws them (y points down), so -pi/2 is twelve o'clock.
"""

from __future__ import annotations

import math

from .data import label_text
from .scales import LinearScale, fmt_tick, fmt_value, nice, tick_step, ticks
from .scene import LegendItem, Mark, Scene, Tip, n, text_width

TAU = 2 * math.pi


def _at(cx, cy, r, a):
    return cx + r * math.cos(a), cy + r * math.sin(a)


def _xy(p):
    return f"{n(p[0])},{n(p[1])}"


def sector(cx, cy, r0, r1, a0, a1) -> str:
    """A pie slice (r0 = 0) or a ring segment, from angle a0 to a1."""
    if a1 - a0 >= TAU - 1e-9:  # a whole circle: two half arcs (one arc can't end where it starts)
        out = (f"M{_xy((cx + r1, cy))} A{n(r1)},{n(r1)} 0 1 1 {_xy((cx - r1, cy))} "
               f"A{n(r1)},{n(r1)} 0 1 1 {_xy((cx + r1, cy))} Z")
        if r0 > 0:  # the hole, wound the other way so it stays empty
            out += (f" M{_xy((cx + r0, cy))} A{n(r0)},{n(r0)} 0 1 0 {_xy((cx - r0, cy))} "
                    f"A{n(r0)},{n(r0)} 0 1 0 {_xy((cx + r0, cy))} Z")
        return out
    large = 1 if a1 - a0 > math.pi else 0
    out = f"M{_xy(_at(cx, cy, r1, a0))} A{n(r1)},{n(r1)} 0 {large} 1 {_xy(_at(cx, cy, r1, a1))}"
    if r0 > 0:
        out += f" L{_xy(_at(cx, cy, r0, a1))} A{n(r0)},{n(r0)} 0 {large} 0 {_xy(_at(cx, cy, r0, a0))} Z"
    else:
        out += f" L{_xy((cx, cy))} Z"
    return out


def _share(v: float, total: float) -> str:
    pct = v / total * 100 if total else 0.0
    return f"{pct:.0f}%" if pct >= 10 or pct == 0 else f"{pct:.1f}%"


def _slices_table(scene, slices, fmt, label_head):
    everything = sum(s.value for s in slices if s.value and s.value > 0)
    scene.head = [label_head, "Value", "Share"]
    scene.rows = [[s.label, fmt_value(s.value, fmt),
                   _share(s.value, everything) if s.value and s.value > 0 else ""] for s in slices]


def _empty(scene, text):
    scene.marks.append(Mark("text", "empty", "empty", x=n(scene.width / 2), y=n(scene.height / 2), text=text,
                            anchor="middle", baseline="middle"))
    return scene


def pie(slices, *, width, height, hidden=frozenset(), hole=0.0, half=False, labels="percent",
        center="", center_label="", fmt=None, label_head="", kind="Pie", empty="No data") -> Scene:
    width, height = max(float(width), 120.0), max(float(height), 80.0)
    scene = Scene(width, height)
    scene.legend = [LegendItem(s.key, s.label, s.color, s.key in hidden) for s in slices]
    _slices_table(scene, slices, fmt, label_head)
    shown = [(j, s) for j, s in enumerate(slices) if s.key not in hidden and s.value and s.value > 0]
    total = sum(s.value for _, s in shown)
    scene.summary = f"{kind} chart, {len(shown)} {'slice' if len(shown) == 1 else 'slices'}" + \
        (f", total {fmt_value(total, fmt)}" if shown else "")

    def payload(hit, key=None):
        j, s = shown[max(0, min(hit, len(shown) - 1))]
        return {"index": j, "label": s.label, "value": s.value,
                "percent": s.value / total * 100 if total else 0.0, "row": s.row}

    scene.payload = payload
    if not shown:
        return _empty(scene, empty)

    pad = 8.0  # room for a hovered slice to step out
    if half:
        radius = max(10.0, min(width / 2 - pad, height - 2 * pad))
        cx, cy = width / 2, pad + radius
        start, sweep = math.pi, math.pi
    else:
        radius = max(10.0, min(width, height) / 2 - pad)
        cx, cy = width / 2, height / 2
        start, sweep = -math.pi / 2, TAU
    inner = radius * max(0.0, min(float(hole or 0.0), 0.95))
    angle = start
    for hit, (j, s) in enumerate(shown):
        a0, a1 = angle, angle + sweep * s.value / total
        angle = a1
        mid = (a0 + a1) / 2
        d = sector(cx, cy, inner, radius, a0, a1)
        scene.marks.append(Mark("path", f"s{s.key}", "slice hit", style=f"fill: {s.color}", d=d, hit=hit,
                                series=s.key))
        if labels and labels != "none":
            ring = (radius + inner) / 2 if inner else radius * 0.62
            text = {"value": fmt_value(s.value, fmt), "label": s.label}.get(labels, _share(s.value, total))
            if (a1 - a0) * ring > text_width(text) + 6 and radius - inner > 22:
                x, y = _at(cx, cy, ring, mid)
                scene.marks.append(Mark("text", f"l{s.key}", "slice-label", x=n(x), y=n(y), text=text,
                                        anchor="middle", baseline="middle"))
        dx, dy = 6 * math.cos(mid), 6 * math.sin(mid)
        light = [Mark("path", "hover-slice", "slice hover-slice", style=f"fill: {s.color}", d=d,
                      transform=f"translate({n(dx)} {n(dy)})")]
        x, y = _at(cx, cy, radius * 0.8 if not inner else (radius + inner) / 2, mid)
        rows = [(s.key, s.color, "", f"{fmt_value(s.value, fmt)} · {_share(s.value, total)}")]
        scene.tips.append(Tip(s.label, rows, n(x), n(y), "right mid" if x >= cx else "left mid", light))
    if inner and center:
        text = fmt_value(total, fmt) if center == "total" else str(center)
        y = cy - (10 if half else (8 if center_label else 0))
        scene.marks.append(Mark("text", "center", "center-value", x=n(cx), y=n(y), text=text, anchor="middle",
                                baseline="middle"))
        if center_label:
            scene.marks.append(Mark("text", "center-label", "center-label", x=n(cx), y=n(y + 20),
                                    text=str(center_label), anchor="middle", baseline="middle"))
    return scene


def polar(slices, *, width, height, hidden=frozenset(), fmt=None, tick_fmt=None, label_head="",
          kind="Polar area", empty="No data") -> Scene:
    width, height = max(float(width), 120.0), max(float(height), 120.0)
    scene = Scene(width, height)
    scene.legend = [LegendItem(s.key, s.label, s.color, s.key in hidden) for s in slices]
    _slices_table(scene, slices, fmt, label_head)
    shown = [(j, s) for j, s in enumerate(slices) if s.key not in hidden and s.value is not None and s.value >= 0]
    scene.summary = f"{kind} chart, {len(shown)} {'segment' if len(shown) == 1 else 'segments'}"

    def payload(hit, key=None):
        j, s = shown[max(0, min(hit, len(shown) - 1))]
        return {"index": j, "label": s.label, "value": s.value, "row": s.row}

    scene.payload = payload
    if not shown:
        return _empty(scene, empty)
    radius = max(20.0, min(width, height) / 2 - 10)
    cx, cy = width / 2, height / 2
    count = max(2, int(radius / 40))
    _, top = nice(0.0, max(s.value for _, s in shown) or 1.0, count)
    rings = ticks(0.0, top, count)
    step = tick_step(0.0, top, count)
    r = LinearScale((0.0, top), (0.0, radius))
    for k, v in enumerate(rings[1:]):
        scene.marks.append(Mark("circle", f"ring{k}", "grid ring", cx=n(cx), cy=n(cy), r=n(r(v))))
    width_each = TAU / len(shown)
    hits = []
    for hit, (j, s) in enumerate(shown):
        a0 = -math.pi / 2 + hit * width_each
        a1 = a0 + width_each
        d = sector(cx, cy, 0.0, r(s.value), a0, a1)
        style = f"fill: {s.color}; stroke: {s.color}"
        scene.marks.append(Mark("path", f"s{s.key}", "polar", style=style, d=d))
        hits.append(Mark("path", f"h{s.key}", "hit", d=sector(cx, cy, 0.0, radius, a0, a1), hit=hit, series=s.key))
        x, y = _at(cx, cy, max(r(s.value), radius * 0.4) * 0.8, (a0 + a1) / 2)
        light = [Mark("path", "hover-polar", "polar hover-polar", style=style, d=d)]
        scene.tips.append(Tip(s.label, [(s.key, s.color, "", fmt_value(s.value, fmt))], n(x), n(y),
                              "right mid" if x >= cx else "left mid", light))
    scene.marks.extend(hits)
    for k, v in enumerate(rings[1:]):
        scene.marks.append(Mark("text", f"rt{k}", "tick ring-tick", x=n(cx + 3), y=n(cy - r(v) + 10),
                                text=fmt_tick(v, step, tick_fmt)))
    return scene


def radar(categories, series, *, width, height, hidden=frozenset(), fmt=None, tick_fmt=None, rows=(),
          x_label="", kind="Radar", empty="No data", points=None) -> Scene:
    width, height = max(float(width), 160.0), max(float(height), 160.0)
    count = len(categories)
    for s in series:
        s.values = (list(s.values) + [None] * count)[:count]
    names = [label_text(c) for c in categories]
    shown = [s for s in series if s.key not in hidden]
    scene = Scene(width, height)
    scene.legend = [LegendItem(s.key, s.label, s.color, s.key in hidden) for s in series]
    scene.head = [x_label, *[s.label for s in series]]
    scene.rows = [[names[i], *[fmt_value(s.values[i], fmt) for s in series]] for i in range(count)]
    scene.summary = f"{kind} chart of {', '.join(s.label for s in shown) or 'nothing'} over {count} axes"

    def payload(i, key):
        i = max(0, min(i, count - 1))
        values = {s.key: s.values[i] for s in series}
        return {"index": i, "label": categories[i], "series": key, "value": values.get(key) if key else None,
                "values": values, "row": rows[i] if i < len(rows) else None}

    scene.payload = payload
    if count < 3 or not shown:
        return _empty(scene, empty if count >= 3 or not count else "A radar chart needs three or more axes")

    room = min(max(text_width(t) for t in names), width * 0.22)
    radius = max(30.0, min(width / 2 - room - 14, height / 2 - 26))
    cx, cy = width / 2, height / 2
    values = [v for s in shown for v in s.values if v is not None] or [0.0]
    lo, hi = min(0.0, min(values)), max(0.0, max(values))
    if lo == hi:
        hi = 1.0
    tick_count = max(2, int(radius / 35))
    lo, hi = nice(lo, hi, tick_count)
    rings = ticks(lo, hi, tick_count)
    step = tick_step(lo, hi, tick_count)
    r = LinearScale((lo, hi), (0.0, radius))

    def angle(i):
        return -math.pi / 2 + TAU * i / count

    def ring(v):
        return " ".join(("M" if i == 0 else "L") + _xy(_at(cx, cy, r(v), angle(i))) for i in range(count)) + " Z"

    for k, v in enumerate(rings):
        if r(v) > 0:
            scene.marks.append(Mark("path", f"ring{k}", "grid ring", d=ring(v)))
    for i in range(count):
        x, y = _at(cx, cy, radius, angle(i))
        scene.marks.append(Mark("line", f"spoke{i}", "grid", x1=n(cx), y1=n(cy), x2=n(x), y2=n(y)))
        lx, ly = _at(cx, cy, radius + 10, angle(i))
        c, s_ = math.cos(angle(i)), math.sin(angle(i))
        scene.marks.append(Mark("text", f"c{i}", "tick axis-name", x=n(lx), y=n(ly),
                                text=_cut(names[i], int(room / (11 * 0.58))),
                                anchor="start" if c > 0.3 else "end" if c < -0.3 else "middle",
                                baseline="hanging" if s_ > 0.3 else "middle" if s_ > -0.3 else None))
    for s in shown:
        pts = [_at(cx, cy, r(v if v is not None else lo), angle(i)) for i, v in enumerate(s.values)]
        d = " ".join(("M" if i == 0 else "L") + _xy(p) for i, p in enumerate(pts)) + " Z"
        scene.marks.append(Mark("path", f"area|{s.key}", "radar-area", style=f"fill: {s.color}; stroke: {s.color}",
                                d=d))
        if points is None or points:
            for i, (x, y) in enumerate(pts):
                if s.values[i] is not None:
                    scene.marks.append(Mark("circle", f"o{i}|{s.key}", "point", style=f"stroke: {s.color}",
                                            cx=n(x), cy=n(y), r=3))
    for i in range(count):
        half = math.pi / count
        scene.marks.append(Mark("path", f"h{i}", "hit", d=sector(cx, cy, 0.0, radius + 12, angle(i) - half,
                                                                 angle(i) + half), hit=i))
    for k, v in enumerate(rings):
        if r(v) > 0:
            scene.marks.append(Mark("text", f"rt{k}", "tick ring-tick", x=n(cx + 3), y=n(cy - r(v) + 10),
                                    text=fmt_tick(v, step, tick_fmt)))
    for i in range(count):
        x, y = _at(cx, cy, radius, angle(i))
        light = [Mark("line", "hover-spoke", "hover-spoke", x1=n(cx), y1=n(cy), x2=n(x), y2=n(y))]
        tip_rows = []
        for s in shown:
            v = s.values[i]
            if v is None:
                continue
            px, py = _at(cx, cy, r(v), angle(i))
            light.append(Mark("circle", f"hover|{s.key}", "hover-point", style=f"fill: {s.color}",
                              cx=n(px), cy=n(py), r=5))
            tip_rows.append((s.key, s.color, s.label, fmt_value(v, fmt)))
        tx, ty = _at(cx, cy, radius * 0.7, angle(i))
        scene.tips.append(Tip(names[i], tip_rows, n(tx), n(ty), "right mid" if tx >= cx else "left mid", light))
    return scene


def _cut(text: str, room: int) -> str:
    room = max(room, 4)
    return text if len(text) <= room else text[: room - 1].rstrip() + "…"
