"""Hot reload: state-preserving class swap, error reporting, the dev server."""

import json
import threading
import time
import urllib.error
import urllib.request

import pytest

from pyweft import Renderer, TemplateError, apply_patches, diff, load_component, to_dicts
from pyweft.cli import describe_change, make_dev_server, render_shell, snapshot
from pyweft.hotreload import classes_by_file, format_error, hot_swap
from pyweft.vdom import Element


def write(root, rel, text):
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def text_of(nodes):
    return "".join(
        n.text if not isinstance(n, Element) else text_of(n.children) for n in nodes
    )


class App:
    """A loaded app plus the host's side of the loop, as the shell runs it."""

    def __init__(self, root):
        self.root = root
        self.cls = load_component(root / "app.weft")
        self.component = self.cls()
        self.component.on_init()
        self.renderer = Renderer(self.component)
        self.tree = self.renderer.render()
        self.settle()

    def settle(self):
        while self.renderer.after_render():
            self.apply(self.renderer.render())

    def apply(self, new_tree):
        ops = diff(self.tree, new_tree)
        assert apply_patches(to_dicts(self.tree), ops) == to_dicts(new_tree)
        self.tree = new_tree
        return ops

    def click(self, path):
        node = self.tree[path[0]]
        for i in path[1:]:
            node = node.children[i]
        self.renderer.dispatch(node.events["click"])
        self.apply(self.renderer.render())
        self.settle()

    def reload(self):
        """What pyweft_hot_reload does after the changed files are written."""
        new_cls = load_component(self.root / "app.weft")
        changed = hot_swap(self.renderer, new_cls)
        self.cls = new_cls
        ops = self.apply(self.renderer.render())
        self.settle()
        return changed, ops

    @property
    def text(self):
        return text_of(self.tree)


COUNTER = """<template>
  <div><b>{{ count }}</b><button @click="count += 1">+</button></div>
</template>
<code>
count: int = 0
</code>
"""


# ------------------------------------------------------------------ the swap


def test_template_edit_keeps_state(tmp_path):
    write(tmp_path, "app.weft", COUNTER)
    app = App(tmp_path)
    app.click([0, 1])
    app.click([0, 1])
    assert app.text == "2+"

    write(tmp_path, "app.weft", COUNTER.replace("<b>{{ count }}</b>", "<i>clicks: {{ count }}</i>"))
    changed, ops = app.reload()
    assert app.text == "clicks: 2+"  # new template, old state
    assert changed == [str((tmp_path / "app.weft").resolve())]
    assert ops  # patched, not remounted
    app.click([0, 1])
    assert app.text == "clicks: 3+"  # handlers bound to the new render


def test_code_edit_takes_effect_and_keeps_state(tmp_path):
    write(tmp_path, "app.weft", COUNTER)
    app = App(tmp_path)
    app.click([0, 1])
    src = COUNTER.replace('@click="count += 1"', '@click="bump"').replace(
        "count: int = 0", "count: int = 0\n\ndef bump(self):\n    self.count += 10"
    )
    write(tmp_path, "app.weft", src)
    app.reload()
    app.click([0, 1])
    assert app.text == "11+"


def test_new_fields_get_defaults_and_mutable_ones_are_copied(tmp_path):
    write(tmp_path, "app.weft", COUNTER)
    app = App(tmp_path)
    app.click([0, 1])
    src = COUNTER.replace(
        "<b>{{ count }}</b>", "<b>{{ count }} {{ label }} {{ len(tags) }}</b>"
    ).replace("count: int = 0", 'count: int = 0\nlabel: str = "new"\ntags: list = []')
    write(tmp_path, "app.weft", src)
    app.reload()
    assert app.text == "1 new 0+"
    app.component.tags.append("x")
    assert app.cls.tags == []  # the class default was not mutated


def test_child_state_survives_edit_of_child(tmp_path):
    write(tmp_path, "app.weft", "<template><div><Counter /><Counter /></div></template><code></code>")
    write(tmp_path, "counter.weft", COUNTER)
    app = App(tmp_path)
    app.click([0, 0, 1])  # first child only
    assert app.text == "1+0+"

    write(tmp_path, "counter.weft", COUNTER.replace("{{ count }}", "[{{ count }}]"))
    app.reload()
    assert app.text == "[1]+[0]+"
    kids = list(app.renderer.instances.values())
    assert all(type(k) is app.cls.components["Counter"] for k in kids)


def test_child_state_survives_edit_of_parent(tmp_path):
    write(tmp_path, "app.weft", "<template><div><Counter /></div></template><code></code>")
    write(tmp_path, "counter.weft", COUNTER)
    app = App(tmp_path)
    app.click([0, 0, 1])
    write(tmp_path, "app.weft", "<template><div><Counter /><p>Hi</p></div></template><code></code>")
    app.reload()
    assert app.text == "1+Hi"


