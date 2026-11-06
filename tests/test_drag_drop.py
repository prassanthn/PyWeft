"""Drag and drop: sortable lists (@sort) and dropped files (event.files)."""

import base64

from pyweft import Renderer, component_from_source
from pyweft.dialogs import PickedFile
from pyweft.events import Event
from pyweft.parser import parse_template
from pyweft.vdom import Element


def encoded(name, data, kind=""):
    return {"name": name, "type": kind, "size": len(data), "data": base64.b64encode(data).decode()}


def test_event_files():
    event = Event({"type": "drop", "files": [encoded("a.csv", b"x,y\n1,2\n"), encoded("logo.png", b"\x89PNG")]})
    files = event.files
    assert [f.name for f in files] == ["a.csv", "logo.png"]
    assert files[0].text == "x,y\n1,2\n" and files[1].data == b"\x89PNG"
    assert (files[0].size, files[1].type) == (8, "image/png")
    assert event.files is files  # decoded once
    assert Event({"type": "click"}).files == []
    assert PickedFile("notes", b"").type == "application/octet-stream"


def test_sortable_attributes_become_data_attributes():
    (ul,) = parse_template(
        '<ul sortable="board" sortable-name="todo"><li sortable-ignore="">h</li>'
        '<li><span sortable-handle="">=</span></li></ul>'
    )
    assert set(ul.attrs) == {"data-pw-sortable", "data-pw-sortable-name"}
    assert set(ul.children[0].attrs) == {"data-pw-sortable-ignore"}
    assert set(ul.children[1].children[0].attrs) == {"data-pw-handle"}
    (ul,) = parse_template('<ul :sortable-name="col"><li>x</li></ul>')
    assert ul.expr_attrs == {"data-pw-sortable-name": "col"}


BOARD = """
<template>
  <div>
    <For each="col in ['todo', 'done']" key="col">
      <ul sortable="board" :sortable-name="col" @sort="move(event)">
        <For each="card in board[col]" key="card"><li>{{ card }}</li></For>
      </ul>
    </For>
  </div>
</template>
<code>
board: dict = {"todo": ["a", "b", "c"], "done": ["x"]}

def move(self, event):
    card = self.board[event.from_list].pop(event.from_index)
    self.board[event.to_list].insert(event.to_index, card)
</code>
"""


def test_sort_event_reorders_and_moves_between_lists():
    app = component_from_source(BOARD, "Board")()
    r = Renderer(app)
    (div,) = r.render()
    todo, done = [ul for ul in div.children if isinstance(ul, Element)]
    assert todo.attrs["data-pw-sortable"] == "board" and done.attrs["data-pw-sortable-name"] == "done"
    assert "sort" in todo.events
    r.dispatch(todo.events["sort"], {"type": "sort", "from_index": 0, "to_index": 2,
                                     "from_list": "todo", "to_list": "todo", "keyboard": False})
    assert app.board == {"todo": ["b", "c", "a"], "done": ["x"]}
    r.render()
    r.dispatch(done.events["sort"], {"type": "sort", "from_index": 1, "to_index": 0,
                                     "from_list": "todo", "to_list": "done", "keyboard": False})
    assert app.board == {"todo": ["b", "a"], "done": ["c", "x"]}
