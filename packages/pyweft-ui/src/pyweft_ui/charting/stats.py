"""Small statistics for charts, in plain Python (no numpy needed)."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class Fit:
    slope: float
    intercept: float
    r2: float

    def __call__(self, x: float) -> float:
        return self.intercept + self.slope * x


def linear_fit(xs, ys) -> Fit | None:
    """Least-squares line through the points; None with fewer than two
    distinct x values."""
    pairs = [(float(x), float(y)) for x, y in zip(xs, ys) if x is not None and y is not None]
    count = len(pairs)
    if count < 2:
        return None
    mx = sum(x for x, _ in pairs) / count
    my = sum(y for _, y in pairs) / count
    sxx = sum((x - mx) ** 2 for x, _ in pairs)
    if sxx == 0:
        return None
    sxy = sum((x - mx) * (y - my) for x, y in pairs)
    slope = sxy / sxx
    intercept = my - slope * mx
    total = sum((y - my) ** 2 for _, y in pairs)
    residual = sum((y - (intercept + slope * x)) ** 2 for x, y in pairs)
    return Fit(slope, intercept, 1.0 - residual / total if total else 1.0)
