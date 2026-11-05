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
from contextvars import ContextVar
from xml.parsers import expat
from dataclasses import dataclass, field
from typing import Any

from .events import parse_bind_modifiers, parse_event_spec
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
    # Where it is in the file (0 if unknown); not part of what it means.
    line: int = field(default=0, compare=False, repr=False, kw_only=True)
    attrs: dict[str, list[tuple[str, str]]] = field(default_factory=dict)
    # Event spec ("click", "keydown.enter") -> handler source; see events.py.
    events: dict[str, str] = field(default_factory=dict)
    bind: str | None = None
    bind_mods: tuple[str, ...] = ()
    key_expr: str | None = None
    children: list[Any] = field(default_factory=list)
    # ``:name="expr"`` bindings -- evaluated as Python, unlike ``attrs`` which
    # interpolate to strings. On components these become typed props.
    expr_attrs: dict[str, str] = field(default_factory=dict)
    # class:active="expr" (the class is added while expr is true) and
    # style:width="expr" (the property is set unless expr is None/False).
    class_toggles: dict[str, str] = field(default_factory=dict)
    style_props: dict[str, str] = field(default_factory=dict)


@dataclass
class TIf:
    """branches is [(cond_src, children), ...]; a None cond is the else."""

    branches: list[tuple[str | None, list[Any]]]
    line: int = field(default=0, compare=False, repr=False, kw_only=True)


@dataclass
class TFor:
    var: str
    iter_src: str
    index_var: str | None = None
    key_expr: str | None = None
    children: list[Any] = field(default_factory=list)
    line: int = field(default=0, compare=False, repr=False, kw_only=True)


@dataclass
class TSlot:
    """``<Slot name="footer" :item="row">fallback</Slot>`` in a component's
    template: where the content its parent passed is rendered. ``attrs`` and
    ``expr_attrs`` are slot props, handed to that content as variables."""

    name: str = "default"
    attrs: dict[str, list[tuple[str, str]]] = field(default_factory=dict)
    expr_attrs: dict[str, str] = field(default_factory=dict)
    children: list[Any] = field(default_factory=list)
    line: int = field(default=0, compare=False, repr=False, kw_only=True)


@dataclass
class TFill:
    """``<Fill name="footer">...</Fill>`` directly inside a component tag:
    content for one of its named slots."""

    name: str
    children: list[Any] = field(default_factory=list)
    line: int = field(default=0, compare=False, repr=False, kw_only=True)


@dataclass
class TAwait:
    """``<Await task="load(id)" key="id">`` pending content ``<Then
    as="user">`` ... ``<Catch as="error">`` ... ``</Await>``: what to show
    while an awaitable runs, once it returns, and if it raises. ``then`` /
    ``catch`` are None when the block is absent (not the same as empty)."""

    task: str
    key_expr: str | None = None
    pending: list[Any] = field(default_factory=list)
    then_var: str = "value"
    then: list[Any] | None = None
    catch_var: str = "error"
    catch: list[Any] | None = None
    line: int = field(default=0, compare=False, repr=False, kw_only=True)

    @property
    def blocks(self) -> list[list[Any]]:
        return [self.pending, self.then or [], self.catch or []]


def subtrees(node: Any) -> list[list[Any]]:
    """The child lists of any template node, for code that walks a template
    without caring what each control element means."""
    if isinstance(node, TIf):
        return [children for _, children in node.branches]
    if isinstance(node, TAwait):
        return node.blocks
    return [node.children] if isinstance(node, (TElement, TFor, TSlot, TFill)) else []


# ------------------------------------------------------------ source slicing

_BLOCK_OPEN = re.compile(r"<(template|code|style)\s*>")
_TEMPLATE_TAG = re.compile(r"<(/?)template\b[^>]*?(/?)>")
_AFTER_BLOCK = re.compile(r"\s*(?:$|<(?:template|code|style)\s*>|<!--)")


def _template_end(src: str, start: int) -> re.Match[str] | None:
    # Balanced, so a <template> element inside the markup can't end it.
    depth = 1
    for tag in _TEMPLATE_TAG.finditer(src, start):
        if tag.group(1):
            depth -= 1
            if depth == 0:
                return tag
        elif not tag.group(2):
            depth += 1
    return None


