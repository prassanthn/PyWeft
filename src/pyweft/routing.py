"""Pages and navigation: a folder of ``.weft`` files becomes the app's screens.

In ``app.weft``::

    <nav><Link to="/">Home</Link> <Link to="/orders">Orders</Link></nav>
    <Pages />

    <code>
    from pyweft import Link, router
    Pages = router("pages")
    </code>

``pages/index.weft`` shows at ``/``, ``pages/orders.weft`` at ``/orders``,
``pages/settings/profile.weft`` at ``/settings/profile`` (``_`` in a name
becomes ``-`` in the URL). ``route = "/orders/{id}"`` in a page's code block
sets its URL instead; ``id`` then arrives as a prop, converted to the type the
page declares. Query parameters (``?status=paid``) fill declared props too.

The location is the part of the URL after ``#`` (``app/#/orders``), so a
built app works on any static host. It is held here, once per process (one
page per Python), and kept in step with the address bar by the host: the host
calls :func:`location_changed` when the user navigates (links, the back
button), and :func:`navigate` tells the host to update the address bar.
Without a host (tests, scripts) the history lives in memory.
"""

from __future__ import annotations

import weakref
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import parse_qsl, unquote, urlencode

from .binding import prop_value
from .component import _LOAD, component_from_source, declared_props, load_component
from .parser import TemplateError


class MemoryHistory:
    """The history without a browser: what tests and scripts navigate."""

    def __init__(self, start: str = "/"):
        self.entries = [start]
        self.index = 0

    def current(self) -> str:
        return self.entries[self.index]

    def push(self, url: str) -> None:
        del self.entries[self.index + 1 :]
        self.entries.append(url)
        self.index += 1

    def replace(self, url: str) -> None:
        self.entries[self.index] = url

    def back(self) -> None:
        # A browser reports the move asynchronously; this reports it at once.
        if self.index > 0:
            self.index -= 1
            location_changed(self.entries[self.index])


_host: Any = MemoryHistory()
_url: str | None = None  # normalised; read from the host on first use
# Live <Pages> and <Link>s, re-rendered when the location changes.
_watchers: weakref.WeakSet = weakref.WeakSet()


def set_host(host: Any) -> None:
    """Hosts call this before the first render with an object that has
    ``current()``, ``push(url)``, ``replace(url)`` and ``back()``."""
    global _host, _url
    _host, _url = host, None


def _normalise(url: str) -> str:
    path, _, query = url.partition("?")
    path = "/" + "/".join(part for part in unquote(path).split("/") if part)
    if query:
        query = urlencode(parse_qsl(query, keep_blank_values=True))
    return f"{path}?{query}" if query else path


def _current() -> str:
    global _url
    if _url is None:
        _url = _normalise(_host.current())
    return _url


def _notify() -> None:
    for watcher in list(_watchers):
        watcher.state_has_changed()


@dataclass(frozen=True)
class Location:
    path: str
    query: dict[str, str]


def location() -> Location:
    """Where the app is: ``location().path`` is ``"/orders/7"``,
    ``location().query`` is ``{"status": "paid"}`` for ``?status=paid``."""
    path, _, query = _current().partition("?")
    return Location(path, dict(parse_qsl(query, keep_blank_values=True)))


def location_changed(url: str) -> None:
    """For hosts: the user went to ``url`` (a link, the back button, a
    typed address). Pages re-render if it is somewhere new."""
    global _url
    url = _normalise(url)
    if url != _current():
        _url = url
        _notify()


def navigate(to: str, *, replace: bool = False, query: dict[str, Any] | None = None) -> None:
    """Go to ``to``, such as ``"/orders/7"``. ``query`` adds parameters
    (``query={"status": "paid"}``); ``replace=True`` replaces the current
    history entry instead of adding one, so Back skips it (for redirects)."""
    global _url
    if not to.startswith("/"):
        raise ValueError(f"navigate() takes a path starting with /, got {to!r}")
    if query:
        to += ("&" if "?" in to else "?") + urlencode(query)
    url = _normalise(to)
    if url == _current():
        return
    _url = url
    (_host.replace if replace else _host.push)(url)
    _notify()


def back() -> None:
    """Go back one step in the history, as the browser's Back button does."""
    _host.back()


# ------------------------------------------------------------------ routes


@dataclass(frozen=True)
class Route:
    pattern: str  # "/orders/{id}"
    page: type
    parts: tuple[str, ...]  # "orders", "{id}"

    def match(self, segments: list[str]) -> dict[str, str] | None:
        if len(segments) != len(self.parts):
            return None
        params: dict[str, str] = {}
        for part, segment in zip(self.parts, segments):
            if part.startswith("{"):
                params[part[1:-1]] = segment
            elif part != segment:
                return None
        return params


