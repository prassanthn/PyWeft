"""Dashboard charts: gauge, funnel and waterfall."""

from __future__ import annotations

import math
from collections.abc import Mapping

from .axes import category_labels, cut, value_axis, widest
from .data import color_of, field, label_text, number
from .scales import LinearScale, fmt_value
from .scene import LegendItem, Mark, Scene, Tip, n, text_width


# ------------------------------------------------------------------- gauge
def _bands(bands, lo, hi):
    """[(from, to, colour)] from [(to, colour)], {"to", "color"[, "from"]}
    dicts or "60:success, 80:warning, 100:danger" text, each starting
    where the last ended."""
    if isinstance(bands, str):
        bands = [tuple(part.split(":", 1)) for part in bands.split(",") if ":" in part]
    out, start = [], lo
    for band in bands or []:
        if isinstance(band, Mapping):
            begin = number(band.get("from"))
            end, color = number(band.get("to")), band.get("color")
        else:
            begin, (end, color) = None, (number(band[0]), band[1])
        begin = start if begin is None else begin
        if end is None:
            continue
        out.append((max(lo, begin), min(hi, end), color_of(str(color).strip(), 0)))
        start = end
    return out


def gauge(value, lo=0.0, hi=100.0, *, half=False, bands=(), color=None, fmt=None) -> dict:
    """Everything the Gauge draws, in a 200-wide box. Arcs are strokes: the
    value arc is the whole track drawn with a dash as long as the value
    (pathLength 100), so changes can animate."""
    lo, hi = float(lo), float(hi if hi != lo else lo + 1)
    v = number(value)
    frac = 0.0 if v is None else max(0.0, min(1.0, (v - lo) / (hi - lo)))
    cx, radius, width = 100.0, 80.0, 16.0
    if half:
        cy, start, sweep, box = 96.0, math.pi, math.pi, 124.0
    else:
        cy, start, sweep, box = 100.0, math.radians(135), math.radians(270), 182.0

    def at(r, a):
        return f"{n(cx + r * math.cos(a))},{n(cy + r * math.sin(a))}"

    def arc(r, a0, a1):
        large = 1 if a1 - a0 > math.pi else 0
        return f"M{at(r, a0)} A{n(r)},{n(r)} 0 {large} 1 {at(r, a1)}"

    def angle(x):
        return start + sweep * (max(lo, min(hi, x)) - lo) / (hi - lo)

    ranges = _bands(bands, lo, hi)
    active = next((c for a, b, c in ranges if v is not None and a <= v <= b), None)
    def under(a):  # the min and max labels sit just below the ends of the arc
        return (n(cx + radius * math.cos(a)), n(cy + radius * math.sin(a) + 22))
    return {
        "view": f"0 0 200 {n(box)}",
        "track": arc(radius, start, start + sweep),
        "width": width,
        "dash": f"{n(frac * 100)} 100",
        "frac": frac,
        "color": active or color_of(color, 0),
        "bands": [(arc(radius + width / 2 + 5, angle(a), angle(b)), c) for a, b, c in ranges if b > a],
        "needle": f"transform: rotate({n(math.degrees(start + sweep * frac))}deg); "
                  f"transform-origin: {n(cx)}px {n(cy)}px",
        "needle_tip": n(cx + radius - 4),
        "cx": cx, "cy": cy,
        "value_y": n(cy - 6 if half else cy + 4),
        "label_y": n(cy + 14 if half else cy + 30),
        "min_xy": under(start),
        "max_xy": under(start + sweep),
        "text": "–" if v is None else fmt_value(v, fmt),
        "min_text": fmt_value(lo, fmt), "max_text": fmt_value(hi, fmt),
    }


# ------------------------------------------------------------------ funnel
def _share(part, whole):
    pct = part / whole * 100 if whole else 0.0
    return f"{pct:.0f}%" if pct >= 10 or pct == 0 else f"{pct:.1f}%"


