"""Toasts: short messages that show in a corner and go away by themselves.

``toast("Saved", "success")`` works from any handler, async task or
callback; the ``<ui.Toaster />`` on the page shows them. The list lives here
rather than in a component because the code that raises a toast is rarely
the component that shows it, and the browser runs one page per Python.
"""

from __future__ import annotations

import itertools
from dataclasses import dataclass, field
from typing import Any, Callable

_ids = itertools.count(1)
_toasts: list[Toast] = []
_toasters: list[Any] = []  # the Toaster components on the page


@dataclass(eq=False)
class Toast:
    """One message on screen. ``close()`` takes it away early."""

    message: str
    kind: str = "info"
    title: str = ""
    duration: float | None = 4.0
    action: str = ""
    on_action: Callable[[], Any] | None = None
    id: int = field(default_factory=lambda: next(_ids))
    _timer: Any = field(default=None, init=False, repr=False)

    def close(self) -> None:
        timer, self._timer = self._timer, None
        if timer is not None and not timer.done():
            timer.cancel()
        if self in _toasts:
            _toasts.remove(self)
            _changed()


def toast(
    message: str,
    kind: str = "info",
    *,
    title: str = "",
    duration: float | None = 4.0,
    action: str = "",
    on_action: Callable[[], Any] | None = None,
) -> Toast:
    """Show a message in the page's ``<ui.Toaster />``.

    ``kind`` is info, success, warning or danger. It closes after
    ``duration`` seconds (paused while the pointer or focus is on it), or
    stays until closed when ``duration`` is ``None``. ``action`` adds a
    button, such as "Undo", that calls ``on_action`` and closes the toast.
    Toasts raised before a Toaster is on the page show once it is.
    """
    item = Toast(message, kind, title, duration, action, on_action)
    _toasts.append(item)
    _changed()
    return item


def clear_toasts() -> None:
    """Close every toast."""
    for item in list(_toasts):
        item.close()


def _changed() -> None:
    for toaster in list(_toasters):
        toaster._refresh()