# Every router()'s routes, by its pages folder (a reload replaces its entry),
# so trail() can name the levels of a URL.
_ROUTE_TABLES: dict[str, tuple[Route, ...]] = {}


@dataclass(frozen=True)
class Crumb:
    """One level of a breadcrumb trail: ``to`` is the path to link to, or
    None for a level with no page of its own."""

    to: str | None
    label: str


def trail(path: str | None = None, home: str = "Home") -> list[Crumb]:
    """The breadcrumb trail for ``path`` (the current location by default),
    one crumb per level: ``/orders/7`` gives Home, Orders, Order 7.

    A level's label is its page's ``crumb`` (``crumb = "Orders"`` in the
    code block; ``crumb = "Order {id}"`` fills in route parameters), else
    its URL segment made readable (``order-items`` -> "Order items"), and
    ``home`` for ``/``. A level no page answers to is a crumb with no link;
    ``/`` is left out when no page answers to it."""
    if path is None:
        path = location().path
    segments = [part for part in path.split("/") if part]
    routes = [route for table in reversed(_ROUTE_TABLES.values()) for route in table]
    crumbs: list[Crumb] = []
    for depth in range(len(segments) + 1):
        prefix = segments[:depth]
        to = "/" + "/".join(prefix)
        match = next(((r, params) for r in routes if (params := r.match(prefix)) is not None), None)
        if match is None:
            if depth:
                crumbs.append(Crumb(None, _readable(prefix[-1])))
            continue
        route, params = match
        label = vars(route.page).get("crumb")
        if isinstance(label, str) and label:
            try:
                label = label.format_map(params)
            except (KeyError, IndexError, ValueError):
                pass
        else:
            label = _readable(prefix[-1]) if depth else home
        crumbs.append(Crumb(to, label))
    return crumbs


def _readable(segment: str) -> str:
    text = segment.replace("-", " ").replace("_", " ").strip()
    return text[:1].upper() + text[1:] if text else segment


def _route_for(rel: Path) -> str:
    parts = list(rel.with_suffix("").parts)
    if parts[-1] == "index":
        parts.pop()
    return "/" + "/".join(part.replace("_", "-") for part in parts)


def _make_route(pattern: str, page: type, where: str) -> Route:
    if not pattern.startswith("/"):
        raise TemplateError(f'{where}: route must start with "/", got {pattern!r}')
    parts = tuple(part for part in pattern.split("/") if part)
    declared = declared_props(page)
    for part in parts:
        if part.startswith("{"):
            name = part[1:-1]
            if not (part.endswith("}") and name.isidentifier()):
                raise TemplateError(f"{where}: {part!r} in route {pattern!r} is not {{name}}")
            if name not in declared:
                raise TemplateError(
                    f"{where}: route {pattern!r} takes {name} from the URL; "
                    f"declare it in the code block, such as `{name}: str = \"\"`"
                )
    return Route(pattern, page, parts)


def _class_name(rel: Path) -> str:
    return "".join(word.capitalize() for word in rel.stem.split("_")) or "Page"


_NOT_FOUND_FILE = "not_found.weft"

NotFound = component_from_source(
    '<template><p class="pyweft-not-found">There is no page at {{ path }}.</p></template>'
    '<code>\npath: str = ""\n</code>',
    "NotFound",
)


class _Watching:
    """Re-render when the location changes."""

    def on_init(self) -> None:
        _watchers.add(self)

    def on_dispose(self) -> None:
        _watchers.discard(self)


_PagesBase = component_from_source(
    '<template><Dynamic :is="_page" :props="_props" key="_key" /></template>', "Pages"
)


