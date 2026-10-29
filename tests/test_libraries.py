"""Component libraries installed locally are shipped to the browser from the
local environment instead of from PyPI."""

import importlib
import json
import re
import sys
import threading
import urllib.error
import urllib.request

import pytest

from pyweft.cli import (
    app_libraries,
    browser_packages,
    cmd_build,
    find_library,
    make_dev_server,
    render_shell,
    snapshot,
)

APP = "<template><div><ui.Button>Hi</ui.Button></div></template>\n<code>\nfrom kit import ui\n</code>\n"
BUTTON = "<template><button><Slot /></button></template><code></code>"


def write(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


@pytest.fixture
def env(tmp_path, monkeypatch):
    """site/ on sys.path holding `kit` (a component library, installed as
    the distribution kit-ui with a requirement) and `plainlib` (no .weft)."""
    site = tmp_path / "site"
    write(site / "kit" / "__init__.py",
          "from pathlib import Path\nfrom pyweft import ComponentLibrary\n"
          "ui = ComponentLibrary(Path(__file__).parent, prefix='ui')\n")
    write(site / "kit" / "button.weft", BUTTON)
    write(site / "kit" / "theme" / "base.css", ":root { --ui-primary: blue }")
    write(site / "kit" / "__pycache__" / "x.pyc", "junk")
    write(site / "kit" / "notes.txt", "not shipped")
    write(site / "kit_ui-0.1.dist-info" / "METADATA",
          "Metadata-Version: 2.1\nName: kit-ui\nVersion: 0.1\n"
          "Requires-Dist: humanize>=4\nRequires-Dist: pyweft\n"
          "Requires-Dist: pytest ; extra == \"dev\"\n")
    write(site / "kit_ui-0.1.dist-info" / "top_level.txt", "kit\n")
    write(site / "plainlib" / "__init__.py", "")
    monkeypatch.syspath_prepend(str(site))
    forget_kit()
    importlib.invalidate_caches()

    app = tmp_path / "app"
    write(app / "app.weft", APP)
    write(app / "pyproject.toml",
          '[project]\nname = "app"\nversion = "0.1.0"\n'
          'dependencies = ["kit-ui>=0.1", "plainlib", "requests", "pyweft"]\n')
    yield app
    forget_kit()


def forget_kit():
    """An imported `kit` from another test would shadow this one."""
    for name in [m for m in sys.modules if m.split(".")[0] in ("kit", "plainlib")]:
        del sys.modules[name]


def test_library_found_through_its_distribution_name(env):
    lib = find_library("kit-ui")
    assert lib.name == "kit"
    assert lib.files == ["__init__.py", "button.weft", "theme/base.css"]
    assert find_library("plainlib") is None  # no .weft: an ordinary package
    assert find_library("not-installed-anywhere") is None


def test_browser_installs_the_rest_plus_library_requirements(env):
    assert [lib.name for lib in app_libraries(env)] == ["kit"]
    # kit-ui ships locally; pyweft never goes through micropip; the library's
    # own runtime requirement does, its dev extra does not.
    assert browser_packages(env) == ["plainlib", "requests", "humanize>=4"]


def test_shell_lists_library_files(env):
    html = render_shell(env)
    libs = json.loads(re.search(r"const LIBRARIES = (.*);", html).group(1))
    assert libs == [{"name": "kit", "files": ["__init__.py", "button.weft", "theme/base.css"]}]


def test_build_copies_library(env, tmp_path):
    out = tmp_path / "dist"
    cmd_build(env, out)
    assert (out / "lib" / "kit" / "button.weft").read_text(encoding="utf-8") == BUTTON
    assert (out / "lib" / "kit" / "theme" / "base.css").is_file()
    assert not (out / "lib" / "kit" / "notes.txt").exists()


def test_library_edits_reload_the_page(env):
    from pyweft.cli import describe_change

    snap = snapshot(env)
    assert "lib:kit/button.weft" in snap
    change = describe_change(snap, {**snap, "lib:kit/button.weft": (0, 0)})
    assert change == {"type": "reload", "reason": "lib:kit/button.weft changed"}


def test_dev_server_serves_listed_library_files_only(env):
    server = make_dev_server(env, 0, poll_interval=0.05)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{server.server_address[1]}"
    try:
        body = urllib.request.urlopen(f"{base}/lib/kit/button.weft", timeout=5).read()
        assert body.decode() == BUTTON
        for bad in ["/lib/kit/notes.txt", "/lib/kit/../kit/button.weft",
                    "/lib/plainlib/__init__.py", "/lib/kit/__pycache__/x.pyc"]:
            with pytest.raises(urllib.error.HTTPError) as err:
                urllib.request.urlopen(base + bad, timeout=5)
            assert err.value.code == 404, bad
    finally:
        server.shutdown_dev()
