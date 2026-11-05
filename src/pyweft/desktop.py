"""The desktop host: an app in a native window, Python running as ordinary
CPython on the user's machine (``pyweft run APP --desktop``).

The window is a webview (pywebview: WebView2 on Windows, WebKit on macOS,
GTK or Qt on Linux) showing a small page with the same runtime.js the
browser uses. This file is the bridge the architecture was built for: the
core's patch ops cross pywebview's JavaScript bridge as JSON, and events come
back the same way. Nothing in the core changes.

Threads. pywebview's GUI loop owns the main thread; its JavaScript-to-Python
calls arrive on threads of their own. Every piece of app code runs on one
asyncio loop thread instead, one thing at a time, as in the browser: the
bridge only hands work to that loop. Python then drives each cycle itself,
as shell.html does in the browser: render, push the ops (evaluate_js waits
until they're applied), settle effects, push focus requests.

Host-only, like cli.py: never shipped to the browser.
"""

from __future__ import annotations

import asyncio
import concurrent.futures
import json
import os
import re
import sys
import threading
import traceback
from html import escape
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Callable
from urllib.parse import unquote

from . import dialogs, http, routing, storage
from .component import load_component
from .differ import diff
from .hotreload import format_error, hot_swap
from .renderer import Renderer
from .styles import collect_styles
from .vdom import to_dicts

_STATIC = Path(__file__).parent / "static"

_PAGE = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>__TITLE__</title>
  <style>
    #pyweft-dev-error {
      position: fixed; left: 1rem; right: 1rem; bottom: 1rem; z-index: 2147483647;
      max-height: 50vh; overflow: auto; padding: 0.9rem 1.1rem;
      border-left: 4px solid #e5484d; border-radius: 8px;
      background: #2b1213; color: #ffd8d8; white-space: pre-wrap;
      font: 13px/1.5 ui-monospace, SFMono-Regular, Consolas, monospace;
    }
  </style>
  __HEAD__
  __CSS__
  <style id="pyweft-component-styles"></style>
  <script src="runtime.js"></script>
</head>
<body>
  <div id="app"></div>
  <script>
    // The desktop bridge: events go to Python through pywebview's js_api;
    // Python calls apply()/commands() back with evaluate_js.
    const pyweftDesktop = (() => {
      let sent = 0;  // events handed to Python
      let done = 0;  // events Python has rendered
      // Still typing: the input's latest keystrokes haven't come back yet.
      PyWeftRuntime.options.typing = (el) => sent > done && el === document.activeElement;

      async function start() {
        const api = window.pywebview.api;
        const here = location.hash.startsWith("#/") ? location.hash.slice(1) : "/";
        const first = await api.mount(here);
        setCss(first.css);
        PyWeftRuntime.init(document.getElementById("app"), (id, event) => {
          sent += 1;
          api.dispatch(id, JSON.stringify(event), sent);
        });
        PyWeftRuntime.mount(first.tree);
        window.addEventListener("hashchange", () => {
          if (!location.hash.startsWith("#/")) return; // an in-page anchor
          api.location(location.hash.slice(1));
          window.scrollTo(0, 0);
        });
        await api.mounted();
      }

      function setCss(text) {
        document.getElementById("pyweft-component-styles").textContent = text;
      }

      window.addEventListener("pywebviewready", start);
      return {
        apply(ops, seq) {
          PyWeftRuntime.applyOps(ops);
          if (seq) done = Math.max(done, seq);
        },
        commands: (list) => PyWeftRuntime.runCommands(list),
        css: setCss,
        error(text) {
          let el = document.getElementById("pyweft-dev-error");
          if (!el) {
            el = document.createElement("div");
            el.id = "pyweft-dev-error";
            document.body.appendChild(el);
          }
          el.textContent = text;
        },
        clearError: () => document.getElementById("pyweft-dev-error")?.remove(),
        refreshCss(name) {
          for (const link of document.querySelectorAll("link[rel=stylesheet]")) {
            if (link.getAttribute("href").split("?")[0] === "app/" + name) {
              link.href = "app/" + name + "?v=" + Date.now();
            }
          }
        },
      };
    })();
  </script>
