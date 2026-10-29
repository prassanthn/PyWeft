"""pyweft-ui controls, rendered headless: props, @bind, events, slots."""

import textwrap

import pytest

from pyweft import (
    Renderer,
    TemplateError,
    apply_patches,
    collect_styles,
    diff,
    load_component,
    to_dicts,
)
from pyweft.vdom import Element


def app(tmp_path, template, code=""):
    """Load an app that imports the toolkit, as a real app file would."""
    src = (
        f"<template>{textwrap.dedent(template)}</template>\n"
        f"<code>\nfrom pyweft_ui import ui\n{textwrap.dedent(code)}\n</code>\n"
    )
    path = tmp_path / "app.weft"
    path.write_text(src, encoding="utf-8")
    App = load_component(path)
    instance = App()
    renderer = Renderer(instance)
    renderer.init_root()
    return App, instance, renderer, renderer.render()


def find(nodes, test):
    for node in nodes:
        if isinstance(node, Element):
            if test(node):
                return node
            hit = find(node.children, test)
            if hit is not None:
                return hit
    return None


def tag(name):
    return lambda n: n.tag == name


def cls(name):
    return lambda n: name in n.attrs.get("class", "").split()


def text(nodes):
    return "".join(
        text(n.children) if isinstance(n, Element) else n.text for n in nodes
    )


def cycle(renderer, old):
    new = renderer.render()
    assert apply_patches(to_dicts(old), diff(old, new)) == to_dicts(new)
    return new


# ------------------------------------------------------------------ fields


def test_text_field_binds_and_shows_error(tmp_path):
    _, a, r, tree = app(
        tmp_path,
        '<div><ui.TextField label="Name" required="true" @bind="name" :error="err" @enter="submitted.append(name)" /></div>',
        'name: str = "ada"\nerr: str = ""\nsubmitted: list = []',
    )
    field = find(tree, tag("input"))
    assert field.attrs["value"] == "ada" and "required" in field.attrs
    assert text([find(tree, cls("label"))]).strip() == "Name *"
    r.dispatch(field.events["input"], {"value": "grace"})
    r.dispatch(field.events["keydown.enter"], {"key": "Enter"})
    assert a.name == "grace" and a.submitted == ["grace"]
    a.err = "Too short"
    tree = cycle(r, tree)
    assert find(tree, tag("input")).attrs["aria-invalid"] == "true"
    assert text([find(tree, cls("error"))]) == "Too short"


@pytest.mark.parametrize(
    "start, typed, expected",
    [("0", "12", 12), ("0", "2.5", 2.5), ("1.5", "3", 3.0), ("None", "7", 7), ("4", "", 4), ("4", "-", 4)],
)
def test_number_field_emits_numbers(tmp_path, start, typed, expected):
    _, a, r, tree = app(
        tmp_path,
        '<div><ui.NumberField label="Qty" min="1" @bind="qty" /></div>',
        f"qty = {start}",
    )
    field = find(tree, tag("input"))
    assert field.attrs["min"] == "1.0" and "max" not in field.attrs
    r.dispatch(field.events["input"], {"value": typed})
    assert a.qty == expected and type(a.qty) is type(expected)


def test_select_with_typed_options(tmp_path):
    _, a, r, tree = app(
        tmp_path,
        '<div><ui.Select label="Size" placeholder="Pick one" :options="[(1, \'Small\'), (2, \'Large\')]" @bind="size" /></div>',
        "size = None",
    )
    select = find(tree, tag("select"))
    assert select.attrs["value"] == ""
    assert [text([o]) for o in select.children] == ["Pick one", "Small", "Large"]
    r.dispatch(select.events["change"], {"value": "2"})
    assert a.size == 2
    assert find(cycle(r, tree), tag("select")).attrs["value"] == "2"


def test_select_options_from_a_comma_string(tmp_path):
    _, a, r, tree = app(tmp_path, '<div><ui.Select options="S, M, L" @bind="size" /></div>', 'size = "M"')
    select = find(tree, tag("select"))
    assert [o.attrs["value"] for o in select.children] == ["S", "M", "L"]
    assert select.attrs["value"] == "M"


