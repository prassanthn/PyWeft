"""pyweft.embed, its browser host, and embed.js in the build."""

import json

import pytest

from pyweft import embed, webhost
from pyweft.cli import cmd_build


@pytest.fixture(autouse=True)
def clean():
    yield
    embed.set_host(embed.NotEmbedded())
    embed._listeners.clear()


def test_outside_an_embedding_page_nothing_happens():
    assert not embed.embedded()
    assert embed.params() == {}
    embed.send("saved", {"id": 1})  # no error, no effect


def test_send_checks_its_input():
    with pytest.raises(ValueError, match="non-empty string"):
        embed.send("")
    with pytest.raises(TypeError, match="JSON data"):
        embed.send("saved", {"when": object()})


class FakeHost:
    def __init__(self):
        self.sent = []

    def params(self):
        return {"customer": "42"}

    def send(self, name, detail_json):
        self.sent.append((name, json.loads(detail_json)))


def test_with_a_host():
    host = FakeHost()
    embed.set_host(host)
    assert embed.embedded()
    assert embed.params() == {"customer": "42"}
    params = embed.params()
    params["x"] = "changed"
    assert "x" not in embed.params()  # a copy
    embed.send("saved", {"id": 7, "tags": ["a"]})
    embed.send("closed")
    assert host.sent == [("saved", {"id": 7, "tags": ["a"]}), ("closed", None)]


def test_messages_reach_listeners_until_stopped():
    got = []
    stop = embed.on_message(lambda name, detail: got.append((name, detail)))
    embed.on_message(lambda name, detail: got.append(("second", name)))
    embed.deliver("select", json.dumps({"id": 3}))
    stop()
    stop()  # twice is fine
    embed.deliver("select", "null")
    assert got == [("select", {"id": 3}), ("second", "select"), ("second", "select")]


def test_browser_host_reads_the_query_and_posts_json(monkeypatch):
    posted = []

    class Parent:
        def postMessage(self, message, origin):
            posted.append((json.loads(message), origin))

    class Js:
        class window:
            parent = Parent()

    monkeypatch.setattr(webhost, "_js", lambda: Js)
    host = webhost.EmbedPage("?customer=42&pyweft-embed=1&name=A%20B")
    assert host.params() == {"customer": "42", "name": "A B"}
    embed.set_host(host)
    embed.send("saved", {"id": 1})
    assert posted == [({"pyweft": "event", "name": "saved", "detail": '{"id": 1}'}, "*")]
    # The JSON text starts the way embed.js looks for.
    assert json.dumps({"pyweft": "event"}).startswith('{"pyweft"')


def test_dev_server_serves_embed_js(tmp_path):
    import threading
    import urllib.request

    from pyweft.cli import make_dev_server

    (tmp_path / "app.weft").write_text("<template><p>x</p></template>", encoding="utf-8")
    server = make_dev_server(tmp_path, 0, poll_interval=0.05)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        url = f"http://127.0.0.1:{server.server_address[1]}/embed.js"
        with urllib.request.urlopen(url, timeout=5) as reply:
            assert reply.headers["Content-Type"].startswith("text/javascript")
            assert b"pyweft-app" in reply.read()
    finally:
        server.shutdown_dev()


def test_build_ships_embed_js(tmp_path):
    (tmp_path / "app.weft").write_text("<template><p>x</p></template>", encoding="utf-8")
    cmd_build(tmp_path, tmp_path / "dist", prerender=False)
    script = (tmp_path / "dist" / "embed.js").read_text(encoding="utf-8")
    assert 'customElements.define("pyweft-app"' in script
    page = (tmp_path / "dist" / "index.html").read_text(encoding="utf-8")
    assert "pyweft-embed" in page and "pyweft_embed_message" in page
