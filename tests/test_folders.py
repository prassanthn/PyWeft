"""Components in subfolders: dotted tags, explicit paths, scopes, CLI shipping."""

import pytest

from pyweft import Renderer, TemplateError, collect_styles, load_component
from pyweft.cli import app_css_files, app_pyweft_files, cmd_build, render_shell
from pyweft.vdom import Element


def write(root, rel, text):
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def leaf(rel_text):
    """A component that renders its own label, to see which file was used."""
    return f"<template><span>{rel_text}</span></template><code></code>"


def text_of(nodes):
    return "".join(
        n.text if not isinstance(n, Element) else text_of(n.children) for n in nodes
    )


def render(path, **kw):
    return text_of(Renderer(load_component(path, **kw)()).render())


# ---------------------------------------------------------------- resolution


def test_dotted_tag_resolves_into_folder(tmp_path):
    write(tmp_path, "app.weft", "<template><div><widgets.Row /></div></template><code></code>")
    write(tmp_path, "widgets/row.weft", leaf("widgets/row"))
    assert render(tmp_path / "app.weft") == "widgets/row"


def test_pascal_case_file_name_also_found(tmp_path):
    write(tmp_path, "app.weft", "<template><div><ui.TextField /></div></template><code></code>")
    write(tmp_path, "ui/TextField.weft", leaf("ui/TextField"))
    assert render(tmp_path / "app.weft") == "ui/TextField"


def test_deeply_nested_folders(tmp_path):
    write(
        tmp_path,
        "app.weft",
        "<template><div><forms.inputs.TextField /></div></template><code></code>",
    )
    write(tmp_path, "forms/inputs/text_field.weft", leaf("forms/inputs/text_field"))
    assert render(tmp_path / "app.weft") == "forms/inputs/text_field"


def test_dotted_tag_in_nested_file_resolves_from_app_root(tmp_path):
    write(tmp_path, "app.weft", "<template><div><forms.Field /></div></template><code></code>")
    write(
        tmp_path,
        "forms/field.weft",
        "<template><p><shared.Icon /></p></template><code></code>",
    )
    write(tmp_path, "shared/icon.weft", leaf("root shared/icon"))
    # a decoy where a folder-relative lookup would wrongly land
    write(tmp_path, "forms/shared/icon.weft", leaf("WRONG forms/shared/icon"))
    assert render(tmp_path / "app.weft") == "root shared/icon"


def test_plain_tag_in_nested_file_resolves_alongside_it(tmp_path):
    write(tmp_path, "app.weft", "<template><div><forms.Field /></div></template><code></code>")
    write(tmp_path, "forms/field.weft", "<template><p><Label /></p></template><code></code>")
    write(tmp_path, "forms/label.weft", leaf("forms/label"))
    write(tmp_path, "label.weft", leaf("WRONG root label"))
    assert render(tmp_path / "app.weft") == "forms/label"


def test_explicit_root_overrides_default(tmp_path):
    write(tmp_path, "pages/home.weft", "<template><div><shared.Nav /></div></template><code></code>")
    write(tmp_path, "shared/nav.weft", leaf("shared/nav"))
    assert render(tmp_path / "pages/home.weft", root=tmp_path) == "shared/nav"


def test_missing_dotted_component_names_the_folder(tmp_path):
    write(tmp_path, "app.weft", "<template><div><widgets.Gone /></div></template><code></code>")
    with pytest.raises(TemplateError, match=r"gone\.weft found in widgets/ under the app root"):
        load_component(tmp_path / "app.weft")


def test_invalid_folder_segment_rejected(tmp_path):
    write(tmp_path, "app.weft", "<template><div><my-widgets.Row /></div></template><code></code>")
    with pytest.raises(TemplateError, match="not a valid folder name"):
        load_component(tmp_path / "app.weft")


def test_lowercase_leaf_is_a_plain_element(tmp_path):
    write(tmp_path, "app.weft", "<template><div><svg.thing /></div></template><code></code>")
    tree = Renderer(load_component(tmp_path / "app.weft")()).render()
    assert tree[0].children[0].tag == "svg.thing"


# ----------------------------------------------------------- explicit paths


def test_explicit_relative_path_resolves_against_declaring_file(tmp_path, monkeypatch):
    write(
        tmp_path,
        "app.weft",
        "<template><div><Row /></div></template>\n<code>\n"
        "from pyweft import load_component\n"
        "components = {'Row': load_component('lib/row.weft')}\n"
        "</code>",
    )
    write(tmp_path, "lib/row.weft", leaf("lib/row"))
    monkeypatch.chdir(tmp_path.parent)  # cwd must not matter
    assert render(tmp_path / "app.weft") == "lib/row"


