"""pyweft check's accessibility warnings (a11y.py)."""

import textwrap

import pytest

from pyweft.check import check_app
from pyweft.cli import main


def codes(tmp_path, template, code=""):
    (tmp_path / "app.weft").write_text(
        f"<template>\n{textwrap.dedent(template).strip()}\n</template>\n<code>\n{textwrap.dedent(code)}\n</code>\n",
        encoding="utf-8")
    problems, _ = check_app(tmp_path, deps=False)
    return [(p.line, p.code) for p in problems if p.code.startswith("a11y-")]


HANDLERS = "go = None\nn: int = 1\nname: str = ''\nopen: bool = False\n"


@pytest.mark.parametrize("template, expected", [
    ('<img src="a.png" />', "a11y-missing-alt"),
    ('<div @click="go">x</div>', "a11y-click-without-keyboard"),
    ('<div @click="go" @keydown.enter="go">x</div>', "a11y-not-focusable"),
    ('<span role="button">x</span>', None),                        # no click: nothing to reach
    ('<span role="button" @click="go" @keydown.enter="go">x</span>', "a11y-not-focusable"),
    ('<a @click="go">x</a>', "a11y-anchor-no-href"),
    ('<input @bind="name" />', "a11y-missing-label"),
    ('<select @bind="name"><option>a</option></select>', "a11y-missing-label"),
    ('<button @click="go"><svg viewBox="0 0 2 2"><path d="M0 0" /></svg></button>', "a11y-empty-button"),
    ('<div tabindex="3">x</div>', "a11y-positive-tabindex"),
    ('<div role="buton">x</div>', "a11y-unknown-role"),
    ('<div aria-lable="x">x</div>', "a11y-unknown-aria"),
])
def test_each_rule(tmp_path, template, expected):
    found = codes(tmp_path, template, HANDLERS)
    assert [c for _, c in found] == ([expected] if expected else [])


def test_messages_suggest_the_fix(tmp_path):
    (tmp_path / "app.weft").write_text('<template><div role="buton" aria-lable="x">x</div></template>', encoding="utf-8")
    problems, _ = check_app(tmp_path, deps=False)
    assert "did you mean 'button'?" in problems[0].message + problems[1].message
    assert "did you mean 'aria-label'?" in problems[0].message + problems[1].message


@pytest.mark.parametrize("template", [
    '<img src="a.png" alt="" />',
    '<img src="a.png" :alt="caption" />',
    '<button @click="go" type="button">Save</button>',
    '<button @click="go" aria-label="Close"><svg viewBox="0 0 2 2"><path d="M0 0" /></svg></button>',
    '<button @click="go">{{ name }}</button>',
    '<label>Name <input @bind="name" /></label>',
    '<div><label for="who">Name</label><input id="who" @bind="name" /></div>',
    '<input @bind="name" aria-label="Name" />',
    '<input type="hidden" name="x" />',
    '<input @bind="name" :id="name" />',                           # a bound id: can't tell, so trusted
    '<div class="backdrop" aria-hidden="true" @click="go"></div>',  # click-outside backdrop
    '<div role="button" tabindex="0" @click="go" @keydown.enter="go">x</div>',
    '<ul role="listbox"><li role="option" @click="go">a</li></ul>',  # focus managed by the list
    '<a href="#x" @click="go">x</a>',
    '<div @submit.prevent="">x</div>',
    '<div tabindex="0">x</div>',
    '<Window @keydown.esc="go" />',
])
def test_good_markup_passes(tmp_path, template):
    assert codes(tmp_path, template, HANDLERS) == []


def test_ignore_comment_silences_one_element(tmp_path):
    found = codes(tmp_path, """
        <div>
          <!-- pyweft-ignore: a11y-click-without-keyboard -->
          <div @click="go">a</div>
          <div @click="go">b</div>
          <!-- pyweft-ignore -->
          <img src="x.png" />
          <!-- pyweft-ignore: a11y-missing-alt -->
          <div @click="go">c</div>
        </div>""", HANDLERS)
    assert [c for _, c in found] == ["a11y-click-without-keyboard", "a11y-click-without-keyboard"]
    assert [line for line, _ in found] == [5, 9]


def test_content_passed_to_a_component_is_checked(tmp_path):
    (tmp_path / "box.weft").write_text("<template><section><Slot /></section></template>", encoding="utf-8")
    assert [c for _, c in codes(tmp_path, '<Box><img src="a.png" /></Box>')] == ["a11y-missing-alt"]


def test_no_a11y_flag(tmp_path, capsys):
    (tmp_path / "app.weft").write_text('<template><img src="a.png" /></template>', encoding="utf-8")
    assert main(["check", str(tmp_path), "--no-deps"]) == 0
    assert "a11y-missing-alt" in capsys.readouterr().out
    main(["check", str(tmp_path), "--no-deps", "--no-a11y"])
    assert "No problems found" in capsys.readouterr().out
