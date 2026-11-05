"""``<Html :content="...">``: an HTML string turned into vdom nodes.

The markup is parsed here, in Python, into the same Element/Text nodes a
template produces, so the differ, the patch ops, the runtime, pre-rendering
and every host handle it unchanged: the core still never hands a host a
string of HTML to inject.

By default it is sanitized against an allowlist, because the string usually
comes from somewhere else (Markdown a user wrote, a CMS, an API): tags and
attributes that can run script or load active content are dropped, as are
links to ``javascript:`` and other non-web URLs. ``trusted=True`` keeps
everything except ``<script>`` (which ``innerHTML`` would not run either).
"""

from __future__ import annotations

import functools
import re
from html.parser import HTMLParser
from typing import Any, Union

from .vdom import Element, Node, Text

# Frozen parse result, cached per string: ("text", str) or
# ("element", tag, ((name, value), ...), children).
Frozen = Union[tuple[str, str], tuple[str, str, tuple[tuple[str, str], ...], tuple[Any, ...]]]

VOID = frozenset(
    "area base br col embed hr img input link meta param source track wbr".split()
)

# Kept when sanitizing; any other tag is unwrapped (its content stays).
ALLOWED_TAGS = frozenset(
    """a abbr address article aside audio b bdi bdo blockquote br caption cite
    code col colgroup data dd del details dfn div dl dt em figcaption figure
    footer h1 h2 h3 h4 h5 h6 header hgroup hr i img ins kbd li main mark nav ol
    p picture pre q rp rt ruby s samp section small source span strong sub
    summary sup table tbody td tfoot th thead time tr track u ul var video
    wbr""".split()
)

# Dropped together with their content when sanitizing.
DROPPED_WITH_CONTENT = frozenset(
    """script style template iframe frame frameset object embed applet
    noscript noembed noframes title textarea select option svg math head
    meta link base xmp plaintext""".split()
)

GLOBAL_ATTRS = frozenset("class id title lang dir role style".split())
TAG_ATTRS = {
    "a": {"href", "name", "target", "rel", "hreflang", "download"},
    "img": {"src", "alt", "width", "height", "srcset", "sizes", "loading", "decoding"},
    "td": {"colspan", "rowspan", "align", "headers"},
    "th": {"colspan", "rowspan", "align", "headers", "scope", "abbr"},
    "col": {"span", "width"},
    "colgroup": {"span", "width"},
    "ol": {"start", "reversed", "type"},
    "ul": {"type"},
    "li": {"value"},
    "time": {"datetime"},
    "data": {"value"},
    "del": {"cite", "datetime"},
    "ins": {"cite", "datetime"},
    "q": {"cite"},
    "blockquote": {"cite"},
    "details": {"open"},
    "video": {"src", "controls", "poster", "width", "height", "loop", "muted", "preload", "playsinline"},
    "audio": {"src", "controls", "loop", "muted", "preload"},
    "source": {"src", "srcset", "type", "media", "sizes"},
    "track": {"src", "kind", "srclang", "label", "default"},
    "p": {"align"},
    "div": {"align"},
}
URL_ATTRS = frozenset("href src cite poster".split())
SAFE_SCHEMES = frozenset("http https mailto tel".split())

# HTMLParser lowercases names; SVG (allowed when trusted) is case-sensitive.
_SVG_NAMES = {
    name.lower(): name
    for name in """viewBox preserveAspectRatio gradientUnits gradientTransform
    patternUnits patternContentUnits patternTransform clipPathUnits maskUnits
    maskContentUnits markerWidth markerHeight markerUnits refX refY
    stdDeviation textLength lengthAdjust startOffset pathLength
    linearGradient radialGradient clipPath foreignObject textPath
    feGaussianBlur feOffset feBlend feColorMatrix feComposite feFlood
    feMerge feMergeNode feMorphology feTurbulence feDropShadow
    animateTransform animateMotion""".split()
}