</body>
</html>
"""


class _Location:
    """routing's host: the location after the # in the window's address."""

    def __init__(self, app: DesktopApp):
        self.app = app

    def current(self) -> str:
        return self.app.here

    def push(self, url: str) -> None:
        self.app.here = url
        self.app.js(f"location.hash = {json.dumps(url)}")

    def replace(self, url: str) -> None:
        self.app.here = url
        self.app.js(f"history.replaceState(null, '', {json.dumps('#' + url)})")

    def back(self) -> None:
        self.app.js("history.back()")  # comes back through hashchange


class _Dialogs:
    """pyweft.dialogs in a window: the system's own dialogs. They wait for
    the user, so they run off the loop thread and the app keeps going."""

    def __init__(self, app: DesktopApp):
        self.app = app

    @staticmethod
    def _file_types(types: list[str]) -> tuple[str, ...]:
        if not types:
            return ()
        patterns = ";".join(f"*.{ext}" for ext in types)
        return (f"{', '.join(types).upper()} files ({patterns})", "All files (*.*)")

    async def open(self, types: list[str], multiple: bool) -> list[tuple]:
        import webview

        paths = await asyncio.to_thread(
            self.app.window.create_file_dialog,
            webview.FileDialog.OPEN,
            allow_multiple=multiple,
            file_types=self._file_types(types),
        )

        def read() -> list[tuple]:
            return [(Path(p).name, Path(p).read_bytes(), str(p)) for p in paths or ()]

        return await asyncio.to_thread(read)

    async def save(self, name: str, data: bytes, types: list[str]) -> bool:
        import webview

        chosen = await asyncio.to_thread(
            self.app.window.create_file_dialog,
            webview.FileDialog.SAVE,
            save_filename=name,
            file_types=self._file_types(types),
        )
        if not chosen:
            return False
        path = chosen if isinstance(chosen, str) else chosen[0]
        await asyncio.to_thread(Path(path).write_bytes, data)
        return True

    async def confirm(self, message: str, title: str) -> bool:
        return bool(
            await asyncio.to_thread(
                self.app.window.create_confirmation_dialog, title or "Confirm", message
            )
        )


class _Api:
    """What the page can call (window.pywebview.api.*). pywebview exposes
    every public method, so this holds nothing else."""

    def __init__(self, app: DesktopApp):
        self._app = app

    def mount(self, here: str) -> dict:
        return self._app.call(self._app.mount, here)

    def mounted(self) -> None:
        self._app.call(self._app.settle)

    def dispatch(self, handler_id: str, event_json: str, seq: int) -> None:
        self._app.post(self._app.dispatch, handler_id, json.loads(event_json), seq)

    def location(self, url: str) -> None:
        self._app.post(self._app.location, url)


class DesktopApp:
    """One app, one window. ``window`` is anything with ``evaluate_js``:
    a pywebview window, or a stand-in in tests."""

    def __init__(
        self,
        app_dir: Path,
        window: Any = None,
        base_url: str | None = None,
        storage_file: Path | None = None,
    ):
        self.app_dir = Path(app_dir).resolve()
        self.window = window
        # Where the window's page is served, so relative pyweft.http URLs
        # (assets/data.json) work as they do in the browser.
        self.base_url = base_url
        # pyweft.storage's file; in memory without one (tests).
        self.storage_file = storage_file
        self.here = "/"
        self.tree: list = []
        self.renderer: Renderer | None = None
        self.cls: type | None = None
        self._render_queued = False
        self.loop = asyncio.new_event_loop()
        self._thread = threading.Thread(target=self.loop.run_forever, daemon=True)
        self.api = _Api(self)

    # ---------------------------------------------------- the loop thread

    def start(self) -> None:
        self._thread.start()
        self.call(self._load)

    def stop(self) -> None:
        self.loop.call_soon_threadsafe(self.loop.stop)
        self._thread.join(timeout=5)

    def call(self, fn: Callable, *args: Any) -> Any:
        """Run ``fn`` on the loop thread and wait for its result."""
        future: concurrent.futures.Future = concurrent.futures.Future()

        def run() -> None:
            try:
                future.set_result(fn(*args))
            except BaseException as exc:  # noqa: BLE001 - re-raised in the caller
                future.set_exception(exc)

        self.loop.call_soon_threadsafe(run)
        return future.result()

    def post(self, fn: Callable, *args: Any) -> None:
        """Run ``fn`` on the loop thread, without waiting."""
        self.loop.call_soon_threadsafe(self._guarded, fn, *args)

    def _guarded(self, fn: Callable, *args: Any) -> None:
        try:
            fn(*args)
        except Exception as exc:  # noqa: BLE001 - shown, the app keeps running
            self.report(exc)

    def js(self, script: str) -> Any:
        if self.window is not None:
            return self.window.evaluate_js(script)
        return None

    # ------------------------------------------------------- the app cycle

    def _load(self) -> None:
        sys.path.insert(0, str(self.app_dir))  # the app's own modules
        routing.set_host(_Location(self))
        dialogs.set_host(_Dialogs(self))
        http.set_host(http.Urllib(base_url=self.base_url))
        storage.set_host(
            storage.FileStorage(self.storage_file) if self.storage_file else storage.MemoryStorage()
        )
        self.cls = load_component(self.app_dir / "app.weft")
        self.renderer = Renderer(self.cls())
        # Already on the loop thread whenever app code changes state, except
        # code that made its own thread: call_soon_threadsafe covers both.
        self.renderer.on_invalidate = self._schedule_render
        self.renderer.on_error = self.report
        self.renderer.init_root()

    def mount(self, here: str) -> dict:
        """The page (re)loaded: the whole current page, where it is now."""
        routing.location_changed(here)
        self.here = here
        self.renderer.resend_head()  # a reloaded page has lost the <Head> tags
        self.tree = self.renderer.render()
        return {"tree": to_dicts(self.tree), "css": collect_styles(self.cls)}

    def _render(self) -> list[dict]:
        new = self.renderer.render()
        ops = diff(self.tree, new)
        self.tree = new
        return ops

    def _push(self, ops: list[dict], seq: int = 0) -> None:
        if ops or seq:
            self.js(f"pyweftDesktop.apply({json.dumps(ops)}, {seq})")

    def settle(self) -> None:
        """What happens after every render is on the page: effects and
        on_after_render (rendering again while they change state), then
        focus and scroll requests."""
        while self.renderer.after_render():
            self._push(self._render())
        commands = self.renderer.take_commands()
        for command in commands:
            # The page's <title> is set too, but the window keeps its own.
            if command["op"] == "set_title" and hasattr(self.window, "set_title"):
                self.window.set_title(command["text"])
            elif command["op"] == "head" and hasattr(self.window, "set_title"):
                # A <Head> <title> names the window while it is shown.
                titles = [n for n in command["nodes"] if n.get("tag") == "title"]
                if titles:
                    self.window.set_title("".join(c.get("text", "") for c in titles[-1]["children"]))
                    self._head_titled = True
                elif getattr(self, "_head_titled", False):
                    from .cli import app_identity

                    self.window.set_title(app_identity(self.app_dir).title)
                    self._head_titled = False
        if commands:
            self.js(f"pyweftDesktop.commands({json.dumps(commands)})")

    def dispatch(self, handler_id: str, event: dict, seq: int) -> None:
        try:
            self.renderer.dispatch(handler_id, event)
        finally:
            # Rendered even when the handler failed: it may have changed
            # state first, and the page must learn the event was handled.
            self._push(self._render(), seq)
        self.settle()

    def location(self, url: str) -> None:
        self.here = url
        routing.location_changed(url)

    def _schedule_render(self) -> None:
        # Many state changes in one go become one render.
        if not self._render_queued:
            self._render_queued = True
            self.loop.call_soon_threadsafe(self._rerender)

    def _rerender(self) -> None:
        self._render_queued = False
        if self.renderer.needs_render():
            self._guarded(lambda: (self._push(self._render()), self.settle()))

    def report(self, exc: BaseException) -> None:
        summary = format_error(exc, root=str(self.app_dir))
        print(f"pyweft: {summary}", file=sys.stderr)
        traceback.print_exception(exc, file=sys.stderr)
        self.js(f"pyweftDesktop.error({json.dumps(summary)})")

    # ------------------------------------------------------- hot reload

    def hot_reload(self) -> None:
        """A .weft file changed: recompile, move live components onto the
        new classes keeping their state, and patch the page."""
        new_cls = load_component(self.app_dir / "app.weft")
        changed = hot_swap(self.renderer, new_cls)
        ops = self._render()
        self.cls = new_cls
        self.js(f"pyweftDesktop.css({json.dumps(collect_styles(new_cls))})")
        self._push(ops)
        self.js("pyweftDesktop.clearError()")
        self.settle()
        names = [str(Path(f).relative_to(self.app_dir)) for f in changed]
        print(f"pyweft: hot-reloaded {', '.join(names) or 'app'}")


# --------------------------------------------------------------- settings

# [tool.pyweft.desktop] in the app's pyproject.toml: setting -> (kind, default).
_WINDOW_SETTINGS: dict[str, tuple[str, Any]] = {
    "width": ("pixels", 1100),
    "height": ("pixels", 800),
    "min_size": ("pair", None),
    "resizable": ("bool", True),
    "maximized": ("bool", False),
    "fullscreen": ("bool", False),
    "on_top": ("bool", False),
    "frameless": ("bool", False),
    "background_color": ("color", None),
}
_KINDS = {
    "pixels": "a whole number of pixels, like 1200",
    "pair": "two whole numbers, like [800, 600]",
    "bool": "true or false",
    "color": 'a colour like "#1e293b"',
}


def _fits(kind: str, value: Any) -> bool:
    def pixels(v: Any) -> bool:
        return isinstance(v, int) and not isinstance(v, bool) and v > 0

    if kind == "pixels":
        return pixels(value)
    if kind == "pair":
        return isinstance(value, list) and len(value) == 2 and all(pixels(v) for v in value)
    if kind == "bool":
        return isinstance(value, bool)
    return isinstance(value, str) and re.fullmatch(r"#[0-9a-fA-F]{6}", value) is not None


def window_options(app_dir: Path) -> dict[str, Any]:
    """``webview.create_window`` arguments from ``[tool.pyweft.desktop]``;
    anything the app leaves out keeps its default. A setting that doesn't
    exist or doesn't fit is a CliError naming it."""
    from .cli import CliError, app_settings

    settings = app_settings(app_dir).get("desktop", {})
    unknown = sorted(set(settings) - set(_WINDOW_SETTINGS))
    if unknown:
        raise CliError(
            f"pyproject.toml [tool.pyweft.desktop] has no setting {unknown[0]!r}; "
            f"the settings are {', '.join(_WINDOW_SETTINGS)}"
        )
    options: dict[str, Any] = {}
    for name, (kind, default) in _WINDOW_SETTINGS.items():
        value = settings.get(name, default)
        if value is None:
            continue
        if not _fits(kind, value):
            raise CliError(
                f"pyproject.toml [tool.pyweft.desktop] {name} must be {_KINDS[kind]}, "
                f"not {value!r}"
            )
        options[name] = tuple(value) if kind == "pair" else value
    return options


