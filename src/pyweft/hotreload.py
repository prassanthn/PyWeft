"""Hot reload: move live components onto freshly compiled classes.

During development the host recompiles the app from its files and calls
``hot_swap``. Each live instance -- root and children -- has its class
replaced by the new class compiled from the same file, keeping the instance's
``__dict__``: that dict *is* the component's state, so counters, typed input
and lists survive the edit. The next render shows the new template and the
differ patches only what changed.

The swap has to happen before rendering: the renderer replaces a child whose
class is not the one its parent's registry names, which would reset it.
"""

from __future__ import annotations

import copy
import traceback
from pathlib import PurePosixPath
from typing import Any

from .effects import dispose_effects


def _source_file(cls: type) -> str | None:
    # Own attribute only: a subclass of a loaded component is not that file.
    return vars(cls).get("__weft_file__")


def classes_by_file(root: type) -> dict[str, type]:
    """Every class reachable from ``root`` through ``components``
    registries, keyed by the file it was loaded from."""
    found: dict[str, type] = {}
    seen: set[type] = set()

    def walk(cls: type) -> None:
        if cls in seen:
            return
        seen.add(cls)
        source = _source_file(cls)
        if source is not None:
            found.setdefault(source, cls)
        for child in getattr(cls, "components", {}).values():
            walk(child)

    walk(root)
    return found


def _add_new_defaults(instance: Any, cls: type) -> None:
    """Fields added in the edit read their class default; mutable ones must
    be copied per instance, exactly as Component.__init__ does."""
    for name in dir(cls):
        if name.startswith("_") or name == "components" or name in vars(instance):
            continue
        try:
            value = getattr(cls, name)
        except AttributeError:
            continue
        if isinstance(value, (list, dict, set)):
            setattr(instance, name, copy.deepcopy(value))


def hot_swap(renderer: Any, new_root: type) -> list[str]:
    """Move every live component of ``renderer`` onto its class in the newly
    loaded tree under ``new_root``. Returns the files whose source changed.

    State (instance attributes) is kept. Components whose source changed
    have their effects cleaned up and reset, so they run again with the new
    code after the next render; ``on_init`` does not run again.
    """
    by_file = classes_by_file(new_root)
    changed: list[str] = []
    for instance in [renderer.component, *renderer.instances.values()]:
        old = type(instance)
        if instance is renderer.component:
            new = new_root
        else:
            new = by_file.get(_source_file(old) or "")
        if new is None or new is old:
            continue  # not from a file, or the file is gone: render decides
        if vars(old).get("__weft_src__") != vars(new).get("__weft_src__"):
            dispose_effects(instance)
            instance.__dict__.pop("_pw_effects", None)
            source = _source_file(new)
            if source is not None and source not in changed:
                changed.append(source)
        instance.__class__ = new
        _add_new_defaults(instance, new)
        instance._dirty = True
    return changed


def format_error(exc: BaseException, root: str | None = None) -> str:
    """A short, readable description of an error raised while reloading:
    the location in the ``.weft`` file where possible, then the error itself.
    Paths are shown relative to ``root`` when given."""

    def where(path: str) -> str:
        if root:
            try:
                return str(PurePosixPath(path).relative_to(root))
            except ValueError:
                pass
        return path

    lines: list[str] = []
    frames = [
        (f.filename, f.lineno, f.line) for f in traceback.extract_tb(exc.__traceback__)
    ]
    # Raised by run_in_background: where it failed in the background too.
    frames += getattr(exc, "_pyweft_background_frames", [])
    for filename, lineno, line in frames:
        if filename.endswith(".weft"):
            code = f": {line.strip()}" if line else ""
            lines.append(f"{where(filename)}, line {lineno}{code}")
    if isinstance(exc, SyntaxError) and exc.filename and exc.filename.endswith(".weft"):
        text = (exc.text or "").strip()
        lines.append(f"{where(exc.filename)}, line {exc.lineno}: {text}".rstrip(": "))
        lines.append(f"SyntaxError: {exc.msg}")
    else:
        lines.append(f"{type(exc).__name__}: {exc}")
    return "\n".join(lines)
