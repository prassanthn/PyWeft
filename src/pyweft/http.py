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
    """The standard library's urllib, on a thread so the app keeps running.
    The default host; a desktop window installs one with ``base_url`` set
    to where it serves the app, so relative URLs work there too."""

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


_host: Any = Urllib()


def set_host(host: Any) -> None:
    """For hosts: an object with ``async request(method, url, headers,
    body, timeout)`` returning ``(status, headers, data, final_url)``, that
    raises :class:`NetworkError` when no answer came."""
    global _host
    _host = host


async def request(
    method: str,
    url: str,
    *,
    params: Mapping[str, Any] | None = None,
    headers: Mapping[str, str] | None = None,
    json: Any = None,
    data: bytes | str | Mapping[str, Any] | None = None,
    timeout: float | None = 30,
) -> Response:
    """Send a request and return the :class:`Response`, whatever its status.

    ``params`` are added to the URL's query. The body is ``json`` (any
    JSON-able value, sent as application/json) or ``data``: bytes, text
    (UTF-8), or a mapping sent as a form. ``timeout`` is in seconds;
    TimeoutError when it runs out.
    """
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

    call = _host.request(method.upper(), url, sent, body, timeout)
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


async def get(url: str, **options: Any) -> Response:
    """``request("GET", url, ...)``"""
    return await request("GET", url, **options)


async def post(url: str, **options: Any) -> Response:
    """``request("POST", url, ...)``"""
    return await request("POST", url, **options)


async def put(url: str, **options: Any) -> Response:
    """``request("PUT", url, ...)``"""
    return await request("PUT", url, **options)


async def patch(url: str, **options: Any) -> Response:
    """``request("PATCH", url, ...)``"""
    return await request("PATCH", url, **options)


async def delete(url: str, **options: Any) -> Response:
    """``request("DELETE", url, ...)``"""
    return await request("DELETE", url, **options)


async def get_json(url: str, **options: Any) -> Any:
    """GET ``url`` and return its body parsed as JSON; :class:`HTTPError`
    unless the status is 2xx."""
    return (await request("GET", url, **options)).raise_for_status().json()
