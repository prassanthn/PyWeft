"""``@effect``: methods that re-run after a render when the state they read
changes.

There is no reactive state to subscribe to, so dependencies are discovered by
running the effect against a stand-in for ``self`` that records every state
attribute read through it -- including reads inside computed properties and
helper methods, which are re-bound to the stand-in. Only effects pay for this;
ordinary attribute access on components stays a plain attribute access.

After each render has been applied, the host calls ``Renderer.after_render()``,
which compares each effect's recorded values with the current ones and re-runs
only the effects whose inputs changed. Values are snapshotted with a deep copy,
so ``self.items.append(x)`` counts as a change, not just reassignment.
"""

from __future__ import annotations

import copy
import inspect
import types
from typing import Any, Callable

_MARK = "__pyweft_effect__"
_MISSING = object()


def effect(fn: Callable) -> Callable:
    """Mark a component method as an effect.

    The method runs after the component's first render, then again after any
    later render in which a state value it read has changed. If it returns a
    callable, that callable is the cleanup: it runs before the next run and
    when the component is disposed.
    """
    if inspect.iscoroutinefunction(fn):
        raise TypeError(_ASYNC_EFFECT.format(name=fn.__name__))
    setattr(fn, _MARK, True)
    return fn


# Only reads before the first await could be tracked, and a write after it
# would land after the render it belongs to. A task started from the effect
# makes that split explicit, and returning task.cancel makes "latest wins".
_ASYNC_EFFECT = (
    "@effect {name} cannot be async. Start the async work from a plain "
    "effect and return its cancel as the cleanup: "
    "task = self.start_task(self.load(...)); return task.cancel"
)


def effect_names(cls: type) -> list[str]:
    """Names of ``@effect`` methods on ``cls`` and its bases, base-first."""
    names: list[str] = []
    for klass in reversed(cls.__mro__):
        for name, value in vars(klass).items():
            if getattr(value, _MARK, False) and name not in names:
                names.append(name)
    return names


class EffectState:
    """Per-instance bookkeeping for one effect."""

    __slots__ = ("deps", "cleanup")

    def __init__(self) -> None:
        self.deps: dict[str, Any] | None = None  # None: never run
        self.cleanup: Callable[[], Any] | None = None


def _snapshot(value: Any) -> Any:
    try:
        return copy.deepcopy(value)
    except Exception:
        return value  # uncopyable: fall back to comparing the object itself


def _same(old: Any, new: Any) -> bool:
    try:
        return bool(old == new)
    except Exception:  # e.g. an array whose == has no single truth value
        return old is new


def _class_attr(cls: type, name: str) -> Any:
    for klass in cls.__mro__:
        if name in vars(klass):
            return vars(klass)[name]
    return _MISSING


class _Tracker:
    """Stands in for ``self`` while an effect runs.

    Reads of state are recorded, writes go through to the real component and
    are remembered so the host knows to re-render. Methods defined by the
    framework base class are bound to the real component: they touch private
    bookkeeping, not user state, and must not count as dependencies.
    """

    __slots__ = ("_pw_target", "_pw_reads", "_pw_wrote")

    def __init__(self, target: Any):
        object.__setattr__(self, "_pw_target", target)
        object.__setattr__(self, "_pw_reads", set())
        object.__setattr__(self, "_pw_wrote", False)

    def __getattribute__(self, name: str) -> Any:
        target = object.__getattribute__(self, "_pw_target")
        cls = type(target)
        attr = _class_attr(cls, name)

        if name not in vars(target):
            if isinstance(attr, property):
                return attr.fget(self) if attr.fget else getattr(target, name)
            if isinstance(attr, types.FunctionType):
                from .component import Component

                if _class_attr(Component, name) is attr:
                    return getattr(target, name)
                return types.MethodType(attr, self)
            if isinstance(attr, (staticmethod, classmethod)):
                return getattr(target, name)

        value = getattr(target, name)
        if not name.startswith("_") and not callable(value):
            object.__getattribute__(self, "_pw_reads").add(name)
        return value

    def __setattr__(self, name: str, value: Any) -> None:
        target = object.__getattribute__(self, "_pw_target")
        setattr(target, name, value)
        if not name.startswith("_"):
            object.__setattr__(self, "_pw_wrote", True)

    def __delattr__(self, name: str) -> None:
        delattr(object.__getattribute__(self, "_pw_target"), name)
        object.__setattr__(self, "_pw_wrote", True)


def _states(component: Any) -> dict[str, EffectState]:
    states = component.__dict__.get("_pw_effects")
    if states is None:
        states = {name: EffectState() for name in effect_names(type(component))}
        component.__dict__["_pw_effects"] = states
    return states


def _changed(component: Any, deps: dict[str, Any]) -> bool:
    for name, old in deps.items():
        if not _same(old, getattr(component, name, _MISSING)):
            return True
    return False


def run_effects(component: Any) -> bool:
    """Run the component's due effects. Returns True if any of them wrote
    state, meaning the host should render again."""
    wrote = False
    for name, state in _states(component).items():
        if state.deps is not None and not _changed(component, state.deps):
            continue
        if state.cleanup is not None:
            cleanup, state.cleanup = state.cleanup, None
            cleanup()
        tracker = _Tracker(component)
        fn = _class_attr(type(component), name)
        result = fn(tracker)
        if inspect.isawaitable(result):
            if inspect.iscoroutine(result):
                result.close()
            raise TypeError(_ASYNC_EFFECT.format(name=name))
        # Snapshot after the run, so an effect that writes one of its own
        # inputs settles instead of re-triggering itself on the next pass.
        state.deps = {
            dep: _snapshot(getattr(component, dep, _MISSING))
            for dep in object.__getattribute__(tracker, "_pw_reads")
        }
        state.cleanup = result if callable(result) else None
        wrote = wrote or object.__getattribute__(tracker, "_pw_wrote")
    return wrote


def dispose_effects(component: Any) -> None:
    states = component.__dict__.get("_pw_effects")
    if not states:
        return
    for state in states.values():
        if state.cleanup is not None:
            cleanup, state.cleanup = state.cleanup, None
            cleanup()