def funnel(slices, *, width, height, fmt=None, shape="bars", color=None, label_head="", kind="Funnel",
           empty="No data") -> Scene:
    width = max(float(width), 160.0)
    shown = [(j, s) for j, s in enumerate(slices) if s.value is not None and s.value >= 0]
    height = float(height) if height else 44.0 * max(len(shown), 1) + 12
    scene = Scene(width, height)
    first = shown[0][1].value if shown else 0.0
    scene.head = [label_head, "Value", "Of first", "From previous"]
    scene.rows = [[s.label, fmt_value(s.value, fmt), _share(s.value, first) if k else "100%",
                   _share(s.value, shown[k - 1][1].value) if k else ""] for k, (j, s) in enumerate(shown)]
    scene.summary = f"{kind} chart, {len(shown)} stages" + (
        f", from {fmt_value(first, fmt)} to {fmt_value(shown[-1][1].value, fmt)}" if shown else "")

    def payload(hit, key=None):
        k = max(0, min(hit, len(shown) - 1))
        j, s = shown[k]
        previous = shown[k - 1][1].value if k else s.value
        return {"index": j, "label": s.label, "value": s.value,
                "percent": s.value / first * 100 if first else 0.0,
                "conversion": s.value / previous * 100 if previous else 0.0, "row": s.row}

    scene.payload = payload
    if not shown:
        scene.marks.append(Mark("text", "empty", "empty", x=n(width / 2), y=n(height / 2), text=empty,
                                anchor="middle", baseline="middle"))
        return scene
    right_texts = [f"{fmt_value(s.value, fmt)} · {_share(s.value, first)}" for _, s in shown]
    left = min(widest([s.label for _, s in shown]), width * 0.3) + 12
    right = widest(right_texts) * (12 / 11) + 10
    x0, x1 = left, max(left + 20, width - right)
    room, mid = x1 - x0, (x0 + x1) / 2
    row = (height - 12) / len(shown)
    thick = row if shape == "funnel" else row * 0.72
    top = max(s.value for _, s in shown) or 1.0
    widths = [max(2.0, room * s.value / top) for _, s in shown]
    chars = int((left - 12) / (11 * 0.58))
    for k, (j, s) in enumerate(shown):
        paint = color_of(color, 0) if color is not None else s.color
        y = 6 + row * k + (row - thick) / 2
        w = widths[k]
        if shape == "funnel":
            w2 = widths[k + 1] if k + 1 < len(shown) else w
            gap = 1.0
            d = (f"M{n(mid - w / 2)},{n(y + gap)} L{n(mid + w / 2)},{n(y + gap)} "
                 f"L{n(mid + w2 / 2)},{n(y + thick - gap)} L{n(mid - w2 / 2)},{n(y + thick - gap)} Z")
            shape_mark = Mark("path", f"s{j}", "stage hit", style=f"fill: {paint}", d=d, hit=k)
        else:
            shape_mark = Mark("rect", f"s{j}", "stage hit", style=f"fill: {paint}", x=n(mid - w / 2), y=n(y),
                              w=n(w), h=n(thick), rx=3, hit=k)
            if k + 1 < len(shown):
                w2, y2 = widths[k + 1], 6 + row * (k + 1) + (row - thick) / 2
                scene.marks.append(Mark("path", f"n{j}", "neck", style=f"fill: {paint}",
                                        d=f"M{n(mid - w / 2)},{n(y + thick)} L{n(mid + w / 2)},{n(y + thick)} "
                                          f"L{n(mid + w2 / 2)},{n(y2)} L{n(mid - w2 / 2)},{n(y2)} Z"))
        scene.marks.append(shape_mark)
        cy = y + thick / 2
        scene.marks.append(Mark("text", f"l{j}", "tick", x=n(left - 10), y=n(cy), text=cut(s.label, chars),
                                anchor="end", baseline="middle"))
        scene.marks.append(Mark("text", f"v{j}", "stage-value", x=n(x1 + 8), y=n(cy), text=right_texts[k],
                                baseline="middle"))
        rows = [("value", paint, "", fmt_value(s.value, fmt)), ("first", None, "Of first", _share(s.value, first))]
        if k:
            before = shown[k - 1][1].value
            rows += [("prev", None, "From previous", _share(s.value, before)),
                     ("lost", None, "Lost", fmt_value(before - s.value, fmt))]
        light = [Mark("rect", "hover-band", "hover-band", x=0, y=n(6 + row * k), w=n(width), h=n(row))]
        scene.tips.append(Tip(s.label, rows, n(mid + w / 2 + 6), n(cy), "right mid", light)
                          if mid + w / 2 < width * 0.55 else Tip(s.label, rows, n(mid), n(y + thick), "right", light))
    return scene


