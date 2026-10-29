"""What a component toolkit needs: slots, @bind on components, attributes
passed through to the root element, tags from imports, component libraries."""

import sys
import textwrap

import pytest

from pyweft import (
    ComponentLibrary,
    Renderer,
    TemplateError,
    apply_patches,
    component_from_source,
    diff,
    load_component,
    to_dicts,
)
from pyweft.vdom import Element, Text


def make(src, name="App", **components):
    return component_from_source(textwrap.dedent(src), name, components=components or None)


def text(nodes):
    out = []
    for node in nodes:
        out.append(text(node.children) if isinstance(node, Element) else node.text)
    return "".join(out)


def find(nodes, tag):
    for node in nodes:
        if isinstance(node, Element):
            if node.tag == tag:
                return node
            hit = find(node.children, tag)
            if hit is not None:
                return hit
    return None


def cycle(renderer, old):
    """Render again and check the patch converges, like the browser does."""
    new = renderer.render()
    assert apply_patches(to_dicts(old), diff(old, new)) == to_dicts(new)
    return new


CARD = """
<template>
  <section class="card">
    <header><Slot name="title">Untitled</Slot></header>
    <div class="body"><Slot /></div>
    <If cond="has_slot('footer')"><footer><Slot name="footer" /></footer></If>
  </section>
</template>
<code></code>
"""


# ------------------------------------------------------------------ slots


def test_default_and_named_slots_with_fallback():
    Card = make(CARD, "Card")
    App = make(
        """
        <template><div>
          <Card><p>Hello {{ name }}</p></Card>
          <Card><Fill name="title">Custom</Fill><Fill name="footer"><b>end</b></Fill>body</Card>
        </div></template>
        <code>name: str = "Ada"</code>
        """,
        Card=Card,
    )
    tree = Renderer(App()).render()
    first, second = tree[0].children
    assert text([first]) == "UntitledHello Ada"
    assert find([first], "footer") is None  # has_slot('footer') was False
    assert text([second]) == "Custombodyend"


def test_slot_content_uses_the_parents_state_and_handlers():
    Card = make(CARD, "Card")
    App = make(
        """
        <template><div><Card><button @click="count += 1">{{ count }}</button></Card></div></template>
        <code>count: int = 0</code>
        """,
        Card=Card,
    )
    app = App()
    r = Renderer(app)
    tree = r.render()
    r.dispatch(find(tree, "button").events["click"], {})
    assert app.count == 1
    tree = cycle(r, tree)
    assert text([find(tree, "button")]) == "1"


def test_slot_content_in_a_loop_sees_loop_variables_and_keeps_identity():
    Card = make(CARD, "Card")
    App = make(
        """
        <template><div>
          <For each="item in items" key="item">
            <Card><Fill name="title">{{ item }}</Fill>#{{ item }}</Card>
          </For>
        </div></template>
        <code>items: list = ["a", "b", "c"]</code>
        """,
        Card=Card,
    )
    app = App()
    r = Renderer(app)
    tree = r.render()
    assert [text([c]) for c in tree[0].children] == ["a#a", "b#b", "c#c"]
    app.items = ["c", "a"]
    tree = cycle(r, tree)
    assert [text([c]) for c in tree[0].children] == ["c#c", "a#a"]


def test_scoped_slot_props_become_variables():
    List = make(
        """
        <template><ul><For each="row in rows" index="i">
          <li><Slot :row="row" :index="i">{{ row }}</Slot></li>
        </For></ul></template>
        <code>rows: list = []</code>
        """,
        "List",
    )
    App = make(
        """
        <template><div>
          <List :rows="people"><b>{{ index }}: {{ row['name'] }}</b></List>
          <List :rows="['x']" />
        </div></template>
        <code>people: list = [{"name": "Ada"}, {"name": "Alan"}]</code>
        """,
        List=List,
    )
    tree = Renderer(App()).render()
    custom, fallback = tree[0].children
    assert [text([li]) for li in custom.children] == ["0: Ada", "1: Alan"]
    assert text([fallback]) == "x"


def test_slot_forwarded_through_a_middle_component():
    Card = make(CARD, "Card")
    Panel = make(
        """
        <template><div class="panel"><Card><Slot /></Card></div></template>
        <code></code>
        """,
        "Panel",
        Card=Card,
    )
    App = make(
        "<template><div><Panel><i>{{ msg }}</i></Panel></div></template><code>msg = 'deep'</code>",
        Panel=Panel,
    )
    assert text(Renderer(App()).render()) == "Untitleddeep"


