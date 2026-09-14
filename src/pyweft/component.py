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
from pathlib import Path
from typing import Any, Callable

from .parser import (
    TElement,
    TemplateError,
    TFor,
    TIf,
    parse_template,
    split_source,
)


class Component:
    __template__: list[Any] = []
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
        """Called once before the first render."""

    def on_after_render(self, first: bool) -> None:
        """Called after each render has been applied."""

    def on_dispose(self) -> None:
        """Called when the component is torn down."""

    # ---------------------------------------------------------------- state

    def state_has_changed(self) -> None:
        self._dirty = True
        if self._on_change is not None:
            self._on_change(self)

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


def component_from_source(
    src: str,
    name: str = "Component",
    base: type = Component,
    components: dict[str, type] | None = None,
) -> type:
    template_src, code_src = split_source(src)
    nodes = parse_template(template_src)

    namespace: dict[str, Any] = {}
    exec(compile(textwrap.dedent(code_src), f"<{name}.weft>", "exec"), namespace)
    namespace.pop("__builtins__", None)
    namespace["__template__"] = nodes
    # A `components` dict in the code block wins over the passed-in registry.
    namespace["components"] = {**(components or {}), **namespace.get("components", {})}

    return type(name, (base,), namespace)


_CONTROL_TAGS = {"If", "ElseIf", "Else", "For"}


def _component_tags(nodes: list[Any], found: set[str]) -> set[str]:
    for node in nodes:
        if isinstance(node, TElement):
            if node.tag[0].isupper() and node.tag not in _CONTROL_TAGS:
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


def load_component(
    path: str | Path, name: str | None = None, _loading: set[Path] | None = None
) -> type:
    """Load a ``.weft`` file, resolving child components Vue-SFC-style.

    A capitalised tag like ``<TodoItem>`` is looked up first in the code
    block's explicit ``components`` dict, then as ``TodoItem.weft`` or
    ``todo_item.weft`` next to the referencing file.
    """
    p = Path(path).resolve()
    _loading = _loading if _loading is not None else set()
    if p in _loading:
        raise TemplateError(f"circular component reference involving {p.name}")
    _loading.add(p)
    try:
        cls = component_from_source(p.read_text(encoding="utf-8"), name or p.stem)

        registry = dict(cls.components)
        for tag in sorted(_component_tags(cls.__template__, set())):
            if tag in registry:
                continue
            for candidate in (p.parent / f"{tag}.weft", p.parent / f"{_snake(tag)}.weft"):
                if candidate.exists():
                    registry[tag] = load_component(candidate, tag, _loading)
                    break
            else:
                raise TemplateError(
                    f"component <{tag}> used in {p.name} but no {tag}.weft or "
                    f"{_snake(tag)}.weft found alongside it"
                )
        cls.components = registry
        return cls
    finally:
        _loading.discard(p)
