"""Opening and saving files, and asking the user, the same way everywhere.

In a handler (they're ``async``, so the handler is too)::

    from pyweft import dialogs

    async def load(self):
        file = await dialogs.open_file(types=["csv"])
        if file:                      # None when the user cancelled
            self.rows = parse(file.text)

    async def export(self):
        await dialogs.save_file(self.as_csv(), name="orders.csv")

    async def clear(self):
        if await dialogs.confirm("Delete all orders?"):
            self.orders = []

In a desktop app these are the system's own dialogs; in the browser, the
browser's file picker, a download, and its confirm box. Files come back as
their contents, not paths, because a browser never shows a page the user's
file system; on the desktop the path is there too.

The core only defines the calls. Each host supplies them with
:func:`set_host`, as background.py does for run_in_background: desktop.py
for the window, shell.html for the browser.
"""

from __future__ import annotations

import mimetypes
from dataclasses import dataclass
from typing import Any, Sequence


@dataclass(frozen=True)
class PickedFile:
    """A file the user chose: its name, its contents, and on the desktop
    where it is."""

    name: str
    data: bytes
    path: str | None = None  # desktop only: a browser never says

    @property
    def text(self) -> str:
        """The contents as text (UTF-8)."""
        return self.data.decode("utf-8")

    @property
    def size(self) -> int:
        """The size in bytes."""
        return len(self.data)

    @property
    def type(self) -> str:
        """The media type its name suggests (``image/png``), or
        ``application/octet-stream``."""
        return mime_type(self.name)


class _NoHost:
    async def _missing(self, *args: Any) -> Any:
        raise RuntimeError(
            "dialogs need a page to show them on: they work in the browser and "
            "in a desktop window. In tests, install a stand-in with "
            "pyweft.dialogs.set_host()"
        )

    open = save = confirm = _missing


_host: Any = _NoHost()


def set_host(host: Any) -> None:
    """For hosts: an object with ``async open(types, multiple)`` returning
    ``[(name, data, path), ...]`` (empty when cancelled), ``async save(name,
    data, types)`` returning whether it was saved, and ``async
    confirm(message, title)`` returning a bool."""
    global _host
    _host = host


def _extensions(types: Sequence[str]) -> list[str]:
    # "csv", ".csv" and "*.csv" all mean the same.
    out = []
    for kind in types:
        ext = kind.strip().lstrip("*").lstrip(".").lower()
        if not ext or not ext.replace("-", "").replace("_", "").isalnum():
            raise ValueError(f"file types are extensions like 'csv', got {kind!r}")
        out.append(ext)
    return out


async def _open(types: Sequence[str], multiple: bool) -> list[PickedFile]:
    chosen = await _host.open(_extensions(types), multiple)
    return [PickedFile(name, bytes(data), path) for name, data, path in chosen]


async def open_file(*, types: Sequence[str] = ()) -> PickedFile | None:
    """Let the user choose a file, and return it, or ``None`` if they
    cancelled. ``types=["csv", "txt"]`` limits what can be chosen."""
    files = await _open(types, multiple=False)
    return files[0] if files else None


async def open_files(*, types: Sequence[str] = ()) -> list[PickedFile]:
    """Let the user choose any number of files; an empty list if they
    cancelled."""
    return await _open(types, multiple=True)


async def save_file(
    data: bytes | str, *, name: str = "download", types: Sequence[str] = ()
) -> bool:
    """Save ``data`` (text is saved as UTF-8) as a file the user chooses,
    suggesting ``name``. In a desktop app that's a Save As dialog, and the
    result is False if they cancelled; in the browser it's a download, which
    the browser saves where it saves downloads."""
    if isinstance(data, str):
        data = data.encode("utf-8")
    exts = _extensions(types) or _extensions([name.rpartition(".")[2]] if "." in name else [])
    return bool(await _host.save(name, bytes(data), exts))


async def confirm(message: str, *, title: str = "") -> bool:
    """Ask a yes-or-no question; True for OK."""
    return bool(await _host.confirm(message, title))


def mime_type(name: str) -> str:
    """For hosts: the type a saved file is given."""
    return mimetypes.guess_type(name)[0] or "application/octet-stream"
