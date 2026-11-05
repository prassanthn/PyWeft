"""Talking to the website an app is embedded in.

A built app can be dropped into any web page with its ``embed.js``::

    <script src="https://example.org/orders-app/embed.js" defer></script>
    <pyweft-app data-customer="42"></pyweft-app>

Inside the app::

    from pyweft import embed

    customer = embed.params().get("customer")      # "42": data-* attributes
    embed.send("saved", {"id": order_id})          # a "saved" event on <pyweft-app>
    embed.on_message(lambda name, detail: ...)     # el.send(name, detail) on the page

Everything works outside an embedding page too (``embedded()`` is then
False, ``params()`` empty and ``send()`` does nothing), so an app needn't
care where it runs. The values come from whoever embeds the app: treat
them like any other input from outside.

The core keeps the listeners and checks the data; the browser's host in
webhost.py does the posting, installed with :func:`set_host`.
"""

from __future__ import annotations

import json
from typing import Any, Callable, Protocol

Listener = Callable[[str, Any], Any]


class Host(Protocol):
    def params(self) -> dict[str, str]: ...

    def send(self, name: str, detail_json: str) -> None: ...


class NotEmbedded:
    """The app is a page of its own (or a desktop window, or a test)."""

    def params(self) -> dict[str, str]:
        return {}

    def send(self, name: str, detail_json: str) -> None:
        pass


_host: Any = NotEmbedded()
_listeners: list[Listener] = []


def set_host(host: Any) -> None:
    global _host
    _host = host


def embedded() -> bool:
    """Whether the app is running inside another page's ``<pyweft-app>``."""
    return not isinstance(_host, NotEmbedded)


def params() -> dict[str, str]:
    """The ``data-*`` attributes of the ``<pyweft-app>`` element, without
    the prefix: ``data-customer-id="42"`` is ``{"customer-id": "42"}``.
    Empty when not embedded."""
    return dict(_host.params())


def send(event: str, detail: Any = None) -> None:
    """Fire ``event`` on the embedding page's ``<pyweft-app>`` element, as a
    DOM event whose ``detail`` is ``detail`` (anything JSON can carry):
    ``el.addEventListener("saved", e => e.detail.id)``. Nothing happens
    when not embedded."""
    if not isinstance(event, str) or not event:
        raise ValueError("send(event, ...): the event name is a non-empty string")
    try:
        text = json.dumps(detail)
    except (TypeError, ValueError) as exc:
        raise TypeError(f"send({event!r}, ...): the detail must be JSON data ({exc})") from None
    _host.send(event, text)


def on_message(listener: Listener) -> Callable[[], None]:
    """Call ``listener(name, detail)`` for each ``el.send(name, detail)`` the
    embedding page makes; returns a function that stops it. It runs outside
    any handler, so change state through a Store or call
    ``state_has_changed()`` for the page to show it."""
    _listeners.append(listener)

    def stop() -> None:
        if listener in _listeners:
            _listeners.remove(listener)

    return stop


def deliver(name: str, detail_json: str) -> None:
    """For hosts: a message from the embedding page arrived."""
    detail = json.loads(detail_json) if detail_json else None
    for listener in list(_listeners):
        listener(name, detail)


__all__ = ["embedded", "params", "send", "on_message", "set_host", "deliver", "NotEmbedded"]