def test_moved_child_keeps_state_only_with_a_key(tmp_path):
    # Unkeyed children are identified by position, so inserting before one
    # gives a fresh child -- the same rule as any re-render. A key keeps it.
    write(tmp_path, "app.weft", "<template><div><Counter key=\"'c'\" /></div></template><code></code>")
    write(tmp_path, "counter.weft", COUNTER)
    app = App(tmp_path)
    app.click([0, 0, 1])
    write(
        tmp_path,
        "app.weft",
        "<template><div><h1>Hi</h1><Counter key=\"'c'\" /></div></template><code></code>",
    )
    app.reload()
    assert app.text == "Hi1+"


def test_one_class_per_file_even_when_used_twice(tmp_path):
    write(tmp_path, "app.weft", "<template><div><A /><B /></div></template><code></code>")
    write(tmp_path, "a.weft", "<template><p><Shared /></p></template><code></code>")
    write(tmp_path, "b.weft", "<template><p><Shared /></p></template><code></code>")
    write(tmp_path, "shared.weft", "<template><i>s</i></template><code></code>")
    App_ = load_component(tmp_path / "app.weft")
    assert App_.components["A"].components["Shared"] is App_.components["B"].components["Shared"]
    assert len(classes_by_file(App_)) == 4


EFFECT_APP = """<template><p>{{ n }}</p></template>
<code>
from pyweft import effect

n: int = 0
log: list = []

@effect
def watch(self):
    self.log.append("MARK {}".format(self.n))
    return lambda: self.log.append("stop")
</code>
"""


def test_edited_component_reruns_effects_after_cleanup(tmp_path):
    write(tmp_path, "app.weft", EFFECT_APP)
    app = App(tmp_path)
    assert app.component.log == ["MARK 0"]
    write(tmp_path, "app.weft", EFFECT_APP.replace("MARK", "EDITED"))
    app.reload()
    assert app.component.log == ["MARK 0", "stop", "EDITED 0"]


def test_unchanged_component_keeps_effects(tmp_path):
    write(tmp_path, "app.weft", "<template><div><h1>a</h1><Fx /></div></template><code></code>")
    write(tmp_path, "fx.weft", EFFECT_APP)
    app = App(tmp_path)
    child = next(iter(app.renderer.instances.values()))
    write(tmp_path, "app.weft", "<template><div><h1>b</h1><Fx /></div></template><code></code>")
    changed, _ = app.reload()
    assert changed == [str((tmp_path / "app.weft").resolve())]
    assert child.log == ["MARK 0"]  # not cleaned up, not re-run


def test_on_init_does_not_run_again(tmp_path):
    src = COUNTER.replace("count: int = 0", "count: int = 0\ninits: int = 0\n\ndef on_init(self):\n    self.inits += 1")
    write(tmp_path, "app.weft", src)
    app = App(tmp_path)
    write(tmp_path, "app.weft", src.replace("<b>", "<b>!"))
    app.reload()
    assert app.component.inits == 1


# -------------------------------------------------------------------- errors


def test_broken_file_leaves_running_app_untouched(tmp_path):
    write(tmp_path, "app.weft", COUNTER)
    app = App(tmp_path)
    app.click([0, 1])
    write(tmp_path, "app.weft", COUNTER.replace("</div>", ""))  # malformed XML
    with pytest.raises(TemplateError, match=r"^app\.weft: template is not well-formed"):
        load_component(tmp_path / "app.weft")
    app.click([0, 1])  # the old version still works
    assert app.text == "2+"


def test_failed_render_keeps_old_handlers(tmp_path):
    write(tmp_path, "app.weft", COUNTER)
    app = App(tmp_path)
    write(tmp_path, "app.weft", COUNTER.replace("{{ count }}", "{{ missing }}"))
    new_cls = load_component(tmp_path / "app.weft")
    hot_swap(app.renderer, new_cls)
    with pytest.raises(Exception):
        app.renderer.render()
    handler = app.tree[0].children[1].events["click"]
    assert handler in app.renderer.handlers  # the page on screen still responds


def test_syntax_error_reports_weft_line(tmp_path):
    write(tmp_path, "app.weft", COUNTER.replace("count: int = 0", "count: int = = 0"))
    with pytest.raises(SyntaxError) as info:
        load_component(tmp_path / "app.weft")
    message = format_error(info.value)
    assert "app.weft, line 5" in message  # line in the file, not the block
    assert message.endswith("SyntaxError: invalid syntax") or "SyntaxError:" in message


