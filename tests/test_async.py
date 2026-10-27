"""Async handlers, async lifecycle hooks, start_task, cancellation, errors."""

import asyncio
import gc
import warnings

import pytest

import pyweft.renderer as renderer_module
from pyweft import Renderer, component_from_source, effect
from pyweft.vdom import Element


def text(nodes):
    out = []
    for node in nodes:
        if isinstance(node, Element):
            out.append(text(node.children))
        else:
            out.append(node.text)
    return "".join(out)


def find_events(nodes, event):
    """Handler ids for ``event``, in document order."""
    found = []
    for node in nodes:
        if isinstance(node, Element):
            if event in node.events:
                found.append(node.events[event])
            found.extend(find_events(node.children, event))
    return found


@pytest.fixture(params=["eager", "lazy"])
def start_mode(request, monkeypatch):
    """Every behaviour must hold whether tasks start eagerly (3.12+) or on
    the loop's next pass (3.10/3.11, or a loop that is not running)."""
    if request.param == "eager" and not renderer_module._EAGER:
        pytest.skip("eager tasks need Python 3.12+")
    monkeypatch.setattr(renderer_module, "_EAGER", request.param == "eager")
    return request.param


LOADER = """
<template><p><button @click="load">go</button>{{ status }}</p></template>
<code>
import asyncio
status: str = "idle"
gate = None

async def load(self):
    self.status = "loading"
    await self.gate.wait()
    self.status = "done"
</code>
"""


def make(src, **components):
    return component_from_source(src, "App", components=components or None)


# ------------------------------------------------------------ async handlers


def test_async_handler_renders_before_and_after_await(start_mode):
    async def main():
        app = make(LOADER)()
        app.gate = asyncio.Event()
        r = Renderer(app)
        invalidations = []
        r.on_invalidate = lambda: invalidations.append(1)

        (click,) = find_events(r.render(), "click")
        r.dispatch(click, {})
        if start_mode == "lazy":
            await asyncio.sleep(0)  # the first step runs on the next pass
        assert "loading" in text(r.render())
        assert r.pending_tasks()

        app.gate.set()
        await r.idle()
        assert not r.pending_tasks()
        assert invalidations, "a finished task must ask the host to render"
        assert r.needs_render()
        assert "done" in text(r.render())

    asyncio.run(main())


def test_eager_start_needs_no_extra_render_for_the_first_step():
    if not renderer_module._EAGER:
        pytest.skip("eager tasks need Python 3.12+")

    async def main():
        app = make(LOADER)()
        app.gate = asyncio.Event()
        r = Renderer(app)
        invalidations = []
        r.on_invalidate = lambda: invalidations.append(1)
        (click,) = find_events(r.render(), "click")
        r.dispatch(click, {})
        # "loading" was set inside dispatch, so the host's render covers it.
        assert app.status == "loading" and invalidations == []
        app.gate.set()
        await r.idle()

    asyncio.run(main())


def test_handler_that_never_suspends_finishes_inside_dispatch(start_mode):
    src = """
<template><button @click="go">{{ n }}</button></template>
<code>
n: int = 0
async def go(self):
    self.n += 1
</code>
"""

    async def main():
        app = make(src)()
        r = Renderer(app)
        (click,) = find_events(r.render(), "click")
        r.dispatch(click, {})
        await r.idle()
        assert app.n == 1 and not r.pending_tasks()
        assert text(r.render()) == "1"

    asyncio.run(main())


def test_expression_handler_with_loop_variable(start_mode):
    src = """
<template><ul><For each="x in items" key="x"><li @click="pick(x)">{{ x }}</li></For></ul>
<p>{{ picked }}</p></template>
<code>
import asyncio
items: list = ["a", "b", "c"]
picked: str = ""
async def pick(self, x):
    await asyncio.sleep(0)
    self.picked = x
</code>
"""

    async def main():
        app = make(src)()
        r = Renderer(app)
        clicks = find_events(r.render(), "click")
        r.dispatch(clicks[1], {})
        await r.idle()
        assert app.picked == "b"

    asyncio.run(main())


def test_awaitable_that_is_not_a_coroutine(start_mode):
    src = """
<template><button @click="go">{{ value }}</button></template>
<code>
value = None
future = None
def go(self):
    return self.future
</code>
"""

    async def main():
        app = make(src)()
        app.future = asyncio.get_running_loop().create_future()
        r = Renderer(app)
        (click,) = find_events(r.render(), "click")
        r.dispatch(click, {})
        assert r.pending_tasks()
        app.future.set_result(5)
        await r.idle()
        assert not r.pending_tasks()

    asyncio.run(main())


