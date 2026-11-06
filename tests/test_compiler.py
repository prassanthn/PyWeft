"""Compiled templates (compiler.py) must render exactly what the renderer's
tree walk renders: same nodes, same handler ids, same refs, same handler
behaviour. Checked on every example and on randomly generated templates."""

import asyncio
import random
import sys
from pathlib import Path

import pytest

from pyweft import Renderer, compiler, component_from_source, load_component
from pyweft.expressions import ExpressionError, compile_function
from pyweft.vdom import Element, to_dicts

ROOT = Path(__file__).resolve().parents[1]


def render_both(make, monkeypatch, settle=None):
    """Render a fresh instance with and without compilation."""
    results = []
    for enabled in (True, False):
        monkeypatch.setattr(compiler, "ENABLED", enabled)
        r = Renderer(make())
        if settle:
            settle(r)
        tree = r.render()
        refs = {key[1]: r._path_to(el) for key, el in r._refs.items()}
        results.append((r, to_dicts(tree), sorted(r.handlers), refs))
    monkeypatch.setattr(compiler, "ENABLED", True)
    (r1, *compiled_out), (r2, *walked_out) = results
    assert compiled_out == walked_out
    return r1, r2


@pytest.mark.parametrize("app", [
    "examples/todo/app.weft",
    "examples/shop/app.weft",
    "packages/pyweft-ui/gallery/app.weft",
])
def test_examples_render_the_same(app, monkeypatch):
    pytest.importorskip("humanize") if "todo" in app else None
    sys.path.insert(0, str((ROOT / app).parent))
    try:
        cls = load_component(ROOT / app)

        async def main():
            # One renderer, rendered both ways: its child instances are kept,
            # so ids they number themselves (ui-stepper-1) stay the same.
            r = Renderer(cls())
            r.init_root()
            out = []
            for enabled in (True, False, True):
                monkeypatch.setattr(compiler, "ENABLED", enabled)
                tree = to_dicts(r.render())
                out.append((tree, sorted(r.handlers), {k[1]: r._path_to(e) for k, e in r._refs.items()}))
            assert out[0] == out[1] == out[2]

        asyncio.run(main())
    finally:
        sys.path.remove(str((ROOT / app).parent))


def test_every_ui_control_compiles():
    import pyweft_ui

    folder = Path(pyweft_ui.__file__).parent
    for path in sorted(folder.glob("*.weft")):
        cls = getattr(pyweft_ui.ui, "".join(p.title() for p in path.stem.split("_")), None)
        if cls is None:
            continue
        assert compiler.compiled(cls) is not None, path.name


# ------------------------------------------------------------- random templates

STATE = """
<code>
a: bool = False
b: bool = True
count: int = 0
picked = None
items: list = []
def bump(self, n=1):
    self.count += n
</code>
"""

TAGS = ["div", "span", "p", "section", "b"]