def test_scoped_styles_of_slot_content_belong_to_the_parent():
    Card = component_from_source(CARD + "<style>.body { color: red }</style>", "Card")
    App = component_from_source(
        "<template><div><Card><p>x</p></Card></div></template><code></code>"
        "<style>p { color: blue }</style>",
        "App",
        components={"Card": Card},
    )
    p = find(Renderer(App()).render(), "p")
    assert "data-w-app" in p.attrs and "data-w-card" not in p.attrs


@pytest.mark.parametrize(
    "parent, message",
    [
        ('<Card><Fill name="nope">x</Fill></Card>', 'Fill name="nope">, but Card would never show it'),
        ('<Card><Fill name="title">a</Fill><Fill name="title">b</Fill></Card>', 'two <Fill name="title">'),
        ('<Card>x<Fill name="default">y</Fill></Card>', "both content outside <Fill>"),
        ('<p><Fill name="title">x</Fill></p>', "must be directly inside a component tag"),
    ],
)
def test_slot_mistakes_are_template_errors(parent, message):
    Card = make(CARD, "Card")
    App = make(f"<template><div>{parent}</div></template><code></code>", Card=Card)
    with pytest.raises(TemplateError, match=message):
        Renderer(App()).render()


def test_fill_needs_a_name():
    with pytest.raises(TemplateError, match="requires name"):
        make("<template><div><Fill>x</Fill></div></template><code></code>")


# ------------------------------------------------------------ @bind on components


FIELD = """
<template><label>{{ label }}<input :value="value" @input="emit('update', event.value.upper())" /></label></template>
<code>
label: str = ""
value: str = ""
</code>
"""


def test_bind_on_a_component():
    Field = make(FIELD, "Field")
    App = make(
        """
        <template><div><Field label="Name" @bind="name" /><p>{{ name }}</p></div></template>
        <code>name: str = "ada"</code>
        """,
        Field=Field,
    )
    app = App()
    r = Renderer(app)
    tree = r.render()
    assert find(tree, "input").attrs["value"] == "ada"
    r.dispatch(find(tree, "input").events["input"], {"value": "grace"})
    assert app.name == "GRACE"
    tree = cycle(r, tree)
    assert find(tree, "input").attrs["value"] == "GRACE" and text([find(tree, "p")]) == "GRACE"


def test_bind_on_a_component_with_own_update_handler():
    Field = make(FIELD, "Field")
    App = make(
        """
        <template><div><Field @bind="name" @update="log.append(name)" /></div></template>
        <code>
name: str = ""
log: list = []
        </code>
        """,
        Field=Field,
    )
    app = App()
    r = Renderer(app)
    r.dispatch(find(r.render(), "input").events["input"], {"value": "x"})
    assert app.log == ["X"]


def test_bind_modifiers_on_a_component_are_an_error():
    Field = make(FIELD, "Field")
    App = make('<template><div><Field @bind.lazy="name" /></div></template><code>name = ""</code>', Field=Field)
    with pytest.raises(TemplateError, match="takes no modifiers"):
        Renderer(App()).render()


# ------------------------------------------------------ attribute passthrough


BUTTON = """
<template><button class="btn" style="padding: 4px" :disabled="disabled" @click="emit('click')"><Slot /></button></template>
<code>
disabled: bool = False
variant: str = "plain"
</code>
"""


def test_undeclared_attributes_reach_the_root_element():
    Button = make(BUTTON, "Button")
    App = make(
        """
        <template><div>
          <Button variant="primary" class="wide" style="color: red" id="go"
                  aria-label="Go" data-x="1" :title="hint" :hidden="False">Go</Button>
        </div></template>
        <code>hint = "press"</code>
        """,
        Button=Button,
    )
    app = App()
    r = Renderer(app)
    button = find(r.render(), "button")
    assert button.attrs["class"] == "btn wide"
    assert button.attrs["style"] == "padding: 4px; color: red"
    assert {k: button.attrs[k] for k in ("id", "aria-label", "data-x", "title")} == {
        "id": "go", "aria-label": "Go", "data-x": "1", "title": "press",
    }
    assert "hidden" not in button.attrs and "variant" not in button.attrs
    (child,) = r.instances.values()
    assert child.variant == "primary"  # declared: a prop, not an attribute


