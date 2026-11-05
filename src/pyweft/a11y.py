"""Accessibility checks for ``pyweft check``: mistakes that lock out
keyboard and screen-reader users, found by reading templates. Host-only.

Each finding is a warning with an ``a11y-`` code. They are deliberately
the cheap, sure ones (a missing alt, a click with no keyboard way to do the
same, a field with no label); what the template can't tell (a bound id, a
component's own markup) is given the benefit of the doubt.
"""

from __future__ import annotations

import difflib
import re
from collections.abc import Callable, Iterable
from typing import Any

from .parser import TElement, THtml, TSlot, TStatic, subtrees

# WAI-ARIA 1.2, plus the graphics roles.
ROLES = frozenset("""
alert alertdialog application article banner blockquote button caption cell checkbox code columnheader
combobox complementary contentinfo definition deletion dialog directory document emphasis feed figure form
generic grid gridcell group heading img insertion link list listbox listitem log main marquee math menu
menubar menuitem menuitemcheckbox menuitemradio meter navigation none note option paragraph presentation
progressbar radio radiogroup region row rowgroup rowheader scrollbar search searchbox separator slider
spinbutton status strong subscript superscript switch tab table tablist tabpanel term textbox time timer
toolbar tooltip tree treegrid treeitem graphics-document graphics-object graphics-symbol
""".split())

ARIA = frozenset("aria-" + name for name in """
activedescendant atomic autocomplete braillelabel brailleroledescription busy checked colcount colindex
colindextext colspan controls current describedby description details disabled dropeffect errormessage
expanded flowto grabbed haspopup hidden invalid keyshortcuts label labelledby level live modal multiline
multiselectable orientation owns placeholder posinset pressed readonly relevant required roledescription
rowcount rowindex rowindextext rowspan selected setsize sort valuemax valuemin valuenow valuetext
""".split())

# Elements a keyboard can already reach and use.
INTERACTIVE = frozenset({"a", "button", "input", "select", "textarea", "summary", "details", "option",
                         "label", "audio", "video", "iframe"})
# Roles that promise the element can be used (and so must be reachable).
WIDGET_ROLES = frozenset({"button", "link", "checkbox", "radio", "switch", "tab", "menuitem",
                          "menuitemcheckbox", "menuitemradio", "option", "slider", "spinbutton", "textbox",
                          "combobox", "searchbox", "treeitem", "gridcell", "scrollbar"})
# Children whose container keeps focus and points at them (aria-activedescendant).
MANAGED_ROLES = frozenset({"option", "treeitem", "gridcell"})
UNLABELLED_INPUTS = frozenset({"hidden", "submit", "button", "reset", "image"})
NAMES = ("aria-label", "aria-labelledby", "title")

Add = Callable[[int, str, str, str], None]


def audit(nodes: list[Any], add: Add, is_component: Callable[[str], bool]) -> None:
    """Report problems in a template's nodes through ``add(line, severity,
    code, message)``. Component tags aren't checked (their markup is in
    their own file), but content passed into them is."""
    targets, dynamic = _label_targets(nodes)
    _Audit(add, is_component, targets, dynamic).walk(nodes, False, 0)