def _raw_end(src: str, start: int, name: str) -> re.Match[str] | None:
    # Python and CSS aren't markup, so nothing can be balanced: the block
    # ends at the first closing tag followed by another block or the end,
    # so "</code>" inside a string mostly stays in. Failing that, the last.
    closes = list(re.finditer(rf"</{name}\s*>", src[start:]))
    for close in closes:
        if _AFTER_BLOCK.match(src, start + close.end()):
            break
    else:
        if not closes:
            return None
        close = closes[-1]
    return re.compile(rf"</{name}\s*>").match(src, start + close.start())


def block_spans(src: str) -> dict[str, tuple[int, int]]:
    """Where the top-level ``<template>``, ``<code>`` and ``<style>`` blocks'
    contents are: ``{"code": (start, end), ...}``. Blocks are found by
    scanning, not by regex over the whole file, so markup inside the
    template (an HTML ``<code>`` element, say) is not taken for a block."""
    spans: dict[str, tuple[int, int]] = {}
    pos = 0
    while (opening := _BLOCK_OPEN.search(src, pos)) is not None:
        comment = src.find("<!--", pos, opening.start())
        if comment != -1:
            close = src.find("-->", comment + 4)
            pos = len(src) if close == -1 else close + 3
            continue
        name = opening.group(1)
        end = (
            _template_end(src, opening.end())
            if name == "template"
            else _raw_end(src, opening.end(), name)
        )
        if end is None:
            raise TemplateError(f"<{name}> block is not closed")
        spans.setdefault(name, (opening.end(), end.start()))
        pos = end.end()
    return spans


def split_source(src: str) -> tuple[str, str, str]:
    """Return (template_source, code_source, style_source)."""
    spans = block_spans(src)
    if "template" not in spans:
        raise TemplateError("no <template> block found")

    def content(name: str) -> str:
        start, end = spans.get(name, (0, 0))
        return src[start:end]

    return content("template"), textwrap.dedent(content("code")), textwrap.dedent(content("style"))


_AT_ATTR = re.compile(r"@([A-Za-z_][\w.\-]*)\s*=")
_COLON_ATTR = re.compile(r":([A-Za-z_][\w.\-]*)\s*=")
_TOGGLE_ATTR = re.compile(r"(class|style):([A-Za-z_\-][\w\-]*)\s*=")


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
            if src.startswith("<!--", i):
                # A comment is copied as it is: an apostrophe in it ("the
                # box's") must not open a quote, nor @click in it be rewritten.
                end = src.find("-->", i + 4)
                end = n if end < 0 else end + 3
                out.append(src[i:end])
                i = end
                continue
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
        # class:active= / style:width= at an attribute-name position: XML
        # would read "class" as a namespace prefix.
        if ch in "cs" and out and out[-1].isspace():
            match = _TOGGLE_ATTR.match(src, i)
            if match:
                out.append(f"py-{match.group(1)}-{match.group(2)}=")
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


_ROOT_TAG = "<pyweft-root>"
# Line numbers of the elements being converted, by id(): ElementTree keeps
# none, and its C elements take no extra attributes.
_LINES: ContextVar[dict[int, int]] = ContextVar("_LINES", default={})


def parse_template(template_src: str, first_line: int = 1) -> list[Any]:
    """The template tree. ``first_line`` is the file line the template text
    starts on, so nodes' ``line`` and error messages count file lines."""
    src = rewrite_at_directives(template_src)
    root, lines = _parse_xml(_ROOT_TAG + src + "</pyweft-root>", first_line - 1)
    token = _LINES.set(lines)
    try:
        return _convert_children(root)
    finally:
        _LINES.reset(token)


def _parse_xml(text: str, line_offset: int) -> tuple[ET.Element, dict[int, int]]:
    """ElementTree's tree, built from expat directly so each element's line
    is known. Names are handled as ElementTree does (namespaces as {uri}name;
    comments and processing instructions dropped)."""
    parser = expat.ParserCreate(namespace_separator="}")
    parser.buffer_text = True
    lines: dict[int, int] = {}
    stack: list[ET.Element] = []
    found: list[ET.Element] = []

    def name(raw: str) -> str:
        return "{" + raw if "}" in raw else raw

    def start(tag: str, attrs: dict[str, str]) -> None:
        el = ET.Element(name(tag), {name(k): v for k, v in attrs.items()})
        lines[id(el)] = parser.CurrentLineNumber + line_offset
        if stack:
            stack[-1].append(el)
        else:
            found.append(el)
        stack.append(el)

    def end(tag: str) -> None:
        stack.pop()

    def chars(data: str) -> None:
        current = stack[-1]
        if len(current):
            current[-1].tail = (current[-1].tail or "") + data
        else:
            current.text = (current.text or "") + data

    parser.StartElementHandler = start
    parser.EndElementHandler = end
    parser.CharacterDataHandler = chars
    try:
        parser.Parse(text, True)
    except expat.ExpatError as exc:
        column = exc.offset - (len(_ROOT_TAG) if exc.lineno == 1 else 0)
        raise TemplateError(
            f"template is not well-formed XML: {expat.ErrorString(exc.code)}: "
            f"line {exc.lineno + line_offset}, column {column + 1}"
        ) from None
    return found[0], lines


