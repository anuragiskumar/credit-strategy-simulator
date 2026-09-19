"""Static server for the ui/ prototype.

    python -m ui.serve [port]

There is no build step and no backend: index.html, app.js and data.js are the whole thing.
"""
from __future__ import annotations

import functools
import http.server
import socketserver
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    port = int(argv[0]) if argv else 8777
    handler = http.server.SimpleHTTPRequestHandler
    handler.extensions_map[".html"] = "text/html; charset=utf-8"
    handler.extensions_map[".js"] = "text/javascript; charset=utf-8"
    socketserver.TCPServer.allow_reuse_address = True
    with socketserver.TCPServer(("127.0.0.1", port), functools.partial(handler, directory=str(HERE))) as srv:
        print(f"ui prototype on http://127.0.0.1:{port}/index.html")
        srv.serve_forever()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
