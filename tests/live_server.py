"""A small asyncio server for the live-data tests (and, run as a script,
for trying pyweft.http's streams in a browser): server-sent events, a
streamed body and a WebSocket echo, with CORS so a page on another port
may use it.

    python tests/live_server.py 8650

Routes:
- ``/events?n=3&retry=50&close_after=2``: events ``tick 1..n`` (id = the
  number), resuming after ``Last-Event-ID``; the first event's data names
  the ``Authorization`` header received. ``close_after`` drops the
  connection after that many events (to test reconnecting).
- ``/stream``: the text ``alpha\\nbeta\\r\\ngamma`` in three chunks.
- ``/status/<code>``: an empty answer with that status.
- ``/ws``: a WebSocket echo. ``close`` -> the server closes (4000, "bye");
  ``frag`` -> a fragmented message ``ab``; ``ping`` -> a ping, then
  ``pong?``; ``auth`` -> the Authorization header it got. Chooses the
  ``chat`` subprotocol when offered.
"""

from __future__ import annotations

import asyncio
import sys
from urllib.parse import parse_qs, urlsplit

from pyweft import websocket as ws

CORS = (
    "Access-Control-Allow-Origin: *\r\n"
    "Access-Control-Allow-Headers: authorization, last-event-id, cache-control, content-type\r\n"
    "Access-Control-Allow-Methods: GET, POST, OPTIONS\r\n"
)


async def handle(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
    try:
        head = await reader.readuntil(b"\r\n\r\n")
    except (asyncio.IncompleteReadError, ConnectionError):
        writer.close()
        return
    request_line, *lines = head.decode("latin-1").split("\r\n")
    method, target, _ = request_line.split(" ", 2)
    headers = {}
    for line in lines:
        name, _, value = line.partition(":")
        if name:
            headers[name.strip().lower()] = value.strip()
    url = urlsplit(target)
    query = {k: v[0] for k, v in parse_qs(url.query).items()}
    try:
        if method == "OPTIONS":
            writer.write(f"HTTP/1.1 204 No Content\r\n{CORS}Content-Length: 0\r\n\r\n".encode())
        elif url.path == "/ws" and headers.get("upgrade", "").lower() == "websocket":
            await websocket(reader, writer, headers)
            return
        elif url.path == "/events":
            await events(writer, headers, query)
        elif url.path == "/stream":
            writer.write(f"HTTP/1.1 200 OK\r\n{CORS}Content-Type: text/plain; charset=utf-8\r\n"
                         "Transfer-Encoding: chunked\r\n\r\n".encode())
            for piece in (b"alpha\nbe", b"ta\r", b"\ngamma"):
                writer.write(f"{len(piece):x}\r\n".encode() + piece + b"\r\n")
                await writer.drain()
                await asyncio.sleep(0.05)
            writer.write(b"0\r\n\r\n")
        elif url.path.startswith("/status/"):
            code = int(url.path.rsplit("/", 1)[1])
            writer.write(f"HTTP/1.1 {code} Status\r\n{CORS}Content-Length: 0\r\n\r\n".encode())
        else:
            writer.write(f"HTTP/1.1 404 Not Found\r\n{CORS}Content-Length: 0\r\n\r\n".encode())
        await writer.drain()
    except (ConnectionError, asyncio.CancelledError):
        pass
    finally:
        writer.close()


async def events(writer: asyncio.StreamWriter, headers: dict, query: dict) -> None:
    n = int(query.get("n", 3))
    close_after = int(query.get("close_after", 0))
    start = int(headers.get("last-event-id") or 0)
    writer.write(f"HTTP/1.1 200 OK\r\n{CORS}Content-Type: text/event-stream\r\n"
                 "Cache-Control: no-cache\r\n\r\n".encode())
    retry = query.get("retry")
    if retry:
        writer.write(f"retry: {retry}\n\n".encode())
    writer.write(b": a comment, ignored\n")
    sent = 0
    for i in range(start + 1, n + 1):
        data = f"auth={headers.get('authorization', '')}" if i == 1 else f"tick {i}"
        writer.write(f"id: {i}\nevent: tick\ndata: {data}\n\n".encode())
        await writer.drain()
        await asyncio.sleep(0.02)
        sent += 1
        if close_after and sent >= close_after and i < n:
            return  # dropped mid-stream: the client reconnects
    if query.get("hold"):
        await asyncio.sleep(3600)  # stays open until the client goes


async def websocket(reader: asyncio.StreamReader, writer: asyncio.StreamWriter, headers: dict) -> None:
    offered = [p.strip() for p in headers.get("sec-websocket-protocol", "").split(",") if p.strip()]
    chosen = "chat" if "chat" in offered else ""
    writer.write(
        ("HTTP/1.1 101 Switching Protocols\r\nUpgrade: websocket\r\nConnection: Upgrade\r\n"
         f"Sec-WebSocket-Accept: {ws.accept_key(headers['sec-websocket-key'])}\r\n"
         + (f"Sec-WebSocket-Protocol: {chosen}\r\n" if chosen else "") + "\r\n").encode()
    )
    await writer.drain()

    def frame(opcode, payload, fin=True):
        writer.write(ws.encode_frame(opcode, payload, mask=False, fin=fin))

    try:
        while True:
            fin, opcode, payload = await ws.read_frame(reader)
            if opcode == ws.CLOSE:
                frame(ws.CLOSE, payload[:2] or ws.close_payload(1000, ""))
                await writer.drain()
                return
            if opcode == ws.PONG:
                frame(ws.TEXT, b"pong!")
            elif opcode == ws.TEXT:
                text = payload.decode()
                if text == "close":
                    frame(ws.CLOSE, ws.close_payload(4000, "bye"))
                    await writer.drain()
                    await asyncio.sleep(0.2)
                    return
                if text == "frag":
                    frame(ws.TEXT, b"a", fin=False)
                    frame(ws.CONTINUATION, b"b")
                elif text == "ping":
                    frame(ws.PING, b"hi")
                    frame(ws.TEXT, b"pong?")
                elif text == "auth":
                    frame(ws.TEXT, headers.get("authorization", "").encode())
                else:
                    frame(ws.TEXT, payload)
            elif opcode == ws.BINARY:
                frame(ws.BINARY, payload)
            await writer.drain()
    except (asyncio.IncompleteReadError, ConnectionError):
        pass
    finally:
        writer.close()


async def start(port: int = 0) -> asyncio.AbstractServer:
    return await asyncio.start_server(handle, "127.0.0.1", port)


if __name__ == "__main__":
    async def main() -> None:
        server = await start(int(sys.argv[1]) if len(sys.argv) > 1 else 8650)
        print("serving on", server.sockets[0].getsockname(), flush=True)
        await server.serve_forever()

    asyncio.run(main())
