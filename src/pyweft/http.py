"""Calling web APIs and loading files, the same way everywhere.

In a handler (requests are ``async``, so the handler is too)::

    from pyweft import http

    async def on_init(self):
        self.orders = await http.get_json("https://api.example.com/orders")

    async def save(self):
        response = await http.post(URL, json={"name": self.name})
        if not response.ok:
            self.error = f"Couldn't save ({response.status})"

A relative URL means a file the app ships: ``await
http.get_json("assets/prices.json")`` reads ``assets/prices.json`` in the
browser and in a desktop window alike.

In the browser the request is the page's own ``fetch``, so the browser's
rules apply: a server on another site must allow it (CORS). A desktop app,
and plain Python such as tests, use the standard library on a thread, with
no such rule.

The core only defines the calls; the browser supplies its host with
:func:`set_host` (webhost.py), as it does for dialogs. Without one, requests
go through urllib.
"""

from __future__ import annotations

import asyncio
import json as _json
from dataclasses import dataclass, field
from typing import Any, Mapping
from urllib.parse import urlencode, urljoin


_DEFAULT: Any = object()  # "the client's timeout"


class NetworkError(ConnectionError):
    """The request got no answer: no connection, a name that doesn't
    resolve, or, in the browser, a server that doesn't allow requests from
    this page."""


class HTTPError(Exception):
    """From :meth:`Response.raise_for_status` and :func:`get_json`: the
    status wasn't 2xx. The response is on ``.response``. (:func:`request`
    itself returns every answer, whatever its status.)"""

    def __init__(self, response: Response):
        super().__init__(f"{response.status} from {response.url}")
        self.response = response
        self.status = response.status


@dataclass(frozen=True)
class Response:
    """What came back: ``status``, ``headers`` (names in lower case), the
    body as ``data`` (bytes), ``text`` and ``json()``."""

    url: str
    status: int
    headers: Mapping[str, str] = field(default_factory=dict)
    data: bytes = b""

    @property
    def ok(self) -> bool:
        """True for a 2xx status."""
        return 200 <= self.status < 300

    @property
    def text(self) -> str:
        """The body as text, in the charset the server named (else UTF-8)."""
        kind = self.headers.get("content-type", "")
        charset = "utf-8"
        for part in kind.split(";")[1:]:
            name, _, value = part.strip().partition("=")
            if name.lower() == "charset" and value:
                charset = value.strip('"')
        return self.data.decode(charset, errors="replace")

    def json(self) -> Any:
        """The body parsed as JSON."""
        return _json.loads(self.text)

    def raise_for_status(self) -> Response:
        """Raise :class:`HTTPError` unless the status is 2xx; returns the
        response, so calls chain."""
        if not self.ok:
            raise HTTPError(self)
        return self


