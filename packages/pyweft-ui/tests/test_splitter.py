"""ui.Splitter and AppShell's resizable sidebar."""

import pytest

from pyweft import Renderer, component_from_source, storage
from pyweft.vdom import Element

TWO = """
<template><div><ui.Splitter @bind="sizes" {extra}>
  <Fill name="first"><p>a</p></Fill><Fill name="second"><p>b</p></Fill>{third}
</ui.Splitter></div></template>
<code>
from pyweft_ui import ui
sizes = None
</code>
"""


@pytest.fixture(autouse=True)
def fresh_storage():
    storage.set_host(storage.MemoryStorage())
    yield
    storage.set_host(storage.MemoryStorage())


def mount(extra="", third=False, **state):
    src = TWO.format(extra=extra, third='<Fill name="third"><p>c</p></Fill>' if third else "")
    app = component_from_source(src, "App")(**state)
    r = Renderer(app)
    r.init_root()
    r.render()
    return app, r


def walk(nodes):
    for n in nodes:
        if isinstance(n, Element):
            yield n
            yield from walk(n.children)


def parts(r):
    nodes = list(walk(r._tree))
    panes = [n for n in nodes if n.attrs.get("class", "").startswith("pane")]
    dividers = [n for n in nodes if n.attrs.get("class") == "divider"]
    return panes, dividers


def test_equal_by_default_and_rendered_for_the_runtime():
    app, r = mount()
    panes, dividers = parts(r)
    assert [p.attrs["style"] for p in panes] == ["flex: 50 1 0; min-width: 10%"] * 2
    (d,) = dividers
    assert "data-pw-splitter" in d.attrs and "split" in d.events
    assert (d.attrs["role"], d.attrs["aria-valuenow"], d.attrs["aria-orientation"]) == ("separator", "50", "vertical")
    assert d.attrs["aria-controls"] == panes[0].attrs["id"]


def test_dragging_sets_the_pair_and_respects_limits():
    app, r = mount()
    (d,) = parts(r)[1]
    r.dispatch(d.events["split"], {"type": "split", "ratio": 0.3, "before": 300, "after": 700})
    assert app.sizes == [30.0, 70.0]
    r.render()
    (d,) = parts(r)[1]
    r.dispatch(d.events["split"], {"type": "split", "ratio": 0.02, "before": 20, "after": 980})
    assert app.sizes == [10.0, 90.0]  # min 10, max 90


def test_keyboard():
    app, r = mount(':sizes="[40, 60]"')
    (d,) = parts(r)[1]
    r.dispatch(d.events["keydown.right.prevent"], {"type": "keydown", "key": "ArrowRight"})
    assert app.sizes == [45.0, 55.0]
    r.render()
    (d,) = parts(r)[1]
    r.dispatch(d.events["keydown.end.prevent"], {"type": "keydown", "key": "End"})
    assert app.sizes == [90.0, 10.0]
    r.render()
    (d,) = parts(r)[1]
    r.dispatch(d.events["keydown.home.prevent"], {"type": "keydown", "key": "Home"})
    assert app.sizes == [10.0, 90.0]


def test_collapse_and_restore():
    app, r = mount('collapsible="true" :sizes="[30, 70]"')
    (d,) = parts(r)[1]
    r.dispatch(d.events["keydown.enter.prevent"], {"type": "keydown", "key": "Enter"})
    assert app.sizes == [0, 100.0]
    r.render()
    panes, (d,) = parts(r)
    assert "collapsed" in panes[0].attrs["class"] and "inert" in panes[0].attrs
    assert panes[0].attrs["style"] == "flex: 0 1 0; min-width: 0"
    r.dispatch(d.events["dblclick"], {"type": "dblclick"})
    assert app.sizes == [30.0, 70.0]


def test_not_collapsible_ignores_enter():
    app, r = mount()
    (d,) = parts(r)[1]
    r.dispatch(d.events["keydown.enter.prevent"], {"type": "keydown", "key": "Enter"})
    assert app.sizes is None


def test_three_panes():
    app, r = mount(third=True)
    panes, dividers = parts(r)
    assert len(panes) == 3 and len(dividers) == 2
    r.dispatch(dividers[1].events["split"], {"type": "split", "ratio": 0.25, "before": 10, "after": 30})
    # The first pane keeps its third; the other two share theirs 1:3.
    assert app.sizes == [pytest.approx(100 / 3), 16.67, 50.0]


def test_vertical_and_height():
    app, r = mount('direction="vertical" height="300px"')
    (root,) = [n for n in walk(r._tree) if n.attrs.get("class", "").startswith("splitter")]
    assert "vertical" in root.attrs["class"] and root.attrs["style"] == "height: 300px"
    panes, (d,) = parts(r)
    assert panes[0].attrs["style"].endswith("min-height: 10%")
    assert d.attrs["aria-orientation"] == "horizontal"


def test_stacks_when_narrow():
    app, r = mount()
    (root,) = [n for n in walk(r._tree) if n.attrs.get("class", "").startswith("splitter")]
    r.dispatch(root.events["resize"], {"type": "resize", "width": 400, "height": 300})
    r.render()
    panes, dividers = parts(r)
    assert dividers == [] and all("style" not in p.attrs for p in panes)


def test_remembered_between_visits():
    app, r = mount('storage_key="mail"')
    (d,) = parts(r)[1]
    r.dispatch(d.events["split"], {"type": "split", "ratio": 0.35, "before": 35, "after": 65})
    assert storage.get("ui-splitter:mail") == [35.0, 65.0]
    app2, r2 = mount('storage_key="mail"')
    assert parts(r2)[1][0].attrs["aria-valuenow"] == "35"


# ------------------------------------------------------------------ AppShell

SHELL = """
<template><ui.AppShell title="t" {extra}><Fill name="nav"><p>nav</p></Fill><p>main</p></ui.AppShell></template>
<code>
from pyweft_ui import ui
</code>
"""


def shell(extra=""):
    app = component_from_source(SHELL.format(extra=extra), "App")()
    r = Renderer(app)
    r.init_root()
    r.render()
    return r


def test_app_shell_sidebar_is_fixed_unless_resizable():
    r = shell()
    assert not [n for n in walk(r._tree) if "data-pw-splitter" in n.attrs]
    r = shell('resizable_nav="true" nav_width="260"')
    (side,) = [n for n in walk(r._tree) if n.tag == "nav"]
    assert "resizable" in side.attrs["class"] and "--nav-width: 260px" in side.attrs["style"]
    (d,) = [n for n in walk(r._tree) if "data-pw-splitter" in n.attrs]
    r.dispatch(d.events["split"], {"type": "split", "ratio": 0.2, "before": 333, "after": 900})
    r.render()
    (side,) = [n for n in walk(r._tree) if n.tag == "nav"]
    assert "--nav-width: 333px" in side.attrs["style"]
    assert storage.get("ui-app-shell:nav-width") == 333
    (d,) = [n for n in walk(r._tree) if "data-pw-splitter" in n.attrs]
    r.dispatch(d.events["keydown.end.prevent"], {"type": "keydown", "key": "End"})
    r.render()
    (side,) = [n for n in walk(r._tree) if n.tag == "nav"]
    assert "--nav-width: 480px" in side.attrs["style"]  # nav_max
    # A new visit starts where the last one left off.
    r2 = shell('resizable_nav="true"')
    (side,) = [n for n in walk(r2._tree) if n.tag == "nav"]
    assert "--nav-width: 480px" in side.attrs["style"]
