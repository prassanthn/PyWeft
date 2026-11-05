"""Grids of coloured cells: heatmaps, correlation matrices, calendars."""

from __future__ import annotations

import datetime as _dt
from collections.abc import Mapping, Sequence

from .axes import cut, empty, widest
from .data import _first_key, _keys, color_of, field, ink, label_text, mix, number, ramp, readable, rows_of
from .scales import fmt_tick, fmt_value, tick_step
from .scene import Mark, Scene, Tip, n, text_width
from .stats import pearson, quantile, spearman

LOW = "var(--ui-info, #0969da)"
HIGH = "var(--ui-danger, #d1242f)"


def heat_input(data, x="", y="", value="", x_labels=(), y_labels=()):
    """(column names, row names, matrix of numbers or None). Data: a list
    of lists (named by x_labels/y_labels), a {row: {column: value}} dict,
    or rows with x, y and value fields (values for the same cell add up)."""
    if isinstance(data, Sequence) and data and all(isinstance(r, Sequence) and not isinstance(r, str) for r in data):
        width = max(len(r) for r in data)
        xs = [str(v) for v in x_labels] or [str(i + 1) for i in range(width)]
        ys = [str(v) for v in y_labels] or [str(i + 1) for i in range(len(data))]
        return xs, ys, [[number(r[j]) if j < len(r) else None for j in range(len(xs))] for r in data]
    if isinstance(data, Mapping) and data and all(isinstance(v, Mapping) for v in data.values()):
        ys = [label_text(k) for k in data]
        xs = list(dict.fromkeys(label_text(k) for inner in data.values() for k in inner))
        matrix = [[None] * len(xs) for _ in ys]
        for i, inner in enumerate(data.values()):
            for k, v in inner.items():
                matrix[i][xs.index(label_text(k))] = number(v)
        return xs, ys, matrix
    rows = rows_of(data)
    if rows:
        texts = [k for k in _keys(rows[0]) if number(field(rows[0], k)) is None or isinstance(field(rows[0], k), str)]
        x = x or (texts[0] if texts else None)
        y = y or (texts[1] if len(texts) > 1 else None)
        value = value or _first_key(rows, want_number=True)
    xs = list(dict.fromkeys(label_text(field(r, x)) for r in rows))
    ys = list(dict.fromkeys(label_text(field(r, y)) for r in rows))
    matrix = [[None] * len(xs) for _ in ys]
    for r in rows:
        v = number(field(r, value))
        if v is None:
            continue
        i, j = ys.index(label_text(field(r, y))), xs.index(label_text(field(r, x)))
        matrix[i][j] = v if matrix[i][j] is None else matrix[i][j] + v
    return xs, ys, matrix


def correlation(data, fields=(), method="pearson"):
    """(names, matrix) of correlations between number fields of rows (all
    of them unless ``fields`` names some)."""
    rows = rows_of(data)
    if isinstance(fields, str):
        fields = [f.strip() for f in fields.split(",") if f.strip()]
    if not fields and rows:
        fields = [k for k in _keys(rows[0]) if number(field(rows[0], k)) is not None
                  and not isinstance(field(rows[0], k), str)]
    columns = {f: [number(field(r, f)) for r in rows] for f in fields}
    pick = spearman if method == "spearman" else pearson
    matrix = [[1.0 if a == b else pick(columns[b], columns[a]) for b in fields] for a in fields]
    return [readable(f) for f in fields], matrix


