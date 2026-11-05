"""What a chart accepts as data, turned into series of numbers.

Rows (dicts or objects), a dict of columns, a pandas or polars DataFrame,
a pandas Series or a plain {label: value} dict all work; so does the
``{"labels": [...], "datasets": [...]}`` shape Chart.js uses, so data
written for it can be reused.
"""

from __future__ import annotations

import datetime as _dt
import math
import numbers
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field as _field

PALETTE = ["#6366f1", "#14b8a6", "#f59e0b", "#ec4899", "#0ea5e9",
           "#22c55e", "#a855f7", "#ef4444", "#84cc16", "#64748b"]
NAMED = {"primary", "success", "warning", "danger", "info", "muted", "text"}


def color_of(color, index: int) -> str:
    """The series' own colour, a theme name (primary, danger ...) or the
    next palette colour (``--ui-chart-1`` ... ``--ui-chart-10``)."""
    if color:
        color = str(color).strip()
        return f"var(--ui-{color})" if color in NAMED else color
    i = index % len(PALETTE)
    return f"var(--ui-chart-{i + 1}, {PALETTE[i]})"


def colors_list(colors) -> list:
    if not colors:
        return []
    if isinstance(colors, str):
        return [c.strip() for c in colors.split(",") if c.strip()]
    return list(colors)


def rows_of(data) -> list:
    if data is None:
        return []
    if callable(getattr(data, "to_dicts", None)):          # polars
        return list(data.to_dicts())
    if callable(getattr(data, "to_dict", None)) and not isinstance(data, Mapping):
        if hasattr(data, "columns"):                        # pandas DataFrame
            return list(data.to_dict("records"))
        data = data.to_dict()                               # pandas Series
    if isinstance(data, Mapping):
        columns = {k: v for k, v in data.items() if _is_column(v)}
        if columns and len(columns) == len(data):
            size = max(len(v) for v in columns.values())
            return [{k: (list(v)[i] if i < len(v) else None) for k, v in columns.items()} for i in range(size)]
        return [{"label": k, "value": v} for k, v in data.items()]
    return list(data)


def _is_column(v) -> bool:
    return isinstance(v, Sequence) and not isinstance(v, (str, bytes)) or hasattr(v, "tolist")


def field(row, key):
    if isinstance(row, Mapping):
        return row.get(key)
    if isinstance(key, int) and isinstance(row, Sequence):
        return row[key] if -len(row) <= key < len(row) else None
    return getattr(row, key, None)


def number(v) -> float | None:
    """A plotted value: None, NaN and text that isn't a number are gaps."""
    if v is None:
        return None
    if isinstance(v, bool):
        return float(v)
    if isinstance(v, int):
        return v  # stays whole, so format="{}%" says 62%, not 62.0%
    if isinstance(v, numbers.Real):
        f = float(v)
        return None if math.isnan(f) or math.isinf(f) else f
    if isinstance(v, str):
        try:
            return number(float(v.replace(",", "")))
        except ValueError:
            return None
    try:
        return number(float(v))  # Decimal, numpy scalars
    except (TypeError, ValueError):
        return None


def label_text(v) -> str:
    if v is None:
        return ""
    if isinstance(v, float) and v.is_integer():
        return str(int(v))
    if isinstance(v, (_dt.date, _dt.datetime)):
        return v.isoformat(sep=" ", timespec="minutes") if isinstance(v, _dt.datetime) else v.isoformat()
    return str(v)


def readable(key) -> str:
    text = str(key).replace("_", " ").strip()
    return text[:1].upper() + text[1:]


@dataclass
class Series:
    key: str
    label: str
    values: list
    color: str
    kind: str = "bar"        # bar, line, area
    axis: str = "left"       # left, right
    stack: str | None = None
    dash: str | None = None  # an SVG dash pattern, "6 4"
    curve: str | None = None
    points: bool | None = None
    width: float | None = None
    low: list | None = None   # error bars or a band: the bottom of each value's range
    high: list | None = None
    trend: bool = False       # a least-squares line through the values


@dataclass
class Slice:
    key: str
    label: str
    value: float | None
    color: str
    row: object = None
    extra: dict = _field(default_factory=dict)


