"""Pre-rendering an app's first screen on the host (pyweft.prerender, and the
CLI that puts it in the page)."""

import re
import subprocess
import sys
import textwrap

import pytest

from pyweft import cli, routing
from pyweft.prerender import prerender, to_html
from pyweft.vdom import Element, Text


@pytest.fixture(autouse=True)
def isolated(monkeypatch):
    # prerender() puts the app folder on sys.path, as the subprocess needs.
    monkeypatch.setattr(sys, "path", list(sys.path))
    yield
    sys.modules.pop("helpers", None)
    routing.set_host(routing.MemoryHistory())


def write(tmp_path, files):
    for name, src in files.items():
        path = tmp_path / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(textwrap.dedent(src), encoding="utf-8")
    return tmp_path


COUNTER = {
    "app.weft": """
        <template>
          <main class="box">
            <h1>Count: {{ count }}</h1>
            <button @click="count += 1">+1</button>
            <p>{{ note }}</p>
          </main>
        </template>
        <code>
        import helpers
        count: int = 3
        note: str = ""
        def on_init(self):
            self.note = helpers.greeting()
        </code>
        <style>h1 { color: teal; }</style>
    """,
    "helpers.py": "def greeting():\n    return 'Hello & <welcome>'\n",
}


def test_html_matches_what_the_runtime_builds():
    nodes = [
        Element("p", {"title": 'a "b" & c', "hidden": ""}, {}, [Text("1 < 2 & 3")], None),
        Element("input", {"value": "x"}, {"input": "h"}, [], None),
        Element("textarea", {"value": "line <1>"}, {}, [], None),
        Element("select", {"value": "b"}, {}, [
            Element("option", {"value": "a"}, {}, [Text("A")], None),
            Element("option", {"value": "b"}, {}, [Text("B")], None),
        ], None),
        Element("script", {}, {}, [Text("alert(1)")], None),
    ]
    assert to_html(nodes) == (
        '<p title="a &quot;b&quot; &amp; c" hidden>1 &lt; 2 &amp; 3</p>'
        '<input value="x">'
        "<textarea>line &lt;1&gt;</textarea>"
        '<select><option value="a">A</option><option value="b" selected>B</option></select>'
    )


def test_first_screen_includes_on_init_app_modules_and_styles(tmp_path):
    result = prerender(write(tmp_path, COUNTER))
    assert "<h1 data-w-app>Count: 3</h1>" in result["html"]
    assert "<p data-w-app>Hello &amp; &lt;welcome&gt;</p>" in result["html"]
    assert "h1[data-w-app]" in result["css"]
    assert result["location"] == ""  # no router: fine at any address


def test_an_app_with_pages_records_where_it_was_rendered(tmp_path):
    app = write(tmp_path, {
        "app.weft": """
            <template><div><Pages /></div></template>
            <code>
            from pyweft import router
            Pages = router("pages")
            </code>
        """,
        "pages/index.weft": "<template><h1>Home</h1></template>",
    })
    result = prerender(app)
    assert "<h1>Home</h1>" in result["html"] and result["location"] == "/"


def test_the_page_carries_the_first_screen(tmp_path):
    page = cli.render_shell(write(tmp_path, COUNTER), prerender=True)
    app = re.search(r'<div id="app"([^>]*)>(.*?)</div>\s*<div id="pyweft-bar">', page, re.S)
    assert app.group(1) == ' data-pyweft-prerendered="" inert'
    assert "Count: 3" in app.group(2)
    assert re.search(r'<style id="pyweft-component-styles">[^<]*h1\[data-w-app\]', page)


def test_app_text_is_never_taken_for_a_placeholder(tmp_path):
    files = dict(COUNTER)
    files["app.weft"] = files["app.weft"].replace("Count:", "__PYWEFT_HEAD__ __PYWEFT_DEV__")
    page = cli.render_shell(write(tmp_path, files), prerender=True)
    assert "__PYWEFT_HEAD__ __PYWEFT_DEV__ 3" in page


def test_an_app_that_cannot_render_here_gets_the_loading_screen(tmp_path, capsys):
    files = dict(COUNTER)
    files["app.weft"] = files["app.weft"].replace("import helpers", "import js  # browser only")
    page = cli.render_shell(write(tmp_path, files), prerender=True)
    assert '<div id="app"></div>' in page and "pyweft-weave" in page
    err = capsys.readouterr().err
    assert "no pre-rendered page" in err and "app.weft, line" in err and "js" in err


def test_rendering_runs_once_per_state_of_the_files(tmp_path, monkeypatch):
    app = write(tmp_path, COUNTER)
    runs = []
    real = subprocess.run

    def counting(*args, **kwargs):
        runs.append(1)
        return real(*args, **kwargs)

    monkeypatch.setattr(cli.subprocess, "run", counting)
    cli.render_shell(app, prerender=True)
    cli.render_shell(app, prerender=True)
    assert len(runs) == 1
    (app / "app.weft").write_text(
        (app / "app.weft").read_text(encoding="utf-8").replace("count: int = 3", "count: int = 4"),
        encoding="utf-8",
    )
    assert "Count: 4" in cli.render_shell(app, prerender=True)
    assert len(runs) == 2


def test_build_prerenders_unless_told_not_to(tmp_path):
    app = write(tmp_path / "app", COUNTER)
    cli.cmd_build(app, tmp_path / "on")
    cli.cmd_build(app, tmp_path / "off", prerender=False)
    assert "Count: 3" in (tmp_path / "on" / "index.html").read_text(encoding="utf-8")
    assert '<div id="app"></div>' in (tmp_path / "off" / "index.html").read_text(encoding="utf-8")
