"""The browser's hosts for pyweft.http, pyweft.storage and pyweft.embed.

Used only in the browser (the page's bootstrap in shell.html, and
worker.js), never by the core: it reaches for ``js`` and ``pyodide``, which
it imports when called, so the module itself imports anywhere (PyInstaller
collects every module of the package). It is a module rather than part of
the bootstrap so the page and the worker share it.
"""

from __future__ import annotations

import asyncio

from . import embed, http, storage


def _js():
    import js  # type: ignore[import-not-found]

    return js


class Fetch:
    """pyweft.http through the browser's fetch: relative URLs resolve
    against the page, and the browser's rules (CORS) apply."""

    async def request(self, method, url, headers, body, timeout):
        from pyodide.http import pyfetch  # type: ignore[import-not-found]

        options = {"method": method, "headers": headers}
        if body is not None:
            options["body"] = body
        try:
            reply = await pyfetch(url, **options)
        except Exception as exc:  # fetch only fails when no answer came
            raise http.NetworkError(
                f"couldn't reach {url}: the network is down, or the server doesn't "
                "allow requests from this page (CORS)"
            ) from exc
        return reply.status, dict(reply.headers), await reply.bytes(), reply.url

    async def open_stream(self, method, url, headers, body, timeout):
        # fetch itself, for its body's reader: the stream is read as it
        # arrives, and an AbortController stops it.
        from pyodide.ffi import to_js  # type: ignore[import-not-found]

        js = _js()
        controller = js.AbortController.new()
        init = {"method": method, "headers": headers, "signal": controller.signal}
        if body is not None:
            init["body"] = to_js(body)
        try:
            reply = await js.fetch(url, to_js(init, dict_converter=js.Object.fromEntries))
        except Exception as exc:
            raise http.NetworkError(
                f"couldn't reach {url}: the network is down, or the server doesn't "
                "allow requests from this page (CORS)"
            ) from exc
        reader = reply.body.getReader()

        async def chunks():
            try:
                while True:
                    try:
                        part = await reader.read()
                    except Exception as exc:  # aborted, or the connection dropped
                        raise http.NetworkError(f"lost the connection to {url}") from exc
                    if part.done:
                        return
                    yield part.value.to_bytes()
            finally:
                controller.abort()

        names = {str(k): str(v) for k, v in (entry.to_py() for entry in reply.headers.entries())}
        return reply.status, names, str(reply.url), chunks(), controller.abort

    async def open_websocket(self, url, protocols, headers, timeout):
        if headers:
            raise ValueError(
                "browsers don't let a page send headers with a WebSocket: put the "
                "token in the address (?token=...) or send it as the first message"
            )
        socket = _BrowserSocket(url, protocols)
        try:
            await asyncio.wait_for(socket.opened, timeout)
        except asyncio.TimeoutError:
            socket.close_now()
            raise TimeoutError(f"no answer from {url} within {timeout} s") from None
        return socket


