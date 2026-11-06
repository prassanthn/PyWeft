"""A WebSocket client on the standard library (RFC 6455), for everywhere
except the browser, which has its own (webhost.py): desktop apps, tests and
plain Python. pyweft.http.websocket() is the API apps use; this is the
default host's half of it.

Frames are read by a task of the connection's own, which answers pings and
puts messages on a queue, so a connection that only sends still answers the
server's pings. ``encode_frame``/``read_frame`` also serve the server side
(tests, local tools): only the client masks what it sends.
"""

from __future__ import annotations

import asyncio
import base64
import hashlib
import os
import ssl
import struct
from urllib.parse import urlsplit

_GUID = "258EAFA5-E914-47DA-95CA-C5AB0DC85B11"
TEXT, BINARY, CLOSE, PING, PONG, CONTINUATION = 0x1, 0x2, 0x8, 0x9, 0xA, 0x0
MAX_MESSAGE = 16 * 1024 * 1024  # a message larger than this closes the connection (1009)


class ProtocolError(Exception):
    """The other side broke the WebSocket protocol."""


def accept_key(key: str) -> str:
    """The Sec-WebSocket-Accept value for a Sec-WebSocket-Key."""
    return base64.b64encode(hashlib.sha1((key + _GUID).encode()).digest()).decode()


def encode_frame(opcode: int, payload: bytes, mask: bool, fin: bool = True) -> bytes:
    head = bytearray([(0x80 if fin else 0) | opcode])
    length = len(payload)
    flag = 0x80 if mask else 0
    if length < 126:
        head.append(flag | length)
    elif length < 1 << 16:
        head.append(flag | 126)
        head += struct.pack("!H", length)
    else:
        head.append(flag | 127)
        head += struct.pack("!Q", length)
    if not mask:
        return bytes(head) + payload
    key = os.urandom(4)
    return bytes(head) + key + _xor(payload, key)


