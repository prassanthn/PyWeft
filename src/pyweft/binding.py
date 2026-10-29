"""``@bind``: which property a control binds, and converting what the user
typed back to the field's type.

The type comes from the field's *declaration* -- its annotation, else the type
of its class-level default -- not from its current value. Converting by the
current value lost the type for good the moment a bound number box was cleared
(the field became ``""``, and every later keystroke stayed a string).
"""

from __future__ import annotations

import functools
import inspect
import types
import typing
from typing import Any

# Returned by ``convert`` when the text cannot be stored in the field (letters
# in a number box, an empty box for a field that cannot be None): the field
# keeps its last good value while the user is still typing.
KEEP = object()

_SCALARS = (bool, int, float, str)
_TRUE = {"true", "1", "on", "yes"}
_FALSE = {"false", "0", "off", "no", ""}


def bind_kind(tag: str, attrs: dict[str, str]) -> str:
    """``"checkbox"``, ``"radio"`` or ``"value"`` (text, number, textarea,
    select ...): what the binding reads and writes on the element."""
    if tag == "input":
        kind = attrs.get("type", "").lower()
        if kind in ("checkbox", "radio"):
            return kind
    return "value"


@functools.lru_cache(maxsize=1024)  # called for every bound element, every render
def declared_type(cls: type, field: str) -> tuple[type | None, bool]:
    """(scalar type or None if unknown, whether None is allowed)."""
    annotation = _annotation(cls, field)
    if annotation is not None:
        args = typing.get_args(annotation)
        if typing.get_origin(annotation) in (typing.Union, types.UnionType):
            allows_none = type(None) in args
            scalars = [a for a in args if a in _SCALARS]
            return (scalars[0] if len(scalars) == 1 else None), allows_none
        if annotation in _SCALARS:
            return annotation, False
    default = getattr(cls, field, None)
    if default is None:
        return None, True
    return (type(default) if type(default) in _SCALARS else None), False


def _annotation(cls: type, field: str) -> Any:
    for klass in cls.__mro__:
        try:
            annotations = inspect.get_annotations(klass, eval_str=True)
        except Exception:
            try:
                annotations = inspect.get_annotations(klass)
            except Exception:
                continue
        if field in annotations:
            value = annotations[field]
            return None if isinstance(value, str) else value
    return None


def prop_value(cls: type, name: str, text: str) -> Any:
    """A plain attribute on a component tag, as the declared field's type:
    ``cols="3"`` -> 3, ``disabled="true"`` -> True. Raises ValueError (with
    a message for the template author) when the text doesn't fit."""
    target, allows_none = declared_type(cls, name)
    if target is bool:
        lowered = text.strip().lower()
        # An empty value is the attribute's presence: disabled="" is on.
        if lowered in ("", "true", "1", "yes", "on", name.lower()):
            return True
        if lowered in ("false", "0", "no", "off"):
            return False
        raise ValueError(f"expects true or false, got {text!r}")
    if target in (int, float):
        if allows_none and not text.strip():
            return None
        try:
            return target(text.strip())
        except ValueError:
            kind = "a whole number" if target is int else "a number"
            raise ValueError(f"expects {kind}, got {text!r}") from None
    return text


def convert(text: str, target: type | None, allows_none: bool, number: bool) -> Any:
    """What to store for ``text`` typed into a field of type ``target``, or
    ``KEEP``. ``number`` (``@bind.number``) parses even when the field's type
    is unknown or ``str``."""
    if target is bool:
        lowered = text.strip().lower()
        if lowered in _TRUE:
            return True
        if lowered in _FALSE:
            return False
        return KEEP
    if target in (int, float) or number:
        stripped = text.strip()
        if not stripped:
            return None if allows_none else KEEP
        for parse in ((int,) if target is int else (float,) if target is float else (int, float)):
            try:
                return parse(stripped)
            except ValueError:
                continue
        return KEEP
    if target is None and allows_none and text == "":
        return None
    return text
