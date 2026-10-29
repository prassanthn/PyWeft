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

import asyncio
import functools
import inspect
import sys
from functools import partial
from typing import Any, Awaitable, Callable

from .binding import KEEP, bind_kind, convert, declared_type, prop_value
from .component import component_named, declared_props, is_component_tag
from .effects import dispose_effects, run_effects
from .events import Event
from .expressions import ExpressionError, Scope, eval_expr, render_parts, run_handler
from .parser import TElement, TemplateError, TFill, TFor, TIf, TSlot, TStatic
from .styles import marker
from .vdom import Element, Node, Text

# Consecutive after-render passes in which effects changed state. Past this,
# effects are feeding each other forever and it is a bug in the app.
_MAX_EFFECT_PASSES = 100


class EffectLoopError(RuntimeError):
    pass


# Eager tasks (3.12+) run up to their first real suspension inside the call
# that started them, so `self.loading = True` before the first await lands in
# the render that follows the click instead of one loop pass later.
_EAGER = sys.version_info >= (3, 12)


def _running_loop() -> asyncio.AbstractEventLoop:
    try:
        return asyncio.get_running_loop()
    except RuntimeError:
        raise RuntimeError(
            "async handlers and start_task() need a running asyncio event loop. "
            "The browser always has one; headless, drive the renderer from "
            "inside asyncio.run(...) and await renderer.idle() for the tasks"
        ) from None


async def _await(awaitable: Awaitable) -> Any:
    return await awaitable


def _dispose(component: Any) -> None:
    for task in component.__dict__.pop("_pw_tasks", ()):
        task.cancel()
    component.__dict__.pop("_pw_start", None)
    # Effect cleanups first: on_dispose is user code that may not call super().
    dispose_effects(component)
    component.on_dispose()
    # A timer the component forgot to cancel must not keep requesting renders.
    component.__dict__.pop("_pw_invalidate", None)


@functools.lru_cache(maxsize=1024)
def slot_names(cls: type) -> frozenset[str]:
    """The slots a component's template renders, anywhere in it."""
    found: set[str] = set()

    def walk(nodes: list[Any]) -> None:
        for node in nodes:
            if isinstance(node, TSlot):
                found.add(node.name)
            if isinstance(node, TIf):
                for _, children in node.branches:
                    walk(children)
            elif isinstance(node, (TElement, TFor, TSlot, TFill)):
                walk(node.children)

    walk(cls.__template__)
    return frozenset(found)


def _is_blank(tnode: Any) -> bool:
    """Whitespace between <Fill>s on one line is not default-slot content."""
    return isinstance(tnode, TStatic) and all(
        kind == "static" and not text.strip() for kind, text in tnode.parts
    )