def test_passthrough_needs_a_single_root():
    Two = make("<template><p>a</p><p>b</p></template><code></code>", "Two")
    App = make('<template><div><Two class="x" /></div></template><code></code>', Two=Two)
    with pytest.raises(TemplateError, match="renders 2 root elements, so class has nowhere to go"):
        Renderer(App()).render()


def test_properties_and_imports_are_not_props():
    Child = make(
        """
        <template><p>{{ shout }}</p></template>
        <code>
import json
word: str = "hi"

@property
def shout(self):
    return self.word.upper()
        </code>
        """,
        "Child",
    )
    from pyweft.component import declared_props

    assert declared_props(Child) == {"word"}


# ------------------------------------------------------------ tags from imports


@pytest.fixture
def library(tmp_path, monkeypatch):
    """A package `kit` holding .weft components, importable like any library."""
    pkg = tmp_path / "kit"
    pkg.mkdir()
    (pkg / "__init__.py").write_text(
        "from pathlib import Path\nfrom pyweft import ComponentLibrary\n"
        "ui = ComponentLibrary(Path(__file__).parent, prefix='ui')\n",
        encoding="utf-8",
    )
    (pkg / "button.weft").write_text(BUTTON + "<style>.btn { color: red }</style>", encoding="utf-8")
    (pkg / "card.weft").write_text(CARD.replace("<code></code>", "<code></code>"), encoding="utf-8")
    (pkg / "text_field.weft").write_text(FIELD, encoding="utf-8")
    (pkg / "toolbar.weft").write_text(
        "<template><nav><Button class='tool'><Slot /></Button></nav></template><code></code>",
        encoding="utf-8",
    )
    monkeypatch.syspath_prepend(str(tmp_path))
    forget_kit()
    yield pkg
    forget_kit()


def forget_kit():
    """Each test's `kit` lives in its own tmp folder; drop the last one."""
    for name in [m for m in sys.modules if m == "kit" or m.startswith("kit.")]:
        del sys.modules[name]


def test_library_components_as_dotted_tags(library, tmp_path):
    app_dir = tmp_path / "app"
    app_dir.mkdir()
    (app_dir / "app.weft").write_text(
        textwrap.dedent(
            """
            <template><div>
              <ui.Card><Fill name="title">T</Fill><ui.Button class="x">Go</ui.Button></ui.Card>
              <ui.TextField @bind="name" />
              <ui.Toolbar>Tools</ui.Toolbar>
            </div></template>
            <code>
            from kit import ui
            name: str = "a"
            </code>
            <style>.x { margin: 0 }</style>
            """
        ),
        encoding="utf-8",
    )
    App = load_component(app_dir / "app.weft")
    tree = Renderer(App()).render()
    assert text(tree) == "TGoTools"
    button = find(tree, "button")
    # The library's styles are scoped under its own prefix, apart from the app's.
    assert "data-w-ui-button" in button.attrs and "data-w-app" in button.attrs
    from kit import ui

    assert "[data-w-ui-button]" in ui.Button.__style__
    assert {"Button", "Card", "TextField", "Toolbar"} <= set(dir(ui))


def test_import_a_single_component_class(library):
    App = make(
        """
        <template><div><Button>Hi</Button></div></template>
        <code>
from kit import ui
Button = ui.Button
        </code>
        """
    )
    assert text(Renderer(App()).render()) == "Hi"


def test_unknown_library_component_is_a_clear_error(library):
    from kit import ui

    with pytest.raises(AttributeError, match="has no component Missing"):
        ui.Missing


def test_imported_tag_wins_over_a_file_of_the_same_name(library, tmp_path):
    app_dir = tmp_path / "app2"
    app_dir.mkdir()
    (app_dir / "Button.weft").write_text("<template><b>local</b></template><code></code>", encoding="utf-8")
    (app_dir / "app.weft").write_text(
        "<template><div><Button>lib</Button></div></template>\n"
        "<code>\nfrom kit import ui\nButton = ui.Button\n</code>",
        encoding="utf-8",
    )
    assert text(Renderer(load_component(app_dir / "app.weft")()).render()) == "lib"
