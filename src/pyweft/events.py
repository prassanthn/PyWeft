"""Event specs (``@keydown.enter.ctrl``) and the event object handlers get.

A template's event attribute is kept whole as the event *spec*:
``keydown.enter`` travels unchanged through the vdom and the patch ops as an
``events`` key, so two handlers for one DOM event (``@keydown.enter`` and
``@keydown.esc``) are simply two keys. The host's runtime splits the spec and
applies the modifiers inside its listener, because ``preventDefault()`` and
``stopPropagation()`` cannot wait for a round trip to Python. This module only
validates specs, so a typo is a template error instead of a handler that
silently never fires.

The payload a host sends with an event is a plain dict; see ``Event`` for the
keys the browser host fills in.
"""

from __future__ import annotations

import re
from typing import Any

# Change how the event is delivered; valid on any event.
EVENT_OPTIONS = frozenset({"prevent", "stop", "self", "once", "capture", "passive"})
# The handler runs only if these keys are held; ``exact``: and no others.
SYSTEM_KEYS = frozenset({"ctrl", "alt", "shift", "meta", "exact"})
# On mouse events, which button; on key events left/right are arrow keys.
MOUSE_BUTTONS = frozenset({"left", "middle", "right"})
KEY_EVENTS = frozenset({"keydown", "keyup", "keypress"})
# Any key, by its KeyboardEvent.key value in kebab-case: enter, a, page-down.
_KEY_NAME = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")

BIND_MODIFIERS = frozenset({"lazy", "trim", "number"})


def parse_event_spec(spec: str) -> str:
    """Validate ``click.prevent`` / ``keydown.enter.ctrl`` and return it
    normalised (modifiers lower-cased). Raises ValueError with a readable
    message for an unknown modifier."""
    name, *mods = spec.split(".")
    if not name:
        raise ValueError(f"@{spec}: missing event name")
    mods = [m.lower() for m in mods]
    for mod in mods:
        if mod in EVENT_OPTIONS or mod in SYSTEM_KEYS:
            continue
        if name in KEY_EVENTS:
            if _KEY_NAME.match(mod):
                continue  # a key name: enter, esc, a, f1, page-down ...
        elif mod in MOUSE_BUTTONS:
            continue
        hint = (
            "key modifiers such as .enter only work on keydown/keyup"
            if name not in KEY_EVENTS and _KEY_NAME.match(mod)
            else "modifiers are " + ", ".join(sorted(EVENT_OPTIONS | SYSTEM_KEYS))
        )
        raise ValueError(f"@{spec}: unknown modifier .{mod} ({hint})")
    if "passive" in mods and "prevent" in mods:
        raise ValueError(
            f"@{spec}: .passive and .prevent contradict each other (a passive "
            "listener cannot prevent the default action)"
        )
    return ".".join([name, *mods])


def parse_bind_modifiers(directive: str) -> tuple[str, ...]:
    """``bind.lazy.trim`` -> ``("lazy", "trim")``."""
    _, *mods = directive.split(".")
    mods = [m.lower() for m in mods]
    unknown = [m for m in mods if m not in BIND_MODIFIERS]
    if unknown:
        raise ValueError(
            f"@{directive}: unknown modifier .{unknown[0]} (@bind takes "
            + ", ".join(f".{m}" for m in sorted(BIND_MODIFIERS))
            + ")"
        )
    return tuple(mods)


class Event(dict):
    """The event a handler receives: a dict, with attribute access too, so
    ``event["key"]`` and ``event.key`` both work.

    Keys the browser host provides, where they apply:

    - ``type``: the DOM event name (``"click"``, ``"keydown"``)
    - ``value``: the target's value (inputs, selects, textareas)
    - ``checked``: checkboxes and radio buttons
    - ``key``, ``code``, ``repeat``: keyboard events
    - ``ctrlKey``, ``shiftKey``, ``altKey``, ``metaKey``: keyboard and mouse
    - ``clientX``, ``clientY``, ``offsetX``, ``offsetY``, ``button``,
      ``buttons``: mouse and pointer events (``deltaX``/``deltaY`` on wheel)
    - ``form``: on ``submit``, the form's fields as ``{name: value}`` (a list
      when several fields share a name)
    """

    def __getattr__(self, name: str) -> Any:
        try:
            return self[name]
        except KeyError:
            raise AttributeError(
                f"this {self.get('type', 'event')} event has no {name!r}; "
                f"it has {', '.join(sorted(self)) or 'nothing'}"
            ) from None