# --------------------------------------------------------------- waterfall
def waterfall(slices, *, width, height, totals=(), total_field="total", fmt=None, tick_fmt=None, labels=True,
              x_label="", y_label="", up=None, down=None, total_color=None, kind="Waterfall",
              empty="No data") -> Scene:
    """Bars that start where the last one ended. A slice is a total when its
    row's ``total_field`` is true or its label is in ``totals``: it stands on
    zero and shows the running total (or its own value, when it has one)."""
    width, height = max(float(width), 160.0), max(float(height), 120.0)
    up, down = color_of(up or "success", 0), color_of(down or "danger", 0)
    total_paint = color_of(total_color, 0)
    names = set(totals or ())
    steps, running = [], 0.0
    for s in slices:
        is_total = s.label in names or (s.row is not None and bool(field(s.row, total_field)))
        if is_total:
            top = s.value if s.value is not None else running
            steps.append((s, 0.0, top, "total", top))
            running = top
        else:
            change = s.value or 0.0
            steps.append((s, running, running + change, "up" if change >= 0 else "down", change))
            running += change
    count = len(steps)
    scene = Scene(width, height)
    scene.head = [x_label, "Change", "Total"]
    scene.rows = [[s.label, "" if how == "total" else _signed(v, fmt), fmt_value(top, fmt)]
                  for s, base, top, how, v in steps]
    scene.summary = f"{kind} chart, {count} steps" + (f", ending at {fmt_value(running, fmt)}" if count else "")
    scene.legend = []

    def payload(i, key=None):
        s, base, top, how, v = steps[max(0, min(i, count - 1))]
        return {"index": i, "label": s.label, "value": s.value if how != "total" else top, "total": top,
                "is_total": how == "total", "row": s.row}

    scene.payload = payload
    if not count:
        scene.marks.append(Mark("text", "empty", "empty", x=n(width / 2), y=n(height / 2), text=empty,
                                anchor="middle", baseline="middle"))
        return scene
    axis = value_axis([v for _, b, t, _, _ in steps for v in (b, t)], max(2, int((height - 50) / 45)),
                      fmt=tick_fmt, zero=True)
    px0 = widest(axis.texts) + 10 + (18 if y_label else 0)
    px1 = width - 14
    py0, py1 = 10.0 + (14 if labels else 0), height - 24 - (18 if x_label else 0)
    ys = LinearScale((axis.lo, axis.hi), (py1, py0))
    step = (px1 - px0) / count
    centers = [px0 + step * (i + 0.5) for i in range(count)]
    thick = min(step * 0.7, 80.0)
    marks = scene.marks
    for j, (v, text) in enumerate(zip(axis.values, axis.texts)):
        p = n(ys(v))
        marks.append(Mark("line", f"g{j}", "grid zero" if v == 0 and axis.lo < 0 else "grid",
                          x1=n(px0), x2=n(px1), y1=p, y2=p))
        marks.append(Mark("text", f"t{j}", "tick", x=n(px0 - 8), y=p, text=text, anchor="end", baseline="middle"))
    marks.append(Mark("line", "axis", "axis", x1=n(px0), x2=n(px1), y1=n(py1), y2=n(py1)))
    marks.extend(category_labels([s.label for s, *_ in steps], centers, step, py1 + 16))
    if x_label:
        marks.append(Mark("text", "title-bottom", "axis-title", x=n((px0 + px1) / 2), y=n(height - 6),
                          text=x_label, anchor="middle"))
    if y_label:
        mid = n((py0 + py1) / 2)
        marks.append(Mark("text", "title-side", "axis-title", x=12, y=mid, text=y_label, anchor="middle",
                          baseline="middle", transform=f"rotate(-90 12 {mid})"))
    for i in range(count):
        marks.append(Mark("rect", f"h{i}", "hit band", x=n(px0 + step * i), y=n(py0), w=n(step), h=n(py1 - py0),
                          hit=i))
    for i, (s, base, top, how, v) in enumerate(steps):
        a, b = sorted((ys(base), ys(top)))
        paint = {"up": up, "down": down}.get(how, total_paint)
        marks.append(Mark("rect", f"b{i}", "bar hit", style=f"fill: {paint}", x=n(centers[i] - thick / 2), y=n(a),
                          w=n(thick), h=n(max(b - a, 1.0)), rx=n(min(3.0, thick / 4)), hit=i))
        if i + 1 < count:
            level = n(ys(top))
            marks.append(Mark("line", f"k{i}", "connector", x1=n(centers[i] + thick / 2),
                              x2=n(centers[i + 1] - thick / 2), y1=level, y2=level))
        if labels:
            text = fmt_value(top, fmt) if how == "total" else _signed(v, fmt)
            above = how == "up" or (how == "total" and top >= 0)
            if text_width(text) <= step + 4:
                marks.append(Mark("text", f"l{i}", "value-label", x=n(centers[i]), y=n(a - 5 if above else b + 13),
                                  text=text, anchor="middle"))
    for i, (s, base, top, how, v) in enumerate(steps):
        rows = [("total", None, "Total", fmt_value(top, fmt))] if how == "total" else \
            [("change", up if how == "up" else down, "Change", _signed(v, fmt)),
             ("total", None, "Running total", fmt_value(top, fmt))]
        light = [Mark("rect", "hover-band", "hover-band", x=n(px0 + step * i), y=n(py0), w=n(step), h=n(py1 - py0))]
        right = centers[i] < width / 2
        scene.tips.append(Tip(s.label, rows, n(px0 + step * (i + 1) if right else px0 + step * i), n(py0),
                              "right" if right else "left", light))
    return scene


def _signed(v, fmt) -> str:
    text = fmt_value(abs(v), fmt)
    return ("+" if v >= 0 else "−") + text
