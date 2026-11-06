"""Templates prepared ahead of time.

Loading a ``.weft`` file means parsing its template (XML into a template
tree), scoping its ``<style>`` block and, later, generating its compiled
render code. None of that depends on anything but the file's text, so
``pyweft build`` and ``pyweft run`` do it once, for every file the app ships
(component libraries included), and send the results as one bundle. The page
installs it before loading the app, and the loader takes a file's results
from it when the file's text is the one they were made from (by its hash):
an edited file, as in a hot reload, simply isn't found and is parsed as
before, so a stale bundle is never wrong, only less useful.

What can't be done ahead is compiling the ``<code>`` blocks to bytecode,
which depends on the exact Python version (the browser's is Pyodide's, not
the build machine's), and running them.
"""

from __future__ import annotations

import hashlib
import pickle
from typing import Any, Iterable

# Bump when the template tree's classes change shape: an old bundle is then
# ignored rather than unpickled into the wrong fields.
FORMAT = 1
# Stands in for the scope id in a bundled <style> block: the scope comes from
# where the file is loaded from, which the build doesn't decide.
SCOPE = "pwscopeplaceholder"

_entries: dict[str, dict[str, Any]] = {}


def fingerprint() -> str:
    """What a bundle depends on besides the version: the template tree's
    classes (their fields) and the helpers generated code calls. Both sides
    compute it from their own code, so a bundle from a different build of
    the framework is ignored instead of unpickled into the wrong shapes."""
    from dataclasses import fields

    from . import compiler, parser

    classes = [getattr(parser, name) for name in sorted(dir(parser)) if name.startswith("T")
               and isinstance(getattr(parser, name), type) and hasattr(getattr(parser, name), "__dataclass_fields__")]
    shape = [(c.__name__, [f.name for f in fields(c)]) for c in classes]
    return hashlib.sha1(repr((FORMAT, shape, sorted(compiler._RUNTIME))).encode()).hexdigest()


def key(src: str) -> str:
    return hashlib.sha1(src.encode("utf-8")).hexdigest()


def prepare(src: str) -> dict[str, Any]:
    """Everything about one ``.weft`` text that doesn't depend on where it
    is loaded from: the template tree, the scoped CSS (scope left as
    SCOPE) and the compiled template's source."""
    from .compiler import generate
    from .parser import block_spans, parse_template, split_source
    from .styles import scope_css

    template_src, _, style_src = split_source(src)
    first_line = src.count("\n", 0, block_spans(src)["template"][0]) + 1
    nodes = parse_template(template_src, first_line)
    entry: dict[str, Any] = {
        "template": nodes,
        "style": scope_css(style_src, SCOPE).strip() if style_src.strip() else "",
    }
    try:
        # Its constants refer to nodes of this very tree; pickled together,
        # they stay the same objects.
        entry["generated"] = generate(nodes)
    except Exception:  # noqa: BLE001 - the renderer generates it, or walks the tree
        pass
    return entry


def bundle(sources: Iterable[str]) -> bytes:
    """The bundle for these ``.weft`` texts. A file with a mistake in it is
    left out: loading it reports the mistake as usual."""
    from . import __version__

    entries: dict[str, dict[str, Any]] = {}
    for src in sources:
        try:
            entries[key(src)] = prepare(src)
        except Exception:  # noqa: BLE001 - see the docstring
            continue
    header = {"format": FORMAT, "pyweft": __version__, "fingerprint": fingerprint()}
    return pickle.dumps({**header, "entries": entries}, protocol=4)


def install(data: bytes) -> int:
    """Use a bundle made by :func:`bundle` (by the same PyWeft version);
    returns how many files it covers, 0 when it doesn't fit. Only for a
    bundle the app's own server sent: it is unpickled."""
    from . import __version__

    try:
        payload = pickle.loads(data)
    except Exception:  # noqa: BLE001 - damaged or foreign: load without it
        return 0
    fits = (
        isinstance(payload, dict)
        and payload.get("format") == FORMAT
        and payload.get("pyweft") == __version__
        and payload.get("fingerprint") == fingerprint()
    )
    if not fits:
        return 0
    entries = payload.get("entries") or {}
    _entries.update(entries)
    return len(entries)


def lookup(src: str) -> dict[str, Any] | None:
    """The prepared results for this exact text, if a bundle had them."""
    return _entries.get(key(src)) if _entries else None


def clear() -> None:
    _entries.clear()


__all__ = ["bundle", "install", "lookup", "prepare", "clear", "FORMAT"]
