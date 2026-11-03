"""Keeping data between visits, the same way everywhere.

Values are anything JSON can hold: numbers, text, True/False/None, and
lists and dicts of those::

    from pyweft import storage, effect

    items: list = []

    def on_init(self):
        self.items = storage.get("todos", [])

    @effect
    def keep(self):
        storage.set("todos", self.items)    # re-runs whenever items changes

Calls are plain functions, not ``async``, so they work anywhere: in
``on_init``, an effect, a property, or a module a component imports.

In the browser the data lives in the browser's local storage for the site,
kept apart per app, about 5 MB in all. In a desktop window it's a JSON file
in the user's data folder. In plain Python (tests, pre-rendering) it lives
in memory, in a :class:`MemoryStorage` you can look into.

``get`` returns a fresh copy each time: changing a list you got back
doesn't change what is stored until you ``set`` it again.
"""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Any, Iterable


class MemoryStorage:
    """Storage that lasts as long as the process: the default, and handy in
    tests (``storage.set_host(MemoryStorage())`` starts each one empty)."""

    def __init__(self, items: dict[str, str] | None = None):
        self.items: dict[str, str] = dict(items or {})

    def get(self, key: str) -> str | None:
        return self.items.get(key)

    def set(self, key: str, text: str) -> None:
        self.items[key] = text

    def delete(self, key: str) -> None:
        self.items.pop(key, None)

    def keys(self) -> Iterable[str]:
        return list(self.items)


class FileStorage(MemoryStorage):
    """Storage in one JSON file, read once and rewritten on every change. A
    desktop window uses one in the user's data folder."""

    def __init__(self, path: str | os.PathLike):
        self.path = Path(path)
        try:
            items = json.loads(self.path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            items = {}
        except (OSError, ValueError) as exc:
            raise OSError(f"can't read the app's saved data in {self.path}: {exc}") from None
        if not isinstance(items, dict):
            raise OSError(f"{self.path} isn't the app's saved data")
        super().__init__({key: json.dumps(value) for key, value in items.items()})

    def set(self, key: str, text: str) -> None:
        super().set(key, text)
        self._save()

    def delete(self, key: str) -> None:
        if key in self.items:
            super().delete(key)
            self._save()

    def _save(self) -> None:
        # Written to a temporary file and swapped in, so a crash halfway
        # through never leaves half a file.
        self.path.parent.mkdir(parents=True, exist_ok=True)
        data = {key: json.loads(text) for key, text in self.items.items()}
        fd, tmp = tempfile.mkstemp(dir=self.path.parent, prefix=".storage-", suffix=".json")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as out:
                json.dump(data, out, ensure_ascii=False, indent=1)
            os.replace(tmp, self.path)
        except BaseException:
            Path(tmp).unlink(missing_ok=True)
            raise


class Unavailable:
    """For places with nowhere to keep data, such as run_in_background's
    worker: every call says why."""

    def __init__(self, reason: str):
        self.reason = reason

    def _refuse(self, *args: Any) -> Any:
        raise RuntimeError(self.reason)

    get = set = delete = keys = _refuse


_host: Any = MemoryStorage()


def set_host(host: Any) -> None:
    """For hosts: an object with ``get(key)`` returning the stored text or
    None, ``set(key, text)``, ``delete(key)`` and ``keys()``. The core does
    the JSON."""
    global _host
    _host = host


def _check_key(key: str) -> str:
    if not isinstance(key, str) or not key:
        raise TypeError(f"storage keys are non-empty text, got {key!r}")
    return key


def get(key: str, default: Any = None) -> Any:
    """The value stored under ``key``, or ``default`` if there is none."""
    text = _host.get(_check_key(key))
    return default if text is None else json.loads(text)


def set(key: str, value: Any) -> None:  # noqa: A001 - storage.set reads well
    """Store ``value`` under ``key``, replacing what was there."""
    try:
        text = json.dumps(value, ensure_ascii=False, allow_nan=False)
    except (TypeError, ValueError) as exc:
        raise TypeError(
            f"storage keeps values JSON can hold (numbers, text, True/False/None, "
            f"lists and dicts of those); {key!r} got {type(value).__name__}: {exc}"
        ) from None
    _host.set(_check_key(key), text)


def delete(key: str) -> None:
    """Remove ``key``; nothing happens if it isn't there."""
    _host.delete(_check_key(key))


def keys() -> list[str]:
    """Every key with a value, sorted."""
    return sorted(_host.keys())


def has(key: str) -> bool:
    """Whether ``key`` has a value."""
    return _host.get(_check_key(key)) is not None


def clear() -> None:
    """Remove everything this app stored."""
    for key in list(_host.keys()):
        _host.delete(key)