def heatmap(x_names, y_names, matrix, *, width, height, lo=None, hi=None, color=None, low_color=None,
            diverging=False, center=0.0, labels=False, fmt=None, x_label="", y_label="", skip=None, legend=True,
            kind="Heatmap", empty_text="No data") -> Scene:
    width = max(float(width), 160.0)
    high = color_of(color, 0) if color or not diverging else HIGH
    low = color_of(low_color, 0) if low_color else LOW
    values = [v for row in matrix for v in row if v is not None]
    cols, count = len(x_names), len(y_names)
    scene = Scene(width, float(height) if height else 300.0)
    scene.head = ["", *x_names]
    scene.rows = [[y_names[i], *[fmt_value(v, fmt) for v in row]] for i, row in enumerate(matrix)]
    scene.summary = f"{kind}, {count} rows by {cols} columns" + (
        f", values from {fmt_value(min(values), fmt)} to {fmt_value(max(values), fmt)}" if values else "")
    if not values or not cols or not count:
        scene.payload = lambda i, key=None: {"index": i}
        return empty(scene, empty_text)
    vmin = float(lo) if lo is not None else min(values)
    vmax = float(hi) if hi is not None else max(values)
    if diverging:
        spread = max(abs(vmin - center), abs(vmax - center)) or 1.0
        vmin, vmax = (center - spread, center + spread) if lo is None and hi is None else (vmin, vmax)

    def t_of(v):
        if v is None:
            return None
        if diverging:
            return 0.5 + (v - center) / (2 * max(vmax - center, center - vmin, 1e-12))
        return (v - vmin) / (vmax - vmin) if vmax > vmin else 1.0

    left = min(widest(y_names), width * 0.3) + 10 + (18 if y_label else 0)
    right = 14.0 + (58 if legend else 0)
    px0, px1 = left, max(left + 20, width - right)
    cell_w = (px1 - px0) / cols
    tilt = widest(x_names) + 6 > cell_w
    bottom = (min(widest(x_names), 90) * 0.71 + 14 if tilt else 22) + (18 if x_label else 0)
    top = 8.0
    if not height:
        cell_h = max(16.0, min(cell_w, 40.0))
        scene.height = top + cell_h * count + bottom
    py0, py1 = top, scene.height - bottom
    cell_h = (py1 - py0) / count
    marks = scene.marks
    cells = []
    for i, row in enumerate(matrix):
        for j, v in enumerate(row):
            if skip and skip(i, j):
                continue
            t = t_of(v)
            x, y = px0 + cell_w * j, py0 + cell_h * i
            hit = len(cells)
            cells.append((i, j, v, x, y))
            marks.append(Mark("rect", f"c{i}|{j}", "cell hit", style=f"fill: {ramp(t, low, high, diverging)}",
                              x=n(x + 0.5), y=n(y + 0.5), w=n(max(cell_w - 1, 0.5)), h=n(max(cell_h - 1, 0.5)),
                              rx=2, hit=hit))
            if labels and v is not None:
                text = fmt_value(v, fmt)
                if cell_w >= text_width(text) + 4 and cell_h >= 14:
                    marks.append(Mark("text", f"v{i}|{j}", "cell-label", style=f"fill: {ink(t, diverging)}",
                                      x=n(x + cell_w / 2), y=n(y + cell_h / 2), text=text, anchor="middle",
                                      baseline="middle"))
    chars = int((left - 10 - (18 if y_label else 0)) / (11 * 0.58))
    every = max(1, int(14 // max(cell_h, 1)) + (1 if cell_h < 14 else 0))
    for i, name in enumerate(y_names):
        if i % every == 0:
            marks.append(Mark("text", f"y{i}", "tick", x=n(px0 - 6), y=n(py0 + cell_h * (i + 0.5)),
                              text=cut(name, chars), anchor="end", baseline="middle"))
    every = max(1, int(14 // max(cell_w, 1)) + (1 if cell_w < 14 else 0)) if tilt else 1
    for j, name in enumerate(x_names):
        if j % every:
            continue
        x, y = n(px0 + cell_w * (j + 0.5)), n(py1 + 14)
        if tilt:
            marks.append(Mark("text", f"x{j}", "tick", x=x, y=n(py1 + 8), text=cut(name, 16), anchor="end",
                              baseline="middle", transform=f"rotate(-45 {x} {n(py1 + 8)})"))
        else:
            marks.append(Mark("text", f"x{j}", "tick", x=x, y=y, text=name, anchor="middle"))
    if x_label:
        marks.append(Mark("text", "title-bottom", "axis-title", x=n((px0 + px1) / 2), y=n(scene.height - 6),
                          text=x_label, anchor="middle"))
    if y_label:
        mid = n((py0 + py1) / 2)
        marks.append(Mark("text", "title-side", "axis-title", x=12, y=mid, text=y_label, anchor="middle",
                          baseline="middle", transform=f"rotate(-90 12 {mid})"))
    if legend:
        steps, bar_x = 24, px1 + 14
        span = py1 - py0
        for k in range(steps):
            t = 1 - (k + 0.5) / steps
            marks.append(Mark("rect", f"lg{k}", "", style=f"fill: {ramp(t, low, high, diverging)}", x=n(bar_x),
                              y=n(py0 + span * k / steps), w=10, h=n(span / steps + 0.5)))
        step = tick_step(vmin, vmax, 4)
        for key, v, y in (("hi", vmax, py0), ("mid", (vmin + vmax) / 2, (py0 + py1) / 2), ("lo", vmin, py1)):
            marks.append(Mark("text", f"lg-{key}", "tick", x=n(bar_x + 14), y=n(y), text=fmt_tick(v, step, fmt),
                              baseline="middle"))
    for hit, (i, j, v, x, y) in enumerate(cells):
        light = [Mark("rect", "hover-cell", "hover-cell", x=n(x + 0.5), y=n(y + 0.5), w=n(max(cell_w - 1, 0.5)),
                      h=n(max(cell_h - 1, 0.5)), rx=2)]
        swatch = ramp(t_of(v), low, high, diverging)
        right = x + cell_w < width / 2
        scene.tips.append(Tip(f"{y_names[i]} · {x_names[j]}", [("v", swatch, "", fmt_value(v, fmt))],
                              n(x + cell_w if right else x), n(y + cell_h / 2), "right mid" if right else "left mid",
                              light))
    scene.payload = lambda hit, key=None: (lambda c: {"index": hit, "x": x_names[c[1]], "y": y_names[c[0]],
                                                      "value": c[2], "row": c[0], "column": c[1]})(cells[hit])
    return scene


# ---------------------------------------------------------------- calendar
MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
WEEKDAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]


def to_date(v) -> _dt.date | None:
    if isinstance(v, _dt.datetime):
        return v.date()
    if isinstance(v, _dt.date):
        return v
    if isinstance(v, str):
        try:
            return _dt.date.fromisoformat(v.strip()[:10])
        except ValueError:
            return None
    return None


def days_input(data, date="", value="") -> dict:
    """{date: total} from rows with a date and a value (a row without a
    value counts 1), or a {date: value} dict."""
    if isinstance(data, Mapping) and not any(isinstance(v, (list, tuple)) for v in data.values()):
        items = [(to_date(k), number(v)) for k, v in data.items()]
    else:
        rows = rows_of(data)
        if rows and not date:
            date = next((k for k in _keys(rows[0]) if to_date(field(rows[0], k))), None)
        if rows and not value:
            value = _first_key(rows, want_number=True)
        items = [(to_date(field(r, date)), number(field(r, value)) if value else 1.0) for r in rows]
    days = {}
    for d, v in items:
        if d is not None and v is not None:
            days[d] = days.get(d, 0.0) + v
    return days


def spoken_date(d: _dt.date) -> str:
    return f"{WEEKDAYS[d.weekday()]} {d.day} {MONTHS[d.month - 1]} {d.year}"


def calendar(days, *, width, start=None, end=None, week_start=0, color=None, fmt=None, kind="Calendar",
             empty_text="No data") -> Scene:
    width = max(float(width), 160.0)
    paint = color_of(color, 0)
    end = to_date(end) or (max(days) if days else _dt.date.today())
    start = to_date(start) or end - _dt.timedelta(days=364)
    first = start - _dt.timedelta(days=(start.weekday() - week_start) % 7)
    weeks = (end - first).days // 7 + 1
    left, top, gap = 30.0, 18.0, 3.0
    room = width - left - 4
    cell = min(18.0, room / weeks - gap)
    if cell < 9:  # too narrow for the whole range: keep the latest weeks
        cell = 9.0
        keep = max(1, int((room + gap) // (cell + gap)))
        first += _dt.timedelta(days=7 * (weeks - keep))
        weeks = keep
    height = top + 7 * (cell + gap) + 30
    scene = Scene(width, height)
    shown = {d: v for d, v in days.items() if start <= d <= end and d >= first}
    total = sum(shown.values())
    scene.summary = (f"{kind} from {spoken_date(max(start, first))} to {spoken_date(end)}: "
                     f"{len(shown)} days with data, total {fmt_value(total, fmt)}")
    scene.head = ["Date", "Value"]
    scene.rows = [[d.isoformat(), fmt_value(v, fmt)] for d, v in sorted(shown.items())]
    positive = sorted(v for v in shown.values() if v > 0)
    cuts = [quantile(positive, q) for q in (0.25, 0.5, 0.75)] if positive else []

    def level(v):
        if v is None or v <= 0 or not cuts:
            return 0
        return 1 + sum(v > c for c in cuts)

    shades = ["var(--ui-subtle, #f6f8fa)", mix(paint, 30), mix(paint, 55), mix(paint, 78), paint]
    marks = scene.marks
    dates = []
    for k in range(weeks * 7):
        d = first + _dt.timedelta(days=k)
        if d < start or d > end:
            continue
        col, row = k // 7, k % 7
        x, y = left + col * (cell + gap), top + row * (cell + gap)
        v = shown.get(d)
        hit = len(dates)
        dates.append((d, v, x, y))
        marks.append(Mark("rect", f"d{d.isoformat()}", "day hit", style=f"fill: {shades[level(v)]}", x=n(x), y=n(y),
                          w=n(cell), h=n(cell), rx=2, hit=hit))
    months = []  # (column, month): each week holding the 1st of a month
    for col in range(weeks):
        week = [first + _dt.timedelta(days=col * 7 + r) for r in range(7)]
        firsts = [d for d in week if d.day == 1 and start <= d <= end]
        if firsts:
            months.append((col, firsts[0].month))
    if not months or months[0][0] > 2:
        months.insert(0, (0, max(start, first).month))
    last_x = -99.0
    for col, month in months:
        x = left + col * (cell + gap)
        if x - last_x >= 28:
            marks.append(Mark("text", f"m{col}", "tick", x=n(x), y=n(top - 6), text=MONTHS[month - 1]))
            last_x = x
    for row in (0, 2, 4):
        name = WEEKDAYS[(week_start + row) % 7]
        marks.append(Mark("text", f"w{row}", "tick", x=n(left - 6), y=n(top + row * (cell + gap) + cell / 2),
                          text=name, anchor="end", baseline="middle"))
    key_y = top + 7 * (cell + gap) + 8
    key_x = width - 4 - 5 * (cell + gap) - 30
    marks.append(Mark("text", "less", "tick", x=n(key_x - 6), y=n(key_y + cell / 2), text="Less", anchor="end",
                      baseline="middle"))
    for k, shade in enumerate(shades):
        marks.append(Mark("rect", f"key{k}", "", style=f"fill: {shade}", x=n(key_x + k * (cell + gap)), y=n(key_y),
                          w=n(cell), h=n(cell), rx=2))
    marks.append(Mark("text", "more", "tick", x=n(key_x + 5 * (cell + gap) + 2), y=n(key_y + cell / 2), text="More",
                      baseline="middle"))
    for d, v, x, y in dates:
        light = [Mark("rect", "hover-cell", "hover-cell", x=n(x), y=n(y), w=n(cell), h=n(cell), rx=2)]
        right = x < width / 2
        scene.tips.append(Tip(spoken_date(d), [("v", shades[level(v)], "", "No data" if v is None else fmt_value(v, fmt))],
                              n(x + cell if right else x), n(y + cell / 2), "right mid" if right else "left mid", light))
    scene.payload = lambda hit, key=None: {"index": hit, "date": dates[hit][0], "value": dates[hit][1]}
    if not dates:
        return empty(scene, empty_text)
    return scene