class Urllib:
    """The standard library: urllib for requests and http.client for
    streams, on threads so the app keeps running, and websocket.py for
    WebSockets. The default host; a desktop window installs one with
    ``base_url`` set to where it serves the app, so relative URLs work
    there too."""

    def __init__(self, base_url: str | None = None):
        self.base_url = base_url

    async def request(
        self, method: str, url: str, headers: dict[str, str], body: bytes | None,
        timeout: float | None,
    ) -> tuple[int, dict[str, str], bytes, str]:
        if "://" not in url:
            if self.base_url is None:
                raise ValueError(
                    f"{url!r} is relative, and there's no page here for it to be "
                    "relative to: use a full URL, like https://example.com/data.json"
                )
            url = urljoin(self.base_url, url)
        return await asyncio.to_thread(self._send, method, url, headers, body, timeout)

    @staticmethod
    def _send(method, url, headers, body, timeout):
        # Imported here: the browser never takes this path, and urllib pulls
        # in ssl, which Pyodide doesn't load unless asked.
        import urllib.error
        import urllib.request

        request = urllib.request.Request(url, data=body, headers=headers, method=method)
        try:
            with urllib.request.urlopen(request, timeout=timeout) as reply:
                return reply.status, dict(reply.headers.items()), reply.read(), reply.url
        except urllib.error.HTTPError as reply:  # 4xx and 5xx still have a body
            with reply:
                return reply.code, dict(reply.headers.items()), reply.read(), reply.url
        except urllib.error.URLError as exc:
            if isinstance(exc.reason, TimeoutError):
                raise TimeoutError(f"no answer from {url}") from None
            raise NetworkError(f"couldn't reach {url}: {exc.reason}") from None
        except TimeoutError:
            raise TimeoutError(f"no answer from {url}") from None
        except OSError as exc:
            raise NetworkError(f"couldn't reach {url}: {exc}") from None


    async def open_stream(self, method, url, headers, body, timeout):
        return await asyncio.to_thread(_stdlib_open_stream, self.base_url, method, url, headers, body, timeout)

    async def open_websocket(self, url, protocols, headers, timeout):
        from . import websocket

        if "://" not in url:
            if self.base_url is None:
                raise ValueError(f"{url!r} is relative: use a full ws:// or wss:// address")
            url = urljoin(self.base_url, url)
        if url.startswith(("http://", "https://")):
            url = "ws" + url[4:]
        try:
            return await asyncio.wait_for(websocket.connect(url, tuple(protocols), headers), timeout)
        except asyncio.TimeoutError:
            raise TimeoutError(f"no answer from {url} within {timeout} s") from None
        except ConnectionError as exc:
            raise NetworkError(str(exc)) from None

# ------------------------------------------------------------- hosts' streams


def _stdlib_open_stream(base_url, method, url, headers, body, timeout):
    """The standard library's half of :func:`stream`: http.client (urllib
    can't leave a body unread with no timeout), on a thread per read."""
    import http.client
    import socket
    from urllib.parse import urlsplit

    if "://" not in url:
        if base_url is None:
            raise ValueError(
                f"{url!r} is relative, and there's no page here for it to be "
                "relative to: use a full URL, like https://example.com/events"
            )
        url = urljoin(base_url, url)
    parts = urlsplit(url)
    kind = http.client.HTTPSConnection if parts.scheme == "https" else http.client.HTTPConnection
    connection = kind(parts.hostname, parts.port, timeout=timeout)
    path = (parts.path or "/") + (f"?{parts.query}" if parts.query else "")
    try:
        connection.request(method, path, body=body, headers=headers)
        reply = connection.getresponse()
    except (TimeoutError, socket.timeout):
        connection.close()
        raise TimeoutError(f"no answer from {url}") from None
    except OSError as exc:
        connection.close()
        raise NetworkError(f"couldn't reach {url}: {exc}") from None
    if connection.sock is not None:
        connection.sock.settimeout(None)  # a stream may be quiet for a long time

    async def chunks():
        try:
            while True:
                try:
                    part = await asyncio.to_thread(reply.read1, 65536)
                except (OSError, ValueError, http.client.HTTPException) as exc:
                    raise NetworkError(f"lost the connection to {url}: {exc}") from None
                if not part:
                    return
                yield part
        finally:
            close()

    def close():
        sock = connection.sock
        if sock is not None:
            try:
                sock.shutdown(socket.SHUT_RDWR)  # wakes a read blocked on its thread
            except OSError:
                pass
        connection.close()

    return reply.status, dict(reply.getheaders()), url, chunks(), close


_host: Any = Urllib()


def set_host(host: Any) -> None:
    """For hosts: an object with

    - ``async request(method, url, headers, body, timeout)`` returning
      ``(status, headers, data, final_url)``, raising :class:`NetworkError`
      when no answer came;
    - ``async open_stream(...)`` (same arguments) returning ``(status,
      headers, final_url, chunks, close)``: an async iterator of bytes and
      a function that stops it;
    - ``async open_websocket(url, protocols, headers, timeout)`` returning a
      connection with ``protocol``, ``close_code``, ``close_reason``,
      ``async send(str | bytes)``, ``async receive()`` (None once closed)
      and ``async close(code, reason)``.
    """
    global _host
    _host = host


