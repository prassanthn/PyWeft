"""Candlestick (and OHLC) charts, with volume and moving averages."""

from __future__ import annotations

from dataclasses import dataclass

from .axes import category_labels, empty, value_axis, widest, y_ticks
from .data import _keys, color_of, field, label_text, number, rows_of
from .scales import LinearScale, fmt_tick, fmt_value, tick_step
from .scene import LegendItem, Mark, Scene, Tip, n
from .stats import moving_average


@dataclass
class Candle:
    label: str
    open: float
    high: float
    low: float
    close: float
    volume: float | None = None
    row: object = None


def _named(row, want):
    """The row's field called ``want``, ignoring case ("Open", "OPEN")."""
    for k in _keys(row):
        if str(k).lower() == want:
            return k
    return want


def candles_input(data, date="", open="", high="", low="", close="", volume="") -> list[Candle]:
    rows = rows_of(data)
    if not rows:
        return []
    first = rows[0]
    names = {k: v or _named(first, k) for k, v in
             (("date", date), ("open", open), ("high", high), ("low", low), ("close", close), ("volume", volume))}
    out = []
    for r in rows:
        o, h, lo, c = (number(field(r, names[k])) for k in ("open", "high", "low", "close"))
        if None in (o, h, lo, c):
            continue
        out.append(Candle(label_text(field(r, names["date"])), o, max(h, o, c), min(lo, o, c), c,
                          number(field(r, names["volume"])), r))
    return out