class Gen:
    def __init__(self, rng):
        self.rng = rng
        self.loop_vars = []

    def expr(self):
        options = ["count", "count * 2", "'x' if a else None", "b", "len(items)",
                   "sum(i['n'] for i in items)", "[i['id'] for i in items if i['n'] > count]"]
        for var in self.loop_vars:
            options += [f"{var}['id']", f"{var}['n'] + count", f"(lambda k: {var}['id'] + k)(count)"]
        return self.rng.choice(options)

    def text(self):
        return self.rng.choice(["hi ", "{{ %s }}" % self.expr(), "a{{ %s }}b" % self.expr()])

    def attrs(self, keyed_by=None):
        out = []
        rng = self.rng
        if rng.random() < 0.4:
            out.append('class="c%d"' % rng.randrange(3))
        if rng.random() < 0.3:
            out.append('title="t{{ %s }}"' % self.expr())
        if rng.random() < 0.3:
            out.append(':data-x="%s"' % rng.choice(["count if a else None", "b", "a", "count"]))
        if rng.random() < 0.3:
            out.append('class:on="%s"' % rng.choice(["a", "b", "count > 1"]))
        if rng.random() < 0.2:
            out.append("style:width=\"f'{count}px' if b else None\"")
        if rng.random() < 0.3:
            target = self.loop_vars[-1] + "['id']" if self.loop_vars else "count"
            out.append(rng.choice(['@click="bump"', f'@click="picked = {target}"', '@click.prevent=""',
                                   '@keydown.enter="bump(2)"']))
        if rng.random() < 0.15:
            out.append(f'ref="r{rng.randrange(4)}"')
        if keyed_by is None and rng.random() < 0.1:
            out.append('key="count"')
        return " ".join(out)

    def element(self, depth, keyed_by=None):
        tag = self.rng.choice(TAGS)
        return f"<{tag} {self.attrs(keyed_by)}>{self.children(depth + 1)}</{tag}>"

    def children(self, depth):
        if depth > 4:
            return self.text()
        parts = []
        for _ in range(self.rng.randrange(0, 4)):
            kind = self.rng.random()
            if kind < 0.3:
                parts.append(self.text())
            elif kind < 0.65:
                parts.append(self.element(depth))
            elif kind < 0.8:
                parts.append(self.branch(depth))
            else:
                parts.append(self.loop(depth))
        return "".join(parts)

    def branch(self, depth):
        out = f'<If cond="{self.rng.choice(["a", "b", "count > 1", "items"])}">{self.children(depth + 1)}</If>'
        if self.rng.random() < 0.5:
            out += f'<ElseIf cond="{self.expr()}">{self.children(depth + 1)}</ElseIf>'
        if self.rng.random() < 0.5:
            out += f"<Else>{self.children(depth + 1)}</Else>"
        return out

    def loop(self, depth):
        # Reusing an outer loop's name on purpose: the inner one shadows it.
        var = self.rng.choice(["it", "row", "it"])
        source = self.rng.choice(["items", "items[:2]"] + [f"[{v}]" for v in self.loop_vars])
        keyed = self.rng.random() < 0.5
        index = ' index="n"' if self.rng.random() < 0.4 else ""
        self.loop_vars.append(var)
        if keyed:
            body = self.element(depth + 1, keyed_by=var)
            head = f'<For each="{var} in {source}" key="{var}[\'id\']"{index}>'
        else:
            body = self.children(depth + 1)
            head = f'<For each="{var} in {source}"{index}>'
        self.loop_vars.pop()
        return f"{head}{body}</For>"


@pytest.mark.parametrize("seed", range(150))
def test_random_templates_render_the_same(seed, monkeypatch):
    rng = random.Random(seed)
    template = f"<template><main>{Gen(rng).children(0)}</main></template>{STATE}"
    cls = component_from_source(template, "Random")
    items = [{"id": i, "n": rng.randrange(4)} for i in rng.sample(range(10), rng.randrange(5))]
    state = {"a": rng.random() < 0.5, "b": rng.random() < 0.5, "count": rng.randrange(4), "items": items}

    def make():
        return cls(**state)

    compiled_r, walked_r = render_both(make, monkeypatch)
    # The same handler does the same thing in both.
    for handler_id in sorted(compiled_r.handlers)[:3]:
        compiled_r.dispatch(handler_id, {"key": "Enter"})
        walked_r.dispatch(handler_id, {"key": "Enter"})
        assert (compiled_r.component.count, compiled_r.component.picked) == \
               (walked_r.component.count, walked_r.component.picked)
    # And re-rendering after the change still matches.
    monkeypatch.setattr(compiler, "ENABLED", True)
    first = to_dicts(compiled_r.render())
    monkeypatch.setattr(compiler, "ENABLED", False)
    assert first == to_dicts(walked_r.render())


# ------------------------------------------------------------- expression names

def render_text(src, **state):
    cls = component_from_source(src, "App")
    nodes = Renderer(cls(**state)).render()

    def text(ns):
        return "".join(text(n.children) if isinstance(n, Element) else n.text for n in ns)
    return text(nodes)


CODE = "<code>\nitems: list = [1, 2, 3]\nfactor: int = 10\nlen = None\n</code>"


