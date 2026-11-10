"""Keeps a chart's last layout while nothing it is laid out from changed.

Every render renders the whole page, so a click anywhere used to lay out
every chart on it again (a page of KDEs, histograms and box plots: about
0.2 s per click in the browser). A chart's layout depends only on its own
fields, the width and the hidden series, so the scene is kept until one of
them differs. The fields are compared against a deep copy taken when the
scene was made: data changed in place counts as changed.
"""

from __future__ import annotations

import copy
import datetime
from collections.abc import Callable
from typing import Any


class LayoutMemo:
    """``get(build, width, hidden)`` returns ``build(width, hidden)``, or the
    scene it returned last time if nothing it reads has changed.

    ``build`` must be a bound method whose result depends only on its
    owner's public fields and its arguments (what the chart controls pass
    to ChartView); anything else is laid out every time."""

    def __init__(self) -> None:
        self._key: tuple | None = None
        self._fields: dict[str, Any] | None = None
        self._scene: Any = None

    def get(self, build: Callable, width: float, hidden: frozenset) -> Any:
        owner = getattr(build, "__self__", None)
        if owner is None or not hasattr(owner, "__dict__"):
            return build(width, hidden)
        # The class and function: a hot reload changes them. Today: a
        # calendar without an end date ends today.
        key = (build.__func__, type(owner), width, hidden, datetime.date.today())
        fields = layout_fields(owner)
        if self._key == key and self._fields is not None and same_fields(fields, self._fields):
            return self._scene
        scene = build(width, hidden)
        try:
            self._fields = copy.deepcopy(fields)
        except Exception:  # something that can't be copied: no memo
            self._key = self._fields = self._scene = None
            return scene
        self._key, self._scene = key, scene
        return scene


def layout_fields(owner: Any) -> dict[str, Any]:
    """The instance's public fields: props passed in and state it set.
    Event callbacks (``on_select``) are made anew every render and never
    shape a layout; other functions (a ``format``) count, by equality."""
    return {
        name: value for name, value in vars(owner).items()
        if not name.startswith("_") and not (name.startswith("on_") and callable(value))
    }


def same_fields(new: dict[str, Any], old: dict[str, Any]) -> bool:
    return new.keys() == old.keys() and all(same(new[name], old[name]) for name in new)


def same(a: Any, b: Any) -> bool:
    """Equal values; a DataFrame or Series (pandas, polars) by ``equals``.
    Anything that can't say (a numpy array: elementwise ==) is different."""
    equals = getattr(type(a), "equals", None)
    if callable(equals) and type(a) is type(b):
        try:
            return bool(a.equals(b))
        except Exception:
            return False
    try:
        return bool(a == b)
    except Exception:
        return False