def _dash(v) -> str | None:
    if v in (None, False, "", "false"):
        return None
    if v is True or v == "true":
        return "6 4"
    if isinstance(v, (list, tuple)):
        return " ".join(str(x) for x in v)
    return str(v)


def _specs(y, series) -> list[dict]:
    specs = []
    for source in (y, series):
        if not source:
            continue
        if isinstance(source, str):
            source = [s.strip() for s in source.split(",") if s.strip()]
        elif isinstance(source, Mapping):
            source = [{"key": k, "label": v} for k, v in source.items()]
        for item in source:
            spec = dict(item) if isinstance(item, Mapping) else {"key": item}
            spec["key"] = spec.get("key", spec.get("field", spec.get("y")))
            specs.append(spec)
    seen = {}
    for spec in specs:  # a key named in both y and series: series wins
        seen[str(spec["key"])] = {**seen.get(str(spec["key"]), {}), **spec}
    return list(seen.values())


def _kind(spec: Mapping, default: str) -> str:
    kind = str(spec.get("type") or spec.get("kind") or default)
    if kind == "line" and spec.get("fill") not in (None, False, "", "false"):
        return "area"
    return kind


def _curve(spec: Mapping) -> str | None:
    if spec.get("curve"):
        return str(spec["curve"])
    # Chart.js's stepped: true/"before" holds each value until the next
    # point (step-after here), "after" jumps first, "middle" halfway.
    stepped = spec.get("stepped")
    if stepped:
        return {"after": "step-before", "middle": "step"}.get(stepped, "step-after")
    tension = spec.get("tension")
    if tension:
        return "smooth"
    return None


def _keys(row) -> list:
    if isinstance(row, Mapping):
        return list(row)
    if hasattr(row, "__dataclass_fields__"):
        return list(row.__dataclass_fields__)
    return [k for k in vars(row) if not k.startswith("_")] if hasattr(row, "__dict__") else []


def _first_key(rows, want_number: bool):
    if not rows:
        return None
    row = rows[0]
    for k in _keys(row):
        if (number(field(row, k)) is not None and not isinstance(field(row, k), str)) == want_number:
            return k
    return None


def cartesian_input(data, x="", y="", series=(), kind="bar", colors=()):
    """(categories, [Series], rows) from what a cartesian chart was given."""
    palette = colors_list(colors)
    if isinstance(data, Mapping) and "datasets" in data:
        return _from_chartjs(data, kind, palette)
    rows = rows_of(data)
    specs = _specs(y, series)
    if not x:
        x = _first_key(rows, want_number=False)
    if not specs and rows:
        first = rows[0]
        specs = [{"key": k} for k in _keys(first) if k != x and number(field(first, k)) is not None
                 and not isinstance(field(first, k), str)]
    categories = [field(r, x) for r in rows] if x is not None else list(range(1, len(rows) + 1))
    out = []
    for i, spec in enumerate(specs):
        key = spec["key"]
        own = spec.get("color") or (palette[i] if i < len(palette) else None)
        out.append(Series(
            key=str(key),
            label=str(spec.get("label") or readable(key)),
            values=[number(field(r, key)) for r in rows],
            color=color_of(own, i),
            kind=_kind(spec, kind),
            axis="right" if str(spec.get("axis", "left")) in ("right", "y2") else "left",
            stack=str(spec["stack"]) if spec.get("stack") not in (None, "") else None,
            dash=_dash(spec.get("dash")),
            curve=_curve(spec),
            points=spec.get("points"),
            width=spec.get("width"),
            trend=spec.get("trend") not in (None, False, "", "false"),
        ))
        out[-1].low, out[-1].high = _range(spec, rows, out[-1].values)
    return categories, out, rows


