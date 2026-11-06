"""Templates prepared ahead of time (precompiled.py) and the bundle the page
installs."""

import pickle

import pytest

from pyweft import Renderer, compiler, component, precompiled
from pyweft.cli import app_bundle, cmd_build
from pyweft.component import component_from_source, load_component
from pyweft.vdom import to_dicts

SRC = """<template>
  <ul class="list">
    <For each="item in items" key="item"><li @click="pick(item)">{{ item }}</li></For>
  </ul>
</template>
<code>
items: list = ["a", "b"]
picked = None
def pick(self, item):
    self.picked = item
</code>
<style>
.list li { color: red }
</style>
"""


@pytest.fixture(autouse=True)
def clean():
    precompiled.clear()
    yield
    precompiled.clear()


def test_bundle_round_trip():
    data = precompiled.bundle([SRC, "<template><p>broken</template>"])  # the broken one is left out
    assert precompiled.install(data) == 1
    entry = precompiled.lookup(SRC)
    assert entry["template"][0].tag == "ul"
    assert "[data-w-pwscopeplaceholder]" in entry["style"]
    assert "def _pw_render(" in entry["generated"][0]
    assert precompiled.lookup(SRC + " ") is None  # any change: not found


def test_a_bundle_that_does_not_fit_is_ignored(monkeypatch):
    data = precompiled.bundle([SRC])
    assert precompiled.install(b"not a pickle") == 0
    payload = pickle.loads(data)
    for field, value in [("format", 999), ("pyweft", "0.0.1"), ("fingerprint", "x")]:
        assert precompiled.install(pickle.dumps({**payload, field: value})) == 0
    assert precompiled.lookup(SRC) is None


def test_the_loader_uses_it(monkeypatch):
    precompiled.install(precompiled.bundle([SRC]))
    # Neither the parser nor the generator runs for a bundled text.
    monkeypatch.setattr(component, "parse_template", lambda *a: pytest.fail("parsed"))
    monkeypatch.setattr(compiler, "generate", lambda *a: pytest.fail("generated"))
    cls = component_from_source(SRC, "Picker", scope="widgets-picker")
    assert cls.__style__ == ".list li[data-w-widgets-picker] { color: red }"
    app = cls()
    r = Renderer(app)
    tree = r.render()
    assert [li.children[0].text for li in tree[0].children] == ["a", "b"]
    r.dispatch(tree[0].children[1].events["click"], {})
    assert app.picked == "b"


def test_same_output_with_and_without_a_bundle(tmp_path):
    (tmp_path / "app.weft").write_text(SRC, encoding="utf-8")
    plain = to_dicts(Renderer(load_component(tmp_path / "app.weft")()).render())
    precompiled.install(app_bundle(tmp_path))
    bundled_cls = load_component(tmp_path / "app.weft")
    assert to_dicts(Renderer(bundled_cls()).render()) == plain


def test_build_writes_the_bundle(tmp_path):
    (tmp_path / "app.weft").write_text(SRC, encoding="utf-8")
    cmd_build(tmp_path, tmp_path / "dist", prerender=False)
    assert precompiled.install((tmp_path / "dist" / "pyweft-bundle.bin").read_bytes()) == 1
    page = (tmp_path / "dist" / "index.html").read_text(encoding="utf-8")
    assert "pyweft-bundle.bin" in page and "prefetch(" in page


def test_idle_compiling_uses_the_bundled_source(monkeypatch):
    precompiled.install(precompiled.bundle([SRC]))
    cls = component_from_source(SRC, "Picker2")
    monkeypatch.setattr(compiler, "generate", lambda *a: pytest.fail("generated"))
    r = Renderer(cls())
    r.compile_when_idle = True
    r.render()
    assert r.compile_templates() is False
    assert compiler.compiled(cls, create=False) is not None
