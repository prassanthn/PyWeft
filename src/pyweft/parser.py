"""Parse a ``.weft`` file into a template tree plus a code block.

File shape::

    <template>
      <button @click="increment">{{ count }}</button>
    </template>

    <code>
    count: int = 0

    def increment(self):
        self.count += 1
    </code>

The ``<code>`` and ``<style>`` blocks are cut out by string scanning *before*
any XML parsing, because Python source is full of ``<``, ``>`` and ``&`` (and
CSS of ``>``) and would blow up an XML parser. Only the ``<template>`` block
is parsed as XML.

The template must be well-formed XML (close your tags, quote your attributes).
That buys us the stdlib ``xml.etree`` parser instead of a bespoke HTML5
tokenizer, which is a large amount of complexity to skip for a PoC.
"""

from __future__ import annotations

import re
import textwrap
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from typing import Any

from .expressions import parse_interpolation


class TemplateError(RuntimeError):
    pass


# ---------------------------------------------------------------- node types


@dataclass
class TStatic:
    """Literal text, possibly with {{ }} holes."""

    parts: list[tuple[str, str]]


@dataclass
class TElement:
    tag: str
    attrs: dict[str, list[tuple[str, str]]] = field(default_factory=dict)
    events: dict[str, str] = field(default_factory=dict)
    bind: str | None = None
    key_expr: str | None = None
    children: list[Any] = field(default_factory=list)
    # ``:name="expr"`` bindings -- evaluated as Python, unlike ``attrs`` which
    # interpolate to strings. On components these become typed props.
    expr_attrs: dict[str, str] = field(default_factory=dict)


@dataclass
class TIf:
    """branches is [(cond_src, children), ...]; a None cond is the else."""

    branches: list[tuple[str | None, list[Any]]]


@dataclass
class TFor:
    var: str
    iter_src: str
    index_var: str | None = None
    key_expr: str | None = None
    children: list[Any] = field(default_factory=list)


# ------------------------------------------------------------ source slicing

_TEMPLATE_RE = re.compile(r"<template\s*>(.*)</template\s*>", re.S)
_CODE_RE = re.compile(r"<code\s*>(.*)</code\s*>", re.S)
_STYLE_RE = re.compile(r"<style\s*>(.*)</style\s*>", re.S)


def split_source(src: str) -> tuple[str, str, str]:
    """Return (template_source, code_source, style_source)."""
    code = ""
    match = _CODE_RE.search(src)
    if match:
        code = match.group(1)
        src = src[: match.start()] + src[match.end() :]
    style = ""
    match = _STYLE_RE.search(src)
    if match:
        style = match.group(1)
        src = src[: match.start()] + src[match.end() :]
    tmpl = _TEMPLATE_RE.search(src)
    if not tmpl:
        raise TemplateError("no <template> block found")
    return tmpl.group(1), textwrap.dedent(code), textwrap.dedent(style)


_AT_ATTR = re.compile(r"@([A-Za-z_][\w.\-]*)\s*=")
_COLON_ATTR = re.compile(r":([A-Za-z_][\w.\-]*)\s*=")


def rewrite_at_directives(src: str) -> str:
    """Rewrite ``@click="..."`` to ``py-at-click="..."`` and ``:prop="..."``
    to ``py-colon-prop="..."``.

    XML attribute names cannot start with ``@`` or ``:``, so the Blazor-ish /
    Vue-ish sugar has to be normalised before the XML parser sees it. This is a
    small state machine rather than a bare regex so that ``@`` or ``:`` inside
    text or attribute values (an email address, a URL) is left alone.
    """
    out: list[str] = []
    i, n = 0, len(src)
    in_tag = False
    quote: str | None = None
    while i < n:
        ch = src[i]
        if not in_tag:
            if ch == "<":
                in_tag = True
            out.append(ch)
            i += 1
            continue
        if quote:
            if ch == quote:
                quote = None
            out.append(ch)
            i += 1
            continue
        if ch in "\"'":
            quote = ch
            out.append(ch)
            i += 1
            continue
        if ch == ">":
            in_tag = False
            out.append(ch)
            i += 1
            continue
        if ch == "@" and out and (out[-1].isspace() or out[-1] == "<"):
            match = _AT_ATTR.match(src, i)
            if match:
                out.append("py-at-" + match.group(1) + "=")
                i = match.end()
                continue
        # Only after whitespace: an attribute-name position. A ':' elsewhere in
        # a tag (a namespaced attribute name, say) is not our sugar.
        if ch == ":" and out and out[-1].isspace():
            match = _COLON_ATTR.match(src, i)
            if match:
                out.append("py-colon-" + match.group(1) + "=")
                i = match.end()
                continue
        out.append(ch)
        i += 1
    return "".join(out)


