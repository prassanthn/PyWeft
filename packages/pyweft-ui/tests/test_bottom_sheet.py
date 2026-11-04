"""BottomSheet: opening, the ways it closes, items, focus, swipe."""

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


def layer(tree):
    return find(tree, cls("layer"))


def is_open(tree):
    found = layer(tree)
    return found is not None and "open" in found.attrs["class"].split()


def ops(r):
    r.after_render()
    return [c["op"] for c in r.take_commands()]


CODE = """
shown: bool = False
closes: list = []
picked: list = []
ACTIONS = [{"value": "link", "label": "Copy link", "icon": "copy"},
           {"value": "mail", "label": "Email", "description": "Opens your mail app"},
           {"value": "off", "label": "Print", "disabled": True},
           {"value": "rm", "label": "Delete", "danger": True}]
"""
SHEET = ('<div><button class="opener" @click="shown = True">Share</button>'
         '<ui.BottomSheet title="Share" @bind="shown" :items="ACTIONS" @select="picked.append(event)" '
         '@close="closes.append(event)"><p class="extra">More</p>'
         '<Fill name="actions"><button class="done" @click="shown = False">Done</button></Fill>'
         '</ui.BottomSheet></div>')


def opened(tmp_path, template=SHEET):
    _, a, r, tree = app(tmp_path, template, CODE)
    assert layer(tree) is None            # nothing on the page until first opened
    r.dispatch(find(tree, cls("opener")).events["click"], {})
    tree = cycle(r, tree)
    return a, r, tree


def test_opens_with_title_items_content_and_focus(tmp_path):
    a, r, tree = opened(tmp_path)
    assert is_open(tree) and "inert" not in layer(tree).attrs
    sheet = find(tree, cls("sheet"))
    assert sheet.attrs["role"] == "dialog" and sheet.attrs["aria-modal"] == "true"
    assert sheet.attrs["aria-label"] == "Share" and sheet.attrs["style"] == "max-width: 40rem"
    assert text([find(tree, cls("title"))]) == "Share" and find(tree, cls("handle")) is not None
    labels = [text(every([i], cls("label"))) for i in every(tree, cls("item"))]
    assert labels == ["Copy link", "Email", "Print", "Delete"]
    items = every(tree, cls("item"))
    assert "disabled" in items[2].attrs and "danger" in items[3].attrs["class"]
    assert text(every([items[1]], cls("desc"))) == "Opens your mail app"
    assert text([find(tree, cls("extra"))]) == "More" and find(tree, cls("done")) is not None
    assert ops(r) == ["save_focus", "focus"]


def test_choosing_an_item_selects_and_closes(tmp_path):
    a, r, tree = opened(tmp_path)
    ops(r)
    r.dispatch(every(tree, cls("item"))[0].events["click"], {})
    tree = cycle(r, tree)
    assert a.picked == ["link"] and a.closes == ["select"] and a.shown is False
    # Still on the page, closed: hidden and inert so it can slide away.
    assert layer(tree) is not None and not is_open(tree) and "inert" in layer(tree).attrs
    assert ops(r) == ["restore_focus"]


def test_esc_backdrop_and_own_buttons(tmp_path):
    a, r, tree = opened(tmp_path)
    r.dispatch(layer(tree).events["keydown.esc.stop"], {})
    tree = cycle(r, tree)
    assert a.closes == ["esc"] and not is_open(tree)
    r.dispatch(find(tree, cls("opener")).events["click"], {})
    tree = cycle(r, tree)
    assert is_open(tree)
    r.dispatch(find(tree, cls("backdrop")).events["click"], {})
    tree = cycle(r, tree)
    assert a.closes == ["esc", "backdrop"]
    r.dispatch(find(tree, cls("opener")).events["click"], {})
    tree = cycle(r, tree)
    r.dispatch(find(tree, cls("done")).events["click"], {})
    tree = cycle(r, tree)
    assert not is_open(tree) and a.closes == ["esc", "backdrop"]   # the app closed it: no event


def test_swipe_down_closes_a_small_drag_does_not(tmp_path):
    a, r, tree = opened(tmp_path)
    grip = find(tree, cls("grip"))
    assert "grabbable" in grip.attrs["class"]
    r.dispatch(grip.events["pointerdown"], {"clientY": 400})
    r.dispatch(layer(tree).events["pointerup"], {"clientY": 430})
    tree = cycle(r, tree)
    assert is_open(tree)
    r.dispatch(grip.events["pointerdown"], {"clientY": 400})
    r.dispatch(layer(tree).events["pointercancel"], {})
    r.dispatch(layer(tree).events["pointerup"], {"clientY": 600})   # no grab any more
    tree = cycle(r, tree)
    assert is_open(tree)
    r.dispatch(layer(tree).events["pointerup"], {"clientY": 900})    # up without a grab
    tree = cycle(r, tree)
    assert is_open(tree)
    r.dispatch(find(tree, cls("grip")).events["pointerdown"], {"clientY": 400})
    r.dispatch(layer(tree).events["pointerup"], {"clientY": 470})
    tree = cycle(r, tree)
    assert not is_open(tree) and a.closes == ["swipe"]


def test_not_dismissible(tmp_path):
    a, r, tree = opened(tmp_path, SHEET.replace('title="Share"', 'title="Share" dismissible="false"'))
    assert find(tree, cls("handle")) is None and "grabbable" not in find(tree, cls("grip")).attrs["class"]
    r.dispatch(layer(tree).events["keydown.esc.stop"], {})
    r.dispatch(find(tree, cls("backdrop")).events["click"], {})
    r.dispatch(find(tree, cls("grip")).events["pointerdown"], {"clientY": 0})
    r.dispatch(layer(tree).events["pointerup"], {"clientY": 500})
    tree = cycle(r, tree)
    assert is_open(tree) and a.closes == []
    r.dispatch(every(tree, cls("item"))[3].events["click"], {})       # an item still closes it
    tree = cycle(r, tree)
    assert not is_open(tree) and a.closes == ["select"]


def test_content_only_sheet_without_title(tmp_path):
    a, r, tree = opened(tmp_path, '<div><button class="opener" @click="shown = True">x</button>'
                                  '<ui.BottomSheet aria_label="Filters" max_width="30rem" @bind="shown">'
                                  '<p class="extra">Body</p></ui.BottomSheet></div>')
    sheet = find(tree, cls("sheet"))
    assert sheet.attrs["aria-label"] == "Filters" and sheet.attrs["style"] == "max-width: 30rem"
    assert find(tree, cls("title")) is None and find(tree, cls("items")) is None
    assert find(tree, cls("actions")) is None and text([find(tree, cls("extra"))]) == "Body"
