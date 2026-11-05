"""Axis arithmetic: round tick values, linear scales, number formatting."""

from __future__ import annotations

import math
from collections.abc import Callable

_E10, _E5, _E2 = math.sqrt(50), math.sqrt(10), math.sqrt(2)


def tick_step(lo: float, hi: float, count: int) -> float:
    """A step of 1, 2 or 5 times a power of ten giving about ``count`` ticks."""
    span = abs(hi - lo)
    if span == 0 or count <= 0:
        return 1.0
    raw = span / count
    step = 10 ** math.floor(math.log10(raw))
    err = raw / step
    if err >= _E10:
        step *= 10
    elif err >= _E5:
        step *= 5
    elif err >= _E2:
        step *= 2
    return step


def nice(lo: float, hi: float, count: int = 5) -> tuple[float, float]:
    """Widen [lo, hi] to whole steps, so the axis starts and ends on a tick."""
    if lo == hi:
        return lo, hi
    for _ in range(2):  # the second pass settles a step changed by widening
        step = tick_step(lo, hi, count)
        lo, hi = math.floor(lo / step) * step, math.ceil(hi / step) * step
    return _clean(lo, step), _clean(hi, step)


def ticks(lo: float, hi: float, count: int = 5) -> list[float]:
    step = tick_step(lo, hi, count)
    first, last = math.ceil(lo / step - 1e-9), math.floor(hi / step + 1e-9)
    return [_clean(k * step, step) for k in range(first, last + 1)]


def _clean(v: float, step: float) -> float:
    """0.30000000000000004 -> 0.3: round to the step's decimals."""
    digits = max(0, -math.floor(math.log10(step)) + 1) if step > 0 else 0
    v = round(v, digits)
    return 0.0 if v == 0 else v


class LinearScale:
    def __init__(self, domain: tuple[float, float], span: tuple[float, float]):
        self.d0, self.d1 = domain
        self.r0, self.r1 = span

    def __call__(self, v: float) -> float:
        if self.d1 == self.d0:
            return (self.r0 + self.r1) / 2
        return self.r0 + (v - self.d0) / (self.d1 - self.d0) * (self.r1 - self.r0)

    def clamp(self, v: float) -> float:
        lo, hi = sorted((self.d0, self.d1))
        return self(min(max(v, lo), hi))


Format = str | Callable[[float], str] | None


def fmt_value(v, fmt: Format = None) -> str:
    """A value for tooltips and labels. ``fmt`` is a format spec (",.2f"),
    a template ("{:.1f} kg", "${:,.0f}") or a function."""
    if v is None:
        return "–"
    if callable(fmt):
        return str(fmt(v))
    if fmt:
        return fmt.format(v) if "{" in fmt else format(v, fmt)
    if isinstance(v, float):
        if v.is_integer() and abs(v) < 1e15:
            return f"{int(v):,}"
        return f"{v:,.2f}".rstrip("0").rstrip(".")
    if isinstance(v, int):
        return f"{v:,}"
    return str(v)


def fmt_tick(v: float, step: float, fmt: Format = None) -> str:
    """An axis label: short (12k, 1.5M) unless the chart says otherwise."""
    if fmt:
        return fmt_value(v, fmt)
    a = abs(v)
    for size, suffix in ((1e12, "T"), (1e9, "B"), (1e6, "M"), (1e3, "k")):
        if a >= size and step >= size / 10:
            return _trim(v / size, step / size) + suffix
    return _trim(v, step)


def _trim(v: float, step: float) -> str:
    digits = max(0, -math.floor(math.log10(step))) if 0 < step < 1 else 0
    text = f"{v:,.{digits}f}"
    return "0" if text in ("-0", "-0.0") else text