def _range(spec, rows, values):
    """(low, high) lists from a series' "lower"/"upper" fields (a band, a
    confidence interval) or "error" (a field, or one number: plus or minus)."""
    if spec.get("lower") or spec.get("upper"):
        low = [number(field(r, spec["lower"])) if spec.get("lower") else v for r, v in zip(rows, values)]
        high = [number(field(r, spec["upper"])) if spec.get("upper") else v for r, v in zip(rows, values)]
        return low, high
    error = spec.get("error")
    if error in (None, "", False):
        return None, None
    fixed = number(error) if not isinstance(error, str) or number(error) is not None else None
    errs = [fixed if fixed is not None else number(field(r, error)) for r in rows]
    low = [None if v is None or e is None else v - abs(e) for v, e in zip(values, errs)]
    high = [None if v is None or e is None else v + abs(e) for v, e in zip(values, errs)]
    return low, high


def _from_chartjs(data: Mapping, kind: str, palette: list):
    categories = list(data.get("labels") or [])
    first_axis = None
    out = []
    for i, ds in enumerate(data.get("datasets") or []):
        axis_id = ds.get("yAxisID") or "y"
        if first_axis is None:
            first_axis = axis_id
        color = ds.get("borderColor") if _kind(ds, kind) != "bar" else ds.get("backgroundColor")
        if not isinstance(color, str):
            color = ds.get("borderColor") if isinstance(ds.get("borderColor"), str) else None
        own = color or (palette[i] if i < len(palette) else None)
        values = list(ds.get("data") or [])
        out.append(Series(
            key=str(ds.get("label") or f"series {i + 1}"),
            label=str(ds.get("label") or f"Series {i + 1}"),
            values=[number(v) for v in values] + [None] * (len(categories) - len(values)),
            color=color_of(own, i),
            kind=_kind(ds, kind),
            axis="right" if axis_id != first_axis else "left",
            stack=str(ds["stack"]) if ds.get("stack") else None,
            dash=_dash(ds.get("borderDash")),
            curve=_curve(ds),
        ))
    return categories, out, []


def slices_input(data, label="", value="", colors=()) -> list[Slice]:
    """Pie and polar slices: one per row (or {label: value} pair)."""
    palette = colors_list(colors)
    if isinstance(data, Mapping) and "datasets" in data:
        ds = (data.get("datasets") or [{}])[0]
        own = ds.get("backgroundColor")
        own = own if isinstance(own, (list, tuple)) else []
        labels = list(data.get("labels") or [])
        values = list(ds.get("data") or [])
        return [Slice(str(i), label_text(lab), number(values[i]) if i < len(values) else None,
                      color_of(own[i] if i < len(own) else (palette[i] if i < len(palette) else None), i))
                for i, lab in enumerate(labels)]
    rows = rows_of(data)
    label = label or ("label" if rows and field(rows[0], "label") is not None else _first_key(rows, False))
    value = value or ("value" if rows and field(rows[0], "value") is not None else _first_key(rows, True))
    out = []
    for i, row in enumerate(rows):
        own = field(row, "color") if isinstance(row, Mapping) else None
        own = own or (palette[i] if i < len(palette) else None)
        out.append(Slice(str(i), label_text(field(row, label)), number(field(row, value)), color_of(own, i), row))
    return out


def mix(color: str, pct: float, base: str = "var(--ui-surface, #ffffff)") -> str:
    """``pct`` percent of ``color`` over ``base``: lighter shades that still
    follow the theme (a dark theme mixes towards its dark surface)."""
    pct = max(0.0, min(100.0, pct))
    return f"color-mix(in oklab, {color} {pct:.0f}%, {base})"


def ramp(t: float | None, low: str, high: str, diverging: bool = False) -> str:
    """The colour for ``t`` in 0..1: from the surface to ``high``, or with
    ``diverging``, from ``low`` through the surface (0.5) to ``high``."""
    if t is None:
        return "var(--ui-subtle, #f6f8fa)"
    t = max(0.0, min(1.0, t))
    if diverging:
        return mix(low, (0.5 - t) * 200) if t < 0.5 else mix(high, (t - 0.5) * 200)
    return mix(high, 8 + t * 92)


def ink(t: float | None, diverging: bool = False) -> str:
    """Text colour that stays readable on ``ramp(t)``."""
    if t is None:
        return "var(--ui-muted, #59636e)"
    strong = abs(t - 0.5) > 0.3 if diverging else t > 0.55
    return "#ffffff" if strong else "var(--ui-text, #1f2328)"
