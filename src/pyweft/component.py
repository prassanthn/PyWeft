"""Component base class and the ``.weft`` loader.

Reactivity model is Blazor's, not React's: there are no observables and no
proxies. An event handler runs, then the component re-renders and the diff is
sent. If you mutate state outside a handler (a timer, an async callback), call
``state_has_changed()`` yourself.
"""

from __future__ import annotations

import copy
import re
import textwrap
from contextvars import ContextVar
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from .parser import (
    _CODE_RE,
    TElement,
    TemplateError,
    TFor,
    TIf,
    parse_template,
    split_source,
)
from .styles import scope_css


class Component:
    __template__: list[Any] = []
    # Set by the loader when the file has a <style> block: the id stamped on
    # every element this component renders (as ``data-w-<scope>``) and the
    # block's CSS with its selectors rewritten to match only those elements.
    __scope__: str | None = None
    __style__: str = ""
    # Tag name -> component class, consulted by the renderer when a template
    # element's tag is capitalised. Filled by the loader or passed explicitly.
    components: dict[str, type] = {}

    def __init__(self, **params):
        self._dirty = True
        self._on_change: Callable[[Component], None] | None = None
        self._rendered_once = False

        # Class-level mutable defaults (``history: list = []`` in a code block)
        # would otherwise be shared by every instance -- a classic Python
        # footgun that would look like a framework bug. Copy them per instance.
        cls = type(self)
        for name in dir(cls):
            if name.startswith("_") or name == "components":
                continue
            try:
                value = getattr(cls, name)
            except AttributeError:
                continue
            if isinstance(value, (list, dict, set)):
                setattr(self, name, copy.deepcopy(value))

        for key, value in params.items():
            setattr(self, key, value)

    # ------------------------------------------------------------ lifecycle

    def on_init(self) -> None:
        """Called once before the first render. May be ``async``: the part
        before the first ``await`` is in the first render, and the component
        renders again when it finishes."""

    def on_after_render(self, first: bool) -> None:
        """Called after each render has been applied. May be ``async``."""

    def on_dispose(self) -> None:
        """Called when the component is torn down. Must not be ``async``:
        the component's tasks are cancelled just before this runs."""

    def start_task(self, awaitable: Any) -> Any:
        """Run a coroutine (or other awaitable) as a task this component owns,
        and return the ``asyncio.Task``.

        The component re-renders when the task finishes and the task is
        cancelled if the component is removed first. Call
        ``state_has_changed()`` inside it to show progress before the end.
        Works once the component is rendered, from ``on_init`` onwards.
        """
        start = self.__dict__.get("_pw_start")
        if start is None:
            if hasattr(awaitable, "close"):
                awaitable.close()  # no "never awaited" warning on top
            raise RuntimeError(
                f"{type(self).__name__}.start_task() needs the component to be "
                "rendered (call it from on_init or later, not __init__), and "
                "not yet removed"
            )
        return start(awaitable)

    # ---------------------------------------------------------------- state

    def state_has_changed(self) -> None:
        self._dirty = True
        if self._on_change is not None:
            self._on_change(self)
        # Set by the Renderer that owns this instance; how a change made
        # outside a handler (timer, JS callback, asyncio task) reaches the host.
        invalidate = self.__dict__.get("_pw_invalidate")
        if invalidate is not None:
            invalidate()

    def emit(self, event: str, payload: Any = None) -> Any:
        """Invoke the parent's ``@event`` callback, Vue-style.

        ``<Child @remove="drop(item)" />`` in a parent template arrives here as
        an ``on_remove`` callable prop; ``self.emit("remove")`` in the child
        calls it. Emitting an event nobody listens to is a no-op, as in Vue.
        """
        callback = getattr(self, f"on_{event}", None)
        if callable(callback):
            return callback(payload)
        return None


def compile_code_block(src: str, filename: str) -> Any:
    """The ``<code>`` block of a ``.weft`` source, compiled so that line
    numbers in tracebacks are lines of the file, not of the block.
    (split_source's own output stays unpadded.)"""
    _, code_src, _ = split_source(src)
    match = _CODE_RE.search(src)
    if match:
        code_src = "\n" * src.count("\n", 0, match.start(1)) + code_src
    return compile(textwrap.dedent(code_src), filename, "exec")


def component_from_source(
    src: str,
    name: str = "Component",
    base: type = Component,
    components: dict[str, type] | None = None,
    scope: str | None = None,
    filename: str | None = None,
) -> type:
    """``scope`` is the style scope id; it defaults to the snake-cased ``name``
    and only matters when the source has a ``<style>`` block. ``filename`` is
    what tracebacks show for errors in the code block."""
    template_src, _, style_src = split_source(src)
    nodes = parse_template(template_src)

    namespace: dict[str, Any] = {}
    exec(compile_code_block(src, filename or f"<{name}.weft>"), namespace)
    namespace.pop("__builtins__", None)
    namespace["__template__"] = nodes
    if style_src.strip():
        scope = scope or _snake(name)
        namespace["__scope__"] = scope
        namespace["__style__"] = scope_css(style_src, scope).strip()
    else:
        namespace["__scope__"] = None
        namespace["__style__"] = ""
    # A `components` dict in the code block wins over the passed-in registry.
    namespace["components"] = {**(components or {}), **namespace.get("components", {})}

    return type(name, (base,), namespace)


