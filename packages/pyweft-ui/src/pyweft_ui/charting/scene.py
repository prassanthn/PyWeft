"""What a chart layout produces, and chart_view.weft draws."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field


@dataclass(slots=True)
class Mark:
    """One SVG shape. ``kind`` is rect, path, circle, line or text; only the
    fields that kind uses are set (the rest stay None, so the attribute is
    left out). ``hit`` makes it hoverable and clickable: the index of the
    tooltip it shows; ``series`` says which series a click picked."""

    kind: str
    key: str
    cls: str = ""
    style: str | None = None
    x: float | None = None
    y: float | None = None
    w: float | None = None
    h: float | None = None
    rx: float | None = None
    d: str | None = None
    cx: float | None = None
    cy: float | None = None
    r: float | None = None
    x1: float | None = None
    y1: float | None = None
    x2: float | None = None
    y2: float | None = None
    text: str | None = None
    anchor: str | None = None
    baseline: str | None = None
    transform: str | None = None
    hit: int | None = None
    series: str | None = None


@dataclass(slots=True)
class Tip:
    """The tooltip for one hoverable spot: a title and (key, color, label,
    value text) rows, placed beside (x, y) on ``side``; ``marks`` are drawn
    on top while it shows (a highlighted band, bigger points)."""

    title: str
    rows: list
    x: float
    y: float
    side: str = "right"
    marks: list = field(default_factory=list)

    def spoken(self) -> str:
        parts = [f"{label}: {text}" if label else text for _, _, label, text in self.rows]
        return f"{self.title}. " + ", ".join(parts) if self.title else ", ".join(parts)


@dataclass(slots=True)
class LegendItem:
    key: str
    label: str
    color: str
    hidden: bool = False
    shape: str = "box"  # box, line


@dataclass
class Scene:
    width: float
    height: float
    marks: list = field(default_factory=list)
    tips: list = field(default_factory=list)
    legend: list = field(default_factory=list)
    head: list = field(default_factory=list)
    rows: list = field(default_factory=list)
    summary: str = ""
    payload: Callable[[int, str | None], dict] | None = None

    def pick(self, hit: int, series: str | None = None) -> dict:
        return self.payload(hit, series) if self.payload else {"index": hit}


def n(v: float) -> float:
    """A coordinate rounded for the page: a tenth of a pixel is plenty."""
    return round(float(v), 1)


def text_width(text: str, size: float = 11) -> float:
    """About how wide text is in the chart font: layout has no page to measure."""
    return len(text) * size * 0.58 + 2