# ----------------------------------------------------------------- requests


def _prepare(
    method: str, url: str, params: Mapping[str, Any] | None, headers: Mapping[str, str] | None,
    json: Any, data: bytes | str | Mapping[str, Any] | None,
) -> tuple[str, str, dict[str, str], bytes | None]:
    if json is not None and data is not None:
        raise TypeError("send json= or data=, not both")
    sent = {name.lower(): str(value) for name, value in (headers or {}).items()}
    body: bytes | None = None
    if json is not None:
        body = _json.dumps(json).encode("utf-8")
        sent.setdefault("content-type", "application/json")
    elif isinstance(data, Mapping):
        body = urlencode(data, doseq=True).encode("utf-8")
        sent.setdefault("content-type", "application/x-www-form-urlencoded")
    elif isinstance(data, str):
        body = data.encode("utf-8")
        sent.setdefault("content-type", "text/plain; charset=utf-8")
    elif data is not None:
        body = bytes(data)
    if params:
        url += ("&" if "?" in url else "?") + urlencode(params, doseq=True)
    return method.upper(), url, sent, body


class Client:
    """Requests that share an address and headers: an API you sign in to.

    ::

        api = http.Client("https://api.example.com/v1",
                          headers={"Authorization": f"Bearer {token}"})
        orders = await api.get_json("/orders")         # .../v1/orders

    ``headers`` may also be a function returning them, called for every
    request, for a token that changes (``lambda: {"Authorization": ...}``,
    async allowed). Headers passed to one call are added to these and win.
    A ``base_url`` joins with relative URLs (a leading ``/`` keeps its
    path: ``/orders`` above is ``/v1/orders``); full URLs go as they are.
    The module's own functions (``http.get`` ...) are a Client with
    neither.

    WebSockets get the client's address but not its headers: browsers
    can't send headers on a WebSocket (see :meth:`websocket`).
    """

    def __init__(self, base_url: str | None = None, *, headers: Any = None, timeout: float | None = 30):
        self.base_url = base_url.rstrip("/") + "/" if base_url else None
        self.headers = headers
        self.timeout = timeout

    def _url(self, url: str) -> str:
        if self.base_url is None or "://" in url:
            return url
        return self.base_url + url.lstrip("/")

    async def _headers(self, extra: Mapping[str, str] | None) -> dict[str, str]:
        base = self.headers() if callable(self.headers) else self.headers
        if base is not None and hasattr(base, "__await__"):
            base = await base
        merged = {name.lower(): str(value) for name, value in dict(base or {}).items()}
        merged.update({name.lower(): str(value) for name, value in dict(extra or {}).items()})
        return merged

    async def request(
        self,
        method: str,
        url: str,
        *,
        params: Mapping[str, Any] | None = None,
        headers: Mapping[str, str] | None = None,
        json: Any = None,
        data: bytes | str | Mapping[str, Any] | None = None,
        timeout: float | None = _DEFAULT,
    ) -> Response:
        """Send a request and return the :class:`Response`, whatever its status.

        ``params`` are added to the URL's query. The body is ``json`` (any
        JSON-able value, sent as application/json) or ``data``: bytes, text
        (UTF-8), or a mapping sent as a form. ``timeout`` is in seconds;
        TimeoutError when it runs out.
        """
        timeout = self.timeout if timeout is _DEFAULT else timeout
        method, url, sent, body = _prepare(
            method, self._url(url), params, await self._headers(headers), json, data
        )
        call = _host.request(method, url, sent, body, timeout)
        try:
            status, got, content, final = await asyncio.wait_for(call, timeout)
        except asyncio.TimeoutError:  # not the builtin TimeoutError before 3.11
            raise TimeoutError(f"no answer from {url} within {timeout} s") from None
        return Response(
            url=final or url,
            status=int(status),
            headers={name.lower(): value for name, value in dict(got).items()},
            data=bytes(content),
        )

    async def get(self, url: str, **options: Any) -> Response:
        """``request("GET", url, ...)``"""
        return await self.request("GET", url, **options)

    async def post(self, url: str, **options: Any) -> Response:
        """``request("POST", url, ...)``"""
        return await self.request("POST", url, **options)

    async def put(self, url: str, **options: Any) -> Response:
        """``request("PUT", url, ...)``"""
        return await self.request("PUT", url, **options)

    async def patch(self, url: str, **options: Any) -> Response:
        """``request("PATCH", url, ...)``"""
        return await self.request("PATCH", url, **options)

    async def delete(self, url: str, **options: Any) -> Response:
        """``request("DELETE", url, ...)``"""
        return await self.request("DELETE", url, **options)

    async def get_json(self, url: str, **options: Any) -> Any:
        """GET ``url`` and return its body parsed as JSON; :class:`HTTPError`
        unless the status is 2xx."""
        return (await self.request("GET", url, **options)).raise_for_status().json()

    # ---------------------------------------------------------- streaming

    def stream(self, method: str, url: str, **options: Any) -> _Opening:
        """A request whose body is read as it arrives: a long download, a
        model answering token by token. Use it with ``async with``::

            async with http.stream("POST", "/api/chat", json=question) as reply:
                async for text in reply.iter_text():
                    self.answer += text
                    self.state_has_changed()

        Same options as :meth:`request`; ``timeout`` covers waiting for the
        answer to start, not reading it. Leaving the ``async with`` (or the
        task being cancelled) closes the connection."""
        return _Opening(self, method, url, options)

    def events(self, url: str, *, reconnect: bool = True, **options: Any) -> EventStream:
        """Server-sent events from ``url``, as they arrive::

            async for event in http.events("/api/orders/live"):
                self.orders.append(event.json())
                self.state_has_changed()

        Each is a :class:`ServerEvent` (``data``, ``event``, ``id``,
        ``json()``). A dropped connection is reopened after the server's
        ``retry:`` time (3 s unless it says otherwise), sending the last
        event's id as ``Last-Event-ID``, as browsers do; ``reconnect=False``
        ends the loop instead. A status other than 2xx raises
        :class:`HTTPError`, and 204 ends it. Headers work here, unlike in
        the browser's own EventSource. Options as for :meth:`request`."""
        return EventStream(self, url, reconnect, options)

    async def websocket(
        self, url: str, *, protocols: tuple[str, ...] | list[str] = (),
        headers: Mapping[str, str] | None = None, timeout: float | None = _DEFAULT,
    ) -> WebSocket:
        """Open a WebSocket (``ws://``/``wss://``, or a relative address,
        which uses the page's own server)::

            async with await http.websocket("wss://example.com/chat") as ws:
                await ws.send_json({"join": "general"})
                async for message in ws:
                    self.lines.append(message)
                    self.state_has_changed()

        ``protocols`` are subprotocols to offer (``ws.protocol`` is the one
        chosen). ``headers`` only work outside the browser (desktop,
        tests): browsers don't let a page set WebSocket headers, so for
        portable sign-in put the token in the address (``?token=...``) or
        in the first message."""
        timeout = self.timeout if timeout is _DEFAULT else timeout
        url = self._url(url)
        connection = await _host.open_websocket(url, tuple(protocols), dict(headers or {}), timeout)
        return WebSocket(url, connection)


