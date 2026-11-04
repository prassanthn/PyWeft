"""Menu: submenus, headings, custom items and triggers, opening above; and
ContextMenu."""

from pyweft.vdom import Element

from test_controls import app, cls, cycle, find, tag, text


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


def menus(tree):
    return every(tree, lambda n: n.attrs.get("role") == "menu")


def items(menu):
    return [e.children[0] for e in menu.children if e.attrs.get("role") == "none"]


def label(n):
    return text(every([n], cls("label"))).strip() or text([n]).strip()


def commands(r):
    r.after_render()
    return r.take_commands()


def focused(r, tree):
    found = [c for c in commands(r) if c["op"] == "focus"]
    assert found, "no focus request"
    node, nodes = None, tree
    for index in found[-1]["path"]:
        node = nodes[index]
        nodes = node.children
    return node


def key(r, tree, menu, name):
    r.dispatch(menu.events[f"keydown.{name}.prevent.stop"], {"type": "keydown"})
    return cycle(r, tree)


CODE = """
chosen: list = []
items: list = [
    {"heading": "File"},
    {"value": "new", "label": "New", "icon": "plus", "hint": "Ctrl+N"},
    {"label": "Share", "icon": "send", "items": [
        "Email",
        {"label": "Social", "items": ["Mastodon", ("bsky", "Bluesky")]},
        {"value": "x", "label": "Gone", "disabled": True},
    ]},
    "-",
    {"value": "rm", "label": "Delete", "description": "Can't be undone", "danger": True},
]
"""
MENU = '<div><ui.Menu label="File" :items="items" @select="chosen.append(event)" /></div>'


def open_menu(tmp_path, template=MENU, code=CODE):
    _, a, r, tree = app(tmp_path, template, code)
    r.dispatch(find(tree, tag("button")).events["click"], {})
    return a, r, cycle(r, tree)


def test_headings_hints_and_descriptions(tmp_path):
    a, r, tree = open_menu(tmp_path)
    (menu,) = menus(tree)
    assert text(every([menu], cls("heading"))) == "File"
    assert every([menu], cls("heading"))[0].attrs["role"] == "presentation"
    new, share, delete = items(menu)
    assert text(every([new], cls("hint"))) == "Ctrl+N"
    assert text(every([delete], cls("desc"))) == "Can't be undone"
    assert share.attrs["aria-haspopup"] == "menu" and share.attrs["aria-expanded"] == "false"
    assert "aria-haspopup" not in new.attrs
    assert label(focused(r, tree)) == "New"  # headings aren't stops


def test_submenu_by_click_and_choose_deep(tmp_path):
    a, r, tree = open_menu(tmp_path)
    share = items(menus(tree)[0])[1]
    r.dispatch(share.events["click"], {})
    tree = cycle(r, tree)
    root, sub = menus(tree)
    assert items(root)[1].attrs["aria-expanded"] == "true" and "expanded" in items(root)[1].attrs["class"]
    assert sub.attrs["aria-label"] == "Share" and "sub-right" in sub.attrs["class"]
    assert [label(i) for i in items(sub)] == ["Email", "Social", "Gone"]
    assert label(focused(r, tree)) == "Email"
    r.dispatch(items(sub)[1].events["mouseenter"], {})   # hover opens, without focus
    tree = cycle(r, tree)
    assert len(menus(tree)) == 3 and not [c for c in commands(r) if c["op"] == "focus"]
    deepest = menus(tree)[2]
    r.dispatch(items(deepest)[1].events["click"], {})
    tree = cycle(r, tree)
    assert a.chosen == ["bsky"] and menus(tree) == []
    assert focused(r, tree).attrs["aria-haspopup"] == "menu"  # back on the trigger


def test_submenu_keyboard_right_left_and_esc(tmp_path):
    a, r, tree = open_menu(tmp_path)
    root = menus(tree)[0]
    tree = key(r, tree, root, "down")
    assert label(focused(r, tree)) == "Share"
    tree = key(r, tree, menus(tree)[0], "right")
    assert len(menus(tree)) == 2 and label(focused(r, tree)) == "Email"
    sub = menus(tree)[1]
    tree = key(r, tree, sub, "up")                      # wraps, skipping Gone
    assert label(focused(r, tree)) == "Social"
    tree = key(r, tree, menus(tree)[1], "right")
    assert len(menus(tree)) == 3 and label(focused(r, tree)) == "Mastodon"
    tree = key(r, tree, menus(tree)[2], "left")          # back one level
    assert len(menus(tree)) == 2 and label(focused(r, tree)) == "Social"
    tree = key(r, tree, menus(tree)[1], "left")
    assert len(menus(tree)) == 1 and label(focused(r, tree)) == "Share"
    tree = key(r, tree, menus(tree)[0], "left")          # nothing at the top
    assert len(menus(tree)) == 1
    tree = key(r, tree, menus(tree)[0], "right")
    r.dispatch(menus(tree)[1].events["keydown.esc.stop"], {})
    tree = cycle(r, tree)
    assert menus(tree) == [] and a.chosen == []
    assert focused(r, tree).attrs["aria-haspopup"] == "menu"


