"""Walk a parsed template and produce a vdom tree.

Handler ids are path strings built from *keys where available*, falling back to
sibling index. That matters: if an id were purely positional, every handler in
a list would change identity whenever the list reordered, and the diff would
churn event bindings on every move. With keyed segments, a row keeps its
handler id wherever it lands.

The handler table is rebuilt from scratch on every render, so ids belonging to
nodes that no longer exist simply vanish and a late event against a stale id is
a no-op rather than a crash.
"""

from __future__ import annotations

import inspect
from typing import Any, Callable

from .expressions import ExpressionError, Scope, eval_expr, render_parts
from .parser import TElement, TemplateError, TFor, TIf, TStatic
from .vdom import Element, Node, Text


def _takes_arg(fn: Callable) -> bool:
    """Does this callable want the event object passed in?"""
    try:
        sig = inspect.signature(fn)
    except (TypeError, ValueError):
        return False
    for param in sig.parameters.values():
        if param.kind is param.VAR_POSITIONAL:
            return True
        if (
            param.kind in (param.POSITIONAL_ONLY, param.POSITIONAL_OR_KEYWORD)
            and param.default is param.empty
        ):
            return True
    return False


class Renderer:
    def __init__(self, component: Any):
        self.component = component
        self.handlers: dict[str, Callable[[dict | None], Any]] = {}
        # Child component instances, keyed by template path so they keep their
        # state across parent re-renders. Rebuilding this every render would
        # reset every child -- the whole point of the cache is that it isn't.
        self.instances: dict[str, Any] = {}
        self._seen: set[str] = set()

    # ---------------------------------------------------------------- render

    def render(self) -> list[Node]:
        self.handlers = {}
        self._seen = set()
        out: list[Node] = []
        self._emit(self.component.__template__, Scope(self.component), [], out)
        for inst_id in [i for i in self.instances if i not in self._seen]:
            self.instances.pop(inst_id).on_dispose()
        self.component._dirty = False
        return out

    def _emit(
        self,
        tnodes: list[Any],
        scope: Scope,
        path: list[str],
        out: list[Node],
        key: Any = None,
    ) -> None:
        for tnode in tnodes:
            if isinstance(tnode, TStatic):
                out.append(Text(render_parts(tnode.parts, scope)))

            elif isinstance(tnode, TElement):
                node_key = key
                if node_key is None and tnode.key_expr:
                    node_key = eval_expr(tnode.key_expr, scope)
                segment = (
                    f"k:{node_key}" if node_key is not None else f"i:{len(out)}"
                )
                comp_cls = self._resolve_component(scope, tnode.tag)
                if comp_cls is not None:
                    self._component(
                        comp_cls, tnode, scope, path + [segment], out, node_key
                    )
                else:
                    out.append(
                        self._element(tnode, scope, path + [segment], node_key)
                    )

            elif isinstance(tnode, TIf):
                for cond, children in tnode.branches:
                    if cond is None or eval_expr(cond, scope):
                        self._emit(children, scope, path, out, key)
                        break

            elif isinstance(tnode, TFor):
                self._loop(tnode, scope, path, out)

            else:  # pragma: no cover - defensive
                raise TemplateError(f"unknown template node {tnode!r}")

    def _loop(
        self, tnode: TFor, scope: Scope, path: list[str], out: list[Node]
    ) -> None:
        items = eval_expr(tnode.iter_src, scope)
        if items is None:
            return
        for index, item in enumerate(items):
            child_scope = scope.child(**{tnode.var: item})
            if tnode.index_var:
                child_scope = child_scope.child(**{tnode.index_var: index})
            item_key = (
                eval_expr(tnode.key_expr, child_scope) if tnode.key_expr else None
            )
            before = len(out)
            self._emit(tnode.children, child_scope, path, out, item_key)
            if item_key is not None:
                elements = [n for n in out[before:] if isinstance(n, Element)]
                if len(elements) != 1:
                    raise TemplateError(
                        "a keyed <For> body must produce exactly one element "
                        f"per item, got {len(elements)}"
                    )

    # ------------------------------------------------------------ components

    @staticmethod
    def _resolve_component(scope: Scope, tag: str) -> type | None:
        """A capitalised tag naming an entry in the owner's registry is a
        child component; anything else is a plain element."""
        if not tag[0].isupper():
            return None
        registry = getattr(type(scope.component), "components", None)
        return registry.get(tag) if registry else None

    def _component(
        self,
        cls: type,
        tnode: TElement,
        scope: Scope,
        path: list[str],
        out: list[Node],
        key: Any,
    ) -> None:
        if tnode.children:
            raise TemplateError(
                f"<{tnode.tag}> has children, but slots are not supported yet"
            )
        if tnode.bind:
            raise TemplateError(f"@bind is not supported on component <{tnode.tag}>")

        # Props flow down on every render: interpolated attrs as strings,
        # :attrs as evaluated Python values, @events as on_<event> callbacks
        # bound to the *parent's* scope (that is what emit() calls).
        props: dict[str, Any] = {
            name: render_parts(parts, scope) for name, parts in tnode.attrs.items()
        }
        for name, expr in tnode.expr_attrs.items():
            props[name] = eval_expr(expr, scope)
        for event, expr in tnode.events.items():
            props[f"on_{event}"] = self._make_handler(expr, scope)

        inst_id = "/".join(path)
        instance = self.instances.get(inst_id)
        if type(instance) is not cls:
            if instance is not None:
                instance.on_dispose()
            instance = cls(**props)
            instance.on_init()
            self.instances[inst_id] = instance
        else:
            for name, value in props.items():
                setattr(instance, name, value)
        self._seen.add(inst_id)

        self._emit(cls.__template__, Scope(instance), path, out, key)

    # -------------------------------------------------------------- elements

    def _element(
        self, tnode: TElement, scope: Scope, path: list[str], key: Any
    ) -> Element:
        attrs = {
            name: render_parts(parts, scope) for name, parts in tnode.attrs.items()
        }
        # :attr="expr" on a plain element: None/False drops the attribute and
        # True keeps it valueless, so :disabled="busy" works like Vue's.
        for name, expr in tnode.expr_attrs.items():
            value = eval_expr(expr, scope)
            if value is None or value is False:
                continue
            attrs[name] = "" if value is True else str(value)
        events: dict[str, str] = {}
        prefix = "/".join(path)

        for event, expr in tnode.events.items():
            handler_id = f"{prefix}#{event}"
            self.handlers[handler_id] = self._make_handler(expr, scope)
            events[event] = handler_id

        if tnode.bind:
            value = getattr(scope.component, tnode.bind, "")
            attrs.setdefault("value", "" if value is None else str(value))
            handler_id = f"{prefix}#bind"
            self.handlers[handler_id] = self._make_bind_handler(tnode.bind, scope)
            events.setdefault("input", handler_id)

        children: list[Node] = []
        self._emit(tnode.children, scope, path, children)

        return Element(
            tag=tnode.tag, attrs=attrs, events=events, children=children, key=key
        )

    # -------------------------------------------------------------- handlers

    def _make_handler(self, expr: str, scope: Scope) -> Callable:
        # The owning component, not the root: a bare name in a child template
        # must resolve to the child's method, and its state_has_changed must
        # mark the child dirty.
        component = scope.component
        is_name = expr.isidentifier()

        def handler(event: Any = None) -> Any:
            # "no event" defaults to {}, but a falsy payload (0, "", False)
            # from an emit must pass through untouched.
            payload = {} if event is None else event
            if is_name:
                fn = getattr(component, expr, None)
                if not callable(fn):
                    raise ExpressionError(f"no handler named {expr!r}")
                result = fn(payload) if _takes_arg(fn) else fn()
            else:
                # Not a bare name, so evaluate it -- which performs the call in
                # something like @click="remove(item)".
                result = eval_expr(expr, scope.child(event=payload))
            component.state_has_changed()
            return result

        return handler

    def _make_bind_handler(self, field: str, scope: Scope) -> Callable:
        component = scope.component

        def handler(event: dict | None = None) -> None:
            value: Any = (event or {}).get("value", "")
            current = getattr(component, field, None)
            # Coerce back to the type the state already had, so a bound int
            # field doesn't silently turn into a string on first keystroke.
            if isinstance(current, bool):
                value = bool(value)
            elif isinstance(current, int):
                try:
                    value = int(value)
                except (TypeError, ValueError):
                    pass
            elif isinstance(current, float):
                try:
                    value = float(value)
                except (TypeError, ValueError):
                    pass
            setattr(component, field, value)
            component.state_has_changed()

        return handler

    def dispatch(self, handler_id: str, event: dict | None = None) -> Any:
        handler = self.handlers.get(handler_id)
        if handler is None:
            return None  # stale id from a since-replaced render
        return handler(event)