class _Opening:
    """What :meth:`Client.stream` returns: ``async with`` it (or await it,
    and call ``aclose()`` yourself)."""

    def __init__(self, client: Client, method: str, url: str, options: dict[str, Any]):
        self.client, self.method, self.url, self.options = client, method, url, options
        self.response: StreamResponse | None = None

    async def _open(self) -> StreamResponse:
        options = dict(self.options)
        timeout = options.pop("timeout", _DEFAULT)
        timeout = self.client.timeout if timeout is _DEFAULT else timeout
        headers = await self.client._headers(options.pop("headers", None))
        method, url, sent, body = _prepare(
            self.method, self.client._url(self.url), options.pop("params", None), headers,
            options.pop("json", None), options.pop("data", None),
        )
        if options:
            raise TypeError(f"unknown options: {', '.join(sorted(options))}")
        try:
            status, got, final, chunks, close = await asyncio.wait_for(
                _host.open_stream(method, url, sent, body, timeout), timeout
            )
        except asyncio.TimeoutError:
            raise TimeoutError(f"no answer from {url} within {timeout} s") from None
        self.response = StreamResponse(
            final or url, int(status), {k.lower(): v for k, v in dict(got).items()}, chunks, close
        )
        return self.response

    def __await__(self):
        return self._open().__await__()

    async def __aenter__(self) -> StreamResponse:
        return await self._open()

    async def __aexit__(self, *exc: Any) -> None:
        if self.response is not None:
            await self.response.aclose()