def window_icon(app_dir: Path, icon: str | None) -> str | None:
    """The icon file for pywebview, where the platform can use it: an .ico
    on Windows, any image on Linux. macOS takes the Dock icon from a packaged
    app, so there it waits for packaging."""
    if icon is None or sys.platform == "darwin":
        return None
    if sys.platform == "win32" and not icon.lower().endswith(".ico"):
        print(f"pyweft: {icon} isn't an .ico file, which a Windows window icon needs; "
              "the window keeps the default icon")
        return None
    return str((Path(app_dir) / icon).resolve())


# ---------------------------------------------------------------- serving


def page(app_dir: Path) -> str:
    from .cli import app_css_files, app_identity, head_extras, linked_app_css

    head = head_extras(app_dir)
    linked = linked_app_css(head)
    css = "\n  ".join(
        f'<link rel="stylesheet" href="app/{name}" />'
        for name in app_css_files(app_dir)
        if name not in linked
    )
    html = _PAGE.replace("__CSS__", css)
    # Last, in one pass: the app's own text is never taken for a placeholder.
    user = {"__TITLE__": escape(app_identity(app_dir).title), "__HEAD__": head}
    return re.sub("__(?:TITLE|HEAD)__", lambda m: user[m.group(0)], html)


def make_server(app_dir: Path) -> ThreadingHTTPServer:
    """The window's page, runtime.js, the app's CSS and assets, on a free
    local port. Only those: nothing else on disk is reachable."""
    from .cli import _asset_path, app_css_files, content_type

    class Handler(SimpleHTTPRequestHandler):
        def do_GET(self):  # noqa: N802 (stdlib naming)
            route = unquote(self.path.split("?", 1)[0])
            if route in ("/", "/index.html"):
                return self._send("text/html", page(app_dir).encode())
            if route == "/runtime.js":
                return self._send("text/javascript", (_STATIC / "runtime.js").read_bytes())
            if route.startswith("/app/") and route[5:] in app_css_files(app_dir):
                return self._send("text/css", (app_dir / route[5:]).read_bytes())
            if route.startswith("/assets/"):
                path = _asset_path(app_dir, route[len("/assets/") :])
                if path is not None:
                    return self._send(content_type(path), path.read_bytes())
            self.send_error(404)

        def _send(self, ctype: str, body: bytes):
            self.send_response(200)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, fmt, *args):
            pass

    return ThreadingHTTPServer(("127.0.0.1", 0), Handler)