def _merge_attrs(attrs: dict[str, str], extra: dict[str, str]) -> None:
    """Attributes passed to a component, onto its root element: ``class``
    and ``style`` add to the element's own, anything else replaces it."""
    for name, value in extra.items():
        own = attrs.get(name)
        if name == "class" and own:
            attrs[name] = f"{own} {value}"
        elif name == "style" and own:
            attrs[name] = f"{own.rstrip().rstrip(';')}; {value}"
        else:
            attrs[name] = value


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
        self._effect_passes = 0
        # Set by the host: called when a component's state changed outside
        # dispatch/render/after_render, meaning nobody is about to render. The
        # host should schedule a render (and coalesce repeated calls); see
        # needs_render(). Without it, such changes wait for the next event.
        self.on_invalidate: Callable[[], Any] | None = None
        # Set by the host: called with the exception when a task (an async
        # handler, async on_init, start_task) fails, since no caller is left
        # to raise it to. Unset, it goes to the event loop's exception handler.
        self.on_error: Callable[[BaseException], Any] | None = None
        self._busy = 0
        self._watch(component)

    def _watch(self, component: Any) -> None:
        component.__dict__["_pw_invalidate"] = self._invalidated
        component.__dict__["_pw_start"] = partial(self._start, component)

    def init_root(self) -> None:
        """Run the root component's ``on_init`` (as a task if it is async).
        Hosts call this once, before the first render; child components get
        theirs from the renderer when they first appear."""
        self._hook(self.component, self.component.on_init())

    # ----------------------------------------------------------------- tasks

    def _hook(self, component: Any, result: Any) -> None:
        if inspect.isawaitable(result):
            self._start(component, result)

    def _start(self, component: Any, awaitable: Awaitable) -> asyncio.Task:
        """Run ``awaitable`` as a task owned by ``component``: cancelled when
        the component is disposed, and re-rendering it when it finishes."""
        try:
            loop = _running_loop()
        except RuntimeError:
            if inspect.iscoroutine(awaitable):
                awaitable.close()  # no "never awaited" warning on top
            raise
        coro = awaitable if inspect.iscoroutine(awaitable) else _await(awaitable)
        if _EAGER and loop.is_running():
            task = asyncio.Task(coro, loop=loop, eager_start=True)
        else:
            task = loop.create_task(coro)
            # The first step runs on the loop's next pass; render after it.
            loop.call_soon(component.state_has_changed)
        if task.done():
            # Finished without suspending, inside the call that started it, so
            # the render the host does after that call already shows it.
            self._finished(component, task, render=False)
        else:
            component.__dict__.setdefault("_pw_tasks", set()).add(task)
            task.add_done_callback(partial(self._finished, component))
        return task

    def _finished(self, component: Any, task: asyncio.Task, render: bool = True) -> None:
        component.__dict__.get("_pw_tasks", set()).discard(task)
        if task.cancelled():
            return
        exc = task.exception()
        if exc is not None:
            if self.on_error is not None:
                self.on_error(exc)
            else:
                task.get_loop().call_exception_handler(
                    {"message": "exception in a PyWeft task", "exception": exc, "task": task}
                )
        if render:
            # Whatever the task changed, even if it then failed.
            component.state_has_changed()

    def pending_tasks(self) -> list[asyncio.Task]:
        """Unfinished tasks of every live component."""
        return [
            task
            for c in (self.component, *self.instances.values())
            for task in c.__dict__.get("_pw_tasks", ())
        ]

    async def idle(self) -> None:
        """Wait until every live component's tasks have finished, including
        tasks started by those tasks. For headless tests: dispatch, await
        this, then render to see the finished state."""
        while pending := self.pending_tasks():
            await asyncio.wait(pending)
            await asyncio.sleep(0)  # let the done callbacks run

    def _invalidated(self) -> None:
        # Inside a host-driven cycle the host renders afterwards anyway.
        if self._busy == 0 and self.on_invalidate is not None:
            self.on_invalidate()

    def needs_render(self) -> bool:
        """True if any live component changed state since the last render."""
        return any(
            getattr(c, "_dirty", False)
            for c in (self.component, *self.instances.values())
        )

    # ---------------------------------------------------------------- render

    def render(self) -> list[Node]:
        self._busy += 1
        previous_handlers = self.handlers
        try:
            self.handlers = {}
            self._seen = set()
            out: list[Node] = []
            try:
                self._emit(self.component.__template__, Scope(self.component), [], out)
            except BaseException:
                # The page still shows the last good render; keep its handlers
                # working (matters most when a hot reload's render fails).
                self.handlers = previous_handlers
                raise
            for inst_id in [i for i in self.instances if i not in self._seen]:
                _dispose(self.instances.pop(inst_id))
            self.component._dirty = False
            for instance in self.instances.values():
                instance._dirty = False
            return out
        finally:
            self._busy -= 1

    def after_render(self) -> bool:
        """Call once the latest render's patches have been applied.

        Runs due ``@effect`` methods and ``on_after_render`` on every live
        component, children before the root. Returns True when that changed
        state, meaning the host should render, diff and apply again (then call
        this again).
        """
        rerender = False
        self._busy += 1
        try:
            for component in [*self.instances.values(), self.component]:
                first = not getattr(component, "_rendered_once", False)
                component._rendered_once = True
                wrote = run_effects(component)
                self._hook(component, component.on_after_render(first))
                if wrote or getattr(component, "_dirty", False):
                    rerender = True
        finally:
            self._busy -= 1

        if not rerender:
            self._effect_passes = 0
            return False
        self._effect_passes += 1
        if self._effect_passes > _MAX_EFFECT_PASSES:
            self._effect_passes = 0
            raise EffectLoopError(
                f"effects changed state on {_MAX_EFFECT_PASSES} renders in a row; "
                "an effect is probably writing state that another effect reads"
            )
        return True

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

            elif isinstance(tnode, TSlot):
                self._slot(tnode, scope, path, out, key)

            elif isinstance(tnode, TFill):
                raise TemplateError(
                    f'<Fill name="{tnode.name}"> must be directly inside a component tag'
                )

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
        """A capitalised tag (or dotted tag ending in one, ``widgets.Row``)
        naming an entry in the owner's registry is a child component; anything
        else is a plain element."""
        if not is_component_tag(tag):
            return None
        owner = type(scope.component)
        registry = getattr(owner, "components", None)
        found = registry.get(tag) if registry else None
        # Classes built with component_from_source (no loader) still find
        # components they imported.
        return found if found is not None else component_named(owner, tag)

    def _component(
        self,
        cls: type,
        tnode: TElement,
        scope: Scope,
        path: list[str],
        out: list[Node],
        key: Any,
    ) -> None:
        if tnode.bind_mods:
            raise TemplateError(
                f"<{tnode.tag}>: @bind on a component takes no modifiers"
            )

        # Props flow down on every render: interpolated attrs as strings,
        # :attrs as evaluated Python values, @events as on_<event> callbacks
        # bound to the *parent's* scope (that is what emit() calls). An
        # attribute the child does not declare is not a prop: it passes
        # through to the child's root element (class, style, id, aria-*).
        declared = declared_props(cls)
        props: dict[str, Any] = {}
        passthrough: dict[str, str] = {}
        for name, parts in tnode.attrs.items():
            value = render_parts(parts, scope)
            if name in declared:
                try:
                    props[name] = prop_value(cls, name, value)
                except ValueError as exc:
                    raise TemplateError(
                        f'<{tnode.tag} {name}="{value}">: {cls.__name__}.{name} {exc}'
                    ) from None
            else:
                passthrough[name] = value
        for name, expr in tnode.expr_attrs.items():
            value = eval_expr(expr, scope)
            if name in declared:
                props[name] = value
            elif value is not None and value is not False:
                passthrough[name] = "" if value is True else str(value)
        for event, expr in tnode.events.items():
            if "." in event:
                raise TemplateError(
                    f"<{tnode.tag} @{event}>: modifiers apply to page events, "
                    "not to a component's own events"
                )
            props[f"on_{event}"] = self._make_handler(expr, scope)
        if tnode.bind:
            self._bind_component(tnode.bind, scope, props)
        slots = self._collect_slots(cls, tnode, scope)

        inst_id = "/".join(path)
        instance = self.instances.get(inst_id)
        if type(instance) is not cls:
            if instance is not None:
                _dispose(instance)
            instance = cls(**props)
            self._watch(instance)
            self._hook(instance, instance.on_init())
            self.instances[inst_id] = instance
        else:
            for name, value in props.items():
                setattr(instance, name, value)
        self._seen.add(inst_id)
        # Replaced every render: what the parent passes this time is what the
        # child's <Slot>s show (and what has_slot() reports).
        instance.__dict__["_pw_slots"] = slots

        before = len(out)
        self._emit(cls.__template__, Scope(instance), path, out, key)
        roots = [node for node in out[before:] if isinstance(node, Element)]
        # The parent's scoped styles may target the child's root element(s),
        # so those carry the parent's marker as well as the child's own.
        parent_scope = getattr(type(scope.component), "__scope__", None)
        if parent_scope:
            for node in roots:
                node.attrs.setdefault(marker(parent_scope), "")
        if passthrough:
            if len(roots) != 1:
                raise TemplateError(
                    f"<{tnode.tag}> renders {len(roots)} root elements, so "
                    f"{', '.join(sorted(passthrough))} has nowhere to go; give "
                    f"{cls.__name__} a single root element or declare "
                    "the attribute as a field"
                )
            _merge_attrs(roots[0].attrs, passthrough)

    def _bind_component(self, field: str, scope: Scope, props: dict[str, Any]) -> None:
        """``<TextField @bind="email" />``: the child gets the field as its
        ``value`` prop and reports changes with ``emit("update", new)``. A
        parent's own ``@update`` handler runs after the field is set."""
        parent = scope.component
        own = props.get("on_update")
        props["value"] = getattr(parent, field, None)

        def update(new: Any = None) -> Any:
            setattr(parent, field, new)
            if own is not None:
                return own(new)
            parent.state_has_changed()
            return None

        props["on_update"] = update

    @staticmethod
    def _collect_slots(
        cls: type, tnode: TElement, scope: Scope
    ) -> dict[str, tuple[list[Any], Scope]]:
        """Content between a component's tags, by slot name. It is rendered
        later, inside the child, but in *this* scope: the parent's state,
        handlers and loop variables."""
        fills: dict[str, list[Any]] = {}
        loose: list[Any] = []
        for child in tnode.children:
            if isinstance(child, TFill):
                if child.name in fills:
                    raise TemplateError(
                        f'<{tnode.tag}> has two <Fill name="{child.name}">'
                    )
                fills[child.name] = child.children
            elif not _is_blank(child):
                loose.append(child)
        if loose:
            if "default" in fills:
                raise TemplateError(
                    f'<{tnode.tag}> has both content outside <Fill> and a <Fill '
                    'name="default">; use one or the other'
                )
            fills["default"] = loose
        accepted = slot_names(cls)
        for name in fills:
            if name not in accepted:
                where = (
                    f"it has {', '.join(sorted(accepted))}" if accepted else "it has no <Slot>"
                )
                what = "content between its tags" if name == "default" else f'<Fill name="{name}">'
                raise TemplateError(
                    f"<{tnode.tag}> was given {what}, but {cls.__name__} would "
                    f"never show it: {where}"
                )
        return {name: (nodes, scope) for name, nodes in fills.items()}

    def _slot(
        self, tnode: TSlot, scope: Scope, path: list[str], out: list[Node], key: Any
    ) -> None:
        provided = scope.component.__dict__.get("_pw_slots", {}).get(tnode.name)
        if provided is None:
            # Nothing passed: the slot's own children are the fallback.
            self._emit(tnode.children, scope, path, out, key)
            return
        nodes, fill_scope = provided
        slot_props = {
            name: render_parts(parts, scope) for name, parts in tnode.attrs.items()
        }
        for name, expr in tnode.expr_attrs.items():
            slot_props[name] = eval_expr(expr, scope)
        if slot_props:
            fill_scope = fill_scope.child(**slot_props)
        self._emit(nodes, fill_scope, path, out, key)

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
        # Scoped <style> support: mark the element as belonging to its
        # component so the rewritten selectors can find it.
        scope_id = getattr(type(scope.component), "__scope__", None)
        if scope_id:
            attrs[marker(scope_id)] = ""
        events: dict[str, str] = {}
        prefix = "/".join(path)

        for spec, expr in tnode.events.items():
            if not expr.strip():
                # @submit.prevent="": modifiers only. The host applies them;
                # an empty id means there is nothing to call.
                events[spec] = ""
                continue
            handler_id = f"{prefix}#{spec}"
            self.handlers[handler_id] = self._make_handler(expr, scope)
            events[spec] = handler_id

        if tnode.bind:
            self._bind(tnode, scope, attrs, events, prefix)

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
                # Not a bare name: an expression such as @click="remove(item)",
                # or inline statements such as @click="count += 1".
                result = run_handler(expr, scope.child(event=payload))
            if inspect.isawaitable(result):
                # An async handler: runs on as a task, which renders again
                # when it finishes.
                result = self._start(component, result)
            component.state_has_changed()
            return result

        return handler

    def _bind(
        self,
        tnode: TElement,
        scope: Scope,
        attrs: dict[str, str],
        events: dict[str, str],
        prefix: str,
    ) -> None:
        field, mods = tnode.bind, tnode.bind_mods
        kind = bind_kind(tnode.tag, attrs)
        current = getattr(scope.component, field, None)
        if kind == "checkbox":
            if current:
                attrs["checked"] = ""
        elif kind == "radio":
            if current is not None and str(current) == attrs.get("value"):
                attrs["checked"] = ""
        else:
            attrs.setdefault("value", "" if current is None else str(current))

        # Checkboxes and radios report a choice on change; .lazy waits for
        # change (focus leaving the box) instead of every keystroke.
        spec = "change" if kind != "value" or "lazy" in mods else "input"
        bind_handler = self._make_bind_handler(field, scope, kind, mods)
        handler_id = events.get(spec)
        own = self.handlers.get(handler_id) if handler_id else None
        if own is None:
            handler_id = f"{prefix}#bind"
            self.handlers[handler_id] = bind_handler
        else:
            # @bind and the element's own @input: update the field first, so
            # the handler already sees the new value.
            def both(event: Any = None) -> Any:
                bind_handler(event)
                return own(event)

            self.handlers[handler_id] = both
        events[spec] = handler_id

    def _make_bind_handler(
        self, field: str, scope: Scope, kind: str, mods: tuple[str, ...]
    ) -> Callable:
        component = scope.component
        target, allows_none = declared_type(type(component), field)

        def handler(event: dict | None = None) -> None:
            event = event or {}
            if kind == "checkbox":
                value: Any = bool(event.get("checked"))
            else:
                text = str(event.get("value", ""))
                if "trim" in mods:
                    text = text.strip()
                value = convert(text, target, allows_none, "number" in mods)
            if value is not KEEP:
                setattr(component, field, value)
            component.state_has_changed()

        return handler

    def dispatch(self, handler_id: str, event: dict | None = None) -> Any:
        handler = self.handlers.get(handler_id)
        if handler is None:
            return None  # stale id from a since-replaced render
        if type(event) is dict:
            event = Event(event)  # event.key as well as event["key"]
        self._busy += 1
        try:
            return handler(event)
        finally:
            self._busy -= 1