class StreamResponse:
    """A response read as it arrives (:meth:`Client.stream`): ``status``,
    ``ok``, ``headers``, and the body through ``iter_bytes()``,
    ``iter_text()``, ``iter_lines()`` or ``read()``."""

    def __init__(self, url: str, status: int, headers: dict[str, str], chunks: Any, close: Any):
        self.url, self.status, self.headers = url, status, headers
        self._chunks, self._close = chunks, close
        self.closed = False

    @property
    def ok(self) -> bool:
        return 200 <= self.status < 300

    def raise_for_status(self) -> StreamResponse:
        if not self.ok:
            raise HTTPError(self)  # type: ignore[arg-type]
        return self

    async def iter_bytes(self):
        """The body, chunk by chunk, as the network delivers it."""
        async for chunk in self._chunks:
            yield bytes(chunk)

    async def iter_text(self):
        """The body as text (UTF-8 unless the server says), as it arrives."""
        import codecs

        charset = "utf-8"
        for part in self.headers.get("content-type", "").split(";")[1:]:
            name, _, value = part.strip().partition("=")
            if name.lower() == "charset" and value:
                charset = value.strip('"')
        decoder = codecs.getincrementaldecoder(charset)(errors="replace")
        async for chunk in self.iter_bytes():
            text = decoder.decode(chunk)
            if text:
                yield text
        tail = decoder.decode(b"", final=True)
        if tail:
            yield tail

    async def iter_lines(self):
        """The body line by line (``\\n``, ``\\r\\n`` or ``\\r`` ends a line),
        without the line ends."""
        buffer = ""
        pending_cr = False
        async for text in self.iter_text():
            if pending_cr and text.startswith("\n"):
                text = text[1:]
            pending_cr = False
            buffer += text
            while True:
                cut = min((i for i in (buffer.find("\r"), buffer.find("\n")) if i >= 0), default=-1)
                if cut < 0:
                    break
                line, end = buffer[:cut], buffer[cut]
                rest = buffer[cut + 1:]
                if end == "\r":
                    if rest.startswith("\n"):
                        rest = rest[1:]
                    elif not rest:
                        pending_cr = True  # the \n may come in the next chunk
                buffer = rest
                yield line
        if buffer:
            yield buffer

    async def read(self) -> bytes:
        """The rest of the body, all at once."""
        return b"".join([chunk async for chunk in self.iter_bytes()])

    async def aclose(self) -> None:
        if not self.closed:
            self.closed = True
            result = self._close()
            if hasattr(result, "__await__"):
                await result


# ------------------------------------------------------- server-sent events


@dataclass(frozen=True)
class ServerEvent:
    """One server-sent event: its ``data`` (the ``data:`` lines, joined
    with newlines), ``event`` type (``"message"`` unless the server named
    one) and ``id`` (the last id the server set, or None)."""

    data: str
    event: str = "message"
    id: str | None = None

    def json(self) -> Any:
        """``data`` parsed as JSON."""
        return _json.loads(self.data)


