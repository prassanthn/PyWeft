"""<Await task=...>: pending content, <Then>, <Catch>, restarts and cleanup."""

import asyncio

import pytest

import pyweft.renderer as renderer_module
from pyweft import Renderer, component_from_source
from pyweft.check import check_app
from pyweft.parser import TAwait, TemplateError, parse_template
from pyweft.vdom import Element


def text(nodes):
    return "".join(text(n.children) if isinstance(n, Element) else n.text for n in nodes)


def events(nodes, event):
    found = []
    for node in nodes:
        if isinstance(node, Element):
            if event in node.events:
                found.append(node.events[event])
            found.extend(events(node.children, event))
    return found


@pytest.fixture(params=["eager", "lazy"])
def start_mode(request, monkeypatch):
    if request.param == "eager" and not renderer_module._EAGER:
        pytest.skip("eager tasks need Python 3.12+")
    monkeypatch.setattr(renderer_module, "_EAGER", request.param == "eager")
    return request.param


def make(src):
    return component_from_source(src, "App")


USER = """
<template>
  <div>
    <Await task="load(user_id)" key="user_id">
      <p>loading {{ user_id }}</p>
      <Then as="user"><p>hello {{ user }}</p></Then>
      <Catch as="err"><p>failed: {{ err }}</p></Catch>
    </Await>
    <button @click="user_id += 1">next</button>
  </div>
</template>
<code>
import asyncio
user_id: int = 1
calls: list = []
gate = None

async def load(self, uid):
    self.calls.append(uid)
    await self.gate.wait()
    if uid == 3:
        raise ValueError("no such user")
    return f"user{uid}"
</code>
"""


def test_parse_blocks():
    (node,) = parse_template(
        '<Await task="f()" key="k">wait <Then as="v">{{ v }}</Then><Catch>{{ error }}</Catch> more</Await>'
    )
    assert isinstance(node, TAwait)
    assert node.task == "f()" and node.key_expr == "k"
    assert node.then_var == "v" and node.catch_var == "error"
    assert [p.parts for p in node.pending] == [[("static", "wait  more")]]
    (only,) = parse_template('<Await task="f()"><Then>x</Then></Await>')
    assert only.then_var == "value" and only.catch is None and only.pending == []


@pytest.mark.parametrize("src, message", [
    ("<Await>x</Await>", "requires task="),
    ('<Await task="f()" each="x">x</Await>', "only task= and key="),
    ('<Await task="f()"><Then>a</Then><Then>b</Then></Await>', "two <Then>"),
    ('<Await task="f()"><Then as="a b">a</Then></Await>', "Python name"),
    ('<Await task="f()"><Catch key="x">a</Catch></Await>', "only as="),
    ("<div><Then>x</Then></div>", "directly inside an <Await>"),
])
def test_parse_errors(src, message):
    with pytest.raises(TemplateError, match=message):
        parse_template(src)


def test_pending_then_and_restart_on_key(start_mode):
    async def main():
        app = make(USER)()
        app.gate = asyncio.Event()
        r = Renderer(app)
        renders = []
        r.on_invalidate = lambda: renders.append(1)

        assert "loading 1" in text(r.render())
        await asyncio.sleep(0)
        assert app.calls == [1]
        # Rendering again doesn't start it again.
        assert "loading 1" in text(r.render())
        assert app.calls == [1]

        app.gate.set()
        await r.idle()
        assert renders  # the finished task asked the host for a render
        assert "hello user1" in text(r.render())
        assert app.calls == [1]

        app.gate.clear()
        (click,) = events(r.render(), "click")
        r.dispatch(click, {})
        assert "loading 2" in text(r.render())
        app.gate.set()
        await r.idle()
        assert "hello user2" in text(r.render())
        assert app.calls == [1, 2]

    asyncio.run(main())


def test_catch_shows_the_exception(start_mode):
    async def main():
        app = make(USER)()
        app.gate = asyncio.Event()
        app.gate.set()
        app.user_id = 3
        r = Renderer(app)
        errors = []
        r.on_error = errors.append
        r.render()
        await r.idle()
        assert "failed: no such user" in text(r.render())
        assert errors == []  # caught by <Catch>: not an app error

    asyncio.run(main())


def test_without_catch_the_error_is_reported(start_mode):
    async def main():
        app = make("""
<template><div><Await task="boom()"><Then>ok</Then></Await></div></template>
<code>
async def boom(self):
    raise KeyError("x")
</code>""")()
        r = Renderer(app)
        errors = []
        r.on_error = errors.append
        r.render()
        await r.idle()
        await asyncio.sleep(0)
        assert [type(e) for e in errors] == [KeyError]
        assert text(r.render()) == ""

    asyncio.run(main())