def _retitle(app: DesktopApp) -> None:
    # The title can follow an edit; size and the other window settings are
    # fixed when the window opens.
    from .cli import CliError, app_identity

    try:
        title = app_identity(app.app_dir).title
    except CliError as exc:
        print(f"pyweft: {exc}", file=sys.stderr)
        return
    if app.window is not None:
        app.window.set_title(title)
    print("pyweft: window settings other than the title apply after a restart")


def watch(app: DesktopApp, stop: threading.Event, interval: float = 0.3) -> None:
    """Hot reload for the window, from the same file snapshot as the
    browser's dev server."""
    from .cli import snapshot

    current = snapshot(app.app_dir)
    while not stop.wait(interval):
        new = snapshot(app.app_dir)
        changed = {k for k in current.keys() | new.keys() if current.get(k) != new.get(k)}
        current = new
        if not changed:
            continue
        if any(k.endswith(".py") or k.startswith("pyweft:") for k in changed):
            # Imported Python stays cached in this process; only a restart
            # picks up a changed module or a changed PyWeft.
            names = ", ".join(sorted(k.removeprefix("pyweft:") for k in changed))
            print(f"pyweft: {names} changed; restart `pyweft run --desktop` to use it")
            continue
        if "pyproject.toml" in changed:
            _retitle(app)
        weft = [k for k in changed if k.endswith(".weft")]
        if weft:
            app.post(app.hot_reload)
        for name in sorted(k for k in changed if k.endswith(".css")):
            app.js(f"pyweftDesktop.refreshCss({json.dumps(name)})")
        if any(not k.endswith((".weft", ".css")) for k in changed):
            app.js("location.reload()")  # head.html, assets: the page remounts


