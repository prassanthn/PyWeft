"""Options in the forms the toolkit accepts, and matching them to typed text.

Shared by the controls that list options (Chips, ChipInput): ``options``
may be a comma-separated string, a list of values, ``(value, label)``
pairs, or dicts with ``value`` and ``label`` whose other keys (``icon``,
``disabled``, your own) come along as ``data``.
"""

from __future__ import annotations

from typing import Any, Iterable


def normalize(items: Any) -> list[dict]:
    """``[{"value", "label", "data", "icon", "disabled"}, ...]``"""
    if isinstance(items, str):
        items = [part.strip() for part in items.split(",") if part.strip()]
    out = []
    for item in items or []:
        if isinstance(item, dict):
            value = item.get("value", item.get("label"))
            label = item.get("label", value)
        elif isinstance(item, (tuple, list)) and len(item) == 2:
            value, label = item
        else:
            value, label = item, item
        extra = item if isinstance(item, dict) else {}
        out.append({
            "value": value, "label": str(label), "data": item,
            "icon": str(extra.get("icon") or ""), "disabled": bool(extra.get("disabled")),
        })
    return out


def label_of(choices: list[dict], value: Any) -> str:
    """The label of the option with this value, else the value as text."""
    for choice in choices:
        if choice["value"] == value:
            return choice["label"]
    return "" if value is None else str(value)


def find(choices: list[dict], text: str) -> dict | None:
    """The option whose label is ``text``, ignoring case and spaces around."""
    wanted = text.strip().lower()
    return next((c for c in choices if c["label"].strip().lower() == wanted), None)


def matches(
    choices: list[dict], query: str, how: str = "contains", limit: int = 8,
    exclude: Iterable[Any] = (),
) -> list[dict]:
    """The options that match ``query``, each with ``before``/``match``/
    ``after`` around the matched text and its position as ``index``.
    ``how``: contains, starts, or none (all of them, as given)."""
    q = query.strip()
    low = q.lower()
    skip = list(exclude)
    out = []
    for position, choice in enumerate(choices):
        if choice["value"] in skip:
            continue
        text = choice["label"]
        at = text.lower().find(low) if low else -1
        if low and how == "contains" and at < 0:
            continue
        if low and how == "starts" and at != 0:
            continue
        hit = bool(low) and at >= 0
        out.append({
            **choice, "index": len(out), "key": f"{position}-{choice['value']}",
            "before": text[:at] if hit else text, "match": text[at:at + len(q)] if hit else "",
            "after": text[at + len(q):] if hit else "",
        })
        if limit and len(out) >= limit:
            break
    return out
