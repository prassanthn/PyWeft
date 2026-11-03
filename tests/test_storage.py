"""pyweft.storage: values kept between visits, in memory and in a file."""

import json

import pytest

from pyweft import Renderer, component_from_source, storage
from pyweft.cli import app_id, render_shell


@pytest.fixture(autouse=True)
def fresh():
    storage.set_host(storage.MemoryStorage())
    yield
    storage.set_host(storage.MemoryStorage())


def test_round_trip_and_defaults():
    assert storage.get("todos") is None and storage.get("todos", []) == []
    storage.set("todos", [{"text": "milk", "done": False}])
    storage.set("count", 3)
    assert storage.get("todos") == [{"text": "milk", "done": False}]
    assert storage.keys() == ["count", "todos"] and storage.has("count")
    storage.delete("count")
    storage.delete("count")  # already gone: nothing happens
    assert not storage.has("count") and storage.keys() == ["todos"]
    storage.clear()
    assert storage.keys() == []


def test_get_returns_a_copy():
    storage.set("items", [1, 2])
    items = storage.get("items")
    items.append(3)
    assert storage.get("items") == [1, 2]


def test_only_json_values_and_text_keys():
    with pytest.raises(TypeError, match="'when' got date"):
        import datetime

        storage.set("when", datetime.date(2026, 1, 1))
    with pytest.raises(TypeError):
        storage.set("x", float("nan"))
    with pytest.raises(TypeError, match="non-empty text"):
        storage.set("", 1)
    with pytest.raises(TypeError):
        storage.get(3)


def test_file_storage_survives_a_restart(tmp_path):
    path = tmp_path / "data" / "storage.json"
    storage.set_host(storage.FileStorage(path))
    storage.set("name", "Ada")
    storage.set("prefs", {"dark": True})
    assert json.loads(path.read_text(encoding="utf-8")) == {
        "name": "Ada", "prefs": {"dark": True}
    }
    storage.set_host(storage.FileStorage(path))  # the app starts again
    assert storage.get("prefs") == {"dark": True}
    storage.delete("name")
    assert json.loads(path.read_text(encoding="utf-8")) == {"prefs": {"dark": True}}
    assert [p.name for p in path.parent.iterdir()] == ["storage.json"]  # no temp files


def test_a_damaged_file_is_reported(tmp_path):
    path = tmp_path / "storage.json"
    path.write_text("{not json", encoding="utf-8")
    with pytest.raises(OSError, match="saved data"):
        storage.FileStorage(path)


def test_unavailable_says_why():
    storage.set_host(storage.Unavailable("not in the worker"))
    with pytest.raises(RuntimeError, match="not in the worker"):
        storage.get("x")


def test_load_in_on_init_and_save_with_an_effect():
    source = '''
<template><p>{{ len(items) }}</p></template>
<code>
from pyweft import effect, storage
items: list = []

def on_init(self):
    self.items = storage.get("todos", [])

def add(self):
    self.items.append("new")

@effect
def keep(self):
    storage.set("todos", self.items)
</code>'''
    storage.set("todos", ["old"])
    app = component_from_source(source)()
    renderer = Renderer(app)
    renderer.init_root()
    renderer.render()
    renderer.after_render()
    app.add()  # as a handler would
    renderer.render()
    renderer.after_render()
    assert storage.get("todos") == ["old", "new"]
    # The next visit picks it up.
    second = component_from_source(source)()
    Renderer(second).init_root()
    assert second.items == ["old", "new"]


def test_app_id(tmp_path):
    app = tmp_path / "My Shop"
    app.mkdir()
    assert app_id(app) == "my-shop"  # no pyproject: the folder
    (app / "pyproject.toml").write_text('[project]\nname = "Orders_App"\n', encoding="utf-8")
    assert app_id(app) == "orders_app"


def test_the_page_knows_the_app_id(tmp_path):
    (tmp_path / "app.weft").write_text("<template><p>hi</p></template>", encoding="utf-8")
    (tmp_path / "pyproject.toml").write_text('[project]\nname = "notes"\n', encoding="utf-8")
    html = render_shell(tmp_path)
    assert 'const APP_ID = "notes";' in html
    assert "_webhost.install_page(${JSON.stringify(APP_ID)})" in html
