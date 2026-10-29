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
