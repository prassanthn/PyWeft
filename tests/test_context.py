"""provide() / inject(): values passed down the component tree."""

import pytest

from pyweft import Renderer, component_from_source
from pyweft.expressions import ExpressionError
from pyweft.vdom import Element


def text(nodes):
    return "".join(text(n.children) if isinstance(n, Element) else n.text for n in nodes)


LEAF = """
<template><span>{{ inject('theme') }}/{{ inject('user', 'nobody') }}</span></template>
<code>
seen = None
def on_init(self):
    self.seen = self.inject("theme")
</code>
"""

MIDDLE = """
<template><div><Leaf /></div></template>
"""

APP = """
<template><main><Middle /><button @click="theme = 'dark'">dark</button></main></template>
<code>
theme: str = "light"
def on_init(self):
    self.provide("theme", self.theme)
def on_after_render(self, first):
    self.provide("theme", self.theme)
</code>
"""


def build():
    leaf = component_from_source(LEAF, "Leaf")
    middle = component_from_source(MIDDLE, "Middle", components={"Leaf": leaf})
    app = component_from_source(APP, "App", components={"Middle": middle})
    return app, leaf


def test_reaches_through_levels_and_from_on_init():
    app, leaf = build()
    r = Renderer(app())
    r.init_root()
    assert text(r.render()) == "light/nobodydark"
    (child,) = [c for c in r.instances.values() if isinstance(c, leaf)]
    assert child.seen == "light"


def test_templates_see_a_new_value_on_the_next_render():
    app, _ = build()
    root = app()
    r = Renderer(root)
    r.init_root()
    r.render()
    root.provide("theme", "dark")
    assert text(r.render()).startswith("dark/")


def test_nearest_provider_wins_and_a_provider_sees_its_parents_value():
    inner_src = """
<template><section><Slot /></section></template>
<code>
def on_init(self):
    outer = self.inject("level")
    self.provide("level", outer + 1)
</code>
"""
    show = component_from_source("<template><b>{{ inject('level') }}</b></template>", "Show")
    inner = component_from_source(inner_src, "Inner")
    app = component_from_source(
        "<template><div><Show /><Inner><Show /><Inner><Show /></Inner></Inner></div></template>"
        "<code>\ndef on_init(self):\n    self.provide('level', 1)\n</code>",
        "App", components={"Show": show, "Inner": inner},
    )
    r = Renderer(app())
    r.init_root()
    # Content passed into a slot sees what the component showing it provides.
    assert text(r.render()) == "123"


def test_class_keys_and_defaults():
    class Theme:
        name = "teal"

    leaf = component_from_source(
        "<template><i>{{ inject(Theme).name }}</i></template>", "Leaf",
    )
    leaf.Theme = Theme
    app = component_from_source(
        "<template><p><Leaf /></p></template>", "App", components={"Leaf": leaf},
    )
    root = app()
    assert isinstance(root.provide(Theme, Theme()), Theme)
    r = Renderer(root)
    assert text(r.render()) == "teal"


def test_missing_key_is_a_clear_error():
    leaf = component_from_source("<template><i>{{ inject('nope') }}</i></template>", "Leaf")
    app = component_from_source("<template><p><Leaf /></p></template>", "App", components={"Leaf": leaf})
    # In a template it arrives wrapped, with the expression that failed.
    with pytest.raises(ExpressionError, match=r"Leaf.inject\('nope'\): no component above it provides"):
        Renderer(app()).render()
    with pytest.raises(LookupError):
        app().inject("x")  # not rendered: nothing above it


def test_disposal_drops_the_parent_link():
    leaf = component_from_source("<template><i>x</i></template>", "Leaf")
    app = component_from_source(
        "<template><p><If cond='shown'><Leaf /></If></p></template><code>\nshown: bool = True\n</code>",
        "App", components={"Leaf": leaf},
    )
    root = app()
    r = Renderer(root)
    r.render()
    (child,) = r.instances.values()
    assert child.__dict__["_pw_parent"] is root
    root.shown = False
    r.render()
    assert "_pw_parent" not in child.__dict__
