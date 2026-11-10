"""after_paint(): an async handler waits for the page to be drawn before
going on, so what it changed so far shows before slow work."""

import asyncio

import pytest

from pyweft import Renderer, component_from_source

SRC = """
<template>
  <div>
    <If cond="busy"><p class="bar">working</p></If>
    <button @click="work">go</button>
    <p>{{ result }}</p>
  </div>
</template>
<code>
busy: bool = False
result: str = ""
steps: list = []

async def work(self):
    self.busy = True
    await self.after_paint()
    self.steps.append("built")
    self.result = "done"
    self.busy = False
</code>
"""


def make():
    app = component_from_source(SRC, "App")()
    return app, Renderer(app)


def test_without_a_screen_it_returns_at_once():
    app, r = make()

    async def go():
        r.dispatch(r.render()[0].children[-2].events["click"], {})
        await r.idle()

    asyncio.run(go())
    assert app.steps == ["built"] and app.result == "done"
    assert r.take_commands() == []


def test_a_host_that_reports_paints_resumes_it():
    app, r = make()
    r.paint_reports = True

    async def go():
        r.dispatch(r.render()[0].children[-2].events["click"], {})
        await asyncio.sleep(0)
        tree = r.render()  # the host renders: the bar is in it
        assert [n.attrs.get("class") for n in tree[0].children][0] == "bar"
        (command,) = r.take_commands()
        assert command == {"op": "after_paint", "id": 1}
        for _ in range(3):
            await asyncio.sleep(0)
        assert app.steps == []  # waiting for the page
        r.painted([command["id"]])
        await r.idle()

    asyncio.run(go())
    assert app.steps == ["built"] and not app.busy
    r.painted([1, 99])  # again, or unknown: ignored


def test_it_needs_a_rendered_component():
    app = component_from_source(SRC, "App")()
    with pytest.raises(RuntimeError, match="after_paint"):
        asyncio.run(app.after_paint())
