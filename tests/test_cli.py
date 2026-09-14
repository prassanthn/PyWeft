"""The pyweft CLI: dependency parsing, shell generation, scaffold, build."""

import pytest

from pyweft.cli import (
    CliError,
    app_dependencies,
    app_pyweft_files,
    cmd_build,
    cmd_new,
    render_shell,
    pyweft_modules,
)


def make_app(tmp_path, deps='["humanize"]'):
    (tmp_path / "app.weft").write_text(
        "<template><p>hi</p></template><code></code>", encoding="utf-8"
    )
    (tmp_path / "widget.weft").write_text(
        "<template><p>w</p></template><code></code>", encoding="utf-8"
    )
    (tmp_path / "styles.css").write_text("p { color: red }", encoding="utf-8")
    (tmp_path / "pyproject.toml").write_text(
        f'[project]\nname = "x"\nversion = "0.1.0"\ndependencies = {deps}\n',
        encoding="utf-8",
    )
    return tmp_path


def test_dependencies_read_from_pyproject(tmp_path):
    app = make_app(tmp_path, deps='["humanize", "attrs>=23"]')
    assert app_dependencies(app) == ["humanize", "attrs>=23"]


def test_no_pyproject_means_no_packages(tmp_path):
    (tmp_path / "app.weft").write_text("<template><p/></template>", encoding="utf-8")
    assert app_dependencies(tmp_path) == []


def test_app_files_require_root(tmp_path):
    (tmp_path / "other.weft").write_text("<template><p/></template>", encoding="utf-8")
    with pytest.raises(CliError, match="app.weft"):
        app_pyweft_files(tmp_path)


def test_host_modules_not_shipped():
    modules = pyweft_modules()
    assert "cli.py" not in modules and "__main__.py" not in modules
    assert "renderer.py" in modules and "differ.py" in modules


def test_render_shell_fills_placeholders(tmp_path):
    html = render_shell(make_app(tmp_path))
    assert "__PYWEFT_" not in html
    assert '["app.weft", "widget.weft"]' in html
    assert '["humanize"]' in html
    assert '<link rel="stylesheet" href="app/styles.css" />' in html


def test_build_writes_static_site(tmp_path):
    app = make_app(tmp_path)
    out = tmp_path / "dist"
    cmd_build(app, out)
    assert (out / "index.html").is_file()
    assert (out / "runtime.js").is_file()
    assert (out / "pyweft-src" / "renderer.py").is_file()
    assert (out / "app" / "app.weft").is_file()
    assert (out / "app" / "styles.css").is_file()


def test_new_scaffold_builds(tmp_path):
    target = tmp_path / "myapp"
    cmd_new(target)
    assert (target / "app.weft").is_file()
    assert (target / "pyproject.toml").is_file()
    cmd_build(target, target / "dist")  # scaffold must be a valid app
    assert (target / "dist" / "index.html").is_file()


def test_new_refuses_nonempty_dir(tmp_path):
    (tmp_path / "junk.txt").write_text("x", encoding="utf-8")
    with pytest.raises(CliError, match="not empty"):
        cmd_new(tmp_path)
