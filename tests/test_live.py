"""pyweft.http's live data: Client headers, streamed bodies, server-sent
events and WebSockets, against the small server in live_server.py."""

import asyncio
import sys
from pathlib import Path

import pytest

from pyweft import Renderer, component_from_source, http
from pyweft import websocket as ws_protocol
from pyweft.http import _EventParser, ServerEvent

sys.path.insert(0, str(Path(__file__).parent))
import live_server  # noqa: E402


def run(test):
    """Run ``test(base_url)`` with the live server up."""
    async def main():
        server = await live_server.start()
        port = server.sockets[0].getsockname()[1]
        try:
            return await asyncio.wait_for(test(f"http://127.0.0.1:{port}"), 20)
        finally:
            server.close()
    return asyncio.run(main())


# ------------------------------------------------------------------ Client


class Recorder:
    def __init__(self):
        self.seen = []

    async def request(self, method, url, headers, body, timeout):
        self.seen.append((method, url, headers))
        return 200, {}, b"{}", url


@pytest.fixture
def recorder():
    host = Recorder()
    http.set_host(host)
    yield host
    http.set_host(http.Urllib())


def test_client_adds_its_address_and_headers(recorder):
    tokens = iter(["one", "two", "three"])
    api = http.Client("https://api.example.com/v1/", headers=lambda: {"Authorization": f"Bearer {next(tokens)}"})

    async def main():
        await api.get("/orders", params={"page": 2})
        await api.post("items", headers={"X-Trace": "7", "authorization": "override"}, json={})
        await api.get("https://other.example.org/x")
    asyncio.run(main())
    (m1, u1, h1), (m2, u2, h2), (_, u3, h3) = recorder.seen
    assert (m1, u1, h1) == ("GET", "https://api.example.com/v1/orders?page=2", {"authorization": "Bearer one"})
    assert u2 == "https://api.example.com/v1/items"
    assert h2 == {"authorization": "override", "x-trace": "7", "content-type": "application/json"}
    assert u3 == "https://other.example.org/x" and h3 == {"authorization": "Bearer three"}


def test_async_header_function(recorder):
    async def headers():
        await asyncio.sleep(0)
        return {"Authorization": "Bearer fresh"}

    asyncio.run(http.Client(headers=headers).get("https://x.example/"))
    assert recorder.seen[0][2] == {"authorization": "Bearer fresh"}


# ----------------------------------------------------------------- streams


def test_stream_lines_across_chunks():
    async def test(base):
        async with http.stream("GET", f"{base}/stream") as reply:
            assert reply.ok and reply.headers["content-type"].startswith("text/plain")
            lines = [line async for line in reply.iter_lines()]
        assert lines == ["alpha", "beta", "gamma"]
        async with http.stream("GET", f"{base}/stream") as reply:
            assert await reply.read() == b"alpha\nbeta\r\ngamma"
        reply = await http.stream("GET", f"{base}/status/500")
        assert reply.status == 500 and not reply.ok
        with pytest.raises(http.HTTPError):
            reply.raise_for_status()
        await reply.aclose()
    run(test)


def test_stream_unreachable():
    async def main():
        with pytest.raises(http.NetworkError):
            async with http.stream("GET", "http://127.0.0.1:9/nothing", timeout=5):
                pass
    asyncio.run(main())


# ------------------------------------------------------- server-sent events


def parse(text):
    parser, out = _EventParser(), []
    for line in text.split("\n"):
        event = parser.line(line)
        if event:
            out.append(event)
    return out, parser


def test_event_format():
    events, parser = parse(
        "﻿data: one\ndata:  two\n\n"        # two data lines; one space dropped
        ": comment\nevent: update\nid: 7\ndata:{\"a\": 1}\n\n"
        "data\n\n"                                 # a field with no colon: empty data
        "id: 8\n\n"                                # no data: nothing dispatched
        "retry: 250\nretry: soon\ndata: x\n\n"
    )
    assert events == [
        ServerEvent("one\n two"),
        ServerEvent('{"a": 1}', "update", "7"),
        ServerEvent("", "message", "7"),
        ServerEvent("x", "message", "8"),
    ]
    assert events[1].json() == {"a": 1}
    assert parser.retry == 250


def test_events_with_headers_and_ids():
    async def test(base):
        api = http.Client(base, headers={"Authorization": "Bearer abc"})
        got = [event async for event in api.events("/events?n=3", reconnect=False)]
        assert [(e.event, e.id, e.data) for e in got] == [
            ("tick", "1", "auth=Bearer abc"), ("tick", "2", "tick 2"), ("tick", "3", "tick 3"),
        ]
    run(test)


