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
    GET  /api/scenarios            saved scenarios (?product= narrows)
    POST /api/scenarios            {"name", "changes", "product", "window", "preset", "who"}
    POST /api/scenarios/compare    {"ids": [...]}
    POST /api/scenarios/delete     {"id", "who"}
    GET  /api/settings             the governed settings, their history, replay-assumption impact
    POST /api/settings/propose     {"setting", "to", "reason", "who"}    risk appetite: the maker
    POST /api/settings/decide      {"id", "approve", "note", "who"}      the checker (or a withdrawal)
    POST /api/settings/change      {"setting", "to", "who"}              a replay assumption
    POST /api/recompute            {"who"}   rebuild every figure on the approved settings
    POST /api/ask                  {"message", "history", "current", "who", "stream"}  the Simulator's chat.
                                   With "stream": true, one JSON line per step as it happens
                                   ({"stage", "text"}), then {"stage": "done", "answer"}

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
import urllib.parse
from pathlib import Path

HERE = Path(__file__).resolve().parent
MAX_BODY = 64 * 1024

ENGINE = {"engine": None, "error": None, "loading": False}
ASSISTANT: dict = {}     # the chat's model, built on first use from the engine's config


def _assistant(eng):
    """The configured model and its status. Built once: the key is read from the environment here."""
    if not ASSISTANT:
        from src.client_assistant import provider_from_config
        ASSISTANT["provider"], ASSISTANT["status"] = provider_from_config(eng.base.cfg)
    return ASSISTANT["provider"], ASSISTANT["status"]


def _load_engine() -> None:
    """Build the baseline in the background, so the pages are served while it loads."""
    ENGINE["loading"] = True
    try:
        from src.client_api import Engine
        ENGINE["engine"] = Engine.load()
        print("engine ready", flush=True)
        if ENGINE["engine"].policy is not None:
            ENGINE["engine"].impacts()              # warm, so Settings opens without a wait
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

    def _window_query(self):
        """A window from the query string (app_from, app_to, performance_months), or None."""
        query = urllib.parse.parse_qs(self.path.partition("?")[2])
        keys = ("app_from", "app_to", "performance_months")
        if not any(k in query for k in keys):
            return None
        return {k: query[k][0] for k in keys if k in query}

    def _product_query(self):
        query = urllib.parse.parse_qs(self.path.partition("?")[2])
        return query["product"][0] if "product" in query else None

    def do_GET(self):
        from src.client_api import ApiError
        path = self.path.split("?", 1)[0]
        try:
            if path == "/api/health":
                eng = ENGINE["engine"]
                if eng is None:
                    return self._json(200, {"ready": False, "loading": ENGINE["loading"],
                                            "error": ENGINE["error"]})
                out = eng.health(self._window_query(), self._product_query())
                out["assistant"] = _assistant(eng)[1]
                return self._json(200, out)
            if path == "/api/view":
                eng = self._engine()
                return eng and self._json(200, eng.view(self._window_query(),
                                                        self._product_query()))
            if path == "/api/scenarios":
                eng = self._engine()
                return eng and self._json(200, eng.scenarios(self._product_query()))
            if path == "/api/rules":
                eng = self._engine()
                return eng and self._json(200, {"rules": eng.rules(self._window_query(),
                                                                   self._product_query())})
            if path == "/api/settings":
                eng = self._engine()
                return eng and self._json(200, eng.settings(self._product_query()))
        except ApiError as e:
            return self._json(e.status, {"error": str(e)})
        except Exception as e:                  # report, never hang the page
            traceback.print_exc()
            return self._json(500, {"error": f"engine error: {type(e).__name__}: {e}"})
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
                return self._json(200, eng.simulate(body.get("changes"), body.get("window"),
                                                    body.get("product")))
            if path == "/api/goal-seek":
                return self._json(200, eng.goal_seek(body.get("target"), body.get("ceiling"),
                                                     body.get("frozen"), body.get("window"),
                                                     body.get("product")))
            if path == "/api/scenarios":
                return self._json(200, eng.save_scenario(body))
            if path == "/api/scenarios/compare":
                return self._json(200, eng.compare_scenarios(body.get("ids")))
            if path == "/api/scenarios/delete":
                return self._json(200, eng.delete_scenario(body.get("id"), body.get("who")))
            if path == "/api/settings/propose":
                return self._json(200, eng.propose_setting(body))
            if path == "/api/settings/decide":
                return self._json(200, eng.decide_setting(body))
            if path == "/api/settings/change":
                return self._json(200, eng.change_setting(body))
            if path == "/api/recompute":
                return self._json(200, eng.recompute(body.get("who")))
            if path == "/api/ask":
                from src.client_assistant import respond
                if body.get("stream"):
                    return self._stream_ask(eng, body)
                return self._json(200, respond(eng, body, _assistant(eng)[0]))
        except ApiError as e:
            return self._json(e.status, {"error": str(e)})
        except Exception as e:                  # report, never hang the page
            traceback.print_exc()
            return self._json(500, {"error": f"engine error: {type(e).__name__}: {e}"})
        return self._json(404, {"error": f"no such endpoint {path}"})


    def _stream_ask(self, eng, body) -> None:
        """The chat, step by step. HTTP/1.0 with no length: the answer ends when the connection does.

        Headers go first, so a refusal after them is a line in the stream, not a status code.
        """
        from src.client_api import ApiError
        from src.client_assistant import respond
        self.send_response(200)
        self.send_header("Content-Type", "application/x-ndjson; charset=utf-8")
        self.end_headers()

        def emit(row: dict) -> None:
            self.wfile.write((json.dumps(row, ensure_ascii=False) + "\n").encode("utf-8"))
            self.wfile.flush()

        try:
            answer = respond(eng, body, _assistant(eng)[0],
                             progress=lambda stage, text: emit({"stage": stage, "text": text}))
            emit({"stage": "done", "answer": answer})
        except ApiError as e:
            emit({"stage": "error", "error": str(e)})
        except (BrokenPipeError, ConnectionResetError):
            pass                                # the person closed the page; nothing to tell
        except Exception as e:                  # report, never hang the page
            traceback.print_exc()
            emit({"stage": "error", "error": f"engine error: {type(e).__name__}: {e}"})


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
