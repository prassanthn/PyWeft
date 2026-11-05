"""The browser's hosts for pyweft.http, pyweft.storage and pyweft.embed.

Used only in the browser (the page's bootstrap in shell.html, and
worker.js), never by the core: it reaches for ``js`` and ``pyodide``, which
it imports when called, so the module itself imports anywhere (PyInstaller
collects every module of the package). It is a module rather than part of
the bootstrap so the page and the worker share it.
"""

from __future__ import annotations

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