def _line(el: ET.Element) -> int:
    return _LINES.get().get(id(el), 0)


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
        if child.tag in ("Then", "Catch"):
            raise TemplateError(f"<{child.tag}> must be directly inside an <Await>")
        if child.tag == "Await":
            out.append(_convert_await(child))
            out += _text_nodes(child.tail)
            i += 1
            continue
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
        if child.tag in _GLOBAL_TAGS:
            out.append(_convert_global(child))
            out += _text_nodes(child.tail)
            i += 1
            continue
        if child.tag in ("Slot", "Fill"):
            out.append(_convert_slot(child) if child.tag == "Slot" else _convert_fill(child))
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
    return TIf(branches, line=_line(node)), j


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
        line=_line(el),
    )


def _convert_await(el: ET.Element) -> TAwait:
    task = el.get("task")
    if not task or not task.strip():
        raise TemplateError('<Await> requires task="...", the awaitable to wait for, e.g. task="load_orders()"')
    extra = sorted(set(el.attrib) - {"task", "key"})
    if extra:
        raise TemplateError(f"<Await> takes only task= and key=, not {', '.join(extra)}")
    node = TAwait(task=task, key_expr=el.get("key"), line=_line(el))
    # Everything but <Then>/<Catch> is the pending content, text included.
    holder = ET.Element("Await")
    holder.text = el.text
    for kid in el:
        if kid.tag in ("Then", "Catch"):
            if (node.then if kid.tag == "Then" else node.catch) is not None:
                raise TemplateError(f"<Await> has two <{kid.tag}> blocks")
            unknown = sorted(set(kid.attrib) - {"as"})
            if unknown:
                raise TemplateError(f"<{kid.tag}> takes only as=, not {', '.join(unknown)}")
            name = kid.get("as", "value" if kid.tag == "Then" else "error")
            if not name.isidentifier():
                raise TemplateError(f'<{kid.tag} as="{name}">: as= names a variable, so it must be a Python name')
            if kid.tag == "Then":
                node.then_var, node.then = name, _convert_children(kid)
            else:
                node.catch_var, node.catch = name, _convert_children(kid)
            tail = kid.tail or ""
            if len(holder):
                holder[-1].tail = (holder[-1].tail or "") + tail
            else:
                holder.text = (holder.text or "") + tail
        else:
            holder.append(kid)
    node.pending = _convert_children(holder)
    return node


_SLOT_NAME = re.compile(r"^[A-Za-z_][\w-]*$")


def _slot_name(el: ET.Element, required: bool) -> str:
    name = el.get("name")
    if name is None:
        if required:
            raise TemplateError('<Fill> requires name="...", the slot it fills')
        return "default"
    if not _SLOT_NAME.match(name):
        raise TemplateError(f"<{el.tag} name={name!r}>: not a valid slot name")
    return name


def _convert_slot(el: ET.Element) -> TSlot:
    attrs: dict[str, list[tuple[str, str]]] = {}
    expr_attrs: dict[str, str] = {}
    for name, value in el.attrib.items():
        if name == "name":
            continue
        if name.startswith("py-at-"):
            raise TemplateError(f"<Slot> takes no events (@{name[6:]})")
        if name.startswith("py-colon-"):
            name, target = name[len("py-colon-") :], expr_attrs
        else:
            target = attrs
        if not name.isidentifier():
            raise TemplateError(
                f"<Slot> prop {name!r} must be a Python name: the content that "
                "fills the slot sees it as a variable"
            )
        if target is expr_attrs:
            expr_attrs[name] = value
        else:
            attrs[name] = parse_interpolation(value)
    return TSlot(
        name=_slot_name(el, required=False),
        attrs=attrs,
        expr_attrs=expr_attrs,
        children=_convert_children(el),
        line=_line(el),
    )


