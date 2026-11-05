"""Pieces several layouts share: a value axis, and category labels that
skip some when they would overlap."""

from __future__ import annotations

import math
from dataclasses import dataclass

from .scales import fmt_tick, nice, tick_step, ticks
from .scene import Mark, n, text_width


@dataclass
class Axis:
    lo: float
    hi: float
    values: list
    texts: list


def value_axis(values, count, lo_fix=None, hi_fix=None, fmt=None, zero=False, pad=0.0) -> Axis:
    """An axis covering ``values`` with about ``count`` round ticks.
    ``zero`` keeps 0 in range (bars); ``pad`` adds a fraction of the span
    each side, so dots at the extremes aren't cut in half."""
    vals = [v for v in values if v is not None] or [0.0, 1.0]
    lo, hi = float(min(vals)), float(max(vals))
    if pad and hi > lo:
        lo, hi = lo - (hi - lo) * pad, hi + (hi - lo) * pad
    if zero:
        lo, hi = min(lo, 0.0), max(hi, 0.0)
    lo = float(lo_fix) if lo_fix is not None else lo
    hi = float(hi_fix) if hi_fix is not None else hi
    if lo == hi:
        lo, hi = (lo - abs(lo) * 0.5 - 1, hi + abs(hi) * 0.5 + 1) if lo else (0.0, 1.0)
    nlo, nhi = nice(lo, hi, count)
    lo = lo if lo_fix is not None else nlo
    hi = hi if hi_fix is not None else nhi
    marks = ticks(lo, hi, count)
    step = tick_step(lo, hi, count)
    return Axis(lo, hi, marks, [fmt_tick(v, step, fmt) for v in marks])


def widest(texts) -> float:
    return max((text_width(t) for t in texts), default=0.0)


def cut(text: str, room: int) -> str:
    room = max(room, 4)
    return text if len(text) <= room else text[: room - 1].rstrip() + "…"


def category_labels(names, centers, step, y) -> list[Mark]:
    """Labels under a row of categories, every k-th one when they'd touch."""
    shortened = [cut(name, 24) for name in names]
    every = max(1, math.ceil((widest(shortened) + 8) / max(step, 1)))
    return [Mark("text", f"c{i}", "tick", x=n(centers[i]), y=n(y), text=name, anchor="middle")
            for i, name in enumerate(shortened) if i % every == 0]