class _Audit:
    def __init__(self, add: Add, is_component: Callable[[str], bool], targets: set, dynamic: bool):
        self.add = add
        self.is_component = is_component
        self.targets = targets          # static <label for="..."> ids
        self.dynamic_targets = dynamic  # some label's for= is bound: ids can't be matched

    def walk(self, nodes: list[Any], in_label: bool, line: int) -> None:
        for node in nodes:
            if isinstance(node, TElement):
                at = node.line or line
                if not self.is_component(node.tag) and not node.tag.startswith("pyweft-"):
                    self.element(node, in_label, at)
                self.walk(node.children, in_label or node.tag == "label", at)
            else:
                for children in subtrees(node):
                    self.walk(children, in_label, getattr(node, "line", 0) or line)

    def warn(self, line: int, code: str, message: str) -> None:
        self.add(line, "warning", f"a11y-{code}", message)

    def element(self, node: TElement, in_label: bool, line: int) -> None:
        tag = node.tag.lower()
        role = _static(node, "role")
        roles = set(role.split()) if role else set()
        for r in sorted(roles - ROLES):
            self.warn(line, "unknown-role", f'<{tag} role="{r}">: not an ARIA role' + _maybe(r, ROLES))
        for name in [*node.attrs, *node.expr_attrs]:
            if name.startswith("aria-") and name not in ARIA:
                self.warn(line, "unknown-aria", f"<{tag}> {name}: not an ARIA attribute" + _maybe(name, ARIA))
        tabindex = _static(node, "tabindex")
        if tabindex and tabindex.strip().isdigit() and int(tabindex) > 0:
            self.warn(line, "positive-tabindex",
                      f'<{tag} tabindex="{tabindex}">: a positive tabindex moves it ahead of the reading order '
                      'in the Tab sequence: use 0 (or -1 to leave it out)')
        if tag == "img" and not _has(node, "alt"):
            self.warn(line, "missing-alt",
                      '<img> has no alt: describe the picture for screen readers, or write alt="" if it is '
                      "only decoration")
        self.clicks(node, tag, roles, line)
        if tag in ("input", "select", "textarea"):
            self.label(node, tag, in_label, line)
        if tag == "button" and not any(_has(node, n) for n in NAMES) and not _has_text(node.children, self.is_component):
            self.warn(line, "empty-button",
                      "<button> has no text, so screen readers announce just \"button\": add text, or "
                      'aria-label="..." for an icon button')

    def clicks(self, node: TElement, tag: str, roles: set, line: int) -> None:
        clicks = [s for s, handler in node.events.items() if s.split(".")[0] in ("click", "dblclick") and handler.strip()]
        if not clicks or _static(node, "aria-hidden") == "true" or roles & {"presentation", "none"}:
            return
        keys = any(s.split(".")[0] in ("keydown", "keyup", "keypress") for s in node.events)
        if tag == "a" and not _has(node, "href"):
            self.warn(line, "anchor-no-href",
                      '<a @click> without href is not a link to the keyboard or a screen reader: use '
                      '<button type="button">, or give it an href')
        elif tag not in INTERACTIVE and not roles & WIDGET_ROLES:
            if not keys:
                self.warn(line, "click-without-keyboard",
                          f"<{tag} @click>: keyboard users can't do this. Use a <button>, or give it "
                          'role="button", tabindex="0" and @keydown.enter / @keydown.space handlers')
            elif not _has(node, "tabindex"):
                self.warn(line, "not-focusable",
                          f'<{tag} @click>: it handles keys but Tab never reaches it: add tabindex="0" and a role')
        elif tag not in INTERACTIVE and not _has(node, "tabindex") and not roles & MANAGED_ROLES:
            self.warn(line, "not-focusable",
                      f'<{tag} role="{" ".join(sorted(roles & WIDGET_ROLES))}">: Tab never reaches it: add tabindex="0"')

    def label(self, node: TElement, tag: str, in_label: bool, line: int) -> None:
        kind = (_static(node, "type") or "text").strip().lower()
        if tag == "input" and kind in UNLABELLED_INPUTS or in_label or any(_has(node, n) for n in NAMES):
            return
        if _has(node, "id"):
            ident = _static(node, "id")
            if ident is None or ident in self.targets or self.dynamic_targets:
                return  # a bound id, or a label points at it
        self.warn(line, "missing-label",
                  f"<{tag}> has no label, so screen readers can't say what it is for: wrap it in a "
                  '<label>, point a <label for="..."> at its id, or add aria-label (a placeholder is not '
                  "a label)")


_IGNORE = re.compile(r"<!--\s*pyweft-ignore\b:?([^>]*?)-->")


def ignored(lines: list[str], line: int, code: str) -> bool:
    """Whether ``<!-- pyweft-ignore: code -->`` on the element's line, or
    the line above it, silences ``code`` there (no codes: everything)."""
    for at in (line - 1, line - 2):  # 1-based line -> its index, then the one above
        if 0 <= at < len(lines):
            for match in _IGNORE.finditer(lines[at]):
                codes = {c.strip() for c in match.group(1).replace(",", " ").split()}
                if not codes or code in codes:
                    return True
    return False


def _has(node: TElement, name: str) -> bool:
    return name in node.attrs or name in node.expr_attrs


def _static(node: TElement, name: str) -> str | None:
    """The attribute's text when it is written out in full, else None."""
    parts = node.attrs.get(name)
    if parts is None or any(kind != "static" for kind, _ in parts):
        return None
    return "".join(text for _, text in parts)


def _has_text(nodes: Iterable[Any], is_component: Callable[[str], bool]) -> bool:
    for node in nodes:
        if isinstance(node, TStatic):
            if any(kind == "expr" or text.strip() for kind, text in node.parts):
                return True
        elif isinstance(node, TElement):
            if is_component(node.tag) or (node.tag == "img" and (_static(node, "alt") or "alt" in node.expr_attrs)):
                return True  # a component may well render text; can't tell from here
            if any(_has(node, n) for n in ("aria-label", "aria-labelledby")) or _has_text(node.children, is_component):
                return True
        elif isinstance(node, (TSlot, THtml)):
            return True
        elif any(_has_text(children, is_component) for children in subtrees(node)):
            return True
    return False


def _label_targets(nodes: list[Any]) -> tuple[set, bool]:
    targets, dynamic = set(), False

    def walk(items):
        nonlocal dynamic
        for node in items:
            if isinstance(node, TElement):
                if node.tag == "label":
                    value = _static(node, "for")
                    if value is not None:
                        targets.add(value)
                    elif _has(node, "for"):
                        dynamic = True
            for children in subtrees(node):
                walk(children)

    walk(nodes)
    return targets, dynamic


def _maybe(name: str, known: Iterable[str]) -> str:
    close = difflib.get_close_matches(name, list(known), n=1, cutoff=0.75)
    return f" (did you mean {close[0]!r}?)" if close else ""
