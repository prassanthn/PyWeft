"""Will an app's dependencies install in the browser? Checked against a
small stand-in PyPI and Pyodide package list."""

import re
import textwrap
from pathlib import Path

import pytest

from pyweft import browser_deps as bd
from pyweft.check import check_app
from pyweft.cli import main

SNAPSHOT = {
    "pyodide": "0.26.4",
    "python": "3.12.1",
    "packages": {"pydantic": "2.7.0", "pydantic-core": "2.18.1", "typing-extensions": "4.11.0", "numpy": "1.26.4"},
}


def wheel(name, version, native=False):
    tag = "cp312-cp312-manylinux_2_17_x86_64" if native else "py3-none-any"
    return {"filename": f"{name}-{version}-{tag}.whl", "yanked": False, "requires_python": ">=3.8"}


PYPI = {
    "pure": {"1.0": [wheel("pure", "1.0")], "2.0": [wheel("pure", "2.0")], "3.0b1": [wheel("pure", "3.0b1")]},
    "needs-native": {"1.0": [wheel("needs_native", "1.0")]},
    "native": {"1.0": [wheel("native", "1.0", native=True)]},
    "source-only": {"1.0": [{"filename": "source-only-1.0.tar.gz", "yanked": False}]},
    "wants-new-pydantic": {"1.0": [wheel("wants_new_pydantic", "1.0")]},
    "old-python": {"1.0": [dict(wheel("old_python", "1.0"), requires_python="<3.9")]},
    "with-extras": {"1.0": [wheel("with_extras", "1.0")]},
    "a": {"1.0": [wheel("a", "1.0")]},
    "b": {"1.0": [wheel("b", "1.0")]},
}
REQUIRES = {
    ("pure", "2.0"): ["typing-extensions>=4", "windows-only; sys_platform == 'win32'"],
    ("needs-native", "1.0"): ["native>=1"],
    ("wants-new-pydantic", "1.0"): ["pydantic>=2.7.4,<3"],
    ("with-extras", "1.0"): ["pure", "native; extra == 'fast'"],
    ("a", "1.0"): ["pure>=2"],
    ("b", "1.0"): ["pure<2"],
}


def fake_pypi(url):
    m = re.match(r"https://pypi.org/pypi/([^/]+)/(?:([^/]+)/)?json", url)
    name, version = m.group(1), m.group(2)
    if name not in PYPI:
        return None
    if version:
        return {"info": {"requires_dist": REQUIRES.get((name, version), [])}}
    return {"releases": PYPI[name]}


def findings(*requirements):
    return [(f.root, f.code) for f in bd.check(list(requirements), fetch=fake_pypi, snapshot=SNAPSHOT)]


def test_pure_wheels_and_built_in_packages_install():
    assert findings("pure", "pydantic>=2", "numpy") == []
    assert findings("pure>=1,<2") == []
    assert findings("pure==3.0b1") == []                 # a pre-release named outright


def test_what_cannot_install():
    assert findings("native") == [("native", "dependency-native")]
    assert findings("needs-native") == [("needs-native", "dependency-native")]   # found through a dependency
    assert findings("source-only") == [("source-only", "dependency-native")]
    assert findings("pydantic>=2.8") == [("pydantic", "dependency-version")]
    assert findings("wants-new-pydantic") == [("wants-new-pydantic", "dependency-version")]
    assert findings("old-python") == [("old-python", "dependency-version")]
    assert findings("nowhere") == [("nowhere", "dependency-missing")]
    assert findings("pure>=5") == [("pure", "dependency-version")]


def test_messages_name_the_culprit_and_why():
    (f,) = bd.check(["needs-native"], fetch=fake_pypi, snapshot=SNAPSHOT)
    assert f.message.startswith("'native' (needed by needs-native) has native code")
    (f,) = bd.check(["wants-new-pydantic"], fetch=fake_pypi, snapshot=SNAPSHOT)
    assert "the browser has pydantic 2.7.0, built into Pyodide 0.26.4" in f.message