def test_key_change_cancels_the_old_run(start_mode):
    async def main():
        app = make(USER)()
        app.gate = asyncio.Event()
        r = Renderer(app)
        r.render()
        await asyncio.sleep(0)
        (first,) = [e.task for e in r._awaits.values()]
        app.user_id = 2
        r.render()
        await asyncio.sleep(0)
        assert first.cancelled()
        app.gate.set()
        await r.idle()
        assert "hello user2" in text(r.render())

    asyncio.run(main())


def test_leaving_the_page_cancels_it(start_mode):
    async def main():
        app = make("""
<template><div><If cond="shown"><Await task="wait()">...<Then>done</Then></Await></If></div></template>
<code>
import asyncio
shown: bool = True
async def wait(self):
    await asyncio.sleep(10)
</code>""")()
        r = Renderer(app)
        r.render()
        await asyncio.sleep(0)
        (entry,) = r._awaits.values()
        app.shown = False
        r.render()
        await asyncio.sleep(0)
        assert entry.task.cancelled()
        assert r._awaits == {}
        await r.idle()  # returns at once: nothing left running
        assert r.pending_tasks() == []

    asyncio.run(main())


def test_a_task_field_restarts_when_replaced(start_mode):
    async def main():
        app = make("""
<template><div><Await task="job">wait<Then as="n">got {{ n }}</Then></Await><button @click="again">again</button></div></template>
<code>
import asyncio
job = None
runs: int = 0
def on_init(self):
    self.again()
def again(self):
    self.job = self.start_task(self.work())
async def work(self):
    self.runs += 1
    await asyncio.sleep(0)
    return self.runs
</code>""")()
        r = Renderer(app)
        r.init_root()
        r.render()
        await r.idle()
        assert "got 1" in text(r.render())
        (click,) = events(r.render(), "click")
        r.dispatch(click, {})
        await r.idle()
        assert "got 2" in text(r.render())

    asyncio.run(main())


def test_a_shared_task_is_not_cancelled_with_the_block():
    async def main():
        app = make("""
<template><div><If cond="shown"><Await task="job">...</Await></If></div></template>
<code>
shown: bool = True
job = None
</code>""")()
        app.job = asyncio.ensure_future(asyncio.sleep(10))
        r = Renderer(app)
        r.render()
        await asyncio.sleep(0)
        app.shown = False
        r.render()
        await asyncio.sleep(0)
        assert not app.job.cancelled()
        app.job.cancel()

    asyncio.run(main())


def test_plain_values_and_finished_futures_need_no_wait():
    async def main():
        app = make("""
<template><div><Await task="data">wait<Then as="d">{{ d }}</Then><Catch as="e">bad {{ e }}</Catch></Await></div></template>
<code>
data = None
</code>""")()
        app.data = [1, 2]
        r = Renderer(app)
        assert text(r.render()) == "[1, 2]"
        done = asyncio.get_running_loop().create_future()
        done.set_result("ready")
        app.data = done
        assert text(r.render()) == "ready"
        failed = asyncio.get_running_loop().create_future()
        failed.set_exception(ValueError("nope"))
        app.data = failed
        assert text(r.render()) == "bad nope"

    asyncio.run(main())


def test_awaits_in_a_loop_are_separate(start_mode):
    async def main():
        app = make("""
<template><ul><For each="n in nums"><li><Await task="double(n)">..<Then as="v">{{ v }}</Then></Await></li></For></ul></template>
<code>
nums: list = [1, 2, 3]
async def double(self, n):
    return n * 2
</code>""")()
        r = Renderer(app)
        r.render()
        await r.idle()
        assert text(r.render()) == "246"

    asyncio.run(main())


def test_no_loop_is_a_clear_error():
    app = make('<template><div><Await task="go()">x</Await></div></template><code>\nasync def go(self):\n    return 1\n</code>')()
    with pytest.raises(RuntimeError, match="running asyncio event loop"):
        Renderer(app).render()


def test_check_knows_the_as_names(tmp_path):
    (tmp_path / "app.weft").write_text("""<template>
<div>
  <Await task="load()" key="page">
    <p>...</p>
    <Then as="rows"><p>{{ len(rows) }} {{ nope }}</p></Then>
    <Catch><p>{{ error }}</p></Catch>
  </Await>
</div>
</template>
<code>
page: int = 1
async def load(self):
    return []
</code>
""", encoding="utf-8")
    problems, _ = check_app(tmp_path, deps=False)
    assert [(p.code, "nope" in p.message) for p in problems] == [("unknown-name", True)]
