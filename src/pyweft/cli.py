"""The ``pyweft`` command line: scaffold, serve, and build apps.

A pyweft app is a directory of ``.weft`` files with ``app.weft`` as the root,
plus an ordinary ``pyproject.toml``. Dependencies declared there (with ``uv
add`` or by hand) are installed *in the browser* by micropip at page load, so
the same file drives local tooling and the runtime. Only pure-Python wheels or
packages Pyodide ships prebuilt will work -- the browser can't compile C.
"""

from __future__ import annotations

import argparse
import json
import mimetypes
import re
import shutil
import socket
import sys
import threading
import uuid
from dataclasses import dataclass
from html.parser import HTMLParser
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlsplit

try:
    import tomllib
except ModuleNotFoundError:  # Python 3.10
    tomllib = None

_STATIC = Path(__file__).parent / "static"
_PKG_DIR = Path(__file__).parent


class CliError(RuntimeError):
    pass


# ------------------------------------------------------------------ app model


def app_dependencies(app_dir: Path) -> list[str]:
    """``[project].dependencies`` from the app's pyproject.toml, if any."""
    pyproject = app_dir / "pyproject.toml"
    if not pyproject.exists():
        return []
    text = pyproject.read_text(encoding="utf-8")
    if tomllib is not None:
        return list(tomllib.loads(text).get("project", {}).get("dependencies", []))
    # 3.10 fallback: good enough for the flat list uv/pip write.
    match = re.search(r"^dependencies\s*=\s*\[(.*?)\]", text, re.S | re.M)
    return re.findall(r"[\"']([^\"']+)[\"']", match.group(1)) if match else []


ASSETS_DIR = "assets"
# assets/ is served as-is (images, fonts, vendored CSS/JS), so a .css file in
# it must not be linked automatically and a .weft file there is not a component.
_SKIP_DIRS = {"dist", "node_modules", ASSETS_DIR}


def _app_files(app_dir: Path, suffix: str) -> list[str]:
    """App-relative POSIX paths of every ``suffix`` file, including subfolders
    a dotted tag can name (``widgets/row.weft`` for ``<widgets.Row>``).

    Folders that cannot be part of a tag are skipped -- dot-folders such as
    ``.venv``, ``_private`` ones, ``node_modules`` -- and so is build output
    (``dist`` or any folder holding a ``pyweft-src``), which would otherwise
    ship a second copy of the app inside the app.
    """
    found: list[str] = []

    def walk(folder: Path, prefix: str) -> None:
        for entry in sorted(folder.iterdir(), key=lambda e: e.name):
            if entry.is_dir():
                if (
                    entry.is_symlink()
                    or not entry.name.isidentifier()
                    or entry.name.startswith("_")
                    or entry.name in _SKIP_DIRS
                    or (entry / "pyweft-src").is_dir()
                ):
                    continue
                walk(entry, f"{prefix}{entry.name}/")
            elif entry.suffix == suffix:
                found.append(prefix + entry.name)

    walk(app_dir, "")
    return found


def app_pyweft_files(app_dir: Path) -> list[str]:
    files = _app_files(app_dir, ".weft")
    if "app.weft" not in files:
        raise CliError(f"no app.weft in {app_dir} -- the root component must be app.weft")
    return files


def app_css_files(app_dir: Path) -> list[str]:
    return _app_files(app_dir, ".css")


def app_assets(app_dir: Path) -> list[str]:
    """Paths below ``assets/`` (``logo.svg``, ``fonts/inter.woff2``) of every
    file there; served at ``assets/<path>`` by ``run`` and copied by ``build``."""
    root = app_dir / ASSETS_DIR
    if not root.is_dir():
        return []
    return sorted(
        p.relative_to(root).as_posix()
        for p in root.rglob("*")
        if p.is_file() and not p.is_symlink()
    )


