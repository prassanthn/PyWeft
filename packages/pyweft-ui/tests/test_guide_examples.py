"""Every example in docs/guide.md must work: complete examples are loaded and
rendered, fragments are parsed, and the two longer recipes are clicked
through. A broken example fails here, not for a reader."""

import asyncio
import re
from pathlib import Path

import pytest

from pyweft import Renderer, load_component
from pyweft.parser import parse_template
from pyweft.vdom import Element

GUIDE = Path(__file__).parent.parent / "docs" / "guide.md"
BLOCKS = re.findall(r"```xml\n(.*?)```", GUIDE.read_text(encoding="utf-8"), re.S)
NAMED = re.compile(r"^<!-- (\w+\.weft) -->\n")


def complete(block):
    return "<template>" in block and "<code>" in block


FULL = [b for b in BLOCKS if complete(b) and not NAMED.match(b)]
HELPERS = [b for b in BLOCKS if NAMED.match(b)]
FRAGMENTS = [b for b in BLOCKS if not complete(b)]


@pytest.fixture
def app_dir(tmp_path):
    """A folder holding the guide's named helper components."""
    for block in HELPERS:
        name = NAMED.match(block).group(1)
        (tmp_path / name).write_text(NAMED.sub("", block), encoding="utf-8")
    return tmp_path


def load(app_dir, block):
    (app_dir / "app.weft").write_text(block, encoding="utf-8")
    app = load_component(app_dir / "app.weft")()
    renderer = Renderer(app)
    renderer.init_root()
    return app, renderer


def walk(nodes):
    for node in nodes:
        if isinstance(node, Element):
            yield node
            yield from walk(node.children)


def text(node):
    return "".join(
        text(c) if isinstance(c, Element) else c.text for c in node.children
    )


def test_the_guide_has_examples():
    assert len(FULL) >= 7 and len(HELPERS) == 2 and len(FRAGMENTS) >= 15


@pytest.mark.parametrize("block", FULL, ids=lambda b: b.split("\n", 3)[1].strip()[:40])
def test_complete_example_renders(app_dir, block):
    async def main():
        _, renderer = load(app_dir, block)
        renderer.render()
        renderer.after_render()

    asyncio.run(main())  # some examples load data in an async on_init


@pytest.mark.parametrize("block", FRAGMENTS, ids=lambda b: b.strip().split("\n")[0][:40])
def test_fragment_is_valid_template(block):
    parse_template(f"<div>{block}</div>")


def test_signup_form_validates_then_submits(app_dir):
    block = next(b for b in FULL if "Create your account" in b)

    async def main():
        app, r = load(app_dir, block)
        tree = r.render()
        form = next(n for n in walk(tree) if n.tag == "form")
        r.dispatch(form.events["submit.prevent"], {"type": "submit"})
        assert set(app.errors) == {"email", "password", "country"}
        errors = [text(n) for n in walk(r.render()) if "error" in n.attrs.get("class", "").split()]
        assert "Use at least 8 characters" in errors

        fields = [n for n in walk(r.render()) if n.tag in ("input", "select")]
        email, password, country, agree = fields
        r.dispatch(email.events["input"], {"value": "ada@example.com"})
        r.dispatch(password.events["input"], {"value": "correct horse"})
        r.dispatch(country.events["change"], {"value": "India"})
        r.dispatch(agree.events["change"], {"checked": True})
        tree = r.render()
        button = next(n for n in walk(tree) if n.tag == "button")
        assert "disabled" not in button.attrs
        r.dispatch(form.events["submit.prevent"], {"type": "submit"})
        assert app.errors == {} and app.saving
        await r.idle()
        assert app.done and not app.saving
        alert = next(n for n in walk(r.render()) if "alert-success" in n.attrs.get("class", ""))
        assert "ada@example.com" in text(alert)

    asyncio.run(main())


def test_confirm_dialog_recipe(app_dir):
    block = next(b for b in FULL if "Delete this project?" in b)
    app, r = load(app_dir, block)
    tree = r.render()
    r.dispatch(next(n for n in walk(tree) if n.tag == "button").events["click"], {})
    tree = r.render()
    footer = next(n for n in walk(tree) if n.tag == "footer")
    delete = [n for n in walk([footer]) if n.tag == "button"][1]
    r.dispatch(delete.events["click"], {})
    assert app.status == "Deleted Website redesign." and app.confirming is False


def test_tabs_recipe(app_dir):
    block = next(b for b in FULL if "<ui.Tabs" in b)
    app, r = load(app_dir, block)
    tree = r.render()
    assert find_text(tree, "input") is not None  # Profile shows the name field
    tabs = [n for n in walk(tree) if n.attrs.get("role") == "tab"]
    r.dispatch(tabs[2].events["click"], {})
    assert app.tab == "Billing"
    panel = next(n for n in walk(r.render()) if n.attrs.get("role") == "tabpanel")
    assert text(panel) == "You're on the free plan."


def test_table_recipe(app_dir):
    block = next(b for b in FULL if "<ui.Table" in b)
    app, r = load(app_dir, block)
    tree = r.render()
    rows = [n for n in walk(tree) if n.tag == "tr" and "clickable" in n.attrs.get("class", "")]
    assert [text(n.children[3]) for n in rows] == ["1,250.00", "89.90"]  # sorted, largest first
    assert any("badge-success" in n.attrs.get("class", "") for n in walk([rows[0]]))
    r.dispatch(rows[1].events["click"], {})
    assert app.message == "Order 1042 for Grace Hopper"
    app.orders = []
    assert "No orders yet." in [text(n) for n in walk(r.render()) if n.tag == "td"]


def test_toast_recipe(app_dir, toasts):
    block = next(b for b in FULL if "<ui.Toaster" in b)

    async def main():
        app, r = load(app_dir, block)
        tree = r.render()
        save, archive = [n for n in walk(tree) if n.tag == "button"]
        r.dispatch(archive.events["click"], {})
        assert app.notes == ["Groceries", "Ideas"]
        assert [t.message for t in toasts._toasts] == ["Archived “Books”."]
        undo = next(n for n in walk(r.render()) if "action" in n.attrs.get("class", ""))
        r.dispatch(undo.events["click"], {})
        assert app.notes == ["Groceries", "Ideas", "Books"] and toasts._toasts == []
        r.dispatch(save.events["click"], {})
        assert toasts._toasts[0].kind == "success"
        toasts._toasts[0].close()
        await r.idle()

    asyncio.run(main())


def find_text(nodes, tag):
    return next((n for n in walk(nodes) if n.tag == tag), None)


def test_stat_cards_and_email_field(app_dir):
    stats = next(b for b in FULL if "<StatCard" in b)
    _, r = load(app_dir, stats)
    badges = [text(n).strip() for n in walk(r.render()) if "badge" in n.attrs.get("class", "")]
    assert badges == ["12%", "-3%"]

    email = next(b for b in FULL if "<EmailField" in b)
    app, r = load(app_dir, email)
    field = next(n for n in walk(r.render()) if n.tag == "input")
    r.dispatch(field.events["input"], {"value": "nope"})
    assert app.email == "nope"
    error = [n for n in walk(r.render()) if "error" in n.attrs.get("class", "").split()]
    assert text(error[0]) == "That doesn't look like an email address"