def _xor(data: bytes, key: bytes) -> bytes:
    if not data:
        return b""
    # Whole-buffer XOR through int arithmetic: far faster than a byte loop.
    repeated = (key * (len(data) // 4 + 1))[: len(data)]
    return (int.from_bytes(data, "big") ^ int.from_bytes(repeated, "big")).to_bytes(len(data), "big")


async def read_frame(reader: asyncio.StreamReader, limit: int = MAX_MESSAGE) -> tuple[bool, int, bytes]:
    """(fin, opcode, payload), unmasked. IncompleteReadError at EOF."""
    first, second = await reader.readexactly(2)
    if first & 0x70:
        raise ProtocolError("reserved bits set (no extensions were agreed)")
    fin, opcode = bool(first & 0x80), first & 0x0F
    masked, length = bool(second & 0x80), second & 0x7F
    if length == 126:
        (length,) = struct.unpack("!H", await reader.readexactly(2))
    elif length == 127:
        (length,) = struct.unpack("!Q", await reader.readexactly(8))
    if opcode >= 0x8 and (length > 125 or not fin):
        raise ProtocolError("a control frame must be short and not fragmented")
    if length > limit:
        raise ProtocolError(f"a frame of {length} bytes is over the {limit} byte limit")
    key = await reader.readexactly(4) if masked else b""
    payload = await reader.readexactly(length)
    return fin, opcode, _xor(payload, key) if masked else payload


def close_payload(code: int, reason: str) -> bytes:
    return struct.pack("!H", code) + reason.encode("utf-8")[:123] if code else b""


def parse_close(payload: bytes) -> tuple[int, str]:
    if len(payload) < 2:
        return 1005, ""  # no status code given
    return struct.unpack("!H", payload[:2])[0], payload[2:].decode("utf-8", "replace")


class Connection:
    """One open WebSocket: the host connection pyweft.http.WebSocket wraps."""

    def __init__(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter, protocol: str):
        self.reader, self.writer = reader, writer
        self.protocol = protocol
        self.close_code: int | None = None
        self.close_reason = ""
        self._queue: asyncio.Queue = asyncio.Queue()
        self._closing = False
        self._closed = asyncio.get_running_loop().create_future()
        self._lock = asyncio.Lock()
        self._task = asyncio.ensure_future(self._read_loop())

    async def _write(self, opcode: int, payload: bytes) -> None:
        async with self._lock:
            self.writer.write(encode_frame(opcode, payload, mask=True))
            await self.writer.drain()

    async def _read_loop(self) -> None:
        parts: list[bytes] = []
        kind = None
        try:
            while True:
                fin, opcode, payload = await read_frame(self.reader)
                if opcode == PING:
                    await self._write(PONG, payload)
                elif opcode == PONG:
                    pass
                elif opcode == CLOSE:
                    code, reason = parse_close(payload)
                    if not self._closing:  # the server closed first: answer it
                        self._closing = True
                        await self._write(CLOSE, close_payload(code if code != 1005 else 1000, ""))
                    self._finish(code, reason)
                    return
                elif opcode in (TEXT, BINARY) or (opcode == CONTINUATION and kind is not None):
                    if opcode != CONTINUATION:
                        if kind is not None:
                            raise ProtocolError("a new message started before the last one ended")
                        kind = opcode
                    parts.append(payload)
                    if sum(map(len, parts)) > MAX_MESSAGE:
                        raise ProtocolError("message too big")
                    if fin:
                        data = b"".join(parts)
                        self._queue.put_nowait(data.decode("utf-8") if kind == TEXT else data)
                        parts, kind = [], None
                else:
                    raise ProtocolError(f"unexpected frame (opcode {opcode})")
        except asyncio.CancelledError:
            self._finish(1006, "")
            raise
        except ProtocolError as exc:
            try:
                await self._write(CLOSE, close_payload(1009 if "big" in str(exc) else 1002, ""))
            except Exception:  # noqa: BLE001 - closing anyway
                pass
            self._finish(1002, str(exc))
        except (asyncio.IncompleteReadError, ConnectionError, OSError):
            self._finish(1006, "connection lost")
        finally:
            self.writer.close()

    def _finish(self, code: int, reason: str) -> None:
        if self.close_code is None:
            self.close_code, self.close_reason = code, reason
        if not self._closed.done():
            self._closed.set_result(None)
        self._queue.put_nowait(None)

    async def send(self, data: str | bytes) -> None:
        if self.close_code is not None or self._closing:
            raise ConnectionError("the WebSocket is closed")
        if isinstance(data, str):
            await self._write(TEXT, data.encode("utf-8"))
        else:
            await self._write(BINARY, bytes(data))

    async def receive(self) -> str | bytes | None:
        """The next message, or None once the connection has closed."""
        item = await self._queue.get()
        if item is None:
            self._queue.put_nowait(None)  # every later call sees it too
        return item

    async def close(self, code: int = 1000, reason: str = "", timeout: float = 5) -> None:
        if self.close_code is None and not self._closing:
            self._closing = True
            try:
                await self._write(CLOSE, close_payload(code, reason))
                await asyncio.wait_for(asyncio.shield(self._closed), timeout)
            except (asyncio.TimeoutError, ConnectionError, OSError):
                pass
            if self.close_code is None:
                self.close_code, self.close_reason = code, reason
        self._task.cancel()
        try:
            await self._task
        except BaseException:  # noqa: BLE001 - it was cancelled on purpose
            pass
        self._finish(self.close_code or code, self.close_reason)


async def connect(
    url: str, protocols: tuple[str, ...] = (), headers: dict[str, str] | None = None
) -> Connection:
    """Open ``ws://`` or ``wss://`` ``url``. Raises ConnectionError (with the
    status, for a server that answered but refused) when it can't."""
    parts = urlsplit(url)
    if parts.scheme not in ("ws", "wss"):
        raise ValueError(f"{url!r}: a WebSocket address starts with ws:// or wss://")
    secure = parts.scheme == "wss"
    host = parts.hostname or ""
    port = parts.port or (443 if secure else 80)
    path = (parts.path or "/") + (f"?{parts.query}" if parts.query else "")
    context = ssl.create_default_context() if secure else None
    try:
        reader, writer = await asyncio.open_connection(
            host, port, ssl=context, server_hostname=host if secure else None, limit=1 << 16
        )
    except OSError as exc:
        raise ConnectionError(f"couldn't reach {url}: {exc}") from None

    key = base64.b64encode(os.urandom(16)).decode()
    host_header = host if parts.port is None else f"{host}:{port}"
    lines = [
        f"GET {path} HTTP/1.1", f"Host: {host_header}", "Upgrade: websocket",
        "Connection: Upgrade", f"Sec-WebSocket-Key: {key}", "Sec-WebSocket-Version: 13",
    ]
    if protocols:
        lines.append("Sec-WebSocket-Protocol: " + ", ".join(protocols))
    for name, value in (headers or {}).items():
        lines.append(f"{name}: {value}")
    writer.write(("\r\n".join(lines) + "\r\n\r\n").encode("latin-1"))
    await writer.drain()

    try:
        head = await reader.readuntil(b"\r\n\r\n")
    except (asyncio.IncompleteReadError, asyncio.LimitOverrunError, ConnectionError) as exc:
        writer.close()
        raise ConnectionError(f"{url} didn't answer as a WebSocket server ({exc})") from None
    status_line, *header_lines = head.decode("latin-1").split("\r\n")
    status = status_line.split(" ", 2)
    answer: dict[str, str] = {}
    for line in header_lines:
        name, _, value = line.partition(":")
        if name:
            answer[name.strip().lower()] = value.strip()
    if len(status) < 2 or status[1] != "101":
        writer.close()
        code = status[1] if len(status) > 1 else "?"
        raise ConnectionError(f"{url} refused the WebSocket: HTTP {code} {status[2] if len(status) > 2 else ''}".rstrip())
    if answer.get("sec-websocket-accept") != accept_key(key):
        writer.close()
        raise ConnectionError(f"{url} answered the WebSocket handshake wrongly")
    return Connection(reader, writer, answer.get("sec-websocket-protocol", ""))


__all__ = ["connect", "Connection", "encode_frame", "read_frame", "accept_key", "ProtocolError"]

