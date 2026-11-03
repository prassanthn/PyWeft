"""The desktop host's bridge, with a stand-in for the pywebview window that
applies the pushed ops to a dict model of the page (dommodel)."""

import json
import re
import textwrap
import time
import urllib.request

import pytest

from pyweft import routing
from pyweft.desktop import DesktopApp, make_server, page
from pyweft.dommodel import apply_patches

APP = """
<template>
  <main>
    <h1>{{ count }} {{ note }}</h1>
    <button @click="count += 1">+1</button>
    <button @click="later">later</button>
    <button @click="boom">boom</button>
    <input ref="field" @bind="note" />
  </main>
</template>
<code>
import asyncio
count: int = 0
note: str = ""

async def later(self):
    await asyncio.sleep(0.01)
    self.count += 10

def boom(self):
    self.count = -1
    raise ValueError("nope")
</code>
"""


class FakeWindow:
    def __init__(self):
        self.dom = []
        self.scripts = []
        self.done = 0
        self.title = None

    def set_title(self, title):
        self.title = title

    def evaluate_js(self, script):
        self.scripts.append(script)
        match = re.fullmatch(r"pyweftDesktop\.apply\((.*), (\d+)\)", script, re.S)
        if match:
            self.dom = apply_patches(self.dom, json.loads(match.group(1)))
            self.done = max(self.done, int(match.group(2)))


def text(node):
    if node.get("type") == "text":
        return node["text"]
    return "".join(text(c) for c in node.get("children", []))


@pytest.fixture
def desktop(tmp_path):
    apps = []

    def make(files):
        for name, src in files.items():
            path = tmp_path / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(textwrap.dedent(src), encoding="utf-8")
        window = FakeWindow()
        app = DesktopApp(tmp_path, window)
        app.start()
        apps.append(app)
        first = app.api.mount("/")
        window.dom = first["tree"]
        app.api.mounted()
        return app, window, first

    yield make
    for app in apps:
        app.stop()
    routing.set_host(routing.MemoryHistory())


def flush(app, until=lambda: True, timeout=2.0):
    deadline = time.monotonic() + timeout
    while True:
        app.call(lambda: None)
        if until() or time.monotonic() > deadline:
            return


def buttons(window):
    return [n for n in window.dom[0]["children"] if n.get("tag") == "button"]


def test_mount_then_events_round_trip(desktop):
    app, window, first = desktop({"app.weft": APP})
    assert text(window.dom[0]["children"][0]) == "0 "
    plus = buttons(window)[0]["events"]["click"]
    app.api.dispatch(plus, json.dumps({"type": "click"}), 1)
    app.api.dispatch(plus, json.dumps({"type": "click"}), 2)
    flush(app, lambda: window.done == 2)
    assert text(window.dom[0]["children"][0]) == "2 " and window.done == 2


def test_bind_and_async_handlers_render_when_they_finish(desktop):
    app, window, _ = desktop({"app.weft": APP})
    field = window.dom[0]["children"][-1]
    app.api.dispatch(field["events"]["input"], json.dumps({"value": "hi"}), 1)
    app.api.dispatch(buttons(window)[1]["events"]["click"], "{}", 2)
    flush(app, lambda: text(window.dom[0]["children"][0]) == "10 hi")
    assert text(window.dom[0]["children"][0]) == "10 hi"


def test_a_failing_handler_is_shown_and_the_app_keeps_going(desktop, capsys):
    app, window, _ = desktop({"app.weft": APP})
    app.api.dispatch(buttons(window)[2]["events"]["click"], "{}", 1)
    flush(app, lambda: window.done == 1)
    assert text(window.dom[0]["children"][0]) == "-1 "  # state changed before the raise
    errors = [s for s in window.scripts if s.startswith("pyweftDesktop.error(")]
    assert errors and "ValueError: nope" in errors[0]
    assert "ValueError: nope" in capsys.readouterr().err
    app.api.dispatch(buttons(window)[0]["events"]["click"], "{}", 2)
    flush(app, lambda: window.done == 2)
    assert text(window.dom[0]["children"][0]) == "0 "


def test_focus_requests_follow_the_render(desktop):
    app, window, _ = desktop({"app.weft": APP})
    app.call(lambda: app.renderer.component.focus("field"))
    flush(app, lambda: any("commands" in s for s in window.scripts))
    (cmd,) = [s for s in window.scripts if s.startswith("pyweftDesktop.commands(")]
    assert json.loads(cmd[len("pyweftDesktop.commands(") : -1]) == [{"op": "focus", "path": [0, 4]}]


def test_set_title_names_the_window_and_the_page(desktop):
    app, window, _ = desktop({"app.weft": APP})
    app.call(lambda: __import__("pyweft").set_title("Order #7 - Acme"))
    flush(app, lambda: window.title is not None)
    assert window.title == "Order #7 - Acme"
    assert any(s.startswith("pyweftDesktop.commands(") and "Order #7" in s for s in window.scripts)


def test_pages_navigate_both_ways(desktop):
    app, window, _ = desktop({
        "app.weft": """
            <template><div><Link to="/b">B</Link><Pages /></div></template>
            <code>
            from pyweft import Link, router
            Pages = router("pages")
            </code>
        """,
        "pages/index.weft": "<template><h1>A</h1></template>",
        "pages/b.weft": "<template><h1>B page</h1></template>",
    })
    link = window.dom[0]["children"][0]
    app.api.dispatch(link["events"]["click"], json.dumps({"button": 0}), 1)
    flush(app, lambda: window.done == 1)
    assert 'location.hash = "/b"' in window.scripts
    assert text(window.dom[0]["children"][1]) == "B page"
    app.api.location("/")  # the Back button, through hashchange
    flush(app, lambda: text(window.dom[0]["children"][1]) == "A")
    assert text(window.dom[0]["children"][1]) == "A"


def test_hot_reload_keeps_state(desktop, tmp_path):
    app, window, _ = desktop({"app.weft": APP})
    app.api.dispatch(buttons(window)[0]["events"]["click"], "{}", 1)
    flush(app, lambda: window.done == 1)
    path = tmp_path / "app.weft"
    path.write_text(path.read_text(encoding="utf-8").replace("{{ count }}", "Count {{ count }}"), encoding="utf-8")
    app.call(app.hot_reload)
    assert text(window.dom[0]["children"][0]) == "Count 1 "


def test_the_page_and_its_files(tmp_path):
    (tmp_path / "app.weft").write_text("<template><p>x</p></template>", encoding="utf-8")
    (tmp_path / "styles.css").write_text("p {}", encoding="utf-8")
    (tmp_path / "head.html").write_text('<meta name="x" content="__CSS__">', encoding="utf-8")
    (tmp_path / "secret.py").write_text("TOKEN = 1", encoding="utf-8")
    html = page(tmp_path)
    assert '<link rel="stylesheet" href="app/styles.css" />' in html
    assert 'content="__CSS__"' in html  # the app's text is never a placeholder
    server = make_server(tmp_path)
    import threading

    threading.Thread(target=server.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{server.server_address[1]}"
    try:
        assert b"pyweftDesktop" in urllib.request.urlopen(base + "/").read()
        assert b"PyWeftRuntime" in urllib.request.urlopen(base + "/runtime.js").read()
        assert urllib.request.urlopen(base + "/app/styles.css").read() == b"p {}"
        with pytest.raises(urllib.error.HTTPError):
            urllib.request.urlopen(base + "/app/secret.py")
    finally:
        server.shutdown()
        server.server_close()