def test_child_emit_to_async_parent_handler(start_mode):
    child = make(
        '<template><button @click="emit(\'save\', 7)">save</button></template><code></code>'
    )
    parent_src = """
<template><div><Child @save="store(event)" /><p>{{ saved }}</p></div></template>
<code>
import asyncio
saved: int = 0
async def store(self, value):
    await asyncio.sleep(0)
    self.saved = value
</code>
"""

    async def main():
        app = make(parent_src, Child=child)()
        r = Renderer(app)
        (click,) = find_events(r.render(), "click")
        r.dispatch(click, {})
        await r.idle()
        assert app.saved == 7
        assert "7" in text(r.render())

    asyncio.run(main())


# --------------------------------------------------------- lifecycle hooks


def test_async_on_init_of_child(start_mode):
    child_src = """
<template><span>{{ data }}</span></template>
<code>
import asyncio
data: str = "loading"
async def on_init(self):
    await asyncio.sleep(0)
    self.data = "loaded"
</code>
"""

    async def main():
        app = make("<template><div><Child /></div></template><code></code>",
                   Child=make(child_src))()
        r = Renderer(app)
        assert text(r.render()) == "loading"
        await r.idle()
        assert r.needs_render()
        assert text(r.render()) == "loaded"

    asyncio.run(main())


def test_async_on_init_of_root_via_init_root(start_mode):
    src = """
<template><p>{{ data }}</p></template>
<code>
import asyncio
data: str = ""
async def on_init(self):
    self.data = "loading"
    await asyncio.sleep(0)
    self.data = "loaded"
</code>
"""

    async def main():
        app = make(src)()
        r = Renderer(app)
        r.init_root()
        if start_mode == "lazy":
            await asyncio.sleep(0)
        assert text(r.render()) == "loading"
        await r.idle()
        assert text(r.render()) == "loaded"

    asyncio.run(main())


def test_init_root_with_plain_on_init():
    src = """
<template><p>{{ n }}</p></template>
<code>
n: int = 0
def on_init(self):
    self.n = 3
</code>
"""
    app = make(src)()
    r = Renderer(app)
    r.init_root()  # no event loop needed for a synchronous on_init
    assert text(r.render()) == "3"


def test_async_on_after_render(start_mode):
    src = """
<template><p>{{ seen }}</p></template>
<code>
import asyncio
seen: int = 0
async def on_after_render(self, first):
    if first:
        await asyncio.sleep(0)
        self.seen += 1
</code>
"""

    async def main():
        app = make(src)()
        r = Renderer(app)
        r.render()
        r.after_render()
        await r.idle()
        assert app.seen == 1 and r.needs_render()

    asyncio.run(main())


# ------------------------------------------------------------- start_task


def test_start_task_from_handler_and_on_init(start_mode):
    src = """
<template><p><button @click="more">+</button>{{ ticks }}</p></template>
<code>
import asyncio
ticks: int = 0
async def tick(self):
    await asyncio.sleep(0)
    self.ticks += 1
def on_init(self):
    self.start_task(self.tick())
def more(self):
    self.start_task(self.tick())
</code>
"""

    async def main():
        app = make(src)()
        r = Renderer(app)
        r.init_root()
        (click,) = find_events(r.render(), "click")
        r.dispatch(click, {})
        await r.idle()
        assert app.ticks == 2

    asyncio.run(main())


def test_start_task_before_render_is_a_clear_error(recwarn):
    app = make(LOADER)()
    with pytest.raises(RuntimeError, match="on_init or later"):
        app.start_task(app.load())
    gc.collect()
    assert not [w for w in recwarn if "never awaited" in str(w.message)]


def test_idle_waits_for_tasks_started_by_tasks(start_mode):
    src = """
<template><p>{{ steps }}</p></template>
<code>
import asyncio
steps: list = []
async def first(self):
    await asyncio.sleep(0)
    self.steps.append(1)
    self.start_task(self.second())
async def second(self):
    await asyncio.sleep(0)
    self.steps.append(2)
</code>
"""

    async def main():
        app = make(src)()
        r = Renderer(app)
        r.render()
        app.start_task(app.first())
        await r.idle()
        assert app.steps == [1, 2]

    asyncio.run(main())


# ----------------------------------------------------------- cancellation


ROW = """
<template><li>{{ state }}</li></template>
<code>
import asyncio
state: str = "waiting"
log = None
async def on_init(self):
    try:
        await asyncio.sleep(10)
        self.state = "finished"
    except asyncio.CancelledError:
        self.log.append("cancelled")
        raise
def on_dispose(self):
    self.log.append("disposed")
</code>
"""