def data_dir(app_id: str) -> Path:
    """Where a desktop app keeps its data (pyweft.storage): the user's
    application data folder, in a folder named after the app."""
    if sys.platform == "win32":
        base = os.environ.get("APPDATA") or Path.home() / "AppData" / "Roaming"
    elif sys.platform == "darwin":
        base = Path.home() / "Library" / "Application Support"
    else:
        base = os.environ.get("XDG_DATA_HOME") or Path.home() / ".local" / "share"
    return Path(base) / app_id


def run_desktop(app_dir: Path, dev: bool = True) -> None:
    """The app in a window until it closes. ``dev`` (``pyweft run``) adds
    hot reload and terminal messages; a packaged app runs without them."""
    from .cli import CliError, app_id, app_identity, app_pyweft_files

    app_pyweft_files(app_dir)  # fails fast without an app.weft
    identity = app_identity(app_dir)  # and on a mistake in the settings
    options = window_options(app_dir)
    try:
        import webview
    except ImportError:
        raise CliError(
            "the desktop window needs pywebview: "
            'uv add "pyweft[desktop]"  (or: pip install "pyweft[desktop]")'
        ) from None

    server = make_server(app_dir)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    url = f"http://127.0.0.1:{server.server_address[1]}/"
    app = DesktopApp(app_dir, base_url=url, storage_file=data_dir(app_id(app_dir)) / "storage.json")
    try:
        app.start()
    except Exception as exc:  # noqa: BLE001 - shown as a CLI error
        app.stop()
        server.shutdown()
        raise CliError(format_error(exc, root=str(Path(app_dir).resolve()))) from None
    app.window = webview.create_window(identity.title, url, js_api=app.api, **options)
    stop = threading.Event()
    if dev:
        threading.Thread(target=watch, args=(app, stop), daemon=True).start()
        print(f"pyweft: {app_dir} in a desktop window (close it to stop)")
        print("  hot reload is on: saved .weft and .css files appear in the window")
    icon = window_icon(app_dir, identity.icon)
    try:
        webview.start(**({"icon": icon} if icon else {}))  # until the window closes
    finally:
        stop.set()
        server.shutdown()
        app.stop()


_STARTUP_ERROR = """<!DOCTYPE html><html><head><meta charset="utf-8"><title>{title}</title>
<style>body {{ font: 15px/1.5 system-ui, sans-serif; margin: 2rem; color: #1f2328; }}
pre {{ background: #f6f8fa; padding: 1rem; border-radius: 8px; white-space: pre-wrap; }}</style>
</head><body><h1>{title} couldn't start</h1><pre>{error}</pre></body></html>"""


def run_packaged(app_dir: Path) -> None:
    """Entry point of an app built with ``pyweft build --desktop``. There's
    no terminal to print to, so a failure to start shows in a window."""
    try:
        run_desktop(app_dir, dev=False)
    except Exception as exc:  # noqa: BLE001 - shown to the user instead
        import webview

        from .cli import CliError, app_identity

        detail = str(exc) if isinstance(exc, CliError) else traceback.format_exc()
        try:
            title = escape(app_identity(app_dir).title)
        except Exception:  # noqa: BLE001 - the settings may be what failed
            title = "The app"
        webview.create_window(
            "Couldn't start", html=_STARTUP_ERROR.format(title=title, error=escape(detail))
        )
        webview.start()