def test_runtime_error_reports_weft_frame(tmp_path):
    src = COUNTER.replace('@click="count += 1"', '@click="boom"').replace(
        "count: int = 0", "count: int = 0\n\ndef boom(self):\n    return 1 / 0"
    )
    write(tmp_path, "app.weft", src)
    app = App(tmp_path)
    with pytest.raises(ZeroDivisionError) as info:
        app.renderer.dispatch(app.tree[0].children[1].events["click"])
    message = format_error(info.value)
    assert "app.weft, line 8: return 1 / 0" in message
    assert message.splitlines()[-1] == "ZeroDivisionError: division by zero"


# ---------------------------------------------------------- change detection


def test_describe_change_classifies():
    old = {"app.weft": (1, 1), "styles.css": (1, 1), "gone.weft": (1, 1)}
    new = {"app.weft": (2, 1), "styles.css": (1, 1), "new.css": (1, 1)}
    assert describe_change(old, new) == {
        "type": "update",
        "weft": ["app.weft"],
        "weft_removed": ["gone.weft"],
        "css": ["new.css"],
        "css_removed": [],
    }
    assert describe_change(old, old) is None


@pytest.mark.parametrize(
    "key",
    ["pyproject.toml", "loading.html", "head.html", "pyweft:renderer.py", "assets/logo.svg",
     "assets/vendor.css"],
)
def test_startup_framework_and_asset_files_reload(key):
    change = describe_change({key: (1, 1)}, {key: (2, 1)})
    assert change["type"] == "reload"


def test_new_asset_reloads():
    change = describe_change({}, {"assets/new.png": (1, 1)})
    assert change == {"type": "reload", "reason": "assets/new.png changed"}


def test_snapshot_sees_app_and_framework(tmp_path):
    write(tmp_path, "app.weft", COUNTER)
    write(tmp_path, "widgets/row.weft", COUNTER)
    write(tmp_path, "pyproject.toml", "[project]\n")
    write(tmp_path, "head.html", "")
    write(tmp_path, "assets/img/logo.svg", "<svg/>")
    snap = snapshot(tmp_path)
    assert {"app.weft", "widgets/row.weft", "pyproject.toml", "head.html"} <= snap.keys()
    assert "assets/img/logo.svg" in snap
    assert "pyweft:renderer.py" in snap and "pyweft:shell.html" in snap


def test_dev_flag_only_in_run_pages(tmp_path):
    write(tmp_path, "app.weft", COUNTER)
    assert "const DEV = true;" in render_shell(tmp_path, dev=True)
    assert "const DEV = false;" in render_shell(tmp_path)


# ----------------------------------------------------------- the dev server


def read_events(response, count, timeout=5.0):
    events, deadline = [], time.monotonic() + timeout
    while len(events) < count and time.monotonic() < deadline:
        line = response.readline().decode()
        if line.startswith("data: "):
            events.append(json.loads(line[6:]))
    return events


def test_dev_server_streams_changes(tmp_path):
    write(tmp_path, "app.weft", COUNTER)
    server = make_dev_server(tmp_path, 0, poll_interval=0.05)
    port = server.server_address[1]
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        page = urllib.request.urlopen(f"http://127.0.0.1:{port}/", timeout=5).read()
        assert b"const DEV = true;" in page

        stream = urllib.request.urlopen(f"http://127.0.0.1:{port}/__pyweft/events", timeout=5)
        (hello,) = read_events(stream, 1)
        assert hello["type"] == "hello" and hello["server"]

        time.sleep(0.1)
        write(tmp_path, "app.weft", COUNTER.replace("<b>", "<em>").replace("</b>", "</em>"))
        (update,) = read_events(stream, 1)
        assert update == {
            "type": "update",
            "weft": ["app.weft"],
            "weft_removed": [],
            "css": [],
            "css_removed": [],
        }

        write(tmp_path, "pyproject.toml", "[project]\ndependencies = []\n")
        (reload,) = read_events(stream, 1)
        assert reload == {"type": "reload", "reason": "pyproject.toml changed"}
        stream.close()
    finally:
        server.shutdown_dev()