@pytest.mark.parametrize("enabled", [True, False])
def test_generators_and_lambdas_see_template_names(enabled, monkeypatch):
    monkeypatch.setattr(compiler, "ENABLED", enabled)
    src = """<template><p><For each="x in items">{{ sum(x * f for f in [factor]) }}/{{ (lambda: x + factor)() }}/{{ [y for y in items if y > x] }};</For></p></template>
<code>
items: list = [1, 2, 3]
factor: int = 10
</code>"""
    assert render_text(src) == "10/11/[2, 3];20/12/[3];30/13/[];"


@pytest.mark.parametrize("enabled", [True, False])
def test_shadowing_order_matches_the_scope(enabled, monkeypatch):
    monkeypatch.setattr(compiler, "ENABLED", enabled)
    # A field named like a builtin wins over the builtin; a loop variable
    # wins over a field; an inner loop's variable over the outer's.
    src = """<template><p>{{ len is None }}|<For each="factor in [1]">{{ factor }}</For>|<For each="x in [[1, 2]]"><For each="x in x">{{ x }}</For>{{ x }}</For></p></template>""" + CODE
    assert render_text(src) == "True|1|12[1, 2]"


@pytest.mark.parametrize("enabled", [True, False])
def test_errors_read_the_same(enabled, monkeypatch):
    monkeypatch.setattr(compiler, "ENABLED", enabled)
    with pytest.raises(ExpressionError, match=r"error evaluating 'nope \+ 1': NameError: name 'nope' is not defined"):
        render_text("<template><p>{{ nope + 1 }}</p></template>")
    with pytest.raises(ExpressionError, match=r"error evaluating 'items\[9\]': IndexError"):
        render_text("<template><p>{{ items[9] }}</p></template>" + CODE)


def test_frame_dependent_expressions_still_work():
    assert compile_function("(n := 3) + 1") is None
    assert compile_function("sorted(locals())") is None
    src = "<template><p>{{ (total := factor * 2) }} {{ total }}</p></template>" + CODE
    assert render_text(src) == "20 20"


def test_switch_off(monkeypatch):
    cls = component_from_source("<template><p>x</p></template>", "App")
    monkeypatch.setattr(compiler, "ENABLED", False)
    assert compiler.compiled(cls) is None
    monkeypatch.setattr(compiler, "ENABLED", True)
    assert compiler.compiled(cls) is not None
    assert compiler.compiled(cls) is compiler.compiled(cls)


def test_a_template_too_deep_to_compile_is_walked():
    deep = "<For each='x in [1]'>" * 25 + "deep" + "</For>" * 25
    cls = component_from_source(f"<template><p>{deep}</p></template>", "Deep")
    assert compiler.compiled(cls) is None  # too many nested blocks for Python
    assert render_text(f"<template><p>{deep}</p></template>") == "deep"


def test_generated_source_is_readable():
    source, _ = compiler.generate(component_from_source(
        '<template><ul><For each="t in items" key="t"><li @click="pick(t)">{{ t }}</li></For></ul></template>'
        "<code>\nitems: list = []\ndef pick(self, t): pass\n</code>", "App").__template__)
    assert "def _pw_render(" in source and "for _pw_i" in source and "_pw_attr(_pw_c, 'items')" in source


def test_compile_when_idle(monkeypatch):
    monkeypatch.setattr(compiler, "ENABLED", True)
    child = component_from_source("<template><b>{{ n }}</b></template><code>\nn: int = 1\n</code>", "Child")
    app = component_from_source(
        "<template><p><For each='i in range(3)'><Child :n='i' /></For></p></template>",
        "IdleApp", components={"Child": child},
    )
    r = Renderer(app())
    r.compile_when_idle = True
    first = to_dicts(r.render())
    # Walked: nothing compiled yet, both templates waiting.
    assert compiler.compiled(app, create=False) is None
    assert r._to_compile == {app, child}
    assert r.compile_templates(budget=0) is True       # one at a time when out of time
    assert r.compile_templates() is False              # the rest
    assert compiler.compiled(app, create=False) is not None
    assert compiler.compiled(child, create=False) is not None
    assert to_dicts(r.render()) == first               # same output, compiled now
    assert not r._to_compile