# Opening the key tag closes an open element named in the set (but not
# across one of the boundary tags), as an HTML parser would.
_IMPLIED_CLOSE = {
    "li": ({"li"}, {"ul", "ol", "menu"}),
    "dt": ({"dt", "dd"}, {"dl"}),
    "dd": ({"dt", "dd"}, {"dl"}),
    "tr": ({"tr"}, {"table", "thead", "tbody", "tfoot"}),
    "td": ({"td", "th"}, {"tr", "table"}),
    "th": ({"td", "th"}, {"tr", "table"}),
    "thead": ({"thead", "tbody", "tfoot"}, {"table"}),
    "tbody": ({"thead", "tbody", "tfoot"}, {"table"}),
    "tfoot": ({"thead", "tbody", "tfoot"}, {"table"}),
    "option": ({"option"}, {"select", "datalist"}),
}
_CLOSES_P = frozenset(
    """address article aside blockquote details div dl fieldset figcaption
    figure footer form h1 h2 h3 h4 h5 h6 header hgroup hr main nav ol p pre
    section table ul""".split()
)
_P_BOUNDARY = frozenset("table td th caption button object template".split())

# A style attribute is kept (Markdown table alignment uses it) unless it
# loads something or lifts content out of its place (a fixed overlay over
# the app's own buttons).
_UNSAFE_STYLE = ("url(", "expression(", "javascript:", "position:", "behavior:", "-moz-binding", "@import")

_CONTROL_CHARS = re.compile(r"[\x00-\x20\x7f]+")
_SCHEME = re.compile(r"^([a-z][a-z0-9+.\-]*):")


def safe_url(value: str, attr: str = "href", tag: str = "a") -> bool:
    """A relative URL or one with a web/mail/phone scheme; for an image,
    a ``data:image/`` URL too."""
    compact = _CONTROL_CHARS.sub("", value).lower()
    match = _SCHEME.match(compact)
    if match is None:
        return True
    scheme = match.group(1)
    if scheme in SAFE_SCHEMES:
        return True
    return scheme == "data" and tag in ("img", "source") and attr in ("src", "srcset") \
        and compact.startswith("data:image/")


def _safe_srcset(value: str, tag: str) -> bool:
    return all(
        safe_url(candidate.strip().split(" ")[0], "srcset", tag)
        for candidate in value.split(",")
        if candidate.strip()
    )


def _allowed_attr(tag: str, name: str, value: str) -> bool:
    if name not in GLOBAL_ATTRS and name not in TAG_ATTRS.get(tag, ()) and not name.startswith("aria-"):
        return False
    if name in URL_ATTRS:
        return safe_url(value, name, tag)
    if name == "srcset":
        return _safe_srcset(value, tag)
    if name == "style":
        compact = _CONTROL_CHARS.sub("", value).lower()
        # CSS escapes (\75rl) could spell any of them: none of that either.
        return "\\" not in compact and not any(bad in compact for bad in _UNSAFE_STYLE)
    return True