def test_hovering_another_item_closes_the_submenu(tmp_path):
    a, r, tree = open_menu(tmp_path)
    r.dispatch(items(menus(tree)[0])[1].events["mouseenter"], {})
    tree = cycle(r, tree)
    assert len(menus(tree)) == 2
    r.dispatch(items(menus(tree)[0])[0].events["mouseenter"], {})
    tree = cycle(r, tree)
    assert len(menus(tree)) == 1


def test_align_end_opens_submenus_left_and_position_above(tmp_path):
    a, r, tree = open_menu(tmp_path, '<div><ui.Menu label="File" align="end" position="above" :items="items" /></div>')
    assert "pos-above" in find(tree, cls("menu")).attrs["class"]
    r.dispatch(items(menus(tree)[0])[1].events["click"], {})
    tree = cycle(r, tree)
    assert "sub-left" in menus(tree)[1].attrs["class"]


def test_custom_items_reach_submenus_and_custom_trigger(tmp_path):
    template = '''<div><ui.Menu label="Account" :items="items" @select="chosen.append(event)">
      <Fill name="trigger"><img class="avatar" src="me.png" alt="" /></Fill>
      <Fill name="item"><b class="mine">{{ item['label'] }}</b><If cond="item['items']"> &gt;</If></Fill>
    </ui.Menu></div>'''
    _, a, r, tree = app(tmp_path, template, CODE)
    trigger = find(tree, tag("button"))
    assert "bare" in trigger.attrs["class"] and trigger.attrs["aria-label"] == "Account"
    assert find([trigger], cls("avatar")) is not None
    r.dispatch(trigger.events["click"], {})
    tree = cycle(r, tree)
    assert [text([b]) for b in every(tree, cls("mine"))] == ["New", "Share", "Delete"]
    r.dispatch(items(menus(tree)[0])[1].events["click"], {})
    tree = cycle(r, tree)
    assert [text([b]) for b in every([menus(tree)[1]], cls("mine"))] == ["Email", "Social", "Gone"]


def test_menu_keeps_lists_in_view(tmp_path):
    a, r, tree = open_menu(tmp_path)
    found = [c for c in commands(r) if c["op"] == "keep_in_view"]
    assert found and "vertical" not in found[0]          # the drop-down: sideways only
    r.dispatch(items(menus(tree)[0])[1].events["click"], {})
    tree = cycle(r, tree)
    found = [c for c in commands(r) if c["op"] == "keep_in_view"]
    assert found and found[0]["vertical"] is True        # a submenu: up and down too


# ------------------------------------------------------------------ ContextMenu

CTX = '''<div><ui.ContextMenu :items="items" @select="chosen.append(event)" @open="opens.append(1)">
  <p class="zone">Right-click me</p>
</ui.ContextMenu></div>'''


def test_context_menu_opens_at_the_pointer(tmp_path):
    _, a, r, tree = app(tmp_path, CTX, CODE + "opens: list = []\n")
    area = find(tree, cls("area"))
    assert text(every([area], cls("zone"))) == "Right-click me" and menus(tree) == []
    r.dispatch(area.events["contextmenu.prevent"], {"type": "contextmenu", "clientX": 120, "clientY": 340})
    tree = cycle(r, tree)
    (menu,) = menus(tree)
    assert "at-pointer" in menu.attrs["class"] and menu.attrs["style"] == "left: 120px; top: 340px"
    assert menu.attrs["aria-label"] == "Actions" and a.opens == [1]
    ops = commands(r)
    assert ops[0]["op"] == "save_focus"
    assert any(c["op"] == "keep_in_view" and c.get("vertical") for c in ops)
    r.dispatch(items(menu)[0].events["click"], {})
    tree = cycle(r, tree)
    assert a.chosen == ["new"] and menus(tree) == []
    assert commands(r) == [{"op": "restore_focus"}]


def test_context_menu_from_the_keyboard_and_closing(tmp_path):
    _, a, r, tree = app(tmp_path, CTX, CODE + "opens: list = []\n")
    area = find(tree, cls("area"))
    r.dispatch(area.events["keydown.f10.shift.prevent"], {"type": "keydown"})
    tree = cycle(r, tree)
    (menu,) = menus(tree)
    assert "at-pointer" not in menu.attrs["class"] and "style" not in menu.attrs
    assert label(focused(r, tree)) == "New"
    r.dispatch(menu.events["keydown.tab.stop"], {})
    tree = cycle(r, tree)
    assert menus(tree) == [] and commands(r) == []      # Tab moves on: focus not restored
    r.dispatch(find(tree, cls("area")).events["keydown.context-menu.prevent"], {})
    tree = cycle(r, tree)
    r.dispatch(find(tree, cls("backdrop")).events["click"], {})
    tree = cycle(r, tree)
    assert menus(tree) == [] and a.chosen == []


def test_disabled_context_menu_leaves_the_browser_menu(tmp_path):
    _, a, r, tree = app(tmp_path, '<div><ui.ContextMenu disabled="true" :items="items"><p>x</p></ui.ContextMenu>'
                                  '<ui.ContextMenu><p>y</p></ui.ContextMenu></div>', CODE)
    assert all(not a_.events for a_ in every(tree, cls("area")))
