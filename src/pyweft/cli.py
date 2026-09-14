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
import re
import shutil
import sys
from http.server import HTTPServer, SimpleHTTPRequestHandler
from pathlib import Path

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


def app_pyweft_files(app_dir: Path) -> list[str]:
    files = sorted(p.name for p in app_dir.glob("*.weft"))
    if "app.weft" not in files:
        raise CliError(f"no app.weft in {app_dir} -- the root component must be app.weft")
    return files


def app_css_files(app_dir: Path) -> list[str]:
    return sorted(p.name for p in app_dir.glob("*.css"))


_HOST_ONLY = {"cli.py", "__main__.py"}  # never shipped to the browser


def pyweft_modules() -> list[str]:
    return sorted(p.name for p in _PKG_DIR.glob("*.py") if p.name not in _HOST_ONLY)


def render_shell(app_dir: Path) -> str:
    css = "\n  ".join(
        f'<link rel="stylesheet" href="app/{name}" />' for name in app_css_files(app_dir)
    )
    html = (_STATIC / "shell.html").read_text(encoding="utf-8")
    return (
        html.replace("__PYWEFT_TITLE__", app_dir.resolve().name)
        .replace("__PYWEFT_MODULES__", json.dumps(pyweft_modules()))
        .replace("__PYWEFT_APP_FILES__", json.dumps(app_pyweft_files(app_dir)))
        .replace("__PYWEFT_PACKAGES__", json.dumps(app_dependencies(app_dir)))
        .replace("__PYWEFT_CSS__", css)
    )


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
body { color: #222; }
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
    for name in pyweft_modules():
        shutil.copy(_PKG_DIR / name, out / "pyweft-src" / name)
    for name in files + app_css_files(app_dir):
        shutil.copy(app_dir / name, out / "app" / name)
    print(f"built {out}/ -- serve it with any static file server")


def cmd_run(app_dir: Path, port: int) -> None:
    app_pyweft_files(app_dir)  # fail fast with a clear message

    class Handler(SimpleHTTPRequestHandler):
        def do_GET(self):  # noqa: N802 (stdlib naming)
            route = self.path.split("?", 1)[0]
            if route in ("/", "/index.html"):
                # Re-rendered per request so edits to .weft files, css, or
                # pyproject.toml show up on refresh -- the no-build-step loop.
                return self._send("text/html", render_shell(app_dir).encode())
            if route == "/runtime.js":
                return self._file(_STATIC / "runtime.js", "text/javascript")
            name = Path(route).name  # flat lookups only; no traversal
            if route == f"/pyweft-src/{name}" and name in pyweft_modules():
                return self._file(_PKG_DIR / name, "text/x-python")
            if route == f"/app/{name}" and (app_dir / name).is_file():
                ctype = "text/css" if name.endswith(".css") else "text/plain"
                return self._file(app_dir / name, ctype)
            self.send_error(404)

        def _file(self, path: Path, ctype: str):
            self._send(ctype, path.read_bytes())

        def _send(self, ctype: str, body: bytes):
            self.send_response(200)
            self.send_header("Content-Type", f"{ctype}; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, fmt, *args):
            pass  # keep the console quiet

    server = HTTPServer(("127.0.0.1", port), Handler)
    print(f"serving {app_dir} at http://127.0.0.1:{port}/ (Ctrl-C to stop)")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass


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
