"""Shared state: one object that any number of components read and change.

In a module of the app (``cart.py``)::

    from pyweft import Store

    class Cart(Store):
        items: list = []

        @property
        def count(self):
            return len(self.items)

        def add(self, item):
            self.items.append(item)

    cart = Cart()

then ``from cart import cart`` in any component's code block, and
``{{ cart.count }}`` or ``@click="cart.add(product)"`` in its template.

Every render already renders the whole page, so a change made in a handler
shows everywhere with nothing more to do. What a store adds is changes from
anywhere else (a timer, an async task, a JavaScript callback): setting one of
its fields, or calling one of its methods, asks every live page to render.
"""

from __future__ import annotations

import copy
import functools
import inspect
import weakref
from typing import Any

# Renderers alive in this process: a store change reaches each one's host.
# Filled by Renderer.__init__; weak, so a page that's gone is forgotten.
_renderers: weakref.WeakSet = weakref.WeakSet()


def _then_notify(store: Store, awaitable: Any) -> Any:
    async def run() -> Any:
        try:
            return await awaitable
        finally:
            store.changed()

    return run()


def _notifying(fn: Any) -> Any:
    @functools.wraps(fn)
    def method(self: Store, *args: Any, **kwargs: Any) -> Any:
        result = fn(self, *args, **kwargs)
        if inspect.isawaitable(result):
            return _then_notify(self, result)  # once it has finished
        self.changed()
        return result

    return method


class Store:
    """Base class for shared state. Fields are declared like a component's
    (``items: list = []``; mutable defaults are copied per store), and
    ``@property`` works for computed values. Public methods tell the pages
    to render when they return (an ``async`` one when it finishes), so
    ``self.items.append(x)`` inside a method needs nothing more."""

    def __init_subclass__(cls, **kwargs: Any) -> None:
        super().__init_subclass__(**kwargs)
        for name, value in list(vars(cls).items()):
            if not name.startswith("_") and inspect.isfunction(value):
                setattr(cls, name, _notifying(value))

    def __init__(self, **values: Any) -> None:
        object.__setattr__(self, "_pw_ready", False)
        cls = type(self)
        for name in dir(cls):
            if name.startswith("_"):
                continue
            value = getattr(cls, name, None)
            if isinstance(value, (list, dict, set)):
                setattr(self, name, copy.deepcopy(value))
        for name, value in values.items():
            setattr(self, name, value)
        object.__setattr__(self, "_pw_ready", True)

    def __setattr__(self, name: str, value: Any) -> None:
        object.__setattr__(self, name, value)
        if not name.startswith("_") and self.__dict__.get("_pw_ready"):
            self.changed()

    def changed(self) -> None:
        """Ask every page to render, for a change the store can't see, such
        as ``cart.items.append(x)`` made from outside the store's methods,
        outside a handler. Calls during a handler or render cost nothing:
        the host renders afterwards anyway."""
        for renderer in list(_renderers):
            # A template calling a store method only reads; that render is
            # already showing the store as it is.
            if not renderer.rendering:
                renderer.component.state_has_changed()

    # Effects snapshot what they read and compare with ==, so a store that
    # reads the same compares equal, and an in-place change shows up.
    def __eq__(self, other: object) -> bool:
        return type(other) is type(self) and _fields(self) == _fields(other)

    __hash__ = object.__hash__

    def __repr__(self) -> str:
        fields = ", ".join(f"{k}={v!r}" for k, v in _fields(self).items())
        return f"{type(self).__name__}({fields})"


def _fields(store: Store) -> dict[str, Any]:
    return {k: v for k, v in vars(store).items() if not k.startswith("_")}
