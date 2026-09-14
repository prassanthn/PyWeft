"""Diff two vdom trees into a flat, ordered list of patch ops.

Ops are plain JSON-serialisable dicts, which is the whole point: the same list
can cross a webview bridge, a websocket, or nothing at all under Pyodide.

Addressing convention, applied consistently:

* structural ops (insert / remove / move / replace) carry the **parent** path
  plus an index, because that is what a DOM parent needs to act
* in-place ops (set_text / set_attrs / set_events / set_key) carry the
  **node's own** path

Ordering rule: at every level, all structural ops for a parent are emitted
before any op that descends into that parent's children. Indices in descendant
ops therefore refer to positions *after* this level has been reconciled, so a
consumer can apply the list front to back with no bookkeeping.
"""

from __future__ import annotations

from typing import Any

from .vdom import Element, Node, Text


class DiffError(RuntimeError):
    pass


def diff(old_roots: list[Node], new_roots: list[Node]) -> list[dict]:
    """Diff two root lists, treating them as children of a virtual root."""
    return _diff_children(old_roots, new_roots, [])


def _key_of(node: Node, index: int) -> tuple[str, Any]:
    key = getattr(node, "key", None)
    return ("k", key) if key is not None else ("i", index)


def _check_duplicates(keys: list[tuple[str, Any]]) -> None:
    seen = set()
    for kind, value in keys:
        if kind != "k":
            continue
        if value in seen:
            raise DiffError(
                f"duplicate key {value!r} among siblings; keys must be unique"
            )
        seen.add(value)


def _diff_map(old: dict, new: dict) -> dict:
    changed = {k: v for k, v in new.items() if old.get(k) != v}
    removed = [k for k in old if k not in new]
    result: dict[str, Any] = {}
    if changed:
        result["set"] = changed
    if removed:
        result["remove"] = removed
    return result


def _diff_node(
    old: Node, new: Node, parent_path: list[int], index: int
) -> list[dict]:
    node_path = parent_path + [index]

    if type(old) is not type(new):
        return [
            {
                "op": "replace",
                "path": parent_path,
                "index": index,
                "node": new.to_dict(),
            }
        ]

    if isinstance(old, Text):
        if old.text != new.text:
            return [{"op": "set_text", "path": node_path, "text": new.text}]
        return []

    assert isinstance(old, Element) and isinstance(new, Element)

    if old.tag != new.tag:
        return [
            {
                "op": "replace",
                "path": parent_path,
                "index": index,
                "node": new.to_dict(),
            }
        ]

    ops: list[dict] = []

    attrs = _diff_map(old.attrs, new.attrs)
    if attrs:
        ops.append({"op": "set_attrs", "path": node_path, **attrs})

    events = _diff_map(old.events, new.events)
    if events:
        ops.append({"op": "set_events", "path": node_path, **events})

    if old.key != new.key:
        ops.append({"op": "set_key", "path": node_path, "key": new.key})

    ops += _diff_children(old.children, new.children, node_path)
    return ops


def _diff_children(
    old: list[Node], new: list[Node], path: list[int]
) -> list[dict]:
    keyed = any(getattr(n, "key", None) is not None for n in old) or any(
        getattr(n, "key", None) is not None for n in new
    )
    if not keyed:
        return _diff_positional(old, new, path)
    return _diff_keyed(old, new, path)


def _diff_positional(
    old: list[Node], new: list[Node], path: list[int]
) -> list[dict]:
    common = min(len(old), len(new))
    struct: list[dict] = []
    for i in range(len(old) - 1, common - 1, -1):
        struct.append({"op": "remove", "path": path, "index": i})
    for i in range(common, len(new)):
        struct.append(
            {"op": "insert", "path": path, "index": i, "node": new[i].to_dict()}
        )
    descend: list[dict] = []
    for i in range(common):
        descend += _diff_node(old[i], new[i], path, i)
    return struct + descend


def _diff_keyed(old: list[Node], new: list[Node], path: list[int]) -> list[dict]:
    current = [_key_of(n, i) for i, n in enumerate(old)]
    target = [_key_of(n, i) for i, n in enumerate(new)]
    _check_duplicates(target)

    old_by_key: dict[tuple[str, Any], Node] = {}
    for i, key in enumerate(current):
        old_by_key.setdefault(key, old[i])

    struct: list[dict] = []
    descend: list[dict] = []

    # Evict keys that are gone before reconciling the survivors. Without this
    # pass, deleting one row from the middle of a list makes every row below it
    # look "out of place" and the main loop shuffles them up one by one --
    # correct, but O(n) moves for what should be a single removal.
    surviving = set(target)
    for j in range(len(current) - 1, -1, -1):
        if current[j] not in surviving:
            struct.append({"op": "remove", "path": path, "index": j})
            current.pop(j)

    for position, key in enumerate(target):
        if position < len(current) and current[position] == key:
            descend += _diff_node(old_by_key[key], new[position], path, position)
            continue

        found = None
        for j in range(position, len(current)):
            if current[j] == key:
                found = j
                break

        if found is not None:
            struct.append(
                {"op": "move", "path": path, "from": found, "to": position}
            )
            current.insert(position, current.pop(found))
            descend += _diff_node(old_by_key[key], new[position], path, position)
        else:
            struct.append(
                {
                    "op": "insert",
                    "path": path,
                    "index": position,
                    "node": new[position].to_dict(),
                }
            )
            current.insert(position, key)

    # Anything left past the end of the new list is stale. Remove back to
    # front so earlier indices stay valid as we go.
    for j in range(len(current) - 1, len(target) - 1, -1):
        struct.append({"op": "remove", "path": path, "index": j})

    return struct + descend