def test_markers_extras_and_conflicts():
    assert findings("with-extras") == []                  # the extra isn't asked for
    assert findings("with-extras[fast]") == [("with-extras", "dependency-native")]
    assert findings("a", "b") == [("b", "dependency-conflict")]


def test_no_network_is_a_warning_not_an_error():
    def down(url):
        raise OSError("no route")

    (f,) = bd.check(["pure"], fetch=down, snapshot=SNAPSHOT)
    assert (f.severity, f.code) == ("warning", "dependencies-unchecked") and "no route" in f.message


@pytest.mark.parametrize("version, spec, ok", [
    ("2.7.0", ">=2.7.4,<3", False), ("2.7.4", ">=2.7.4,<3", True), ("3.0", "<3", False),
    ("1.4.2", "~=1.4", True), ("2.0", "~=1.4", False), ("1.4.9", "~=1.4.2", True), ("1.5.0", "~=1.4.2", False),
    ("2.0.5", "==2.0.*", True), ("2.1", "==2.0.*", False), ("2.1", "!=2.0.*", True),
    ("1.0rc1", ">=0.9", False), ("1.0", ">=1.0rc1", True), ("1.0.post1", ">1.0", True),
    ("1.0", "==1.0.0", True), ("1.0.dev1", "<1.0", False), ("2026.10.19", ">=2026.10.19", True),
])
def test_specifiers(version, spec, ok):
    assert bd.satisfies(version, spec) is ok


@pytest.mark.parametrize("marker, extras, holds", [
    ('python_version >= "3.8"', (), True),
    ('python_version < "3.11"', (), False),
    ('sys_platform == "emscripten" and platform_machine == "wasm32"', (), True),
    ('sys_platform == "win32" or sys_platform == "darwin"', (), False),
    ('platform_python_implementation != "PyPy"', (), True),
    ('(python_version >= "3.10") and (extra == "dev")', (), False),
    ('(python_version >= "3.10") and (extra == "dev")', ("dev",), True),
    ('"linux" in sys_platform', (), False),
    ('python_full_version >= "3.12.1"', (), True),
])
def test_markers(marker, extras, holds):
    env = bd.browser_environment("3.12.1")
    assert bd.marker_holds(marker, env, frozenset(extras)) is holds


def test_the_snapshot_is_for_the_pyodide_the_shell_loads():
    shell = (Path(bd.__file__).parent / "static" / "shell.html").read_text(encoding="utf-8")
    version = re.search(r"pyodide/v([\d.]+)/full/pyodide\.js", shell).group(1)
    data = bd.pyodide_packages()
    assert data["pyodide"] == version, "run: uv run python scripts/update_pyodide_packages.py"
    assert data["packages"]["pydantic"] and data["python"].startswith("3.")


def test_pyweft_check_points_at_the_pyproject_line(tmp_path, capsys):
    (tmp_path / "app.weft").write_text("<template><p>hi</p></template>", encoding="utf-8")
    (tmp_path / "pyproject.toml").write_text(textwrap.dedent('''
        [project]
        name = "demo"
        dependencies = [
            "pure>=1",
            "needs-native",
            "pydantic >= 2",
        ]
    ''').lstrip(), encoding="utf-8")
    problems, files = check_app(tmp_path, fetch=fake_pypi)
    assert [(p.file, p.line, p.severity, p.code) for p in problems] == [
        ("pyproject.toml", 5, "error", "dependency-native")]
    assert problems[0].message.startswith("in the browser: 'native' (needed by needs-native)")
    assert problems[0].message.endswith("(the desktop app isn't affected)")
    assert check_app(tmp_path, deps=False)[0] == []
    # The CLI: without a fetch of its own it goes to PyPI, which tests turn off.
    assert main(["check", str(tmp_path)]) == 0
    assert "couldn't reach PyPI" in capsys.readouterr().out
    assert main(["check", str(tmp_path), "--no-deps"]) == 0
