"""Small statistics for charts, in plain Python (no numpy needed)."""

from __future__ import annotations

import math
from dataclasses import dataclass, field

from .scales import tick_step


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


def mean(values) -> float | None:
    vals = [v for v in values if v is not None]
    return sum(vals) / len(vals) if vals else None


def std(values) -> float:
    """Sample standard deviation (0 for fewer than two values)."""
    vals = [v for v in values if v is not None]
    if len(vals) < 2:
        return 0.0
    m = sum(vals) / len(vals)
    return math.sqrt(sum((v - m) ** 2 for v in vals) / (len(vals) - 1))


def quantile(ordered, q: float) -> float:
    """The q-quantile of sorted values, interpolating between neighbours
    (the method numpy, pandas and spreadsheets use by default)."""
    if not ordered:
        raise ValueError("no values")
    pos = (len(ordered) - 1) * q
    lo = math.floor(pos)
    hi = min(lo + 1, len(ordered) - 1)
    return ordered[lo] + (ordered[hi] - ordered[lo]) * (pos - lo)


@dataclass
class Summary:
    """What a box plot draws: quartiles, whiskers (the furthest values
    within 1.5 IQR of the box), outliers beyond them, and the mean."""

    count: int
    low: float
    q1: float
    median: float
    q3: float
    high: float
    mean: float
    smallest: float
    largest: float
    outliers: list = field(default_factory=list)


def summary(values) -> Summary | None:
    ordered = sorted(v for v in values if v is not None)
    if not ordered:
        return None
    q1, med, q3 = quantile(ordered, 0.25), quantile(ordered, 0.5), quantile(ordered, 0.75)
    reach = 1.5 * (q3 - q1)
    inside = [v for v in ordered if q1 - reach <= v <= q3 + reach]
    return Summary(len(ordered), inside[0], q1, med, q3, inside[-1], sum(ordered) / len(ordered),
                   ordered[0], ordered[-1], [v for v in ordered if v < q1 - reach or v > q3 + reach])


def bandwidth(values) -> float:
    """Silverman's rule of thumb for a kernel density estimate."""
    vals = sorted(v for v in values if v is not None)
    if len(vals) < 2:
        return 1.0
    spread = std(vals)
    iqr = quantile(vals, 0.75) - quantile(vals, 0.25)
    scale = min(spread, iqr / 1.34) if iqr > 0 else spread
    return 0.9 * (scale or abs(vals[0]) or 1.0) * len(vals) ** -0.2


def kde(values, points, width: float | None = None) -> list[float]:
    """Gaussian kernel density of ``values`` at each of ``points``."""
    vals = [v for v in values if v is not None]
    if not vals:
        return [0.0 for _ in points]
    h = width or bandwidth(vals)
    norm = 1.0 / (len(vals) * h * math.sqrt(2 * math.pi))
    return [norm * sum(math.exp(-0.5 * ((x - v) / h) ** 2) for v in vals) for x in points]


def bin_edges(values, bins=None) -> list[float]:
    """Edges of histogram bins on round numbers. ``bins``: None (choose:
    the Freedman-Diaconis width, or Sturges' count for small or flat
    data), a count, a width given as text ("width:5"), or the edges."""
    vals = [v for v in values if v is not None]
    if isinstance(bins, (list, tuple)):
        return sorted(float(b) for b in bins)
    if not vals:
        return [0.0, 1.0]
    lo, hi = min(vals), max(vals)
    if lo == hi:
        return [lo - 0.5, hi + 0.5]
    if isinstance(bins, str) and bins.startswith("width:"):
        step = float(bins.split(":", 1)[1])
    else:
        if bins:
            count = int(bins)
        else:
            ordered = sorted(vals)
            iqr = quantile(ordered, 0.75) - quantile(ordered, 0.25)
            fd = 2 * iqr / len(vals) ** (1 / 3)
            count = math.ceil((hi - lo) / fd) if fd > 0 else math.ceil(math.log2(len(vals))) + 1
            count = max(1, min(count, 60))
        step = tick_step(lo, hi, max(count, 1))
    first = math.floor(lo / step) * step
    edges = [first]
    while edges[-1] < hi:
        edges.append(round(first + step * len(edges), 10))
    return edges


def bin_counts(values, edges) -> list[int]:
    """How many values fall in each bin; the last bin includes its right edge."""
    counts = [0] * (len(edges) - 1)
    for v in values:
        if v is None or v < edges[0] or v > edges[-1]:
            continue
        lo, hi = 0, len(edges) - 1
        while hi - lo > 1:
            mid = (lo + hi) // 2
            if v >= edges[mid]:
                lo = mid
            else:
                hi = mid
        counts[min(lo, len(counts) - 1)] += 1
    return counts


def pearson(xs, ys) -> float | None:
    pairs = [(x, y) for x, y in zip(xs, ys) if x is not None and y is not None]
    if len(pairs) < 2:
        return None
    mx = sum(x for x, _ in pairs) / len(pairs)
    my = sum(y for _, y in pairs) / len(pairs)
    sxy = sum((x - mx) * (y - my) for x, y in pairs)
    sxx = sum((x - mx) ** 2 for x, _ in pairs)
    syy = sum((y - my) ** 2 for _, y in pairs)
    return sxy / math.sqrt(sxx * syy) if sxx and syy else None


def ranks(values) -> list:
    """Ranks (1-based, ties share their average rank), None kept as None."""
    order = sorted((v, i) for i, v in enumerate(values) if v is not None)
    out = [None] * len(values)
    i = 0
    while i < len(order):
        j = i
        while j + 1 < len(order) and order[j + 1][0] == order[i][0]:
            j += 1
        for k in range(i, j + 1):
            out[order[k][1]] = (i + j) / 2 + 1
        i = j + 1
    return out


def spearman(xs, ys) -> float | None:
    pairs = [(x, y) for x, y in zip(xs, ys) if x is not None and y is not None]
    if len(pairs) < 2:
        return None
    return pearson(ranks([x for x, _ in pairs]), ranks([y for _, y in pairs]))


def moving_average(values, window: int) -> list:
    """The mean of the last ``window`` values at each point (None until
    there are that many)."""
    out, run, total = [], [], 0.0
    for v in values:
        run.append(v)
        total += v or 0.0
        if len(run) > window:
            total -= run.pop(0) or 0.0
        out.append(total / window if len(run) == window and None not in run else None)
    return out