# --------------------------------------------------------------- conversion


def parse_template(template_src: str) -> list[Any]:
    src = rewrite_at_directives(template_src)
    try:
        root = ET.fromstring("<pyweft-root>" + src + "</pyweft-root>")
    except ET.ParseError as exc:
        raise TemplateError(f"template is not well-formed XML: {exc}") from exc
    return _convert_children(root)


def _text_nodes(text: str | None) -> list[Any]:
    """Whitespace-only text containing a newline is formatting; drop it."""
    if not text:
        return []
    if not text.strip():
        return [] if "\n" in text else [TStatic([("static", text)])]
    return [TStatic(parse_interpolation(text))]


_EACH_RE = re.compile(r"^\s*([A-Za-z_]\w*)\s+in\s+(.+)$", re.S)


def _convert_children(el: ET.Element) -> list[Any]:
    out: list[Any] = []
    out += _text_nodes(el.text)
    kids = [k for k in el if not callable(k.tag)]  # drop comments / PIs
    i = 0
    while i < len(kids):
        child = kids[i]
        if child.tag in ("ElseIf", "Else"):
            raise TemplateError(f"<{child.tag}> must directly follow an <If>")
        if child.tag == "If":
            node, i = _convert_if(kids, i)
            out.append(node)
            out += _text_nodes(kids[i - 1].tail)
            continue
        if child.tag == "For":
            out.append(_convert_for(child))
            out += _text_nodes(child.tail)
            i += 1
            continue
        out.append(_convert_element(child))
        out += _text_nodes(child.tail)
        i += 1
    return out


def _convert_if(kids: list[ET.Element], i: int) -> tuple[TIf, int]:
    node = kids[i]
    cond = node.get("cond")
    if cond is None:
        raise TemplateError('<If> requires a cond attribute, e.g. cond="count > 5"')
    branches: list[tuple[str | None, list[Any]]] = [(cond, _convert_children(node))]
    j = i + 1
    while j < len(kids) and kids[j].tag in ("ElseIf", "Else"):
        if (kids[j - 1].tail or "").strip():
            break  # real content between the branches; stop folding
        nxt = kids[j]
        if nxt.tag == "ElseIf":
            cond2 = nxt.get("cond")
            if cond2 is None:
                raise TemplateError("<ElseIf> requires a cond attribute")
            branches.append((cond2, _convert_children(nxt)))
            j += 1
        else:
            branches.append((None, _convert_children(nxt)))
            j += 1
            break
    return TIf(branches), j


def _convert_for(el: ET.Element) -> TFor:
    each = el.get("each")
    if not each:
        raise TemplateError('<For> requires each="item in items"')
    match = _EACH_RE.match(each)
    if not match:
        raise TemplateError(f'bad each expression {each!r}, expected "item in items"')
    return TFor(
        var=match.group(1),
        iter_src=match.group(2).strip(),
        index_var=el.get("index"),
        key_expr=el.get("key"),
        children=_convert_children(el),
    )


def _convert_element(el: ET.Element) -> TElement:
    attrs: dict[str, list[tuple[str, str]]] = {}
    events: dict[str, str] = {}
    expr_attrs: dict[str, str] = {}
    bind: str | None = None
    key_expr: str | None = None

    for name, value in el.attrib.items():
        if name == "key":
            key_expr = value
        elif name.startswith("py-colon-"):
            expr_attrs[name[len("py-colon-") :]] = value
        elif name.startswith("py-at-"):
            directive = name[len("py-at-") :]
            if directive == "bind":
                if not value.isidentifier():
                    raise TemplateError(
                        f"@bind takes a plain state name, got {value!r}"
                    )
                bind = value
            else:
                events[directive] = value
        else:
            attrs[name] = parse_interpolation(value)

    return TElement(
        tag=el.tag,
        attrs=attrs,
        events=events,
        bind=bind,
        key_expr=key_expr,
        children=_convert_children(el),
        expr_attrs=expr_attrs,
    )
