"""pyweft.http: the calls apps make, through the default (urllib) host
against a real local server, and through a stand-in host."""

import asyncio
import json
import socket
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from pyweft import Renderer, component_from_source, http


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def _reply(self, status, body, ctype="application/json", extra=()):
        self.send_response(status)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        for name, value in extra:
            self.send_header(name, value)
        self.end_headers()
        self.wfile.write(body)

    def _echo(self):
        length = int(self.headers.get("Content-Length") or 0)
        body = self.rfile.read(length).decode("utf-8")
        seen = {
            "method": self.command,
            "path": self.path,
            "type": self.headers.get("Content-Type"),
            "token": self.headers.get("X-Token"),
            "body": body,
        }
        self._reply(200, json.dumps(seen).encode())

    def do_GET(self):  # noqa: N802 (stdlib naming)
        if self.path == "/orders":
            self._reply(200, json.dumps([{"id": 1}, {"id": 2}]).encode())
        elif self.path == "/missing":
            self._reply(404, b'{"error": "no such thing"}')
        elif self.path == "/old":
            self._reply(302, b"", extra=[("Location", "/orders")])
        elif self.path == "/latin":
            self._reply(200, "café".encode("latin-1"), "text/plain; charset=ISO-8859-1")
        elif self.path == "/slow":
            time.sleep(1.5)
            try:
                self._reply(200, b"{}")
            except ConnectionError:  # the client stopped waiting, as it should
                pass
        else:
            self._echo()

    do_POST = do_PUT = do_PATCH = do_DELETE = _echo


@pytest.fixture(scope="module")
def server():
    srv = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    srv.daemon_threads = True
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{srv.server_address[1]}"
    srv.shutdown()
    srv.server_close()


@pytest.fixture(autouse=True)
def default_host():
    yield
    http.set_host(http.Urllib())


def run(coro):
    return asyncio.run(coro)


def test_get_json(server):
    assert run(http.get_json(server + "/orders")) == [{"id": 1}, {"id": 2}]


def test_a_failed_status_is_a_response_until_you_ask(server):
    response = run(http.get(server + "/missing"))
    assert response.status == 404 and not response.ok
    assert response.json() == {"error": "no such thing"}
    with pytest.raises(http.HTTPError) as info:
        response.raise_for_status()
    assert info.value.status == 404 and info.value.response is response
    with pytest.raises(http.HTTPError):
        run(http.get_json(server + "/missing"))


def test_post_json_headers_and_params(server):
    response = run(http.post(
        server + "/save", params={"q": "a b", "tag": ["x", "y"]},
        json={"name": "Ada"}, headers={"X-Token": "t1"},
    ))
    seen = response.json()
    assert seen["method"] == "POST"
    assert seen["path"] == "/save?q=a+b&tag=x&tag=y"
    assert seen["type"] == "application/json" and seen["token"] == "t1"
    assert json.loads(seen["body"]) == {"name": "Ada"}
    assert response.headers["content-type"] == "application/json"  # names lower-cased


def test_form_and_text_bodies_and_every_method(server):
    seen = run(http.put(server + "/x", data={"a": "1", "b": "two words"})).json()
    assert seen["method"] == "PUT" and seen["body"] == "a=1&b=two+words"
    assert seen["type"] == "application/x-www-form-urlencoded"
    seen = run(http.patch(server + "/x", data="héllo")).json()
    assert seen["method"] == "PATCH" and seen["body"] == "héllo"
    assert run(http.delete(server + "/x")).json()["method"] == "DELETE"
    with pytest.raises(TypeError):
        run(http.post(server + "/x", json={}, data="x"))


def test_redirects_are_followed(server):
    response = run(http.get(server + "/old"))
    assert response.json() == [{"id": 1}, {"id": 2}]
    assert response.url == server + "/orders"


def test_text_uses_the_servers_charset(server):
    assert run(http.get(server + "/latin")).text == "café"


def test_relative_urls_need_a_base(server):
    with pytest.raises(ValueError, match="relative"):
        run(http.get("assets/data.json"))
    http.set_host(http.Urllib(base_url=server + "/app/"))
    assert run(http.get("orders.json")).json()["path"] == "/app/orders.json"


def test_no_answer_is_a_network_error():
    with socket.socket() as s:  # a port nothing listens on
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
    with pytest.raises(http.NetworkError, match="couldn't reach"):
        run(http.get(f"http://127.0.0.1:{port}/"))


def test_timeout(server):
    with pytest.raises(TimeoutError):
        run(http.get(server + "/slow", timeout=0.3))


def test_a_host_gets_normalised_requests():
    calls = []

    class Fake:
        async def request(self, method, url, headers, body, timeout):
            calls.append((method, url, headers, body, timeout))
            return 201, {"Content-Type": "text/plain"}, b"made", ""

    http.set_host(Fake())
    response = run(http.request("post", "/things", json=[1], headers={"Accept": "x"}))
    assert calls == [("POST", "/things", {"accept": "x", "content-type": "application/json"},
                      b"[1]", 30)]
    assert (response.status, response.text, response.url) == (201, "made", "/things")
    assert response.headers == {"content-type": "text/plain"}


def test_an_async_handler_loads_data_into_the_page(server):
    App = component_from_source(f'''
<template><ul><For each="o in orders"><li>{{{{ o['id'] }}}}</li></For></ul></template>
<code>
from pyweft import http
orders: list = []

async def on_init(self):
    self.orders = await http.get_json("{server}/orders")
</code>''')

    async def main():
        renderer = Renderer(App())
        renderer.init_root()
        await renderer.idle()
        return renderer.render()

    tree = run(main())
    assert [li.children[0].text for li in tree[0].children] == ["1", "2"]