def test_radio_group_binds_typed_value(tmp_path):
    _, a, r, tree = app(
        tmp_path,
        '<div><ui.RadioGroup label="Plan" inline="true" :options="[{\'value\': 1, \'label\': \'Free\'}, {\'value\': 2, \'label\': \'Pro\'}]" @bind="plan" /></div>',
        "plan = 2",
    )
    radios = [n for n in _walk(tree) if n.tag == "input"]
    assert [("checked" in r_.attrs) for r_ in radios] == [False, True]
    assert radios[0].attrs["name"] == radios[1].attrs["name"]
    r.dispatch(radios[0].events["change"], {"value": "1", "checked": True})
    assert a.plan == 1
    radios = [n for n in _walk(cycle(r, tree)) if n.tag == "input"]
    assert [("checked" in r_.attrs) for r_ in radios] == [True, False]


def test_two_radio_groups_get_different_names(tmp_path):
    _, a, r, tree = app(
        tmp_path,
        '<div><ui.RadioGroup options="a, b" @bind="x" /><ui.RadioGroup options="a, b" @bind="y" /></div>',
        'x = "a"\ny = "b"',
    )
    names = {n.attrs["name"] for n in _walk(tree) if n.tag == "input"}
    assert len(names) == 2


@pytest.mark.parametrize("control", ["Checkbox", "Switch"])
def test_checkbox_and_switch(tmp_path, control):
    _, a, r, tree = app(tmp_path, f'<div><ui.{control} label="On" @bind="on" /></div>', "on: bool = False")
    box = find(tree, tag("input"))
    assert "checked" not in box.attrs
    r.dispatch(box.events["change"], {"checked": True})
    assert a.on is True
    assert "checked" in find(cycle(r, tree), tag("input")).attrs


# ------------------------------------------------------------ buttons etc.


def test_button_variants_click_and_loading(tmp_path):
    _, a, r, tree = app(
        tmp_path,
        '<div><ui.Button variant="primary" icon="send" class="wide" @click="clicks += 1">Send</ui.Button>'
        '<ui.Button :loading="True">Wait</ui.Button></div>',
        "clicks: int = 0",
    )
    send, wait = tree[0].children
    assert send.attrs["class"] == "btn btn-primary btn-md wide"
    assert send.attrs["type"] == "button" and "disabled" not in send.attrs
    assert find([send], tag("svg")) is not None and text([send]).strip() == "Send"
    r.dispatch(send.events["click"], {"type": "click"})
    assert a.clicks == 1
    assert "disabled" in wait.attrs and wait.attrs["aria-busy"] == "true"
    assert find([wait], cls("spinner")) is not None


def test_bool_and_int_props_from_plain_attributes(tmp_path):
    _, a, r, tree = app(
        tmp_path,
        '<div><ui.Button disabled="true">a</ui.Button><ui.Button disabled="false">b</ui.Button>'
        '<ui.Grid cols="3"><p>x</p></ui.Grid><ui.Row wrap="false" gap="xl" justify="between"><p>y</p></ui.Row></div>',
    )
    a_btn, b_btn, grid, row = tree[0].children
    assert "disabled" in a_btn.attrs and "disabled" not in b_btn.attrs
    assert grid.attrs["style"].startswith("grid-template-columns: repeat(3, minmax(0, 1fr))")
    assert "flex-wrap: nowrap" in row.attrs["style"] and "gap: 32px" in row.attrs["style"]
    assert "justify-content: space-between" in row.attrs["style"]


def test_bad_prop_value_is_a_template_error(tmp_path):
    with pytest.raises(TemplateError, match=r'Grid.cols expects a whole number, got .three.'):
        app(tmp_path, '<div><ui.Grid cols="three" /></div>')