def _asset_path(app_dir: Path, rel: str) -> Path | None:
    """The file ``assets/<rel>`` names, or None if it is missing or outside
    ``assets/`` (``..``, symlinks), so a crafted URL reaches nothing else."""
    root = (app_dir / ASSETS_DIR).resolve()
    try:
        path = (root / rel).resolve()
    except (OSError, ValueError):
        return None
    if path == root or not path.is_relative_to(root) or not path.is_file():
        return None
    return path


# mimetypes reads the Windows registry, which can be wrong or missing these.
_CONTENT_TYPES = {
    ".css": "text/css",
    ".js": "text/javascript",
    ".mjs": "text/javascript",
    ".json": "application/json",
    ".svg": "image/svg+xml",
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".gif": "image/gif",
    ".webp": "image/webp",
    ".avif": "image/avif",
    ".ico": "image/x-icon",
    ".woff": "font/woff",
    ".woff2": "font/woff2",
    ".ttf": "font/ttf",
    ".otf": "font/otf",
}


def content_type(path: Path) -> str:
    known = _CONTENT_TYPES.get(path.suffix.lower())
    return known or mimetypes.guess_type(path.name)[0] or "application/octet-stream"


# --------------------------------------------------------- component libraries


@dataclass
class Library:
    """A dependency that holds .weft components and is installed where
    ``pyweft run`` runs: shipped to the browser from there (``/lib/<name>/``)
    instead of being installed from PyPI."""

    name: str  # the import name
    folder: Path
    files: list[str]  # POSIX paths below folder


_LIBRARY_SUFFIXES = {".py", ".weft", ".css"}


def _requirement_name(spec: str) -> str:
    match = re.match(r"\s*([A-Za-z0-9][A-Za-z0-9._-]*)", spec)
    return match.group(1) if match else spec.strip()


def _normalise(name: str) -> str:
    return re.sub(r"[-_.]+", "-", name).lower()


def _distribution(dist_name: str):
    from importlib import metadata

    try:
        return metadata.distribution(dist_name)
    except metadata.PackageNotFoundError:
        return None


def _import_names(dist_name: str) -> list[str]:
    """Top-level packages a distribution installs, best effort: its
    top_level.txt, else its file list, else the name with - as _."""
    names: list[str] = []
    dist = _distribution(dist_name)
    if dist is not None:
        top = dist.read_text("top_level.txt")
        if top:
            names += top.split()
        for f in dist.files or []:
            first = f.parts[0]
            if len(f.parts) > 1 and first.isidentifier() and not first.endswith("-info"):
                names.append(first)
    names.append(dist_name.replace("-", "_").replace(".", "_"))
    return list(dict.fromkeys(names))


def find_library(dist_name: str) -> Library | None:
    import importlib.util

    for import_name in _import_names(dist_name):
        try:
            spec = importlib.util.find_spec(import_name)
        except (ImportError, ValueError):
            continue
        if spec is None or not spec.submodule_search_locations:
            continue
        folder = Path(next(iter(spec.submodule_search_locations)))
        files = sorted(
            p.relative_to(folder).as_posix()
            for p in folder.rglob("*")
            if p.is_file()
            and p.suffix in _LIBRARY_SUFFIXES
            and "__pycache__" not in p.parts
        )
        if any(f.endswith(".weft") for f in files):
            return Library(import_name, folder, files)
    return None


def app_libraries(app_dir: Path) -> list[Library]:
    found: dict[str, Library] = {}
    for spec in app_dependencies(app_dir):
        name = _requirement_name(spec)
        if _normalise(name) == "pyweft":
            continue
        library = find_library(name)
        if library is not None:
            found[library.name] = library
    return list(found.values())


