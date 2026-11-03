"""pyweft build --desktop: what gets bundled, without running PyInstaller
(that takes a minute; it was checked by hand on Windows: Shop.exe)."""

import sys
import textwrap
from pathlib import Path

import pytest

from pyweft import packaging
from pyweft.cli import CliError, main
from pyweft.packaging import _stage, app_file_name, app_imports, code_imports, pyinstaller_args


def write(root, files):
    for name, src in files.items():
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        if isinstance(src, bytes):
            path.write_bytes(src)
        else:
            path.write_text(textwrap.dedent(src), encoding="utf-8")
    return root


APP = {
    "app.weft": """
        <template><p>{{ x }}</p></template>
        <code>
        import csv, io
        from collections import Counter
        from helpers import shout
        from .relative import nothing
        import js  # browser only
        x: int = 0
        </code>
    """,
    "pages/index.weft": "<template><p/></template><code>\nimport decimal\n</code>",
    "helpers.py": "import json\n\ndef shout(s):\n    return s.upper()\n",
    "models/__init__.py": "import fractions\n",
    "styles.css": "p {}",
    "assets/icon.ico": b"\0\0\1\0",
    "head.html": "<meta>",
    "pyproject.toml": '[project]\nname = "x"\n\n[tool.pyweft]\ntitle = "Acme: Orders"\nicon = "assets/icon.ico"\n',
    "notes.txt": "not shipped",
    "dist/old.weft": "<template><p/></template>",
}


def test_imports_in_code_are_found():
    assert code_imports("import a.b, c\nfrom d.e import f\nfrom . import g\nfrom .h import i") == {"a", "c", "d"}
    assert code_imports("def broken(:") == set()


def test_the_apps_imports_come_from_its_code_blocks_and_modules(tmp_path):
    names = app_imports(write(tmp_path, APP))
    assert {"csv", "io", "collections", "decimal", "json", "fractions"} <= names
    # its own modules ship as files; browser-only ones don't exist here
    assert not names & {"helpers", "models", "js", "relative"}


def test_only_shipped_files_are_staged(tmp_path):
    app = write(tmp_path / "app", APP)
    _stage(app, tmp_path / "staged")
    staged = sorted(p.relative_to(tmp_path / "staged").as_posix() for p in (tmp_path / "staged").rglob("*") if p.is_file())
    assert staged == [
        "app.weft", "assets/icon.ico", "head.html", "helpers.py",
        "models/__init__.py", "pages/index.weft", "pyproject.toml", "styles.css",
    ]


@pytest.mark.parametrize("title, name", [("Acme Orders", "Acme Orders"), ('A/B: "C"?', "AB C"), ("...", "app")])
def test_titles_become_file_names(title, name):
    assert app_file_name(title) == name


def test_pyinstaller_is_told_about_everything(tmp_path, monkeypatch):
    app = write(tmp_path / "app", APP)
    monkeypatch.setattr(packaging.sys, "platform", "win32")
    args = pyinstaller_args(app, tmp_path / "out", tmp_path / "work")
    joined = " ".join(args)
    assert args[0].endswith("launch.py") and "--onefile" in args and "--windowed" in args
    assert args[args.index("--name") + 1] == "Acme Orders"
    assert ["--collect-all", "pyweft"] == args[args.index("--collect-all"): args.index("--collect-all") + 2]
    assert "--hidden-import csv" in joined and "--hidden-import decimal" in joined
    assert "--hidden-import helpers" not in joined
    assert args[args.index("--icon") + 1].endswith("icon.ico")
    assert f"{tmp_path / 'work' / 'app'};app" in args


def test_component_libraries_are_collected_whole(tmp_path):
    pytest.importorskip("pyweft_ui")
    app = write(tmp_path / "app", {
        "app.weft": "<template><p/></template><code>\nfrom pyweft_ui import ui\n</code>",
        "pyproject.toml": '[project]\nname = "x"\ndependencies = ["pyweft-ui"]\n',
    })
    args = pyinstaller_args(app, tmp_path / "out", tmp_path / "work")
    assert "pyweft_ui" in [args[i + 1] for i, a in enumerate(args) if a == "--collect-all"]
    # The library's own imports (toaster.weft: asyncio) are found too.
    assert "asyncio" in [args[i + 1] for i, a in enumerate(args) if a == "--hidden-import"]


def test_an_icon_the_platform_cant_use_is_skipped(tmp_path, monkeypatch, capsys):
    app = write(tmp_path / "app", dict(APP, **{
        "pyproject.toml": '[tool.pyweft]\nicon = "assets/icon.png"\n', "assets/icon.png": b"png",
    }))
    monkeypatch.setattr(packaging.sys, "platform", "win32")
    assert "--icon" not in pyinstaller_args(app, tmp_path / "out", tmp_path / "work")
    assert "isn't an .ico file" in capsys.readouterr().out


def test_without_pyinstaller_the_error_says_how_to_get_it(tmp_path, monkeypatch, capsys):
    app = write(tmp_path / "app", APP)
    monkeypatch.setitem(sys.modules, "PyInstaller", None)  # as if not installed
    assert main(["build", str(app), "--desktop"]) == 1
    assert 'uv add --dev "pyweft[package]"' in capsys.readouterr().err


def test_build_runs_pyinstaller_with_the_plan(tmp_path, monkeypatch):
    pytest.importorskip("PyInstaller")
    pytest.importorskip("webview")
    app = write(tmp_path / "app", APP)
    seen = {}

    def fake_run(cmd, cwd):
        seen["cmd"], seen["cwd"] = cmd, Path(cwd)
        seen["launcher"] = (Path(cwd) / "launch.py").read_text(encoding="utf-8")
        seen["staged"] = (Path(cwd) / "app" / "app.weft").is_file()
        return type("Done", (), {"returncode": 0})()

    monkeypatch.setattr(packaging.subprocess, "run", fake_run)
    built = packaging.build_desktop(app, tmp_path / "out")
    assert seen["cmd"][1:3] == ["-m", "PyInstaller"] and seen["staged"]
    assert "run_packaged" in seen["launcher"]
    assert built.parent == tmp_path / "out" and built.stem == "Acme Orders"
    assert not seen["cwd"].exists()  # the work folder is cleaned up
