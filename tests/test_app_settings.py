"""[tool.pyweft] (title, icon) and [tool.pyweft.desktop] (the window) in an
app's pyproject.toml, and set_title() while the app runs."""

import sys
import textwrap
import types
from pathlib import Path

import pytest

from pyweft import Renderer, component_from_source, set_title
from pyweft import cli, desktop
from pyweft.cli import CliError, app_identity, app_settings, render_shell
from pyweft.desktop import window_icon, window_options

SETTINGS = """
[project]
name = "acme"
version = "0.1.0"
dependencies = []

[tool.pyweft]
title = "Acme & Co Orders"   # the app's name
icon = "assets/icon.ico"

[tool.pyweft.desktop]
width = 1280
min_size = [800, 600]
maximized = true
background_color = "#1e293b"
"""


def make_app(tmp_path, pyproject=SETTINGS, icon=True):
    (tmp_path / "app.weft").write_text("<template><p>hi</p></template>", encoding="utf-8")
    (tmp_path / "pyproject.toml").write_text(textwrap.dedent(pyproject), encoding="utf-8")
    if icon:
        (tmp_path / "assets").mkdir(exist_ok=True)
        (tmp_path / "assets" / "icon.ico").write_bytes(b"\0\0\1\0")
    return tmp_path


@pytest.mark.parametrize("parser", ["tomllib", "fallback"])
def test_settings_are_read_with_or_without_tomllib(tmp_path, monkeypatch, parser):
    if parser == "fallback":
        monkeypatch.setattr(cli, "tomllib", None)
    settings = app_settings(make_app(tmp_path))
    assert settings == {
        "title": "Acme & Co Orders",
        "icon": "assets/icon.ico",
        "desktop": {
            "width": 1280,
            "min_size": [800, 600],
            "maximized": True,
            "background_color": "#1e293b",
        },
    }


def test_identity_defaults_to_the_folder_name(tmp_path):
    app = make_app(tmp_path, '[project]\nname = "x"\n', icon=False)
    identity = app_identity(app)
    assert identity.title == tmp_path.name and identity.icon is None


@pytest.mark.parametrize(
    "table, message",
    [
        ('titel = "x"', "no setting 'titel'; the settings are title, icon, desktop"),
        ("title = 3", "title must be text"),
        ('icon = "logo.ico"', "must be a file in the app's assets/ folder"),
        ('icon = "assets/missing.ico"', "must be a file in the app's assets/ folder"),
        ('icon = "assets/../app.weft"', "must be a file in the app's assets/ folder"),
    ],
)
def test_identity_mistakes_are_errors(tmp_path, table, message):
    app = make_app(tmp_path, f"[tool.pyweft]\n{table}\n")
    with pytest.raises(CliError, match=message.replace("(", r"\(")):
        app_identity(app)


def test_the_icon_must_be_an_image(tmp_path):
    app = make_app(tmp_path, '[tool.pyweft]\nicon = "assets/notes.txt"\n')
    (app / "assets" / "notes.txt").write_text("x", encoding="utf-8")
    with pytest.raises(CliError, match=r"must be one of \.ico, \.png, \.svg"):
        app_identity(app)


def test_the_browser_page_gets_the_title_and_favicon(tmp_path):
    page = render_shell(make_app(tmp_path))
    assert '<title data-pyweft-title="Acme &amp; Co Orders">Acme &amp; Co Orders</title>' in page
    assert '<link rel="icon" href="assets/icon.ico" />' in page


def test_a_title_is_never_taken_for_a_placeholder(tmp_path):
    app = make_app(tmp_path, '[tool.pyweft]\ntitle = "__PYWEFT_DEV__"\n', icon=False)
    assert '<title data-pyweft-title="__PYWEFT_DEV__">__PYWEFT_DEV__</title>' in render_shell(app)
    assert "<title>__PYWEFT_DEV__</title>" in desktop.page(app)


def test_window_options_fill_in_defaults(tmp_path):
    assert window_options(make_app(tmp_path)) == {
        "width": 1280,
        "height": 800,
        "min_size": (800, 600),
        "resizable": True,
        "maximized": True,
        "fullscreen": False,
        "on_top": False,
        "frameless": False,
        "background_color": "#1e293b",
    }


@pytest.mark.parametrize(
    "line, message",
    [
        ("size = 3", "no setting 'size'"),
        ("width = true", "width must be a whole number of pixels"),
        ('height = "800"', "height must be a whole number of pixels"),
        ("min_size = [800]", "min_size must be two whole numbers"),
        ("resizable = 1", "resizable must be true or false"),
        ('background_color = "navy"', "background_color must be a colour"),
    ],
)
def test_window_mistakes_are_errors(tmp_path, line, message):
    app = make_app(tmp_path, f"[tool.pyweft.desktop]\n{line}\n", icon=False)
    with pytest.raises(CliError, match=message):
        window_options(app)


@pytest.mark.parametrize(
    "platform, icon, used",
    [("win32", "assets/icon.ico", True), ("win32", "assets/icon.png", False),
     ("linux", "assets/icon.png", True), ("darwin", "assets/icon.ico", False)],
)
def test_window_icons_where_the_platform_takes_them(tmp_path, monkeypatch, platform, icon, used):
    monkeypatch.setattr(desktop.sys, "platform", platform)
    result = window_icon(tmp_path, icon)
    assert (result is not None) == used
    if used:
        assert Path(result) == (tmp_path / icon).resolve()


def test_run_desktop_opens_the_window_it_was_told_to(tmp_path, monkeypatch):
    app = make_app(tmp_path)
    calls = {}
    fake = types.ModuleType("webview")

    class Window:
        def evaluate_js(self, script):
            pass

    def create_window(title, url, **kwargs):
        calls["window"] = (title, url, kwargs)
        return Window()

    fake.create_window = create_window
    fake.start = lambda **kwargs: calls.setdefault("start", kwargs)
    monkeypatch.setitem(sys.modules, "webview", fake)
    monkeypatch.setattr(desktop.sys, "platform", "win32")
    desktop.run_desktop(app)
    title, url, kwargs = calls["window"]
    assert title == "Acme & Co Orders" and url.startswith("http://127.0.0.1:")
    assert kwargs["width"] == 1280 and kwargs["maximized"] is True and "js_api" in kwargs
    assert calls["start"]["icon"].endswith("icon.ico")


def test_set_title_reaches_every_live_page():
    App = component_from_source(
        '<template><button @click="rename()">x</button></template>'
        "<code>\nfrom pyweft import set_title\n"
        "def rename(self):\n    set_title('Order #7 - Acme')\n</code>",
        "App",
    )
    r = Renderer(App())
    tree = r.render()
    r.dispatch(tree[0].events["click"])
    assert r.take_commands() == [{"op": "set_title", "text": "Order #7 - Acme"}]
    calls = []
    r.on_invalidate = lambda: calls.append(1)
    set_title("Elsewhere")  # outside a handler: the host must render and settle
    assert calls and r.take_commands() == [{"op": "set_title", "text": "Elsewhere"}]