def browser_packages(app_dir: Path) -> list[str]:
    """What micropip installs in the browser: the app's dependencies minus
    the libraries shipped from this environment (and PyWeft itself, which
    ships as pyweft-src), plus those libraries' own requirements."""
    packages: list[str] = []
    shipped: set[str] = {"pyweft"}
    requirements: list[str] = []
    for spec in app_dependencies(app_dir):
        name = _requirement_name(spec)
        if _normalise(name) == "pyweft":
            continue
        library = find_library(name)
        if library is None:
            packages.append(spec)
            continue
        shipped |= {_normalise(name), _normalise(library.name)}
        dist = _distribution(name)
        requirements += (dist.requires or []) if dist is not None else []
    for req in requirements:
        if re.search(r"extra\s*==", req):
            continue  # optional extras are not installed
        if _normalise(_requirement_name(req)) not in shipped:
            packages.append(req.split(";")[0].strip())
    return list(dict.fromkeys(packages))


_HOST_ONLY = {"cli.py", "__main__.py"}  # never shipped to the browser


def pyweft_modules() -> list[str]:
    return sorted(p.name for p in _PKG_DIR.glob("*.py") if p.name not in _HOST_ONLY)


LOADING_FILE = "loading.html"


def loading_screen(app_dir: Path) -> str:
    """The app's own ``loading.html`` if it has one (an empty file means no
    loading screen), otherwise the built-in default."""
    custom = app_dir / LOADING_FILE
    source = custom if custom.is_file() else _STATIC / LOADING_FILE
    return source.read_text(encoding="utf-8")


HEAD_FILE = "head.html"


def head_extras(app_dir: Path) -> str:
    """The app's ``head.html``, added to the page's ``<head>``: CDN
    stylesheets and scripts, fonts, meta tags. Empty if there is none."""
    path = app_dir / HEAD_FILE
    return path.read_text(encoding="utf-8") if path.is_file() else ""


