"""A plain-Python model of the DOM that applies patch ops.

This is the executable spec for the JavaScript runtime that will live in the
webview: whatever this file does, ``runtime.js`` must do to real DOM nodes. It
also lets the differ be tested properly -- apply the patches to the old tree
and assert the result equals the new tree, which catches ordering and indexing
bugs that op-by-op assertions happily miss.
"""

from __future__ import annotations

import copy
from typing import Any


def _node_at(roots: list[dict], path: list[int]) -> dict:
    node = roots[path[0]]
    for index in path[1:]:
        node = node["children"][index]
    return node


def _children_at(roots: list[dict], path: list[int]) -> list[dict]:
    if not path:
        return roots
    return _node_at(roots, path)["children"]


def apply_patches(roots: list[dict], ops: list[dict]) -> list[dict]:
    """Apply ops to a deep copy of ``roots`` and return the result."""
    roots = copy.deepcopy(roots)

    for op in ops:
        kind = op["op"]

        if kind in ("insert", "remove", "move", "replace"):
            children = _children_at(roots, op["path"])
            if kind == "insert":
                children.insert(op["index"], copy.deepcopy(op["node"]))
            elif kind == "remove":
                children.pop(op["index"])
            elif kind == "replace":
                children[op["index"]] = copy.deepcopy(op["node"])
            else:
                children.insert(op["to"], children.pop(op["from"]))
            continue

        node = _node_at(roots, op["path"])
        if kind == "set_text":
            node["text"] = op["text"]
        elif kind == "set_key":
            node["key"] = op["key"]
        elif kind in ("set_attrs", "set_events"):
            target: dict[str, Any] = node[
                "attrs" if kind == "set_attrs" else "events"
            ]
            for name in op.get("remove", []):
                target.pop(name, None)
            target.update(op.get("set", {}))
        else:  # pragma: no cover - defensive
            raise ValueError(f"unknown op {kind!r}")

    return roots
