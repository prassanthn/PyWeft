"""Treemaps: nested rectangles whose areas show values."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field as _field

from .axes import empty
from .data import color_of, colors_list, field, label_text, mix, number, rows_of
from .scales import fmt_value
from .scene import Mark, Scene, Tip, n, text_width


@dataclass
class Node:
    label: str
    value: float = 0.0
    children: list = _field(default_factory=list)
    row: object = None
    color: str | None = None


def tree_input(data, label="", value="", path="", children="children") -> list[Node]:
    """Top-level nodes from: rows with ``path`` fields ("region, country")
    and a value; dicts with label/value/children; a {name: value} dict,
    nested to any depth ({"Europe": {"France": 3, ...}})."""
    if isinstance(data, Mapping):
        return [_from_mapping(k, v) for k, v in data.items()]
    rows = rows_of(data)
    if path:
        levels = [p.strip() for p in path.split(",") if p.strip()] if isinstance(path, str) else list(path)
        roots: dict = {}
        for r in rows:
            v = number(field(r, value or "value"))
            if v is None:
                continue
            level, node = roots, None
            for name in (label_text(field(r, p)) for p in levels):
                if name not in level:
                    level[name] = (Node(name), {})
                node, level = level[name]
            node.value += v
            node.row = r
        return _unwrap(roots)
    return [_from_dict(r, label, value, children) for r in rows]


def _unwrap(level) -> list[Node]:
    out = []
    for node, below in level.values():
        node.children = _unwrap(below)
        out.append(node)
    return out


def _from_mapping(name, v) -> Node:
    if isinstance(v, Mapping):
        return Node(label_text(name), children=[_from_mapping(k, x) for k, x in v.items()])
    return Node(label_text(name), number(v) or 0.0)


def _from_dict(r, label, value, children) -> Node:
    kids = field(r, children) or []
    name = field(r, label) if label else (field(r, "label") if field(r, "label") is not None else field(r, "name"))
    return Node(label_text(name), number(field(r, value or "value")) or 0.0,
                [_from_dict(k, label, value, children) for k in kids], r,
                field(r, "color") if isinstance(r, Mapping) else None)


def total(node: Node) -> float:
    """A node's value: its children's sum when it has children."""
    if node.children:
        node.value = sum(total(c) for c in node.children)
    return max(node.value, 0.0)


def squarify(values, x, y, w, h) -> list[tuple]:
    """Rectangles for values (largest first) filling (x, y, w, h), laid out
    in rows that keep each rectangle as close to square as possible."""
    whole = sum(values)
    if whole <= 0 or w <= 0 or h <= 0:
        return [(x, y, 0.0, 0.0) for _ in values]
    areas = [v * w * h / whole for v in values]
    out = []
    i = 0

    def worst(row, side):
        s = sum(row)
        return max(side * side * max(row) / (s * s), s * s / (side * side * min(row)))

    while i < len(areas):
        side = min(w, h)
        row = [areas[i]]
        j = i + 1
        while j < len(areas) and worst(row + [areas[j]], side) <= worst(row, side):
            row.append(areas[j])
            j += 1
        s = sum(row)
        if w >= h:
            thick = s / h if h else 0
            yy = y
            for a in row:
                out.append((x, yy, thick, a / thick if thick else 0))
                yy += a / thick if thick else 0
            x, w = x + thick, w - thick
        else:
            thick = s / w if w else 0
            xx = x
            for a in row:
                out.append((xx, y, a / thick if thick else 0, thick))
                xx += a / thick if thick else 0
            y, h = y + thick, h - thick
        i = j
    return out


def treemap(roots, *, width, height, fmt=None, colors=(), depth=None, kind="Treemap", empty_text="No data") -> Scene:
    width, height = max(float(width), 120.0), max(float(height), 100.0)
    scene = Scene(width, height)
    palette = colors_list(colors)
    whole = sum(total(r) for r in roots)
    leaves = []
    marks = scene.marks

    def place(nodes, x, y, w, h, level, path, base, parent_value):
        items = sorted((c for c in nodes if c.value > 0), key=lambda c: -c.value)
        for k, (node, (rx, ry, rw, rh)) in enumerate(zip(items, squarify([c.value for c in items], x, y, w, h))):
            paint = node.color or base or color_of(palette[k] if k < len(palette) else None, k)
            here = path + [node.label]
            deeper = node.children and (depth is None or level + 1 < depth) and rw > 30 and rh > 34
            if deeper:
                marks.append(Mark("rect", f"g{'/'.join(here)}", "tm-group", style=f"fill: {mix(paint, 16)}",
                                  x=n(rx + 1), y=n(ry + 1), w=n(max(rw - 2, 0)), h=n(max(rh - 2, 0)), rx=3))
                if rw > text_width(node.label) * 0.6 + 8:
                    marks.append(Mark("text", f"gt{'/'.join(here)}", "tm-header", x=n(rx + 6), y=n(ry + 13),
                                      text=_fit(node.label, rw - 10)))
                place(node.children, rx + 3, ry + 19, rw - 6, rh - 22, level + 1, here, paint, node.value)
                continue
            hit = len(leaves)
            leaves.append((node, here, parent_value, rx, ry, rw, rh, paint))
            shade = paint if level == 0 else mix(paint, 92 - 9 * (k % 5))
            marks.append(Mark("rect", f"l{'/'.join(here)}", "tm-leaf hit", style=f"fill: {shade}", x=n(rx + 1),
                              y=n(ry + 1), w=n(max(rw - 2, 0)), h=n(max(rh - 2, 0)), rx=2, hit=hit))
            if rw > 36 and rh > 18:
                marks.append(Mark("text", f"lt{'/'.join(here)}", "tm-label", x=n(rx + 6), y=n(ry + 15),
                                  text=_fit(node.label, rw - 10)))
                if rh > 34:
                    marks.append(Mark("text", f"lv{'/'.join(here)}", "tm-value", x=n(rx + 6), y=n(ry + 29),
                                      text=_fit(fmt_value(node.value, fmt), rw - 10)))

    scene.summary = f"{kind} of {len(roots)} {'group' if len(roots) == 1 else 'groups'}, total {fmt_value(whole, fmt)}"
    if whole <= 0:
        scene.payload = lambda i, key=None: {"index": i}
        return empty(scene, empty_text)
    place(roots, 0.0, 0.0, width, height, 0, [], None, whole)
    scene.head = ["", "Value", "Share"]
    scene.rows = [[" › ".join(path), fmt_value(node.value, fmt), f"{node.value / whole * 100:.1f}%"]
                  for node, path, *_ in leaves]
    for node, path, parent_value, rx, ry, rw, rh, paint in leaves:
        rows = [("v", paint, "", fmt_value(node.value, fmt)), ("all", None, "Of all", f"{node.value / whole * 100:.1f}%")]
        if len(path) > 1:
            rows.append(("parent", None, f"Of {path[-2]}", f"{node.value / parent_value * 100:.1f}%"))
        light = [Mark("rect", "hover-cell", "hover-cell", x=n(rx + 1), y=n(ry + 1), w=n(max(rw - 2, 0)),
                      h=n(max(rh - 2, 0)), rx=2)]
        right = rx + rw / 2 < width / 2
        scene.tips.append(Tip(" › ".join(path), rows, n(rx + rw / 2), n(ry + rh / 2),
                              "right mid" if right else "left mid", light))
    scene.payload = lambda i, key=None: (lambda leaf: {"index": i, "label": leaf[0].label, "path": leaf[1],
                                                       "value": leaf[0].value, "row": leaf[0].row})(leaves[i])
    return scene


def _fit(text: str, room: float) -> str:
    chars = int(room / (11 * 0.58))
    return text if len(text) <= chars else (text[: max(chars - 1, 1)] + "…" if chars > 1 else "")
