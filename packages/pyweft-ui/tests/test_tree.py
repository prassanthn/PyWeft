"""Tree: open and close, select, check, load on demand, filter, keyboard."""

from pyweft.vdom import Element

from test_controls import app, cls, cycle, find, text


def every(tree, test):
    out = []

    def walk(nodes):
        for n in nodes:
            if isinstance(n, Element):
                if test(n):
                    out.append(n)
                walk(n.children)

    walk(tree)
    return out


def items(tree):
    return every(tree, lambda n: n.attrs.get("role") == "treeitem")


def names(tree):
    return [" ".join(text(every([i], cls("text"))).split()) for i in items(tree)]


def item(tree, name):
    return next(i for i in items(tree) if " ".join(text(every([i], cls("text"))).split()) == name)


def focused(r, tree):
    r.after_render()
    found = [c for c in r.take_commands() if c["op"] == "focus"]
    assert found, "no focus request"
    node, nodes = None, tree
    for index in found[-1]["path"]:
        node = nodes[index]
        nodes = node.children
    return " ".join(text(every([node], cls("text"))).split())


def key(r, tree, spec, payload=None):
    root = find(tree, lambda n: n.attrs.get("role") == "tree")
    r.dispatch(root.events[spec], payload or {})
    return cycle(r, tree)


CODE = """
picked = None
granted: list = []
activated: list = []
toggles: list = []
loads: list = []
query: str = ""
FILES = [
    {"value": "src", "label": "src", "icon": "folder", "children": [
        {"value": "app", "label": "app.weft", "icon": "file"},
        {"value": "lib", "label": "lib", "icon": "folder", "children": [
            {"value": "util", "label": "util.py", "icon": "file"},
            {"value": "old", "label": "old.py", "disabled": True},
        ]},
    ]},
    {"value": "docs", "label": "docs", "children": None},
    ("readme", "README.md"),
]

def load(self, value):
    self.loads.append(value)
"""
TREE = ('<div><ui.Tree label="Files" :nodes="FILES" @bind="picked" @activate="activated.append(event)" '
        '@toggle="toggles.append(event)" @load="load(event)" :filter="query" {extra} /></div>')


def tree_app(tmp_path, extra="", code=CODE):
    return app(tmp_path, TREE.replace("{extra}", extra), code)


def test_closed_tree_and_aria(tmp_path):
    _, a, r, tree = tree_app(tmp_path)
    root = find(tree, lambda n: n.attrs.get("role") == "tree")
    assert root.attrs["aria-label"] == "Files" and "aria-multiselectable" not in root.attrs
    assert names(tree) == ["src", "docs", "README.md"]
    src, docs, readme = items(tree)
    assert (src.attrs["aria-level"], src.attrs["aria-posinset"], src.attrs["aria-setsize"]) == ("1", "1", "3")
    assert src.attrs["aria-expanded"] == "false" and docs.attrs["aria-expanded"] == "false"
    assert "aria-expanded" not in readme.attrs and readme.attrs["aria-selected"] == "false"
    assert [i.attrs["tabindex"] for i in items(tree)] == ["0", "-1", "-1"]


def test_open_close_and_select(tmp_path):
    _, a, r, tree = tree_app(tmp_path)
    r.dispatch(find([item(tree, "src")], cls("twisty")).events["click.stop"], {})
    tree = cycle(r, tree)
    assert names(tree) == ["src", "app.weft", "lib", "docs", "README.md"]
    assert a.toggles == [{"value": "src", "open": True}]
    assert item(tree, "app.weft").attrs["aria-level"] == "2" and len(every([item(tree, "lib")], cls("guide"))) == 1
    r.dispatch(item(tree, "app.weft").events["click"], {})
    tree = cycle(r, tree)
    assert a.picked == "app" and item(tree, "app.weft").attrs["aria-selected"] == "true"
    assert "selected" in item(tree, "app.weft").attrs["class"]
    r.dispatch(item(tree, "app.weft").events["dblclick"], {})
    assert a.activated == ["app"]
    r.dispatch(item(tree, "src").events["dblclick"], {})              # a parent: closes
    tree = cycle(r, tree)
    assert names(tree) == ["src", "docs", "README.md"] and a.activated == ["app"]


def test_expanded_and_expand_all(tmp_path):
    _, a, r, tree = tree_app(tmp_path, ':expanded="[\'src\', \'lib\']"')
    assert names(tree) == ["src", "app.weft", "lib", "util.py", "old.py", "docs", "README.md"]
    _, a, r, tree = tree_app(tmp_path, 'expand_all="true"')
    assert names(tree)[:5] == ["src", "app.weft", "lib", "util.py", "old.py"]
    assert a.loads == []                                               # not loaded on expand_all
    r.dispatch(find([item(tree, "lib")], cls("twisty")).events["click.stop"], {})
    tree = cycle(r, tree)
    assert "util.py" not in names(tree)


def test_load_on_demand(tmp_path):
    _, a, r, tree = tree_app(tmp_path)
    r.dispatch(find([item(tree, "docs")], cls("twisty")).events["click.stop"], {})
    tree = cycle(r, tree)
    docs = item(tree, "docs")
    assert a.loads == ["docs"] and docs.attrs["aria-busy"] == "true" and find([docs], cls("busy")) is not None
    a.FILES = a.FILES[:1] + [{"value": "docs", "label": "docs", "children": ["guide.md"]}] + a.FILES[2:]
    tree = cycle(r, tree)
    assert names(tree) == ["src", "docs", "guide.md", "README.md"] and "aria-busy" not in item(tree, "docs").attrs
    r.dispatch(find([item(tree, "docs")], cls("twisty")).events["click.stop"], {})
    tree = cycle(r, tree)
    r.dispatch(find([item(tree, "docs")], cls("twisty")).events["click.stop"], {})
    tree = cycle(r, tree)
    assert a.loads == ["docs"]                                        # asked once