class _BrowserSocket:
    """The browser's WebSocket behind pyweft.http.WebSocket: its events
    land on an asyncio queue."""

    def __init__(self, url, protocols):
        from pyodide.ffi import create_proxy, to_js  # type: ignore[import-not-found]

        js = _js()
        loop = asyncio.get_running_loop()
        # Relative to the page, with http(s) turned into ws(s).
        address = js.URL.new(url, js.location.href)
        if address.protocol in ("http:", "https:"):
            address.protocol = "ws:" if address.protocol == "http:" else "wss:"
        self.url = str(address.href)
        self.protocol = ""
        self.close_code = None
        self.close_reason = ""
        self.opened = loop.create_future()
        self.finished = loop.create_future()
        self.queue: asyncio.Queue = asyncio.Queue()

        def on_open(event):
            self.protocol = str(self.ws.protocol)
            if not self.opened.done():
                self.opened.set_result(None)

        def on_message(event):
            data = event.data
            self.queue.put_nowait(data if isinstance(data, str) else bytes(data.to_bytes()))

        def on_close(event):
            self.close_code, self.close_reason = int(event.code), str(event.reason)
            if not self.opened.done():
                self.opened.set_exception(http.NetworkError(
                    f"couldn't open a WebSocket to {self.url} (closed with {event.code})"
                ))
            if not self.finished.done():
                self.finished.set_result(None)
            self.queue.put_nowait(None)
            for proxy in self.proxies:
                proxy.destroy()

        self.proxies = [create_proxy(on_open), create_proxy(on_message), create_proxy(on_close)]
        self.ws = js.WebSocket.new(self.url, to_js(list(protocols)))
        self.ws.binaryType = "arraybuffer"
        self.ws.onopen, self.ws.onmessage, self.ws.onclose = self.proxies

    async def send(self, data):
        from pyodide.ffi import to_js  # type: ignore[import-not-found]

        if self.close_code is not None or int(self.ws.readyState) != 1:
            raise ConnectionError("the WebSocket is closed")
        self.ws.send(data if isinstance(data, str) else to_js(data))

    async def receive(self):
        item = await self.queue.get()
        if item is None:
            self.queue.put_nowait(None)
        return item

    async def close(self, code=1000, reason=""):
        if self.close_code is None:
            self.ws.close(code, reason)
            try:
                await asyncio.wait_for(asyncio.shield(self.finished), 5)
            except asyncio.TimeoutError:
                self.close_code, self.close_reason = code, reason
                self.queue.put_nowait(None)

    def close_now(self):
        try:
            self.ws.close()
        except Exception:  # noqa: BLE001 - it never opened
            pass


class LocalStorage:
    """pyweft.storage in the browser's local storage. Every app on a site
    shares it, so keys are kept apart by the app's id."""

    def __init__(self, app_id: str):
        self.prefix = f"pyweft:{app_id}:"
        self.local = _js().localStorage

    def get(self, key):
        text = self.local.getItem(self.prefix + key)
        return None if text is None else str(text)

    def set(self, key, text):
        try:
            self.local.setItem(self.prefix + key, text)
        except Exception as exc:  # full (about 5 MB a site), or turned off
            raise OSError(
                f"the browser wouldn't store {key!r}: its storage for this site is "
                "full, or turned off"
            ) from exc

    def delete(self, key):
        self.local.removeItem(self.prefix + key)

    def keys(self):
        names = (self.local.key(i) for i in range(self.local.length))
        return [name[len(self.prefix):] for name in names if name.startswith(self.prefix)]


class EmbedPage:
    """pyweft.embed inside a <pyweft-app> (embed.js): the element's data-*
    attributes arrive in the address's query; events go to the parent page
    as JSON text, which embed.js turns into DOM events on the element."""

    def __init__(self, query: str):
        from urllib.parse import parse_qsl

        self._params = {k: v for k, v in parse_qsl(query.lstrip("?")) if k != "pyweft-embed"}

    def params(self):
        return self._params

    def send(self, name, detail_json):
        import json

        message = json.dumps({"pyweft": "event", "name": name, "detail": detail_json})
        # Whoever embeds the app gets its events: "*" says so.
        _js().window.parent.postMessage(message, "*")


def embed_message(name: str, detail_json: str) -> None:
    """Called by shell.html for each el.send(...) of the embedding page."""
    embed.deliver(str(name), str(detail_json))


def install_page(app_id: str) -> None:
    js = _js()
    if "pyweft-embed" in str(js.location.search) and js.window.parent != js.window:
        embed.set_host(EmbedPage(str(js.location.search)))
    http.set_host(Fetch())
    try:
        _js().localStorage.length  # throws where storage is blocked
    except Exception:
        storage.set_host(storage.Unavailable(
            "this browser keeps no data for this site (storage is turned off)"
        ))
    else:
        storage.set_host(LocalStorage(app_id))


def install_worker() -> None:
    # Background functions are plain functions, so pyweft.http (async) has
    # no place there; storage would quietly be a separate, empty one.
    storage.set_host(storage.Unavailable(
        "pyweft.storage isn't available in run_in_background: read what the "
        "function needs before calling it, and pass it in"
    ))