class _StylesheetLinks(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.hrefs: list[str] = []

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag == "link" and "stylesheet" in (a.get("rel") or "").lower().split():
            if a.get("href"):
                self.hrefs.append(a["href"])

    handle_startendtag = handle_starttag


def linked_app_css(head: str) -> set[str]:
    """App .css files that head.html links itself (``app/tailwind.css``), and
    which therefore must not be linked a second time, out of its order."""
    parser = _StylesheetLinks()
    parser.feed(head)
    parser.close()
    found = set()
    for href in parser.hrefs:
        href = re.split(r"[?#]", href, maxsplit=1)[0]
        href = href[2:] if href.startswith("./") else href.lstrip("/")
        if href.startswith("app/"):
            found.add(href[len("app/") :])
    return found


def render_shell(app_dir: Path, dev: bool = False, since: int = 0) -> str:
    """``dev`` turns on hot reload: only ``pyweft run`` pages get it, never
    the static output of ``pyweft build``. ``since`` is how many changes the
    dev server had published when it rendered the page; the page asks for
    the ones after it, so a save made while it was starting is not lost."""
    head = head_extras(app_dir)
    linked = linked_app_css(head)
    css = "\n  ".join(
        f'<link rel="stylesheet" href="app/{name}" data-pyweft-css="{name}" />'
        for name in app_css_files(app_dir)
        if name not in linked
    )
    html = (_STATIC / "shell.html").read_text(encoding="utf-8")
    html = (
        html.replace("__PYWEFT_TITLE__", app_dir.resolve().name)
        .replace("__PYWEFT_MODULES__", json.dumps(pyweft_modules()))
        .replace("__PYWEFT_APP_FILES__", json.dumps(app_pyweft_files(app_dir)))
        .replace("__PYWEFT_PACKAGES__", json.dumps(browser_packages(app_dir)))
        .replace(
            "__PYWEFT_LIBRARIES__",
            json.dumps([{"name": lib.name, "files": lib.files} for lib in app_libraries(app_dir)]),
        )
        .replace("__PYWEFT_DEV__", "true" if dev else "false")
        .replace("__PYWEFT_SINCE__", str(since))
        .replace("__PYWEFT_CSS__", css)
    )
    leftover = re.search(r"__PYWEFT_(?!HEAD__|LOADING__)[A-Z_]+?__", html)
    if leftover:
        # Only possible when shell.html is newer than this process's code:
        # PyWeft was updated while `pyweft run` kept running.
        raise CliError(
            f"shell.html has a placeholder ({leftover.group(0)}) this pyweft "
            "does not fill: PyWeft was updated while `pyweft run` was running. "
            "Restart `pyweft run`."
        )
    # The user's files go in last and in one pass, so text in them is never
    # taken for a placeholder (not even one in the other file).
    user = {"__PYWEFT_HEAD__": head, "__PYWEFT_LOADING__": loading_screen(app_dir)}
    return re.sub("__PYWEFT_(?:HEAD|LOADING)__", lambda m: user[m.group(0)], html)


# ------------------------------------------------------------------ commands


_SCAFFOLD_APP = """\
<template>
  <div class="hello">
    <h1>Hello, {{ name or "stranger" }}!</h1>
    <input @bind="name" placeholder="your name" />
    <button @click="cheer">cheer</button>
    <p>{{ cheers }} cheers so far</p>
  </div>
</template>

<style>
/* Scoped to this component: these rules cannot leak into other components. */
.hello { border: 1px solid #ddd; border-radius: 8px; padding: 1.5rem; }
input, button { font: inherit; padding: 0.35rem 0.7rem; }
</style>

<code>
name: str = ""
cheers: int = 0

def cheer(self):
    self.cheers += 1
</code>
"""

_SCAFFOLD_CSS = """\
/* Global styles. Component-specific rules belong in a <style> block in the
   component's .weft file, where they are scoped to that component. */
body {
  font-family: system-ui, sans-serif;
  max-width: 40rem;
  margin: 3rem auto;
  padding: 0 1rem;
  color: #222;
}
"""

_SCAFFOLD_HEAD = """\
<!--
  Added to the page's <head>: stylesheets and scripts from a CDN, web fonts,
  meta tags. Uncomment what you need.

  Tailwind, no build step (development):
  <script src="https://cdn.jsdelivr.net/npm/@tailwindcss/browser@4"></script>

  Bootstrap's CSS:
  <link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.3/dist/css/bootstrap.min.css" />

  Your own .css files are linked after this file automatically, in
  alphabetical order. Link one here to choose where it goes instead:
  <link rel="stylesheet" href="app/styles.css" />

  Files in the assets/ folder are served at assets/...:
  <link rel="icon" href="assets/favicon.svg" />
-->
"""


def cmd_new(target: Path) -> None:
    if target.exists() and any(target.iterdir()):
        raise CliError(f"{target} already exists and is not empty")
    target.mkdir(parents=True, exist_ok=True)
    (target / "pyproject.toml").write_text(
        f'[project]\nname = "{target.name}"\nversion = "0.1.0"\ndependencies = []\n',
        encoding="utf-8",
    )
    (target / "app.weft").write_text(_SCAFFOLD_APP, encoding="utf-8")
    (target / "styles.css").write_text(_SCAFFOLD_CSS, encoding="utf-8")
    (target / HEAD_FILE).write_text(_SCAFFOLD_HEAD, encoding="utf-8")
    shutil.copy(_STATIC / LOADING_FILE, target / LOADING_FILE)
    print(f"created {target}/")
    print(f"  run it:  pyweft run {target}")
    print(f"  add browser-usable packages with:  uv add <pkg>  (inside {target}/)")


def cmd_build(app_dir: Path, out: Path) -> None:
    files = app_pyweft_files(app_dir)  # validates app.weft exists first
    html = render_shell(app_dir)
    if out.exists():
        shutil.rmtree(out)
    (out / "pyweft-src").mkdir(parents=True)
    (out / "app").mkdir()

    (out / "index.html").write_text(html, encoding="utf-8")
    shutil.copy(_STATIC / "runtime.js", out / "runtime.js")
    shutil.copy(_STATIC / "worker.js", out / "worker.js")
    for name in pyweft_modules():
        shutil.copy(_PKG_DIR / name, out / "pyweft-src" / name)
    for name in files + app_css_files(app_dir):
        target = out / "app" / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy(app_dir / name, target)
    for name in app_assets(app_dir):
        target = out / ASSETS_DIR / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy(app_dir / ASSETS_DIR / name, target)
    for lib in app_libraries(app_dir):
        for name in lib.files:
            target = out / "lib" / lib.name / name
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy(lib.folder / name, target)
    print(f"built {out}/ -- serve it with any static file server")


# ---------------------------------------------------------------- hot reload

# Files that only take effect when the page starts: a change means reload.
_STARTUP_FILES = ("pyproject.toml", LOADING_FILE, HEAD_FILE)
_FRAMEWORK = "pyweft:"  # snapshot key prefix for the framework's own files
_ASSET = ASSETS_DIR + "/"  # snapshot key prefix for assets/ files
_LIB = "lib:"  # snapshot key prefix for component library files
# Everything else of the framework is re-read per request; this is not.
_SERVER_CODE = _FRAMEWORK + "cli.py"
_STALE_MESSAGE = (
    "PyWeft was updated, but this `pyweft run` is still running the old "
    "server code. Restart `pyweft run`, then reload the page."
)


def snapshot(app_dir: Path) -> dict[str, tuple[int, int]]:
    """(mtime, size) of everything a change notification is sent for: the
    app's .weft/.css files, its startup files and assets, and the framework
    itself (so editing PyWeft while running an app reloads the page too)."""
    entries: dict[str, Path] = {}
    for rel in _app_files(app_dir, ".weft") + _app_files(app_dir, ".css"):
        entries[rel] = app_dir / rel
    for name in _STARTUP_FILES:
        entries[name] = app_dir / name
    for rel in app_assets(app_dir):
        entries[_ASSET + rel] = app_dir / ASSETS_DIR / rel
    for lib in app_libraries(app_dir):
        for rel in lib.files:
            entries[f"{_LIB}{lib.name}/{rel}"] = lib.folder / rel
    for path in [*_PKG_DIR.glob("*.py"), *_STATIC.iterdir()]:
        entries[_FRAMEWORK + path.name] = path

    result: dict[str, tuple[int, int]] = {}
    for key, path in entries.items():
        try:
            st = path.stat()
        except OSError:
            continue  # absent, or deleted mid-scan
        result[key] = (st.st_mtime_ns, st.st_size)
    return result


def describe_change(old: dict, new: dict) -> dict | None:
    """The message for the browser, or None if nothing changed.

    ``reload`` when a startup, asset or framework file changed (an image or
    font may be referenced from anywhere, so nothing short of a reload is
    sure to show it); otherwise ``update`` listing changed/added and removed
    .weft and .css files, which the page applies without losing state.
    """
    touched = sorted({k for k in old.keys() | new.keys() if old.get(k) != new.get(k)})
    if not touched:
        return None
    for key in touched:
        if key.startswith((_FRAMEWORK, _ASSET, _LIB)) or key in _STARTUP_FILES:
            name = key[len(_FRAMEWORK) :] if key.startswith(_FRAMEWORK) else key
            return {"type": "reload", "reason": f"{name} changed"}

    def pick(suffix: str, present: bool) -> list[str]:
        return [k for k in touched if k.endswith(suffix) and (k in new) == present]

    return {
        "type": "update",
        "weft": pick(".weft", True),
        "weft_removed": pick(".weft", False),
        "css": pick(".css", True),
        "css_removed": pick(".css", False),
    }


class ChangeFeed:
    """Append-only list of change messages that event-stream handlers wait on."""

    def __init__(self) -> None:
        self.events: list[dict] = []
        self.cond = threading.Condition()
        self.closed = False
        self.stale = False  # the server's own code changed since it started

    def publish(self, event: dict) -> None:
        with self.cond:
            self.events.append(event)
            self.cond.notify_all()

    def close(self) -> None:
        with self.cond:
            self.closed = True
            self.cond.notify_all()


def _watch(app_dir: Path, feed: ChangeFeed, interval: float, stop: threading.Event):
    current = snapshot(app_dir)
    while not stop.wait(interval):
        new = snapshot(app_dir)
        if new == current:
            continue
        # Editors often save in several writes (truncate, write, rename);
        # give them a moment so the page sees the finished file.
        stop.wait(0.1)
        new = snapshot(app_dir)
        event = describe_change(current, new)
        if current.get(_SERVER_CODE) != new.get(_SERVER_CODE):
            # Reloading would only serve new page files from old server code
            # (missing routes, unfilled placeholders). Say so where the user
            # is looking, and keep saying it to pages that connect later.
            print(f"pyweft: {_STALE_MESSAGE}", file=sys.stderr)
            feed.stale = True
            event = {"type": "stale", "reason": _STALE_MESSAGE}
        current = new
        if event:
            feed.publish(event)


class _DevServer(ThreadingHTTPServer):
    daemon_threads = True  # open event streams must not block exit

    if sys.platform == "win32":
        # SO_REUSEADDR on Windows lets a second server listen on a port that
        # is in use, and requests then reach either one: an old `pyweft run`
        # left running would quietly serve pages from stale code.
        allow_reuse_address = False

        def server_bind(self):
            self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
            super().server_bind()


def make_dev_server(
    app_dir: Path, port: int, poll_interval: float = 0.3
) -> ThreadingHTTPServer:
    """The ``pyweft run`` server, not yet serving: the app plus a change
    feed at ``/__pyweft/events`` that hot reload listens to. Call
    ``serve_forever()``, and ``shutdown_dev()`` to stop it and its watcher."""
    app_pyweft_files(app_dir)  # fail fast with a clear message
    feed = ChangeFeed()
    stop = threading.Event()
    # A new id per server run: a page that reconnects to a restarted server
    # reloads, since the server may have been restarted for a reason.
    server_id = uuid.uuid4().hex

    class Handler(SimpleHTTPRequestHandler):
        def do_GET(self):  # noqa: N802 (stdlib naming)
            route = self.path.split("?", 1)[0]
            if route in ("/", "/index.html"):
                # Re-rendered per request so edits to .weft files, css, or
                # pyproject.toml show up on refresh -- the no-build-step loop.
                with feed.cond:
                    since = len(feed.events)
                try:
                    page = render_shell(app_dir, dev=True, since=since)
                except CliError as exc:
                    print(f"error: {exc}", file=sys.stderr)
                    self.send_error(500, explain=str(exc))
                    return
                return self._send("text/html", page.encode())
            if route == "/__pyweft/events":
                return self._events()
            if route in ("/runtime.js", "/worker.js"):
                return self._file(_STATIC / route[1:], "text/javascript")
            name = Path(route).name  # flat lookups only; no traversal
            if route == f"/pyweft-src/{name}" and name in pyweft_modules():
                return self._file(_PKG_DIR / name, "text/x-python")
            if route.startswith("/app/"):
                # Only paths the app actually ships, so a crafted URL cannot
                # reach anything else on disk.
                rel = route[len("/app/") :]
                if rel in app_pyweft_files(app_dir) or rel in app_css_files(app_dir):
                    ctype = "text/css" if rel.endswith(".css") else "text/plain"
                    return self._file(app_dir / rel, ctype)
            if route.startswith("/lib/"):
                # Only files of a library the app depends on, listed by name.
                lib_name, _, rel = route[len("/lib/") :].partition("/")
                for lib in app_libraries(app_dir):
                    if lib.name == lib_name and rel in lib.files:
                        ctype = "text/css" if rel.endswith(".css") else "text/plain"
                        return self._file(lib.folder / rel, ctype)
            if route.startswith(f"/{_ASSET}"):
                path = _asset_path(app_dir, unquote(route[len(_ASSET) + 1 :]))
                if path is not None:
                    return self._file(path, content_type(path))
            self.send_error(404)

        def _file(self, path: Path, ctype: str):
            self._send(ctype, path.read_bytes())

        def _send(self, ctype: str, body: bytes):
            self.send_response(200)
            textual = ctype.startswith("text/") or ctype in (
                "application/json",
                "image/svg+xml",
            )
            self.send_header(
                "Content-Type", f"{ctype}; charset=utf-8" if textual else ctype
            )
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)

        def _events(self):
            """Server-Sent Events: one JSON message per change, held open.

            Starts after the change the page says it has seen: ``Last-Event-ID``
            when the browser reconnects, else ``?since=`` from the page itself
            (changes saved while it was loading), else from now.
            """
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            query = parse_qs(urlsplit(self.path).query)
            start = self.headers.get("Last-Event-ID") or query.get("since", [None])[0]
            with feed.cond:
                seen = len(feed.events)
                if start is not None and start.isdigit():
                    seen = min(int(start), seen)
            try:
                self._emit({"type": "hello", "server": server_id, "stale": feed.stale})
                while True:
                    with feed.cond:
                        feed.cond.wait_for(
                            lambda: len(feed.events) > seen or feed.closed, timeout=15
                        )
                        if feed.closed:
                            return
                        first, new, seen = seen, feed.events[seen:], len(feed.events)
                    for number, event in enumerate(new, first + 1):
                        self._emit(event, number)
                    if not new:  # keeps proxies from closing an idle stream
                        self.wfile.write(b": keepalive\n\n")
                        self.wfile.flush()
            except OSError:
                return  # the page went away

        def _emit(self, event: dict, number: int | None = None):
            # The id is what the browser sends back as Last-Event-ID.
            prefix = f"id: {number}\n" if number is not None else ""
            self.wfile.write(f"{prefix}data: {json.dumps(event)}\n\n".encode())
            self.wfile.flush()

        def log_message(self, fmt, *args):
            pass  # keep the console quiet

    server = _DevServer(("127.0.0.1", port), Handler)
    watcher = threading.Thread(
        target=_watch, args=(app_dir, feed, poll_interval, stop), daemon=True
    )
    watcher.start()

    def shutdown_dev() -> None:
        stop.set()
        feed.close()
        server.shutdown()
        server.server_close()

    server.shutdown_dev = shutdown_dev
    server.feed = feed
    return server


def cmd_run(app_dir: Path, port: int) -> None:
    try:
        server = make_dev_server(app_dir, port)
    except OSError as exc:
        raise CliError(
            f"cannot listen on port {port} ({exc.strerror or exc}). Is another "
            "`pyweft run` still running? Stop it, or pick a port with --port"
        ) from None
    print(f"serving {app_dir} at http://127.0.0.1:{port}/ (Ctrl-C to stop)")
    print("  hot reload is on: saved changes appear in the open page")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.feed.close()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="pyweft", description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    p_new = sub.add_parser("new", help="scaffold a new app directory")
    p_new.add_argument("path", type=Path)

    p_run = sub.add_parser("run", help="serve an app directory for the browser")
    p_run.add_argument("app_dir", type=Path)
    p_run.add_argument("--port", type=int, default=8642)

    p_build = sub.add_parser("build", help="write a self-contained static site")
    p_build.add_argument("app_dir", type=Path)
    p_build.add_argument("--out", type=Path, default=None)

    args = parser.parse_args(argv)
    try:
        if args.command == "new":
            cmd_new(args.path)
        elif args.command == "run":
            cmd_run(args.app_dir, args.port)
        else:
            cmd_build(args.app_dir, args.out or args.app_dir / "dist")
    except CliError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
