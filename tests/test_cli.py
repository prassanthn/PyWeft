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
    assert (
        '<link rel="stylesheet" href="app/styles.css" data-pyweft-css="styles.css" />'
        in html
    )


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


# ------------------------------------------------------------ loading screen


def test_default_loading_screen_without_file(tmp_path):
    html = render_shell(make_app(tmp_path))
    assert "__PYWEFT_LOADING__" not in html
    assert "pyweft-loader__threads" in html
    assert "data-pyweft-status" in html


def test_custom_loading_screen_replaces_default(tmp_path):
    app = make_app(tmp_path)
    (app / "loading.html").write_text(
        '<div class="mine"><span data-pyweft-status></span></div>', encoding="utf-8"
    )
    html = render_shell(app)
    assert '<div class="mine">' in html
    assert "pyweft-loader__threads" not in html


def test_empty_loading_file_means_no_loading_screen(tmp_path):
    app = make_app(tmp_path)
    (app / "loading.html").write_text("", encoding="utf-8")
    html = render_shell(app)
    assert '<div id="pyweft-loading" role="status" aria-live="polite"></div>' in html


def test_placeholder_text_in_loading_file_is_left_alone(tmp_path):
    app = make_app(tmp_path)
    (app / "loading.html").write_text("<p>__PYWEFT_CSS__</p>", encoding="utf-8")
    assert "<p>__PYWEFT_CSS__</p>" in render_shell(app)


def test_new_scaffolds_editable_copy_of_default(tmp_path):
    from pyweft.cli import _STATIC

    target = tmp_path / "myapp"
    cmd_new(target)
    assert (target / "loading.html").read_text(encoding="utf-8") == (
        _STATIC / "loading.html"
    ).read_text(encoding="utf-8")


def test_build_inlines_custom_loading_screen(tmp_path):
    app = make_app(tmp_path)
    (app / "loading.html").write_text('<div class="mine"></div>', encoding="utf-8")
    out = tmp_path / "dist"
    cmd_build(app, out)
    assert '<div class="mine"></div>' in (out / "index.html").read_text(encoding="utf-8")
    assert not (out / "app" / "loading.html").exists()  # inlined, not shipped


# ------------------------------------------------------- head.html and assets


def test_head_file_goes_into_head_before_app_css(tmp_path):
    app = make_app(tmp_path)
    (app / "head.html").write_text(
        '<script src="https://cdn.example/tw.js"></script>', encoding="utf-8"
    )
    html = render_shell(app)
    head = html[: html.index("</head>")]
    assert head.index("cdn.example/tw.js") < head.index('href="app/styles.css"')


def test_no_head_file_leaves_no_trace(tmp_path):
    html = render_shell(make_app(tmp_path))
    assert "__PYWEFT_HEAD__" not in html


def test_shell_leaves_body_unstyled(tmp_path):
    # CSS frameworks must not have to undo a layout PyWeft imposed.
    html = render_shell(make_app(tmp_path))
    style = html[html.index("<style>") : html.index("</style>")]
    assert "body" not in style


def test_css_linked_from_head_is_not_linked_again(tmp_path):
    app = make_app(tmp_path)
    (app / "tailwind.css").write_text("", encoding="utf-8")
    (app / "head.html").write_text(
        '<link rel="stylesheet" href="app/tailwind.css?x=1">', encoding="utf-8"
    )
    html = render_shell(app)
    assert html.count("app/tailwind.css") == 1
    assert 'data-pyweft-css="styles.css"' in html  # the rest still auto-linked


@pytest.mark.parametrize(
    "head, expected",
    [
        ('<link rel="stylesheet" href="./app/a.css" />', {"a.css"}),
        ('<link href="/app/sub/b.css" rel="preload stylesheet">', {"sub/b.css"}),
        ('<LINK REL="Stylesheet" HREF="app/c.css">', {"c.css"}),
        ('<link rel="stylesheet" href="https://cdn.example/app/x.css">', set()),
        ('<link rel="icon" href="app/d.css">', set()),
        ('<!-- <link rel="stylesheet" href="app/e.css"> -->', set()),
    ],
)
def test_linked_app_css(head, expected):
    from pyweft.cli import linked_app_css

    assert linked_app_css(head) == expected


def test_placeholders_inside_head_file_are_left_alone(tmp_path):
    app = make_app(tmp_path)
    (app / "head.html").write_text("<!-- __PYWEFT_LOADING__ -->", encoding="utf-8")
    (app / "loading.html").write_text("<p>__PYWEFT_HEAD__</p>", encoding="utf-8")
    html = render_shell(app)
    assert "<!-- __PYWEFT_LOADING__ -->" in html
    assert "<p>__PYWEFT_HEAD__</p>" in html


def test_assets_are_not_components_or_auto_linked(tmp_path):
    app = make_app(tmp_path)
    (app / "assets").mkdir()
    (app / "assets" / "icons.css").write_text("", encoding="utf-8")
    (app / "assets" / "x.weft").write_text("<template/>", encoding="utf-8")
    html = render_shell(app)
    assert "icons.css" not in html and "x.weft" not in html