def test_removed_component_has_its_tasks_cancelled(start_mode):
    list_src = """
<template><ul><If cond="show"><Row :log="log" /></If></ul></template>
<code>
show: bool = True
log = None
</code>
"""

    async def main():
        log = []
        app = make(list_src, Row=make(ROW))()
        app.log = log
        r = Renderer(app)
        r.render()
        await asyncio.sleep(0)
        assert len(r.pending_tasks()) == 1
        invalidations = []
        r.on_invalidate = lambda: invalidations.append(1)

        app.show = False
        r.render()
        await asyncio.sleep(0)
        assert log == ["disposed", "cancelled"] or log == ["cancelled", "disposed"]
        assert not r.pending_tasks()
        assert invalidations == []  # a cancelled task requests no render

    asyncio.run(main())


def test_start_task_after_removal_is_an_error(start_mode):
    list_src = """
<template><ul><If cond="show"><Row :log="log" /></If></ul></template>
<code>
show: bool = True
log = None
</code>
"""

    async def main():
        app = make(list_src, Row=make(ROW))()
        app.log = []
        r = Renderer(app)
        r.render()
        (row,) = r.instances.values()
        app.show = False
        r.render()
        with pytest.raises(RuntimeError, match="not yet removed"):
            row.start_task(asyncio.sleep(0))

    asyncio.run(main())


# ------------------------------------------------------------------ errors


FAILING = """
<template><button @click="go">{{ status }}</button></template>
<code>
import asyncio
status: str = "idle"
async def go(self):
    self.status = "working"
    await asyncio.sleep(0)
    raise ValueError("backend down")
</code>
"""


def test_task_error_goes_to_on_error_and_state_still_renders(start_mode):
    async def main():
        app = make(FAILING)()
        r = Renderer(app)
        errors = []
        r.on_error = errors.append
        (click,) = find_events(r.render(), "click")
        r.dispatch(click, {})
        await r.idle()
        assert [str(e) for e in errors] == ["backend down"]
        assert r.needs_render() and "working" in text(r.render())

    asyncio.run(main())


def test_error_before_first_await_goes_to_on_error(start_mode):
    src = """
<template><button @click="go">x</button></template>
<code>
async def go(self):
    raise KeyError("early")
</code>
"""

    async def main():
        app = make(src)()
        r = Renderer(app)
        errors = []
        r.on_error = errors.append
        (click,) = find_events(r.render(), "click")
        r.dispatch(click, {})  # does not raise: it is the task's error
        await r.idle()
        await asyncio.sleep(0)
        assert len(errors) == 1 and isinstance(errors[0], KeyError)

    asyncio.run(main())


def test_task_error_without_on_error_reaches_loop_handler(start_mode):
    async def main():
        seen = []
        asyncio.get_running_loop().set_exception_handler(lambda loop, ctx: seen.append(ctx))
        app = make(FAILING)()
        r = Renderer(app)
        (click,) = find_events(r.render(), "click")
        r.dispatch(click, {})
        await r.idle()
        assert len(seen) == 1 and str(seen[0]["exception"]) == "backend down"

    asyncio.run(main())


def test_async_handler_without_event_loop_is_a_clear_error(recwarn):
    app = make(LOADER)()
    r = Renderer(app)
    (click,) = find_events(r.render(), "click")
    with pytest.raises(RuntimeError, match="asyncio.run"):
        r.dispatch(click, {})
    gc.collect()
    assert not [w for w in recwarn if "never awaited" in str(w.message)]


# ----------------------------------------------------------------- effects


def test_async_effect_is_rejected_at_definition():
    with pytest.raises(TypeError, match="cannot be async"):

        @effect
        async def load(self):
            pass


def test_effect_returning_a_coroutine_is_rejected(recwarn):
    src = """
<template><p>x</p></template>
<code>
from pyweft import effect
import asyncio
@effect
def sneaky(self):
    return asyncio.sleep(0)
</code>
"""
    app = make(src)()
    r = Renderer(app)
    r.render()
    with pytest.raises(TypeError, match="cannot be async"):
        r.after_render()
    gc.collect()
    assert not [w for w in recwarn if "never awaited" in str(w.message)]


def test_effect_starting_a_task_latest_wins(start_mode):
    src = """
<template><p>{{ results }}</p></template>
<code>
import asyncio
from pyweft import effect
query: str = "a"
results: str = ""
started: list = []

async def search(self, q):
    self.started.append(q)
    await asyncio.sleep(0.01)
    self.results = q.upper()

@effect
def on_query(self):
    task = self.start_task(self.search(self.query))
    return task.cancel
</code>
"""

    async def main():
        app = make(src)()
        r = Renderer(app)
        r.render()
        r.after_render()
        app.query = "ab"
        app.state_has_changed()
        r.render()
        r.after_render()  # cancels the "a" search, starts "ab"
        await r.idle()
        assert app.results == "AB"

    asyncio.run(main())