_CONTROL_TAGS = {"If", "ElseIf", "Else", "For"}


def is_component_tag(tag: str) -> bool:
    """``TodoItem`` and ``widgets.Row`` are components; ``div`` is not. The
    last dotted segment decides, so folder names can stay lowercase."""
    return tag.rsplit(".", 1)[-1][:1].isupper() and tag not in _CONTROL_TAGS


def _component_tags(nodes: list[Any], found: set[str]) -> set[str]:
    for node in nodes:
        if isinstance(node, TElement):
            if is_component_tag(node.tag):
                found.add(node.tag)
            _component_tags(node.children, found)
        elif isinstance(node, TIf):
            for _, children in node.branches:
                _component_tags(children, found)
        elif isinstance(node, TFor):
            _component_tags(node.children, found)
    return found


def _snake(name: str) -> str:
    return re.sub(r"(?<!^)(?=[A-Z])", "_", name).lower()


@dataclass
class _LoadContext:
    root: Path  # the app root: where dotted tags resolve from
    loading: set[Path]  # files being loaded right now, for cycle detection
    current_dir: Path  # folder of the file whose code block is executing
    # Files already loaded in this load, so a file used by several components
    # becomes one class: compiled once, and an unambiguous target when hot
    # reload moves live instances onto freshly compiled classes.
    loaded: dict[Path, type]


# Set while a .weft file is being loaded, so a load_component() call inside
# its code block resolves relative paths against that file (not the process
# cwd, which in the browser is not the app folder) and shares the same root
# and cycle detection.
_LOAD: ContextVar[_LoadContext | None] = ContextVar("pyweft_load", default=None)


def _scope_id(path: Path, root: Path) -> str:
    """Style scope id: the path below the app root with folders joined by
    ``-`` (``widgets/row.weft`` -> ``widgets-row``), so equal file names in
    different folders cannot share styles. Top-level files keep their stem."""
    try:
        rel = path.relative_to(root)
    except ValueError:
        return path.stem  # loaded from outside the app root
    return "-".join(rel.with_suffix("").parts)


def _find_component(tag: str, referrer: Path, root: Path) -> Path:
    *folders, leaf = tag.split(".")
    for folder in folders:
        if not folder.isidentifier():
            raise TemplateError(
                f"<{tag}> in {referrer.name}: {folder!r} is not a valid folder "
                "name for a component tag (use letters, digits and underscores)"
            )
    base = root.joinpath(*folders) if folders else referrer.parent
    candidates = (base / f"{leaf}.weft", base / f"{_snake(leaf)}.weft")
    for candidate in candidates:
        if candidate.is_file():
            return candidate
    where = (
        f"in {'/'.join(folders)}/ under the app root"
        if folders
        else f"alongside {referrer.name}"
    )
    raise TemplateError(
        f"component <{tag}> used in {referrer.name} but no {candidates[0].name} "
        f"or {candidates[1].name} found {where}"
    )


def load_component(
    path: str | Path, name: str | None = None, *, root: str | Path | None = None
) -> type:
    """Load a ``.weft`` file and, recursively, the components it uses.

    A capitalised tag is looked up first in the code block's explicit
    ``components`` dict, then on disk:

    * ``<TodoItem>`` -- ``TodoItem.weft`` or ``todo_item.weft`` next to the
      file that uses it
    * ``<widgets.Row>`` -- ``widgets/Row.weft`` or ``widgets/row.weft`` under
      the app root, whichever file uses it

    ``root`` defaults to the folder of the first file loaded.
    """
    ctx = _LOAD.get()
    p = Path(path)
    if not p.is_absolute() and ctx is not None:
        p = ctx.current_dir / p
    p = p.resolve()
    if root is not None:
        root_dir = Path(root).resolve()
    elif ctx is not None:
        root_dir = ctx.root
    else:
        root_dir = p.parent
    loading = ctx.loading if ctx is not None else set()
    loaded = ctx.loaded if ctx is not None else {}

    if p in loaded:
        return loaded[p]
    if p in loading:
        raise TemplateError(f"circular component reference involving {p.name}")
    loading.add(p)
    token = _LOAD.set(_LoadContext(root_dir, loading, p.parent, loaded))
    try:
        text = p.read_text(encoding="utf-8")
        try:
            cls = component_from_source(
                text, name or p.stem, scope=_scope_id(p, root_dir), filename=str(p)
            )
        except TemplateError as exc:
            try:
                where = p.relative_to(root_dir).as_posix()
            except ValueError:
                where = p.name
            raise TemplateError(f"{where}: {exc}") from exc
        cls.__weft_file__ = str(p)
        cls.__weft_src__ = text

        registry = dict(cls.components)
        for tag in sorted(_component_tags(cls.__template__, set())):
            if tag not in registry:
                found = _find_component(tag, p, root_dir)
                registry[tag] = load_component(found, tag.rsplit(".", 1)[-1])
        cls.components = registry
        loaded[p] = cls
        return cls
    finally:
        _LOAD.reset(token)
        loading.discard(p)
