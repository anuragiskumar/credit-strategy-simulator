"""Server for the ui/ prototype: the static pages, plus the simulator's engine.

    python -m ui.serve [port]            # pages + engine API (run from the repo root)
    python -m ui.serve [port] --static   # pages only, exactly as before

The pages still work with no engine at all: they read the precomputed `client_data.js`. With the
engine running, the Simulator screen lists every rule, edits thresholds, ladders changes and
goal-seeks to a target the person types. `src/client_api.py` holds the logic; this file only
routes HTTP to it.

    GET  /api/health       {"ready": bool, ...}  — the page polls this to decide which mode it is in
    GET  /api/rules        every decline rule, with what may be edited
    POST /api/simulate     {"changes": [...]}
    POST /api/goal-seek    {"target": 0.30, "ceiling": 0.11, "frozen": ["rule_id", ...]}

Bound to 127.0.0.1 only. This is a single-user demo server, not a deployment.
"""
from __future__ import annotations

import functools
import http.server
import json
import socketserver
import sys
import threading
import traceback
from pathlib import Path

HERE = Path(__file__).resolve().parent
MAX_BODY = 64 * 1024

ENGINE = {"engine": None, "error": None, "loading": False}


def _load_engine() -> None:
    """Build the baseline in the background, so the pages are served while it loads."""
    ENGINE["loading"] = True
    try:
        from src.client_api import Engine
        ENGINE["engine"] = Engine.load()
        print("engine ready", flush=True)
    except Exception as e:                      # the static pages must survive a broken engine
        ENGINE["error"] = f"{type(e).__name__}: {e}"
        traceback.print_exc()
    finally:
        ENGINE["loading"] = False


class Handler(http.server.SimpleHTTPRequestHandler):
    """Serve the prototype with caching off.

    The data file is regenerated whenever the engine changes, and a browser holding an old
    `client_data.js` shows last week's figures with this week's screens — silently, and in front
    of whoever is being demoed to.
    """

    def end_headers(self):
        self.send_header("Cache-Control", "no-store, must-revalidate")
        super().end_headers()

    def _json(self, status: int, payload) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _engine(self):
        eng = ENGINE["engine"]
        if eng is None:
            self._json(503, {"error": ENGINE["error"] or "the engine is still loading",
                             "loading": ENGINE["loading"]})
        return eng

    def do_GET(self):
        path = self.path.split("?", 1)[0]
        if path == "/api/health":
            eng = ENGINE["engine"]
            if eng is None:
                return self._json(200, {"ready": False, "loading": ENGINE["loading"],
                                        "error": ENGINE["error"]})
            return self._json(200, eng.health())
        if path == "/api/rules":
            eng = self._engine()
            return eng and self._json(200, {"rules": eng.rules()})
        if path.startswith("/api/"):
            return self._json(404, {"error": f"no such endpoint {path}"})
        return super().do_GET()

    def do_POST(self):
        from src.client_api import ApiError
        path = self.path.split("?", 1)[0]
        length = int(self.headers.get("Content-Length") or 0)
        if length > MAX_BODY:
            return self._json(413, {"error": "request too large"})
        try:
            body = json.loads(self.rfile.read(length) or b"{}")
        except json.JSONDecodeError:
            return self._json(400, {"error": "the request body is not JSON"})
        if not isinstance(body, dict):
            return self._json(400, {"error": "the request body must be an object"})
        eng = self._engine()
        if eng is None:
            return
        try:
            if path == "/api/simulate":
                return self._json(200, eng.simulate(body.get("changes")))
            if path == "/api/goal-seek":
                return self._json(200, eng.goal_seek(body.get("target"), body.get("ceiling"),
                                                     body.get("frozen")))
        except ApiError as e:
            return self._json(e.status, {"error": str(e)})
        except Exception as e:                  # report, never hang the page
            traceback.print_exc()
            return self._json(500, {"error": f"engine error: {type(e).__name__}: {e}"})
        return self._json(404, {"error": f"no such endpoint {path}"})


class Server(socketserver.ThreadingMixIn, socketserver.TCPServer):
    # Threads so a goal-seek (seconds) never blocks the page from loading its scripts.
    daemon_threads = True
    allow_reuse_address = True


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    static = "--static" in argv
    args = [a for a in argv if not a.startswith("--")]
    port = int(args[0]) if args else 8777
    handler = Handler
    handler.extensions_map[".html"] = "text/html; charset=utf-8"
    handler.extensions_map[".js"] = "text/javascript; charset=utf-8"
    if not static:
        threading.Thread(target=_load_engine, daemon=True).start()
    with Server(("127.0.0.1", port), functools.partial(handler, directory=str(HERE))) as srv:
        mode = "pages only" if static else "pages + engine"
        print(f"ui prototype on http://127.0.0.1:{port}/client.html ({mode})", flush=True)
        srv.serve_forever()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
