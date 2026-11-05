"""Sankey diagrams: amounts flowing between stages."""

from __future__ import annotations

from collections.abc import Mapping, Sequence

from .axes import empty
from .data import color_of, colors_list, field, label_text, number, rows_of
from .scales import fmt_value
from .scene import Mark, Scene, Tip, n


def links_input(data, source="", target="", value=""):
    """[(source, target, value, row)] from rows (fields ``source``,
    ``target``, ``value`` by default) or (source, target, value) tuples."""
    out = []
    for r in rows_of(data):
        if isinstance(r, Sequence) and not isinstance(r, (str, Mapping)) and len(r) >= 3:
            s, t, v = r[0], r[1], r[2]
        else:
            s, t, v = field(r, source or "source"), field(r, target or "target"), field(r, value or "value")
        v = number(v)
        if s is None or t is None or not v or v <= 0 or label_text(s) == label_text(t):
            continue
        out.append((label_text(s), label_text(t), v, r))
    return out


def sankey(links, *, width, height, fmt=None, colors=(), node_width=12.0, padding=10.0, align="left",
           kind="Sankey", empty_text="No data") -> Scene:
    width, height = max(float(width), 200.0), max(float(height), 120.0)
    scene = Scene(width, height)
    names = list(dict.fromkeys(name for s, t, *_ in links for name in (s, t)))
    scene.head = ["From", "To", "Value"]
    scene.rows = [[s, t, fmt_value(v, fmt)] for s, t, v, _ in links]
    scene.summary = f"{kind} diagram: {len(names)} nodes, {len(links)} flows"
    if not links:
        scene.payload = lambda i, key=None: {"index": i}
        return empty(scene, empty_text)
    palette = colors_list(colors)
    paint = {name: color_of(palette[i] if i < len(palette) else None, i) for i, name in enumerate(names)}
    inflow = {name: 0.0 for name in names}
    outflow = {name: 0.0 for name in names}
    for s, t, v, _ in links:
        outflow[s] += v
        inflow[t] += v
    # Columns: the longest path from a source (cycles stop growing after a pass per node).
    depth = {name: 0 for name in names}
    for _ in range(len(names)):
        changed = False
        for s, t, *_ in links:
            if depth[t] < depth[s] + 1 and depth[s] + 1 < len(names):
                depth[t] = depth[s] + 1
                changed = True
        if not changed:
            break
    last = max(depth.values())
    if align == "justify":  # ends of the flow line up on the right (flows may then skip columns)
        for name in names:
            if not outflow[name] and inflow[name]:
                depth[name] = last
    size = {name: max(inflow[name], outflow[name]) for name in names}
    columns = [[name for name in names if depth[name] == c] for c in range(last + 1)]
    columns = [col for col in columns if col]
    # Order each column by where its sources sit (the barycenter rule):
    # fewer crossings before the positions are relaxed below.
    rank = {name: i / max(len(columns[0]) - 1, 1) for i, name in enumerate(columns[0])}
    for col in columns[1:]:
        def place(name):
            ins = [(rank[s], v) for s, t, v, _ in links if t == name and s in rank]
            return sum(r * v for r, v in ins) / sum(v for _, v in ins) if ins else 0.5
        col.sort(key=place)
        rank.update({name: i / max(len(col) - 1, 1) for i, name in enumerate(col)})
    x0, x1 = 4.0, width - 4.0 - node_width
    col_x = {}
    for c, col in enumerate(columns):
        x = x0 + (x1 - x0) * c / max(len(columns) - 1, 1)
        for name in col:
            col_x[name] = x
    scale = min((height - 8 - padding * (len(col) - 1)) / (sum(size[nm] for nm in col) or 1) for col in columns)
    y = {}
    for col in columns:
        used = sum(size[nm] for nm in col) * scale + padding * (len(col) - 1)
        top = (height - used) / 2
        for name in col:
            y[name] = top
            top += size[name] * scale + padding

    def middle(name):
        return y[name] + size[name] * scale / 2

    def settle(col):
        col.sort(key=lambda nm: y[nm])
        floor = 4.0
        for name in col:
            y[name] = max(y[name], floor)
            floor = y[name] + size[name] * scale + padding
        ceiling = height - 4.0
        for name in reversed(col):
            if y[name] + size[name] * scale > ceiling:
                y[name] = ceiling - size[name] * scale
            ceiling = y[name] - padding

    for k in range(8):  # pull each node towards the nodes it is linked to
        alpha = 0.99 ** k * 0.6
        for col in columns[1:]:
            for name in col:
                ins = [(s, v) for s, t, v, _ in links if t == name]
                if ins:
                    want = sum(middle(s) * v for s, v in ins) / sum(v for _, v in ins)
                    y[name] += (want - middle(name)) * alpha
            settle(col)
        for col in reversed(columns[:-1]):
            for name in col:
                outs = [(t, v) for s, t, v, _ in links if s == name]
                if outs:
                    want = sum(middle(t) * v for t, v in outs) / sum(v for _, v in outs)
                    y[name] += (want - middle(name)) * alpha
            settle(col)
    out_at = {name: y[name] for name in names}
    in_at = {name: y[name] for name in names}
    bands = [None] * len(links)
    for i in sorted(range(len(links)), key=lambda i: y[links[i][1]]):  # top of a node: links to higher targets
        s, t, v, _ = links[i]
        bands[i] = [out_at[s], None, v * scale]
        out_at[s] += v * scale
    for i in sorted(range(len(links)), key=lambda i: y[links[i][0]]):
        s, t, v, _ = links[i]
        bands[i][1] = in_at[t]
        in_at[t] += v * scale
    marks = scene.marks
    paths = []
    for i, (s, t, v, _) in enumerate(links):
        sy, ty, w = bands[i]
        ax, bx = col_x[s] + node_width, col_x[t]
        mx = (ax + bx) / 2
        d = (f"M{n(ax)},{n(sy)} C{n(mx)},{n(sy)} {n(mx)},{n(ty)} {n(bx)},{n(ty)} L{n(bx)},{n(ty + w)} "
             f"C{n(mx)},{n(ty + w)} {n(mx)},{n(sy + w)} {n(ax)},{n(sy + w)} Z")
        paths.append(d)
        marks.append(Mark("path", f"k{i}", "link hit", style=f"fill: {paint[s]}", d=d, hit=len(names) + i))
    for k, name in enumerate(names):
        h = max(size[name] * scale, 1.0)
        marks.append(Mark("rect", f"n{k}", "node hit", style=f"fill: {paint[name]}", x=n(col_x[name]), y=n(y[name]),
                          w=n(node_width), h=n(h), rx=2, hit=k))
        at_end = depth[name] == last and last > 0 or (not outflow[name] and col_x[name] > width / 2)
        marks.append(Mark("text", f"nl{k}", "node-label", x=n(col_x[name] - 6 if at_end else col_x[name] + node_width + 6),
                          y=n(y[name] + h / 2), text=name, anchor="end" if at_end else "start", baseline="middle"))
    for k, name in enumerate(names):
        rows = []
        if inflow[name]:
            rows.append(("in", None, "In", fmt_value(inflow[name], fmt)))
        if outflow[name]:
            rows.append(("out", None, "Out", fmt_value(outflow[name], fmt)))
        h = max(size[name] * scale, 1.0)
        light = [Mark("rect", "hover-cell", "hover-cell", x=n(col_x[name]), y=n(y[name]), w=n(node_width), h=n(h), rx=2)]
        light += [Mark("path", f"hover-link{i}", "link hover-link", style=f"fill: {paint[s]}", d=paths[i])
                  for i, (s, t, *_) in enumerate(links) if name in (s, t)]
        right = col_x[name] < width / 2
        scene.tips.append(Tip(name, rows, n(col_x[name] + node_width if right else col_x[name]), n(y[name] + h / 2),
                              "right mid" if right else "left mid", light))
    for i, (s, t, v, _) in enumerate(links):
        sy, ty, w = bands[i]
        rows = [("v", paint[s], "", fmt_value(v, fmt)), ("share", None, f"Of {s}", f"{v / outflow[s] * 100:.1f}%")]
        mx = (col_x[s] + node_width + col_x[t]) / 2
        light = [Mark("path", "hover-link", "link hover-link", style=f"fill: {paint[s]}", d=paths[i])]
        right = mx < width / 2
        scene.tips.append(Tip(f"{s} → {t}", rows, n(mx), n((sy + ty) / 2 + w / 2), "right mid" if right else "left mid",
                              light))

    def payload(i, key=None):
        if i < len(names):
            name = names[i]
            return {"kind": "node", "index": i, "label": name, "value": size[name], "in": inflow[name],
                    "out": outflow[name]}
        s, t, v, row = links[i - len(names)]
        return {"kind": "link", "index": i - len(names), "source": s, "target": t, "value": v, "row": row}

    scene.payload = payload
    return scene