class _EventParser:
    """The text/event-stream format, line by line (the HTML standard's
    rules: a blank line dispatches, ``:`` starts a comment, one space after
    the colon is dropped, ``retry`` takes digits only)."""

    def __init__(self) -> None:
        self.data: list[str] = []
        self.event = ""
        self.last_id: str | None = None
        self.retry: int | None = None
        self.first = True

    def line(self, line: str) -> ServerEvent | None:
        if self.first:
            self.first = False
            line = line.lstrip("﻿")
        if not line:
            if not self.data:
                self.event = ""
                return None
            event = ServerEvent("\n".join(self.data), self.event or "message", self.last_id)
            self.data, self.event = [], ""
            return event
        if line.startswith(":"):
            return None
        name, colon, value = line.partition(":")
        if colon and value.startswith(" "):
            value = value[1:]
        if name == "data":
            self.data.append(value)
        elif name == "event":
            self.event = value
        elif name == "id" and "\0" not in value:
            self.last_id = value
        elif name == "retry" and value.isdigit():
            self.retry = int(value)
        return None


class EventStream:
    """What :meth:`Client.events` returns: iterate it with ``async for``.
    ``last_id`` is the id of the last event received; ``close()`` stops it
    (as does leaving the loop, or cancelling its task)."""

    def __init__(self, client: Client, url: str, reconnect: bool, options: dict[str, Any]):
        self.client, self.url, self.reconnect, self.options = client, url, reconnect, options
        self.last_id: str | None = None
        self.retry = 3.0
        self._response: StreamResponse | None = None
        self._closed = False

    def __aiter__(self):
        return self._events()

    async def _events(self):
        try:
            while not self._closed:
                headers = {"accept": "text/event-stream", "cache-control": "no-cache"}
                headers.update({k.lower(): v for k, v in dict(self.options.get("headers") or {}).items()})
                if self.last_id is not None:
                    headers["last-event-id"] = self.last_id
                options = {**self.options, "headers": headers}
                try:
                    self._response = await _Opening(self.client, "GET", self.url, options)._open()
                except (NetworkError, TimeoutError):
                    if not self.reconnect:
                        raise
                    await asyncio.sleep(self.retry)
                    continue
                response = self._response
                try:
                    if response.status == 204:
                        return  # the server's way of saying "stop"
                    response.raise_for_status()
                    parser = _EventParser()
                    parser.last_id = self.last_id
                    try:
                        async for line in response.iter_lines():
                            event = parser.line(line)
                            if parser.retry is not None:
                                self.retry = parser.retry / 1000
                            self.last_id = parser.last_id
                            if event is not None:
                                yield event
                    except NetworkError:
                        if not self.reconnect:
                            raise
                finally:
                    await response.aclose()
                if not self.reconnect or self._closed:
                    return
                await asyncio.sleep(self.retry)
        finally:
            self._closed = True

    async def close(self) -> None:
        self._closed = True
        if self._response is not None:
            await self._response.aclose()

    async def __aenter__(self) -> EventStream:
        return self

    async def __aexit__(self, *exc: Any) -> None:
        await self.close()


# --------------------------------------------------------------- WebSockets


class WebSocketClosed(ConnectionError):
    """Sending on, or receiving from, a WebSocket that has closed. The
    close code and reason are on ``.code`` and ``.reason``."""

    def __init__(self, code: int | None, reason: str):
        super().__init__(f"the WebSocket closed ({code}{': ' + reason if reason else ''})")
        self.code, self.reason = code, reason