def test_events_reconnect_with_last_event_id():
    async def test(base):
        stream = http.events(f"{base}/events?n=5&close_after=2&retry=50")
        got = []
        async for event in stream:
            got.append(event.data)
            if len(got) == 5:
                break
        assert got == ["auth=", "tick 2", "tick 3", "tick 4", "tick 5"]
        assert stream.last_id == "5" and stream.retry == 0.05
    run(test)


def test_events_errors():
    async def test(base):
        with pytest.raises(http.HTTPError) as err:
            async for _ in http.events(f"{base}/status/401"):
                pass
        assert err.value.status == 401
        assert [e async for e in http.events(f"{base}/status/204")] == []
    run(test)


def test_cancelling_the_task_closes_the_stream():
    async def test(base):
        got = []

        async def listen():
            async for event in http.events(f"{base}/events?n=1&hold=1"):
                got.append(event)

        task = asyncio.ensure_future(listen())
        while not got:
            await asyncio.sleep(0.01)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
    run(test)


# --------------------------------------------------------------- WebSockets


def test_websocket_text_binary_json_and_close():
    async def test(base):
        url = base.replace("http", "ws") + "/ws"
        async with await http.websocket(url, protocols=["chat"]) as ws:
            assert ws.protocol == "chat"
            await ws.send("hello")
            assert await ws.receive() == "hello"
            await ws.send(b"\x00\x01" * 40000)  # over 64 KiB: the long length form
            assert await ws.receive() == b"\x00\x01" * 40000
            await ws.send_json({"n": 1})
            assert await ws.receive_json() == {"n": 1}
            await ws.send("frag")
            assert await ws.receive() == "ab"
            await ws.send("ping")  # the server pings; the client answers on its own
            assert await ws.receive() == "pong?"
            assert await ws.receive() == "pong!"
        assert ws.closed and ws.close_code == 1000
        with pytest.raises(http.WebSocketClosed):
            await ws.send("late")
    run(test)


def test_websocket_server_closes_and_iteration_ends():
    async def test(base):
        ws = await http.websocket(base + "/ws")  # http:// turns into ws://
        await ws.send("one")
        await ws.send("close")
        assert [m async for m in ws] == ["one"]
        assert (ws.close_code, ws.close_reason) == (4000, "bye")
        with pytest.raises(http.WebSocketClosed) as err:
            await ws.receive()
        assert err.value.code == 4000
    run(test)


def test_websocket_headers_outside_the_browser():
    async def test(base):
        api = http.Client(base)
        async with await api.websocket("/ws", headers={"Authorization": "Bearer xyz"}) as ws:
            await ws.send("auth")
            assert await ws.receive() == "Bearer xyz"
    run(test)


def test_websocket_refused():
    async def test(base):
        with pytest.raises(http.NetworkError, match="404"):
            await http.websocket(base.replace("http", "ws") + "/nothing")
        with pytest.raises(ValueError, match="ws://"):
            await ws_protocol.connect("http://example.org/")
    run(test)


def test_frame_round_trip():
    async def main():
        for size in (0, 125, 126, 65535, 65536):
            for mask in (False, True):
                reader = asyncio.StreamReader()
                reader.feed_data(ws_protocol.encode_frame(ws_protocol.BINARY, bytes(range(256)) * (size // 256) + b"x" * (size % 256), mask))
                fin, opcode, payload = await ws_protocol.read_frame(reader)
                assert fin and opcode == ws_protocol.BINARY and len(payload) == size
    asyncio.run(main())


# ---------------------------------------------------------- in a component


def test_a_component_listening_to_events():
    src = """
<template><ul><For each="e in seen"><li>{{ e }}</li></For></ul></template>
<code>
from pyweft import http
url: str = ""
seen: list = []

def on_init(self):
    self.start_task(self.listen())

async def listen(self):
    async for event in http.events(self.url, reconnect=False):
        self.seen.append(event.data)
        self.state_has_changed()
</code>
"""

    async def test(base):
        app = component_from_source(src, "App")(url=f"{base}/events?n=3")
        r = Renderer(app)
        renders = []
        r.on_invalidate = lambda: renders.append(1)
        r.init_root()
        r.render()
        await r.idle()
        assert app.seen == ["auth=", "tick 2", "tick 3"]
        assert len(renders) >= 3  # one per event, plus the task ending
    run(test)