def test_dev_server_serves_assets_and_nothing_outside(tmp_path):
    write(tmp_path, "app.weft", COUNTER)
    write(tmp_path, "assets/logo.svg", "<svg/>")
    write(tmp_path, "assets/my fonts/a.woff2", "font")
    write(tmp_path, "secret.txt", "no")
    server = make_dev_server(tmp_path, 0, poll_interval=0.05)
    port = server.server_address[1]
    threading.Thread(target=server.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{port}"
    try:
        svg = urllib.request.urlopen(f"{base}/assets/logo.svg", timeout=5)
        assert svg.read() == b"<svg/>"
        assert svg.headers["Content-Type"].startswith("image/svg+xml")
        font = urllib.request.urlopen(f"{base}/assets/my%20fonts/a.woff2", timeout=5)
        assert font.headers["Content-Type"] == "font/woff2"  # binary: no charset

        for bad in ["/assets/../secret.txt", "/assets/%2e%2e/secret.txt",
                    "/assets/..%2fsecret.txt", "/assets/", "/assets/missing.png",
                    "/app/secret.txt"]:
            with pytest.raises(urllib.error.HTTPError) as err:
                urllib.request.urlopen(base + bad, timeout=5)
            assert err.value.code == 404, bad
    finally:
        server.shutdown_dev()


def test_saves_made_while_the_page_loads_are_replayed(tmp_path):
    write(tmp_path, "app.weft", COUNTER)
    server = make_dev_server(tmp_path, 0, poll_interval=0.05)
    port = server.server_address[1]
    threading.Thread(target=server.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{port}"
    try:
        page = urllib.request.urlopen(f"{base}/", timeout=5).read()
        assert b"const SINCE = 0;" in page

        # Saved after the page was served, before it connected for changes.
        write(tmp_path, "styles.css", "p { color: red }")
        deadline = time.monotonic() + 5
        while not server.feed.events and time.monotonic() < deadline:
            time.sleep(0.02)
        assert server.feed.events

        stream = urllib.request.urlopen(f"{base}/__pyweft/events?since=0", timeout=5)
        hello, missed = read_events(stream, 2)
        assert hello["type"] == "hello" and missed["css"] == ["styles.css"]
        stream.close()

        # A reconnecting browser sends the last id it saw: nothing is replayed.
        request = urllib.request.Request(
            f"{base}/__pyweft/events?since=0", headers={"Last-Event-ID": "1"}
        )
        stream = urllib.request.urlopen(request, timeout=5)
        read_events(stream, 1)  # hello
        write(tmp_path, "styles.css", "p { color: blue }")
        lines = []
        while not any(line.startswith("data: ") for line in lines):
            lines.append(stream.readline().decode())
        assert "id: 2\n" in lines and json.loads(lines[-1][6:])["css"] == ["styles.css"]
        stream.close()

        assert b"const SINCE = 2;" in urllib.request.urlopen(f"{base}/", timeout=5).read()
    finally:
        server.shutdown_dev()


def test_second_dev_server_on_a_busy_port_is_refused(tmp_path):
    # On Windows a plain HTTPServer would bind anyway and share the port.
    write(tmp_path, "app.weft", COUNTER)
    first = make_dev_server(tmp_path, 0, poll_interval=0.05)
    threading.Thread(target=first.serve_forever, daemon=True).start()
    try:
        port = first.server_address[1]
        with pytest.raises(OSError):
            make_dev_server(tmp_path, port, poll_interval=0.05)
    finally:
        first.shutdown_dev()


def test_run_on_a_busy_port_explains_itself(tmp_path, capsys):
    from pyweft.cli import main

    write(tmp_path, "app.weft", COUNTER)
    first = make_dev_server(tmp_path, 0, poll_interval=0.05)
    threading.Thread(target=first.serve_forever, daemon=True).start()
    try:
        port = first.server_address[1]
        assert main(["run", str(tmp_path), "--port", str(port)]) == 1
        assert "another `pyweft run`" in capsys.readouterr().err
    finally:
        first.shutdown_dev()


def test_unfilled_placeholder_is_an_error_not_a_broken_page(tmp_path, monkeypatch):
    import pyweft.cli as cli

    write(tmp_path, "app.weft", COUNTER)
    static = tmp_path / "static"
    write(static, "shell.html", "<script>const X = __PYWEFT_FROM_THE_FUTURE__;</script>")
    write(static, "loading.html", "")
    monkeypatch.setattr(cli, "_STATIC", static)
    with pytest.raises(cli.CliError, match="Restart `pyweft run`"):
        cli.render_shell(tmp_path, dev=True)


def test_changed_server_code_tells_pages_to_restart_instead_of_reloading(tmp_path, monkeypatch):
    import pyweft.cli as cli

    write(tmp_path, "app.weft", COUNTER)
    edited = threading.Event()
    real_snapshot = cli.snapshot

    def snapshot(app_dir):
        snap = real_snapshot(app_dir)
        if edited.is_set():  # as if cli.py were saved while the server runs
            snap["pyweft:cli.py"] = (0, 0)
        return snap

    monkeypatch.setattr(cli, "snapshot", snapshot)
    server = make_dev_server(tmp_path, 0, poll_interval=0.05)
    port = server.server_address[1]
    threading.Thread(target=server.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{port}/__pyweft/events"
    try:
        stream = urllib.request.urlopen(base, timeout=5)
        (hello,) = read_events(stream, 1)
        assert hello["stale"] is False
        edited.set()
        (event,) = read_events(stream, 1)
        assert event["type"] == "stale" and "Restart `pyweft run`" in event["reason"]
        stream.close()

        late = urllib.request.urlopen(base, timeout=5)  # a page opened afterwards
        (hello,) = read_events(late, 1)
        assert hello["stale"] is True
        late.close()
    finally:
        server.shutdown_dev()