def _convert_fill(el: ET.Element) -> TFill:
    extra = sorted(set(el.attrib) - {"name"})
    if extra:
        raise TemplateError(f"<Fill> takes only name=, not {', '.join(extra)}")
    return TFill(name=_slot_name(el, required=True), children=_convert_children(el), line=_line(el))


# transition= / in= / out= / animate= become data-pw-* attributes that the
# runtime reads when it inserts, removes or moves the element: they travel
# through renders and diffs like any attribute, so no patch op changes.
_MOTION = {
    "transition": ("data-pw-in", "data-pw-out"),
    "in": ("data-pw-in",),
    "out": ("data-pw-out",),
    "animate": ("data-pw-animate",),
}


def _motion(tag: str, table: dict) -> None:
    for name, targets in _MOTION.items():
        # SVG filter primitives (<feBlend in="SourceGraphic">) own "in".
        if name in table and not (name == "in" and tag.startswith("fe")):
            value = table.pop(name)
            for target in targets:
                table[target] = value


# <Window @keydown.ctrl.k="..."> / <Document @visibilitychange="...">: a
# hidden placeholder element whose listeners the runtime puts on window or
# document instead. It is an ordinary element to the renderer and differ, so
# its handlers come and go with the component that renders it.
_GLOBAL_TAGS = {"Window": "pyweft-window", "Document": "pyweft-document"}


def _convert_global(el: ET.Element) -> TElement:
    node = _convert_element(el)
    if node.children:
        raise TemplateError(f"<{el.tag}> takes no content: it only listens for events")
    other = [*node.attrs, *node.expr_attrs] + [f"class:{n}" for n in node.class_toggles] + \
        [f"style:{n}" for n in node.style_props] + (["@bind"] if node.bind else []) + (["key"] if node.key_expr else [])
    if other:
        raise TemplateError(
            f"<{el.tag}> takes only event handlers (@keydown=..., @scroll=...), not {', '.join(other)}"
        )
    if not node.events:
        raise TemplateError(f"<{el.tag}> needs an event handler, such as @keydown.esc=\"close\"")
    node.tag = _GLOBAL_TAGS[el.tag]
    node.attrs = {"hidden": parse_interpolation("")}
    return node


def _convert_element(el: ET.Element) -> TElement:
    attrs: dict[str, list[tuple[str, str]]] = {}
    events: dict[str, str] = {}
    expr_attrs: dict[str, str] = {}
    bind: str | None = None
    bind_mods: tuple[str, ...] = ()
    key_expr: str | None = None
    class_toggles: dict[str, str] = {}
    style_props: dict[str, str] = {}

    for name, value in el.attrib.items():
        if name == "key":
            key_expr = value
        elif name.startswith("py-class-"):
            class_toggles[name[len("py-class-") :]] = value
        elif name.startswith("py-style-"):
            style_props[name[len("py-style-") :]] = value
        elif name.startswith("py-colon-"):
            expr_attrs[name[len("py-colon-") :]] = value
        elif name.startswith("py-at-"):
            directive = name[len("py-at-") :]
            try:
                if directive == "bind" or directive.startswith("bind."):
                    if not value.isidentifier():
                        raise TemplateError(
                            f"@bind takes a plain state name, got {value!r}"
                        )
                    bind = value
                    bind_mods = parse_bind_modifiers(directive)
                else:
                    events[parse_event_spec(directive)] = value
            except ValueError as exc:
                raise TemplateError(f"<{el.tag}> {exc}") from None
        else:
            attrs[name] = parse_interpolation(value)

    _motion(el.tag, attrs)
    _motion(el.tag, expr_attrs)

    if el.tag == "Dynamic" and "is" not in expr_attrs:
        raise TemplateError(
            '<Dynamic> needs :is="..." naming the component class to render'
        )

    return TElement(
        tag=el.tag,
        attrs=attrs,
        events=events,
        bind=bind,
        bind_mods=bind_mods,
        key_expr=key_expr,
        children=_convert_children(el),
        expr_attrs=expr_attrs,
        class_toggles=class_toggles,
        style_props=style_props,
        line=_line(el),
    )