def test_build_copies_assets_and_inlines_head(tmp_path):
    app = make_app(tmp_path)
    (app / "assets" / "fonts").mkdir(parents=True)
    (app / "assets" / "logo.svg").write_text("<svg/>", encoding="utf-8")
    (app / "assets" / "fonts" / "a.woff2").write_bytes(b"\x00\x01")
    (app / "head.html").write_text('<link rel="icon" href="assets/logo.svg">', encoding="utf-8")
    out = tmp_path / "dist"
    cmd_build(app, out)
    assert (out / "assets" / "logo.svg").read_text(encoding="utf-8") == "<svg/>"
    assert (out / "assets" / "fonts" / "a.woff2").read_bytes() == b"\x00\x01"
    assert 'href="assets/logo.svg"' in (out / "index.html").read_text(encoding="utf-8")
    assert not (out / "app" / "head.html").exists()


def test_new_scaffolds_head_file_with_nothing_active(tmp_path):
    target = tmp_path / "myapp"
    cmd_new(target)
    head = (target / "head.html").read_text(encoding="utf-8")
    assert "tailwindcss" in head and "bootstrap" in head
    assert head.strip().startswith("<!--") and head.strip().endswith("-->")
    assert "max-width" in (target / "styles.css").read_text(encoding="utf-8")


# ------------------------------------------------------- the app's .py modules


def add_modules(app):
    files = {
        "helpers.py": "GREETING = 'hi'\n",
        "models/__init__.py": "",
        "models/order.py": "class Order: pass\n",
        "_private/secret.py": "TOKEN = 'x'\n",  # _ folder: never shipped
        "dist/old.py": "",  # build output
        "node_modules/x.py": "",
        "assets/vendored.py": "",  # assets/ is served as-is, not imported
        "build-site.py": "",  # not an identifier: cannot be imported
        "setup.py": "",
        "conftest.py": "",
    }
    for rel, text in files.items():
        path = app / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
    return app


def test_app_python_files_follow_component_folder_rules(tmp_path):
    from pyweft.cli import app_python_files

    app = add_modules(make_app(tmp_path))
    assert app_python_files(app) == ["helpers.py", "models/__init__.py", "models/order.py"]


def test_render_shell_lists_modules_with_components(tmp_path):
    html = render_shell(add_modules(make_app(tmp_path)))
    assert (
        '["app.weft", "widget.weft", "helpers.py", "models/__init__.py", "models/order.py"]'
        in html
    )
    assert "secret.py" not in html


def test_build_copies_modules(tmp_path):
    app = add_modules(make_app(tmp_path))
    out = tmp_path / "site"
    cmd_build(app, out)
    assert (out / "app" / "helpers.py").read_text(encoding="utf-8") == "GREETING = 'hi'\n"
    assert (out / "app" / "models" / "order.py").is_file()
    shipped = {p.relative_to(out / "app").as_posix() for p in (out / "app").rglob("*.py")}
    assert shipped == {"helpers.py", "models/__init__.py", "models/order.py"}


def test_dev_server_serves_modules_and_nothing_else(tmp_path):
    import threading
    import urllib.error
    import urllib.request

    from pyweft.cli import make_dev_server

    app = add_modules(make_app(tmp_path))
    server = make_dev_server(app, 0, poll_interval=0.05)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{server.server_address[1]}"
    try:
        body = urllib.request.urlopen(f"{base}/app/models/order.py", timeout=5).read()
        assert body == (app / "models" / "order.py").read_bytes()
        for bad in ["/app/_private/secret.py", "/app/dist/old.py", "/app/setup.py",
                    "/app/build-site.py", "/app/../helpers.py"]:
            with pytest.raises(urllib.error.HTTPError) as err:
                urllib.request.urlopen(base + bad, timeout=5)
            assert err.value.code == 404, bad
    finally:
        server.shutdown_dev()


def test_snapshot_watches_modules(tmp_path):
    from pyweft.cli import snapshot

    snap = snapshot(add_modules(make_app(tmp_path)))
    assert {"helpers.py", "models/order.py"} <= snap.keys()
    assert "_private/secret.py" not in snap and "setup.py" not in snap


@pytest.mark.parametrize(
    "old, new",
    [
        ({"helpers.py": (1, 1)}, {"helpers.py": (2, 1)}),  # edited
        ({}, {"models/order.py": (1, 1)}),  # added
        ({"helpers.py": (1, 1)}, {}),  # removed
    ],
)
def test_module_change_reloads_the_page(old, new):
    # An imported module stays in sys.modules: hot-swapping the components
    # would keep running the old code, so the page starts over.
    from pyweft.cli import describe_change

    base = {"app.weft": (1, 1)}
    change = describe_change({**base, **old}, {**base, "app.weft": (2, 1), **new})
    assert change["type"] == "reload"
    assert change["reason"] == f"{next(iter(old or new))} changed"


@pytest.mark.parametrize(
    "name, ctype",
    [("a.svg", "image/svg+xml"), ("b.WOFF2", "font/woff2"), ("c.png", "image/png"),
     ("d.js", "text/javascript"), ("e.unknownext", "application/octet-stream")],
)
def test_content_types(name, ctype):
    from pathlib import Path

    from pyweft.cli import content_type

    assert content_type(Path(name)) == ctype
