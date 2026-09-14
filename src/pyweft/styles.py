"""Component-scoped CSS.

A ``<style>`` block in a ``.weft`` file applies only to elements that
component renders. The mechanism is the usual one: the renderer stamps a
marker attribute (``data-w-<scope>``) on every element the component emits,
and every selector in the block gets that attribute appended to its last
compound selector, so ``.row:hover`` becomes ``.row[data-w-todo_item]:hover``.

Both halves derive the scope id from the same place (the component's file
stem, via the loader), which is what keeps them in agreement.

This is deliberately a small string walker rather than a CSS parser. It
understands braces, quoted strings, comma-separated selector lists, nested
conditional at-rules, and pseudo-elements. It does not try to validate CSS.
"""

from __future__ import annotations

import re

_COMMENT_RE = re.compile(r"/\*.*?\*/", re.S)
# At-rules whose block contains ordinary style rules that must be scoped too.
_CONDITIONAL_AT_RULES = ("@media", "@supports", "@container", "@layer", "@scope")
# Pseudo-elements the marker must be inserted in front of, legacy single-colon
# spellings included.
_PSEUDO_ELEMENT_RE = re.compile(
    r"::|:(?:before|after|first-line|first-letter|selection|marker|placeholder)\b"
)


def marker(scope_id: str) -> str:
    """The attribute name stamped on elements of the component ``scope_id``."""
    return f"data-w-{scope_id}"


def scope_css(css: str, scope_id: str) -> str:
    """Rewrite every selector in ``css`` so it only matches ``scope_id``."""
    attr = f"[{marker(scope_id)}]"
    return _scope_block(_COMMENT_RE.sub("", css), attr)


def collect_styles(root: type) -> str:
    """Concatenate the scoped styles of ``root`` and every component it can
    reach through the ``components`` registries, each class once."""
    seen: set[type] = set()
    parts: list[str] = []

    def walk(cls: type) -> None:
        if cls in seen:
            return
        seen.add(cls)
        style = getattr(cls, "__style__", "")
        if style:
            parts.append(style)
        for child in getattr(cls, "components", {}).values():
            walk(child)

    walk(root)
    return "\n".join(parts)


# ------------------------------------------------------------------ internals


def _match_brace(css: str, open_at: int) -> int:
    """Index of the ``}`` closing the ``{`` at ``open_at``; quoted strings are
    skipped so ``content: "}"`` does not confuse the count."""
    depth = 0
    quote: str | None = None
    i = open_at
    while i < len(css):
        ch = css[i]
        if quote:
            if ch == "\\":
                i += 1
            elif ch == quote:
                quote = None
        elif ch in "\"'":
            quote = ch
        elif ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return i
        i += 1
    return len(css)  # unbalanced; treat the rest as the block


def _scope_block(css: str, attr: str) -> str:
    out: list[str] = []
    i = 0
    while i < len(css):
        j = css.find("{", i)
        if j == -1:
            out.append(css[i:])
            break
        k = _match_brace(css, j)
        prelude, body = css[i:j], css[j + 1 : k]
        # Statements before the rule (``@import ...;``, ``@charset ...;``)
        # pass through untouched; only the text after the last ``;`` selects.
        head, sep, selector = prelude.rpartition(";")
        out.append(head + sep)
        stripped = selector.strip()
        if stripped.startswith("@"):
            name = stripped.split(None, 1)[0].lower()
            inner = _scope_block(body, attr) if name in _CONDITIONAL_AT_RULES else body
            out.append(f"{selector}{{{inner}}}")
        elif stripped:
            out.append(f"{_scope_selectors(selector, attr)}{{{body}}}")
        else:
            out.append(f"{selector}{{{body}}}")
        i = k + 1
    return "".join(out)


def _split_top_level(text: str, sep: str) -> list[str]:
    parts: list[str] = []
    depth = 0
    start = 0
    for i, ch in enumerate(text):
        if ch in "([":
            depth += 1
        elif ch in ")]":
            depth -= 1
        elif ch == sep and depth == 0:
            parts.append(text[start:i])
            start = i + 1
    parts.append(text[start:])
    return parts


def _scope_selectors(prelude: str, attr: str) -> str:
    leading = prelude[: len(prelude) - len(prelude.lstrip())]
    scoped = [
        _scope_selector(s.strip(), attr)
        for s in _split_top_level(prelude, ",")
        if s.strip()
    ]
    return leading + ", ".join(scoped) + " "


def _scope_selector(selector: str, attr: str) -> str:
    # Walk back from the end to the start of the last compound selector: the
    # first combinator (space, >, +, ~) that is not inside () or [].
    depth = 0
    start = 0
    for i in range(len(selector) - 1, -1, -1):
        ch = selector[i]
        if ch in ")]":
            depth += 1
        elif ch in "([":
            depth -= 1
        elif depth == 0 and ch in " >+~":
            start = i + 1
            break
    compound = selector[start:]
    # Insert before a pseudo-element, after everything else in the compound.
    pos = len(compound)
    depth = 0
    for i, ch in enumerate(compound):
        if ch in "([":
            depth += 1
        elif ch in ")]":
            depth -= 1
        elif depth == 0:
            m = _PSEUDO_ELEMENT_RE.match(compound, i)
            if m:
                pos = i
                break
    return selector[:start] + compound[:pos] + attr + compound[pos:]