class WebSocket:
    """An open WebSocket (:meth:`Client.websocket`): ``send()`` text or
    bytes, ``send_json()``, ``receive()`` the next message, or ``async
    for`` the messages until it closes. ``close()`` it when done, or use
    ``async with``. ``close_code``/``close_reason`` say how it ended
    (1000 = normally)."""

    def __init__(self, url: str, connection: Any):
        self.url = url
        self._connection = connection

    @property
    def protocol(self) -> str:
        """The subprotocol the server chose, or ``""``."""
        return self._connection.protocol or ""

    @property
    def closed(self) -> bool:
        return self._connection.close_code is not None

    @property
    def close_code(self) -> int | None:
        return self._connection.close_code

    @property
    def close_reason(self) -> str:
        return self._connection.close_reason

    async def send(self, message: str | bytes) -> None:
        """Send a text (str) or binary (bytes) message."""
        if not isinstance(message, (str, bytes, bytearray, memoryview)):
            raise TypeError("send() takes str or bytes; send_json() takes data")
        if self.closed:
            raise WebSocketClosed(self.close_code, self.close_reason)
        await self._connection.send(message if isinstance(message, str) else bytes(message))

    async def send_json(self, value: Any) -> None:
        """Send ``value`` as a JSON text message."""
        await self.send(_json.dumps(value))

    async def receive(self) -> str | bytes:
        """The next message: str for text, bytes for binary.
        :class:`WebSocketClosed` once the connection has closed."""
        message = await self._connection.receive()
        if message is None:
            raise WebSocketClosed(self.close_code, self.close_reason)
        return message

    async def receive_json(self) -> Any:
        """The next message, parsed as JSON."""
        message = await self.receive()
        return _json.loads(message)

    def __aiter__(self):
        return self._messages()

    async def _messages(self):
        while True:
            message = await self._connection.receive()
            if message is None:
                return
            yield message

    async def close(self, code: int = 1000, reason: str = "") -> None:
        """Close it (code 1000: done); waits briefly for the server to agree."""
        await self._connection.close(code, reason)

    async def __aenter__(self) -> WebSocket:
        return self

    async def __aexit__(self, *exc: Any) -> None:
        if not self.closed:
            await self.close()


# ------------------------------------------------------- the module's client

_default = Client()


async def request(method: str, url: str, **options: Any) -> Response:
    """Send a request and return the :class:`Response`, whatever its status.

    ``params`` are added to the URL's query; ``headers`` are sent as given.
    The body is ``json`` (any JSON-able value, sent as application/json) or
    ``data``: bytes, text (UTF-8), or a mapping sent as a form. ``timeout``
    is in seconds (30 by default); TimeoutError when it runs out. For
    headers on every request (sign-in), use a :class:`Client`.
    """
    return await _default.request(method, url, **options)


async def get(url: str, **options: Any) -> Response:
    """``request("GET", url, ...)``"""
    return await _default.request("GET", url, **options)


async def post(url: str, **options: Any) -> Response:
    """``request("POST", url, ...)``"""
    return await _default.request("POST", url, **options)


async def put(url: str, **options: Any) -> Response:
    """``request("PUT", url, ...)``"""
    return await _default.request("PUT", url, **options)


async def patch(url: str, **options: Any) -> Response:
    """``request("PATCH", url, ...)``"""
    return await _default.request("PATCH", url, **options)


async def delete(url: str, **options: Any) -> Response:
    """``request("DELETE", url, ...)``"""
    return await _default.request("DELETE", url, **options)


async def get_json(url: str, **options: Any) -> Any:
    """GET ``url`` and return its body parsed as JSON; :class:`HTTPError`
    unless the status is 2xx."""
    return await _default.get_json(url, **options)


def stream(method: str, url: str, **options: Any) -> _Opening:
    """See :meth:`Client.stream`."""
    return _default.stream(method, url, **options)


def events(url: str, **options: Any) -> EventStream:
    """See :meth:`Client.events`."""
    return _default.events(url, **options)


async def websocket(url: str, **options: Any) -> WebSocket:
    """See :meth:`Client.websocket`."""
    return await _default.websocket(url, **options)
