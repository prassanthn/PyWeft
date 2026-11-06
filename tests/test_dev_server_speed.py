"""pyweft run's server: one connection for many files, and the list of
files it may serve kept per change rather than worked out per request."""

import http.client
import threading
import time

from pyweft.cli import make_dev_server

SRC = "<template><p>hello</p></template>"


def test_dev_server_keeps_connections_and_follows_new_files(tmp_path):
    (tmp_path / "app.weft").write_text(SRC, encoding="utf-8")
    server = make_dev_server(tmp_path, 0, poll_interval=0.05)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    port = server.server_address[1]
    try:
        conn = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
        for path in ("/app/app.weft", "/pyweft-src/renderer.py", "/pyweft-bundle.bin"):
            conn.request("GET", path)
            reply = conn.getresponse()
            assert reply.status == 200, path
            reply.read()
            assert reply.getheader("Connection", "").lower() != "close"  # one connection for all
        conn.request("GET", "/app/later.weft")
        reply = conn.getresponse()
        reply.read()
        assert reply.status == 404
        (tmp_path / "later.weft").write_text("<template><p>x</p></template>", encoding="utf-8")
        for _ in range(100):
            conn.request("GET", "/app/later.weft")
            reply = conn.getresponse()
            reply.read()
            if reply.status == 200:
                break
            time.sleep(0.05)
        assert reply.status == 200  # the cached list of files followed the change
        conn.close()
    finally:
        server.shutdown_dev()
