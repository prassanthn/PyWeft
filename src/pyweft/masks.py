"""Input masks: text typed into a fixed shape, like a phone number.

``<input data-mask="(999) 999-9999" @bind="phone" />`` formats as the user
types: the runtime (static/runtime.js) applies the mask in the page, before
the event reaches Python, so the cursor stays where it belongs. This module
is the same rules in Python, and the executable spec for that code: keep
the two in lockstep. Use it to format a starting value, or to check one.

In a mask, ``9`` is a digit, ``a`` a letter, ``*`` a letter or digit, and
``\\`` makes the next character literal; anything else is literal text,
shown between what's typed. Typed characters are the letters and digits of
the input; literals are filled in around them, never after the last one.
"""

from __future__ import annotations

import re

_SLOTS = {"9": re.compile(r"[0-9]"), "a": re.compile(r"[A-Za-z]"), "*": re.compile(r"[A-Za-z0-9]")}
_TYPED = re.compile(r"[^A-Za-z0-9]")


def tokens(mask: str) -> list[tuple[str, str]]:
    """``[("slot", "9"), ("literal", "("), ...]``"""
    out: list[tuple[str, str]] = []
    escaped = False
    for char in mask:
        if escaped:
            out.append(("literal", char))
            escaped = False
        elif char == "\\":
            escaped = True
        elif char in _SLOTS:
            out.append(("slot", char))
        else:
            out.append(("literal", char))
    return out


def _prefix(toks: list[tuple[str, str]]) -> str:
    # Letters and digits in the literals before the first slot ("+1 (999)"):
    # typed text that starts with them doesn't fill slots with them.
    out = ""
    for kind, char in toks:
        if kind == "slot":
            break
        if not _TYPED.match(char):
            out += char
    return out


def typed(mask: str, text: str) -> str:
    """The characters of ``text`` that fill the mask's slots, in order."""
    toks = tokens(mask)
    chars = _TYPED.sub("", text)
    prefix = _prefix(toks)
    if prefix and chars.startswith(prefix):
        chars = chars[len(prefix):]
    return chars


def fill(mask: str, chars: str) -> tuple[str, list[int]]:
    """``chars`` placed into the mask: the text, and where each placed
    character ends in it (for the cursor). A character that doesn't fit its
    slot (a letter for a 9) is skipped."""
    out, ends, pending, i = "", [], "", 0
    for kind, char in tokens(mask):
        if kind == "literal":
            pending += char
            continue
        while i < len(chars) and not _SLOTS[char].match(chars[i]):
            i += 1
        if i >= len(chars):
            break
        out += pending + chars[i]
        pending = ""
        i += 1
        ends.append(len(out))
    return out, ends


def apply(mask: str, text: str) -> str:
    """``text`` (formatted or not) in the mask's shape:
    ``apply("(999) 999-9999", "5551234567")`` is ``"(555) 123-4567"``."""
    return fill(mask, typed(mask, text))[0]


def slots(mask: str) -> int:
    """How many characters the mask takes."""
    return sum(1 for kind, _ in tokens(mask) if kind == "slot")


def complete(mask: str, text: str) -> bool:
    """Whether ``text`` fills every slot of the mask."""
    return len(fill(mask, typed(mask, text))[1]) == slots(mask)