def test_alert_dismiss_emits_close(tmp_path):
    _, a, r, tree = app(
        tmp_path,
        '<div><If cond="show"><ui.Alert kind="danger" title="Oops" dismissible="true" @close="show = False">Bad</ui.Alert></If></div>',
        "show: bool = True",
    )
    alert = find(tree, cls("alert"))
    assert alert.attrs["role"] == "alert" and "alert-danger" in alert.attrs["class"]
    r.dispatch(find(tree, cls("close")).events["click"], {})
    assert a.show is False
    assert find(cycle(r, tree), cls("alert")) is None


def test_dialog_opens_and_closes_through_bind(tmp_path):
    _, a, r, tree = app(
        tmp_path,
        '<div><ui.Button @click="open = True">Open</ui.Button>'
        '<ui.Dialog title="Sure?" @bind="open" @close="closed.append(1)">Body'
        '<Fill name="footer"><ui.Button @click="open = False">No</ui.Button></Fill></ui.Dialog></div>',
        "open: bool = False\nclosed: list = []",
    )
    assert find(tree, cls("backdrop")) is None
    r.dispatch(find(tree, tag("button")).events["click"], {})
    tree = cycle(r, tree)
    dialog = find(tree, cls("dialog"))
    assert dialog.attrs["role"] == "dialog" and "autofocus" in dialog.attrs
    assert text([find(tree, cls("title"))]) == "Sure?"
    # Esc on the backdrop closes it through @bind.
    r.dispatch(find(tree, cls("backdrop")).events["keydown.esc"], {"key": "Escape"})
    assert a.open is False and a.closed == [1]
    assert find(cycle(r, tree), cls("backdrop")) is None


def test_dialog_not_dismissible(tmp_path):
    _, a, r, tree = app(
        tmp_path, '<div><ui.Dialog title="Wait" dismissible="false" @bind="open">x</ui.Dialog></div>', "open: bool = True"
    )
    assert find(tree, cls("close")) is None
    r.dispatch(find(tree, cls("backdrop")).events["click.self"], {})
    assert a.open is True


# ------------------------------------------------------------------ layout


def test_app_shell_card_and_theme(tmp_path):
    _, a, r, tree = app(
        tmp_path,
        """
        <ui.Theme mode="dark" primary="#0f766e">
          <ui.AppShell title="Shop" width="narrow">
            <Fill name="nav"><a href="#a">A</a></Fill>
            <Fill name="actions"><ui.Badge kind="success">live</ui.Badge></Fill>
            <ui.Card title="Hello" subtitle="world"><p>body</p>
              <Fill name="footer"><ui.Button>OK</ui.Button></Fill>
            </ui.Card>
            <ui.Card><p>plain</p></ui.Card>
          </ui.AppShell>
        </ui.Theme>
        """,
    )
    theme = tree[0]
    assert theme.attrs["data-mode"] == "dark" and theme.attrs["style"] == "--ui-primary: #0f766e"
    assert find(tree, tag("nav")) is not None
    assert find(tree, tag("main")).attrs["style"] == "max-width: 40rem"
    cards = [n for n in _walk(tree) if "card" in n.attrs.get("class", "").split()]
    assert find([cards[0]], tag("header")) is not None and find([cards[0]], tag("footer")) is not None
    assert find([cards[1]], tag("header")) is None and find([cards[1]], tag("footer")) is None


def test_every_control_renders_and_styles_are_prefixed(tmp_path):
    App, a, r, tree = app(
        tmp_path,
        """
        <ui.Theme><ui.Column>
          <ui.Row><ui.Spinner /><ui.Icon name="check" /><ui.Badge>b</ui.Badge></ui.Row>
          <ui.Grid><ui.TextArea label="Notes" rows="3" @bind="notes" /></ui.Grid>
        </ui.Column></ui.Theme>
        """,
        'notes: str = ""',
    )
    css = collect_styles(App)
    for name in ["theme", "column", "row", "spinner", "icon", "badge", "grid", "text_area"]:
        assert f"[data-w-ui-{name}]" in css, name
    assert find(tree, tag("textarea")).attrs["rows"] == "3"
    assert find(tree, tag("path")).attrs["d"].startswith("M5 12.5")


def _walk(nodes):
    for node in nodes:
        if isinstance(node, Element):
            yield node
            yield from _walk(node.children)