def test_checkable_parents_follow_their_leaves(tmp_path):
    _, a, r, tree = tree_app(tmp_path, 'checkable="true" expand_all="true"', CODE.replace("picked = None", "picked: list = ['util', 'elsewhere']"))
    root = find(tree, lambda n: n.attrs.get("role") == "tree")
    assert root.attrs["aria-multiselectable"] == "true"
    checks = {n: item(tree, n).attrs["aria-checked"] for n in ("src", "lib", "util.py", "old.py", "app.weft")}
    assert checks == {"src": "mixed", "lib": "mixed", "util.py": "true", "old.py": "false", "app.weft": "false"}
    assert "aria-selected" not in item(tree, "src").attrs
    r.dispatch(item(tree, "src").events["click"], {})                # checks all (but the disabled leaf)
    tree = cycle(r, tree)
    assert a.picked == ["app", "util", "elsewhere"]
    assert item(tree, "lib").attrs["aria-checked"] == "mixed"        # old.py is disabled
    r.dispatch(item(tree, "src").events["click"], {})                # all enabled checked: unchecks
    tree = cycle(r, tree)
    assert a.picked == ["elsewhere"]
    r.dispatch(item(tree, "README.md").events["click"], {})
    tree = cycle(r, tree)
    assert a.picked == ["readme", "elsewhere"] and item(tree, "README.md").attrs["aria-checked"] == "true"


def test_filter_shows_matches_and_their_parents(tmp_path):
    _, a, r, tree = tree_app(tmp_path)
    a.query = "UTIL"
    tree = cycle(r, tree)
    assert names(tree) == ["src", "lib", "util.py"]
    assert text(every([item(tree, "util.py")], lambda n: n.tag == "mark")) == "util"
    a.query = "lib"                                                    # a match shows all of its children when open
    tree = cycle(r, tree)
    assert names(tree) == ["src", "lib"] and item(tree, "lib").attrs["aria-expanded"] == "false"
    a.query = "zzz"
    tree = cycle(r, tree)
    assert items(tree) == [] and text([find(tree, cls("empty"))]) == "No matches"


def test_keyboard_moves_opens_and_closes(tmp_path):
    _, a, r, tree = tree_app(tmp_path)
    tree = key(r, tree, "keydown.right.prevent")                     # opens src
    assert names(tree)[:3] == ["src", "app.weft", "lib"]
    tree = key(r, tree, "keydown.right.prevent")                     # to its first child
    assert focused(r, tree) == "app.weft"
    tree = key(r, tree, "keydown.down.prevent")
    assert focused(r, tree) == "lib"
    tree = key(r, tree, "keydown.space.prevent")                     # selects
    assert a.picked == "lib"
    tree = key(r, tree, "keydown.enter.prevent")                     # a parent: opens it
    assert "util.py" in names(tree)
    tree = key(r, tree, "keydown.left.prevent")                      # closes it
    assert "util.py" not in names(tree)
    tree = key(r, tree, "keydown.left.prevent")                      # to the parent
    assert focused(r, tree) == "src"
    tree = key(r, tree, "keydown.end.prevent")
    assert focused(r, tree) == "README.md"
    tree = key(r, tree, "keydown.down.prevent")                      # no wrap at the end
    assert focused(r, tree) == "README.md"
    tree = key(r, tree, "keydown.enter.prevent")
    assert a.activated == ["readme"]
    tree = key(r, tree, "keydown.home.prevent")
    assert focused(r, tree) == "src"


def test_type_ahead_and_star(tmp_path):
    _, a, r, tree = tree_app(tmp_path, ':expanded="[\'src\']"')
    tree = key(r, tree, "keydown", {"key": "r"})
    assert focused(r, tree) == "README.md"
    tree = key(r, tree, "keydown", {"key": "l"})                      # wraps round to lib
    assert focused(r, tree) == "lib"
    tree = key(r, tree, "keydown", {"key": "*"})                      # opens lib's siblings that are parents
    assert "util.py" in names(tree)
    tree = key(r, tree, "keydown", {"key": "ArrowDown"})              # not a letter: ignored here
    tree = key(r, tree, "keydown", {"key": "u", "ctrlKey": True})
    r.after_render()
    assert [c for c in r.take_commands() if c["op"] == "focus"] == []


def test_node_fill_and_lines(tmp_path):
    _, a, r, tree = app(tmp_path, '''<div><ui.Tree :nodes="FILES" lines="true" :expanded="['src']">
      <Fill name="node"><b class="mine">{{ node['label'] }} L{{ level }}</b></Fill>
    </ui.Tree></div>''', CODE)
    assert "lines" in find(tree, lambda n: n.attrs.get("role") == "tree").attrs["class"]
    assert [text([b]) for b in every(tree, cls("mine"))][:2] == ["src L0", "app.weft L1"]
    def drawn(name):
        (icon,) = every([item(tree, name)], cls("node-icon"))
        return find([icon], lambda n: n.tag == "path").attrs["d"]
    assert drawn("src L0").startswith("M3.5 18.5V6")                 # folder-open: src is open
    assert drawn("lib L1").startswith("M3.5 6.5V18.5")               # folder: lib is closed