class _Pages(_Watching, _PagesBase):
    _routes: tuple[Route, ...] = ()
    _missing: type = NotFound

    def _resolve(self) -> tuple[type, dict[str, Any], str]:
        # Worked out once per location (and class, which hot reload swaps)
        # rather than once per template expression.
        url = _current()
        cached = self.__dict__.get("_pw_route")
        if cached is not None and cached[0] == (url, type(self)):
            return cached[1]
        place = location()
        segments = [part for part in place.path.split("/") if part]
        result = None
        for route in self._routes:
            params = route.match(segments)
            if params is None:
                continue
            try:
                props = {name: prop_value(route.page, name, raw) for name, raw in params.items()}
            except ValueError:
                continue  # /orders/abc is not /orders/{id} for an int id
            declared = declared_props(route.page)
            for name, raw in place.query.items():
                if name in declared and name not in props and name != "route":
                    try:
                        props[name] = prop_value(route.page, name, raw)
                    except ValueError:
                        pass  # a bad query value leaves the field as it is
            result = (route.page, props, url)
            break
        if result is None:
            props = {"path": place.path} if "path" in declared_props(self._missing) else {}
            result = (self._missing, props, url)
        self.__dict__["_pw_route"] = ((url, type(self)), result)
        return result

    @property
    def _page(self) -> type:
        return self._resolve()[0]

    @property
    def _props(self) -> dict[str, Any]:
        return self._resolve()[1]

    @property
    def _key(self) -> str:
        # Every URL, query included, is a fresh page instance: on_init loads
        # its data again, and a parameter left out of the URL is back at its
        # default instead of keeping the last page's value.
        return self._resolve()[2]

    def on_after_render(self, first: bool) -> None:
        # navigate() while rendering (a page redirecting in on_init) happens
        # after this view chose a page, and render() clears change marks made
        # during it, so check here and ask for another pass.
        cached = self.__dict__.get("_pw_route")
        if cached is not None and cached[0][0] != _current():
            self.state_has_changed()


def router(folder: str | Path = "pages") -> type:
    """A component that shows the page for the current URL, from the
    ``.weft`` files in ``folder`` (relative to the file whose code block
    calls this). ``not_found.weft`` there is shown for unknown URLs and
    receives ``path``. Files and folders starting with ``_`` are skipped."""
    ctx = _LOAD.get()
    base = Path(folder)
    if not base.is_absolute():
        base = (ctx.current_dir if ctx is not None else Path.cwd()) / base
    base = base.resolve()
    if not base.is_dir():
        raise TemplateError(f"router(): no folder {base}")
    # Inside a load the pages share the app's root (scope ids, dotted tags);
    # outside one, the pages folder's parent stands in for it.
    root = None if ctx is not None else base.parent

    routes: list[Route] = []
    missing: type = NotFound
    by_pattern: dict[str, str] = {}
    for file in sorted(base.rglob("*.weft")):
        rel = file.relative_to(base)
        if any(part.startswith(("_", ".")) for part in rel.parts):
            continue
        if not all(part.isidentifier() for part in rel.parts[:-1]):
            continue  # the CLI doesn't ship such folders to the browser either
        page = load_component(file, _class_name(rel), root=root)
        where = f"{base.name}/{rel.as_posix()}"
        if rel.as_posix() == _NOT_FOUND_FILE:
            missing = page
            continue
        pattern = vars(page).get("route") or _route_for(rel)
        route = _make_route(pattern, page, where)
        shape = "/".join("{}" if p.startswith("{") else p for p in route.parts)
        if shape in by_pattern:
            raise TemplateError(
                f"{where} and {by_pattern[shape]} both want the URL {pattern!r}"
            )
        by_pattern[shape] = where
        routes.append(route)
    # Fixed segments before parameters, so /orders/new wins over /orders/{id}.
    routes.sort(key=lambda r: tuple(p.startswith("{") for p in r.parts))
    # Newest last (a reload moves its folder there): trail() asks it first.
    _ROUTE_TABLES.pop(str(base), None)
    _ROUTE_TABLES[str(base)] = tuple(routes)

    return type(
        "Pages",
        (_Pages,),
        {
            "_routes": tuple(routes),
            "_missing": missing,
            # Hot reload finds the pages through this registry and matches
            # this class to its next version by the "file".
            "components": {f"route:{r.pattern}": r.page for r in routes}
            | {"route:not-found": missing},
            "__weft_file__": f"{base}/",
        },
    )


_LinkBase = component_from_source(
    '<template><a :href="\'#\' + to" :class="\'active\' if active else None"'
    ' :aria-current="\'page\' if active else None" @click="follow"><Slot /></a></template>',
    "Link",
)


class Link(_Watching, _LinkBase):
    """``<Link to="/orders">Orders</Link>``: a link to a page, with class
    ``active`` and ``aria-current="page"`` while that page (or, unless
    ``exact``, one below it) is showing."""

    to: str = "/"
    exact: bool = False

    @property
    def active(self) -> bool:
        here = location().path
        target = _normalise(self.to).partition("?")[0]
        if self.exact or target == "/":
            return here == target
        return here == target or here.startswith(target + "/")

    def follow(self, event: Any) -> None:
        # Opening in a new tab or window is the browser's business.
        if any(event.get(k) for k in ("ctrlKey", "shiftKey", "altKey", "metaKey")):
            return
        if event.get("button", 0) != 0:
            return
        navigate(self.to)
