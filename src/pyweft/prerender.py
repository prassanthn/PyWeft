"""Render an app's first screen ahead of time, on the developer's machine.

``pyweft run`` and ``pyweft build`` put the result in the page, so visitors
see the real app while Python starts in the browser instead of a loading
screen; the browser's first render then takes over the same markup. The CLI
runs this as ``python -m pyweft.prerender APP_DIR`` in a separate process:
the app's code runs here too (up to the first ``await`` of an async
``on_init``), and must not be able to break or slow down the CLI itself.

Host-only, like cli.py: never shipped to the browser.
"""

from __future__ import annotations

import asyncio
import html
import json
import sys
from pathlib import Path
from typing import Any

from . import routing
from .component import load_component
from .hotreload import format_error
from .renderer import Renderer
from .styles import collect_styles
from .vdom import Element, Node

MARK = "PYWEFT-PRERENDER "  # prefixes the result line, so the app may print

# Elements with no closing tag in HTML.
_VOID = frozenset(
    "area base br col embed hr img input link meta source track wbr".split()
)


def to_html(nodes: list[Node]) -> str:
    """The vdom as HTML, as the runtime would build it: same elements, same
    attributes. Events don't exist until Python runs, and scripts are left
    out, since the runtime never runs them either."""
    out: list[str] = []
    _write(nodes, out, selected=None)
    return "".join(out)


def _write(nodes: list[Node], out: list[str], selected: str | None) -> None:
    for node in nodes:
        if not isinstance(node, Element):
            out.append(html.escape(node.text, quote=False))
            continue
        if node.tag == "script":
            continue
        attrs = dict(node.attrs)
        inner = selected
        # value is a live property for these, not markup: say it in HTML.
        if node.tag == "textarea":
            text = attrs.pop("value", "")
        elif node.tag == "select":
            inner = attrs.pop("value", None)
        elif node.tag == "option" and selected is not None and attrs.get("value") == selected:
            attrs["selected"] = ""
        out.append(f"<{node.tag}")
        for name, value in attrs.items():
            out.append(f' {name}="{html.escape(value)}"' if value else f" {name}")
        out.append(">")
        if node.tag in _VOID:
            continue
        if node.tag == "textarea":
            out.append(html.escape(text, quote=False))
        elif node.tag == "style":
            # Raw text: escaping would break CSS (a > b); only "</style" ends it.
            css = "".join(c.text for c in node.children if not isinstance(c, Element))
            out.append(css.replace("</style", "<\\/style"))
        else:
            _write(node.children, out, inner)
        out.append(f"</{node.tag}>")


def head_html(nodes: list[Node]) -> tuple[str, str | None]:
    """``<Head>`` content for the page's head (marked, so the runtime
    replaces it), and the text of its last ``<title>``, if any."""
    title = None
    tags = []
    for node in nodes:
        if not isinstance(node, Element):
            continue
        if node.tag == "title":
            title = "".join(c.text for c in node.children if not isinstance(c, Element))
            continue
        tags.append(Element(node.tag, {**node.attrs, "data-pyweft-head": ""}, {}, node.children))
    return to_html(tags), title


def prerender(app_dir: Path) -> dict[str, Any]:
    """``{"html", "css", "location", "head", "title"}`` for the app's first
    screen. ``location`` is the address it was rendered at, or ``""`` when
    the app doesn't route, so any address may show it. ``head`` and
    ``title`` come from its ``<Head>`` blocks (``title`` None without one)."""
    app_dir = app_dir.resolve()
    sys.path.insert(0, str(app_dir))  # the app's own modules, as in the browser
    routing.set_host(routing.MemoryHistory("/"))
    App = load_component(app_dir / "app.weft")

    async def first_screen() -> tuple[list[Node], list[Node]]:
        # What the browser shows once its first render has settled: effects
        # and the synchronous start of an async on_init included.
        renderer = Renderer(App())
        renderer.compile_when_idle = True  # one render: walking is cheaper
        renderer.init_root()
        tree = renderer.render()
        for _ in range(100):
            if not renderer.after_render():
                break
            tree = renderer.render()
        for task in renderer.pending_tasks():
            task.cancel()
        return tree, renderer._head_nodes

    tree, head = asyncio.run(first_screen())
    css = collect_styles(App)
    head_tags, title = head_html(head)
    return {
        "head": head_tags,
        "title": title,
        "html": to_html(tree),
        # Inside <style>, only "</style" could end the element early.
        "css": css.replace("</style", "<\\/style"),
        "location": routing._current() if routing._url is not None else "",
    }


def main(argv: list[str] | None = None) -> int:
    args = sys.argv[1:] if argv is None else argv
    app_dir = Path(args[0])
    try:
        result = prerender(app_dir)
    except BaseException as exc:  # noqa: BLE001 - reported, never raised
        result = {"error": format_error(exc, root=str(app_dir.resolve()))}
    sys.__stdout__.write(MARK + json.dumps(result) + "\n")
    sys.__stdout__.flush()
    return 0


if __name__ == "__main__":
    sys.exit(main())