class _Builder(HTMLParser):
    def __init__(self, trusted: bool):
        super().__init__(convert_charrefs=True)
        self.trusted = trusted
        self.root: list[list] = []
        # Open elements as [tag, attrs, children]; index 0 is a stand-in root.
        self.stack: list[list] = [["", (), self.root]]
        self.skipping: list[str] = []  # open tags inside a dropped element

    # The tags a sanitized tree may hold, and those whose content goes too.
    def _drops(self, tag: str) -> bool:
        return tag == "script" or (not self.trusted and tag in DROPPED_WITH_CONTENT)

    def _keeps(self, tag: str) -> bool:
        return self.trusted or tag in ALLOWED_TAGS

    def _close_until(self, index: int) -> None:
        del self.stack[index:]

    def _implied_closes(self, tag: str) -> None:
        if tag in _IMPLIED_CLOSE:
            closes, boundary = _IMPLIED_CLOSE[tag]
            self._close_nearest(closes, boundary)
        if tag in _CLOSES_P:
            self._close_nearest({"p"}, _P_BOUNDARY)

    def _close_nearest(self, closes: set, boundary: set | frozenset) -> None:
        for index in range(len(self.stack) - 1, 0, -1):
            open_tag = self.stack[index][0]
            if open_tag in closes:
                self._close_until(index)
                return
            if open_tag in boundary:
                return

    def _attrs(self, tag: str, attrs: list[tuple[str, str | None]]) -> tuple[tuple[str, str], ...]:
        out: dict[str, str] = {}
        for name, value in attrs:
            value = "" if value is None else value
            if self.trusted:
                if name.startswith("on"):
                    continue  # inline handlers: script by another name
                out[_SVG_NAMES.get(name, name)] = value
            elif _allowed_attr(tag, name, value):
                out[name] = value
        return tuple(out.items())

    def _open(self, tag: str, attrs: list, empty: bool) -> None:
        if self.skipping:
            if tag not in VOID and not empty:
                self.skipping.append(tag)
            return
        if self._drops(tag):
            if tag not in VOID and not empty:
                self.skipping.append(tag)
            return
        self._implied_closes(tag)
        if not self._keeps(tag):
            return  # unwrapped: its content lands in the parent
        name = _SVG_NAMES.get(tag, tag) if self.trusted else tag
        node = [name, self._attrs(tag, attrs), []]
        self.stack[-1][2].append(node)
        if tag not in VOID and not empty:
            self.stack.append(node)

    def handle_starttag(self, tag: str, attrs: list) -> None:
        self._open(tag, attrs, empty=False)

    def handle_startendtag(self, tag: str, attrs: list) -> None:
        self._open(tag, attrs, empty=True)

    def handle_endtag(self, tag: str) -> None:
        if self.skipping:
            if tag in self.skipping:
                del self.skipping[len(self.skipping) - 1 - self.skipping[::-1].index(tag):]
            return
        name = _SVG_NAMES.get(tag, tag) if self.trusted else tag
        for index in range(len(self.stack) - 1, 0, -1):
            if self.stack[index][0] == name:
                self._close_until(index)
                return
        # An end tag with nothing open to close (or an unwrapped tag's): ignored.

    def handle_data(self, data: str) -> None:
        if not self.skipping and data:
            self.stack[-1][2].append(data)


def _freeze(nodes: list) -> tuple[Frozen, ...]:
    out: list[Frozen] = []
    for node in nodes:
        if isinstance(node, str):
            if out and out[-1][0] == "text":
                out[-1] = ("text", out[-1][1] + node)  # type: ignore[index]
            else:
                out.append(("text", node))
        else:
            tag, attrs, children = node
            out.append(("element", tag, attrs, _freeze(children)))
    return tuple(out)


@functools.lru_cache(maxsize=128)
def parse_html(markup: str, trusted: bool = False) -> tuple[Frozen, ...]:
    """The markup as a frozen tree, sanitized unless ``trusted``. Cached:
    a page re-renders the same string on every render."""
    builder = _Builder(trusted)
    builder.feed(markup)
    builder.close()
    return _freeze(builder.root)


def to_nodes(frozen: tuple[Frozen, ...], extra_attrs: dict[str, str] | None = None) -> list[Node]:
    """Fresh vdom nodes (a render owns its tree), with ``extra_attrs`` (the
    component's scoped-style marker) on every element."""
    out: list[Node] = []
    for item in frozen:
        if item[0] == "text":
            out.append(Text(item[1]))
        else:
            _, tag, attrs, children = item  # type: ignore[misc]
            merged = dict(attrs)
            if extra_attrs:
                merged.update(extra_attrs)
            out.append(Element(tag=tag, attrs=merged, children=to_nodes(children, extra_attrs)))
    return out


def html_nodes(markup: Any, trusted: bool = False, extra_attrs: dict[str, str] | None = None) -> list[Node]:
    """What ``<Html :content=...>`` renders: nothing for None, else the
    markup (an object with ``__html__``, as markupsafe's Markup, or str())."""
    if markup is None:
        return []
    text = markup.__html__() if hasattr(markup, "__html__") else str(markup)
    return to_nodes(parse_html(text, trusted), extra_attrs)


__all__ = ["html_nodes", "parse_html", "to_nodes", "safe_url"]