def test_explicit_load_inherits_app_root(tmp_path):
    write(
        tmp_path,
        "app.weft",
        "<template><div><Row /></div></template>\n<code>\n"
        "from pyweft import load_component\n"
        "components = {'Row': load_component('lib/row.weft')}\n"
        "</code>",
    )
    write(tmp_path, "lib/row.weft", "<template><p><shared.Icon /></p></template><code></code>")
    write(tmp_path, "shared/icon.weft", leaf("root shared/icon"))
    assert render(tmp_path / "app.weft") == "root shared/icon"


def test_cycle_through_explicit_load_detected(tmp_path):
    write(
        tmp_path,
        "a.weft",
        "<template><div><B /></div></template>\n<code>\n"
        "from pyweft import load_component\n"
        "components = {'B': load_component('b.weft')}\n"
        "</code>",
    )
    write(tmp_path, "b.weft", "<template><div><A /></div></template><code></code>")
    with pytest.raises(TemplateError, match="circular"):
        load_component(tmp_path / "a.weft")


# -------------------------------------------------------------------- styles


def test_same_file_name_in_two_folders_gets_two_scopes(tmp_path):
    write(
        tmp_path,
        "app.weft",
        "<template><div><widgets.Row /><forms.Row /></div></template><code></code>",
    )
    styled = "<template><span>x</span></template><style>span { color: red }</style><code></code>"
    write(tmp_path, "widgets/row.weft", styled)
    write(tmp_path, "forms/row.weft", styled.replace("red", "blue"))
    App = load_component(tmp_path / "app.weft")
    widgets, forms = App.components["widgets.Row"], App.components["forms.Row"]
    assert widgets.__scope__ == "widgets-row"
    assert forms.__scope__ == "forms-row"

    tree = Renderer(App()).render()
    spans = tree[0].children
    assert "data-w-widgets-row" in spans[0].attrs
    assert "data-w-forms-row" in spans[1].attrs
    css = collect_styles(App)
    assert "span[data-w-widgets-row]" in css and "span[data-w-forms-row]" in css


def test_top_level_scope_ids_unchanged(tmp_path):
    write(tmp_path, "app.weft", "<template><div><TodoItem /></div></template><code></code>")
    write(
        tmp_path,
        "todo_item.weft",
        "<template><li>x</li></template><style>li { color: red }</style><code></code>",
    )
    App = load_component(tmp_path / "app.weft")
    assert App.components["TodoItem"].__scope__ == "todo_item"


# ----------------------------------------------------------------------- CLI


def make_tree(tmp_path):
    write(tmp_path, "app.weft", "<template><div><widgets.Row /></div></template><code></code>")
    write(tmp_path, "widgets/row.weft", leaf("row"))
    write(tmp_path, "widgets/row.css", "span { color: red }")
    write(tmp_path, "forms/inputs/field.weft", leaf("field"))
    # none of these may ship
    write(tmp_path, ".venv/lib/x.weft", leaf("venv"))
    write(tmp_path, "_drafts/old.weft", leaf("draft"))
    write(tmp_path, "node_modules/pkg/x.weft", leaf("nm"))
    write(tmp_path, "dist/app/app.weft", leaf("dist"))
    write(tmp_path, "site/app/app.weft", leaf("custom build output"))
    (tmp_path / "site" / "pyweft-src").mkdir()
    write(tmp_path, "my-stuff/x.weft", leaf("not reachable by a tag"))
    return tmp_path


def test_cli_collects_nested_files_and_skips_the_rest(tmp_path):
    app = make_tree(tmp_path)
    assert app_pyweft_files(app) == [
        "app.weft",
        "forms/inputs/field.weft",
        "widgets/row.weft",
    ]
    assert app_css_files(app) == ["widgets/row.css"]


def test_shell_lists_nested_files(tmp_path):
    html = render_shell(make_tree(tmp_path))
    assert '"widgets/row.weft"' in html
    assert 'href="app/widgets/row.css"' in html


def test_build_copies_nested_files(tmp_path):
    app = make_tree(tmp_path)
    out = tmp_path.parent / f"{tmp_path.name}-out"
    cmd_build(app, out)
    assert (out / "app" / "widgets" / "row.weft").is_file()
    assert (out / "app" / "forms" / "inputs" / "field.weft").is_file()
    assert (out / "app" / "widgets" / "row.css").is_file()
    assert not (out / "app" / "_drafts").exists()


def test_rebuilding_into_default_dist_does_not_nest_itself(tmp_path):
    app = make_tree(tmp_path)
    cmd_build(app, app / "dist")
    cmd_build(app, app / "dist")
    assert not (app / "dist" / "app" / "dist").exists()