def candlestick(candles, *, width, height, hidden=frozenset(), averages=(), style="candle", volume=True,
                fmt=None, tick_fmt=None, up=None, down=None, y_label="", kind="Candlestick",
                empty_text="No data") -> Scene:
    width, height = max(float(width), 160.0), max(float(height), 140.0)
    up, down = color_of(up or "success", 0), color_of(down or "danger", 0)
    count = len(candles)
    closes = [c.close for c in candles]
    lines = [(int(w), moving_average(closes, int(w)), color_of(None, 2 + i)) for i, w in enumerate(averages or ())]
    has_volume = volume and any(c.volume for c in candles)
    scene = Scene(width, height)
    scene.legend = [LegendItem(f"sma{w}", f"{w}-day average", paint, f"sma{w}" in hidden, "line")
                    for w, _, paint in lines]
    if has_volume:
        scene.legend.append(LegendItem("volume", "Volume", "var(--ui-muted, #59636e)", "volume" in hidden))
    scene.head = ["Date", "Open", "High", "Low", "Close"] + (["Volume"] if has_volume else [])
    scene.rows = [[c.label, *[fmt_value(v, fmt) for v in (c.open, c.high, c.low, c.close)]]
                  + ([fmt_value(c.volume)] if has_volume else []) for c in candles]

    def payload(i, key=None):
        c = candles[max(0, min(i, count - 1))]
        return {"index": i, "date": c.label, "open": c.open, "high": c.high, "low": c.low, "close": c.close,
                "volume": c.volume, "row": c.row}

    scene.payload = payload
    if not count:
        scene.summary = f"{kind} chart with no data"
        return empty(scene, empty_text)
    scene.summary = (f"{kind} chart, {count} periods from {candles[0].label} to {candles[-1].label}: "
                     f"{fmt_value(candles[0].open, fmt)} to {fmt_value(candles[-1].close, fmt)}, "
                     f"low {fmt_value(min(c.low for c in candles), fmt)}, high {fmt_value(max(c.high for c in candles), fmt)}")
    show_volume = has_volume and "volume" not in hidden
    shown_lines = [(w, vals, paint) for w, vals, paint in lines if f"sma{w}" not in hidden]
    prices = [v for c in candles for v in (c.low, c.high)] + [v for _, vals, _ in shown_lines for v in vals if v]
    bottom = height - 24
    price_bottom = bottom - (bottom - 10) * 0.24 if show_volume else bottom
    Y = value_axis(prices, max(2, int((price_bottom - 10) / 45)), fmt=tick_fmt, pad=0.03)
    px0 = widest(Y.texts) + 10 + (18 if y_label else 0)
    px1 = width - 14
    py0, py1 = 10.0, price_bottom
    ys = LinearScale((Y.lo, Y.hi), (py1, py0))
    step = (px1 - px0) / count
    centers = [px0 + step * (i + 0.5) for i in range(count)]
    body = max(1.0, min(step * 0.7, 24.0))
    marks = scene.marks
    y_ticks(marks, Y, ys, px0, px1)
    if y_label:
        mid = n((py0 + py1) / 2)
        marks.append(Mark("text", "title-side", "axis-title", x=12, y=mid, text=y_label, anchor="middle",
                          baseline="middle", transform=f"rotate(-90 12 {mid})"))
    marks.append(Mark("line", "axis", "axis", x1=n(px0), x2=n(px1), y1=n(bottom), y2=n(bottom)))
    marks.extend(category_labels([c.label for c in candles], centers, step, bottom + 16))
    if show_volume:
        vy0, vy1 = price_bottom + 16, bottom
        top_volume = max(c.volume or 0 for c in candles) or 1.0
        vs = LinearScale((0.0, top_volume), (vy1, vy0))
        marks.append(Mark("line", "vgrid", "grid", x1=n(px0), x2=n(px1), y1=n(vy0), y2=n(vy0)))
        marks.append(Mark("text", "vtick", "tick", x=n(px0 - 8), y=n(vy0 + 6),  # inside the panel, clear of prices
                          text=fmt_tick(top_volume, tick_step(0, top_volume, 2)), anchor="end", baseline="middle"))
    for i in range(count):
        marks.append(Mark("rect", f"h{i}", "hit band", x=n(px0 + step * i), y=n(py0), w=n(step), h=n(bottom - py0),
                          hit=i))
    for i, c in enumerate(candles):
        rising = c.close >= c.open
        paint = up if rising else down
        x = centers[i]
        if show_volume and c.volume:
            top_ = vs(c.volume)
            marks.append(Mark("rect", f"vol{i}", "volume", style=f"fill: {paint}", x=n(x - body / 2), y=n(top_),
                              w=n(body), h=n(vy1 - top_)))
        marks.append(Mark("line", f"wick{i}", "wick", style=f"stroke: {paint}", x1=n(x), x2=n(x), y1=n(ys(c.high)),
                          y2=n(ys(c.low))))
        if style == "ohlc":
            marks.append(Mark("line", f"o{i}", "wick", style=f"stroke: {paint}", x1=n(x - body / 2), x2=n(x),
                              y1=n(ys(c.open)), y2=n(ys(c.open))))
            marks.append(Mark("line", f"c{i}", "wick", style=f"stroke: {paint}", x1=n(x), x2=n(x + body / 2),
                              y1=n(ys(c.close)), y2=n(ys(c.close))))
        else:
            a, b = sorted((ys(c.open), ys(c.close)))
            hollow = rising and style == "hollow"  # rising candles drawn as outlines
            marks.append(Mark("rect", f"b{i}", "candle hollow" if hollow else "candle",
                              style=f"stroke: {paint}" if hollow else f"fill: {paint}; stroke: {paint}",
                              x=n(x - body / 2), y=n(a), w=n(body), h=n(max(b - a, 1.0))))
    for w, vals, paint in shown_lines:
        run = []
        segments = []
        for i, v in enumerate(vals):
            if v is None:
                if run:
                    segments.append(run)
                run = []
            else:
                run.append(i)
        if run:
            segments.append(run)
        for k, seg in enumerate(segments):
            d = " ".join(("M" if j == 0 else "L") + f"{n(centers[i])},{n(ys(vals[i]))}" for j, i in enumerate(seg))
            marks.append(Mark("path", f"sma{w}|{k}", "line thin", style=f"stroke: {paint}", d=d))
    for i, c in enumerate(candles):
        before = candles[i - 1].close if i else c.open
        change = (c.close - before) / before * 100 if before else 0.0
        rows = [("open", None, "Open", fmt_value(c.open, fmt)), ("high", None, "High", fmt_value(c.high, fmt)),
                ("low", None, "Low", fmt_value(c.low, fmt)), ("close", up if c.close >= c.open else down, "Close",
                                                               fmt_value(c.close, fmt)),
                ("change", None, "Change", f"{change:+.2f}%")]
        if has_volume and c.volume is not None:
            rows.append(("volume", None, "Volume", fmt_value(c.volume)))
        for w, vals, paint in shown_lines:
            if vals[i] is not None:
                rows.append((f"sma{w}", paint, f"{w}-day average", fmt_value(round(vals[i], 4), fmt)))
        light = [Mark("rect", "hover-band", "hover-band", x=n(px0 + step * i), y=n(py0), w=n(step), h=n(bottom - py0))]
        right = centers[i] < width / 2
        scene.tips.append(Tip(c.label, rows, n(px0 + step * (i + 1) if right else px0 + step * i), n(py0),
                              "right" if right else "left", light))
    return scene
