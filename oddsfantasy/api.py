from __future__ import annotations

import json
import mimetypes
import os
import sys
import threading
import time
import traceback
import urllib.request
from collections.abc import Callable
from pathlib import Path
from socketserver import ThreadingMixIn
from urllib.parse import parse_qs
from wsgiref.simple_server import WSGIRequestHandler, WSGIServer, make_server

from . import odds_details, ratelimit
from .build_info import build_info
from .config import DEFAULT_SEASON
from .services import (
    compute_best_lineup,
    compute_projections,
    list_defenses,
    resolve_league,
    resolve_user_leagues,
)

_DEBUG_FLAG = False

try:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(line_buffering=True, write_through=True)
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(line_buffering=True, write_through=True)
except Exception:
    pass


def _json_response(start_response: Callable, status: str, payload: dict):
    body = json.dumps(payload, indent=2).encode("utf-8")
    headers = [
        ("Content-Type", "application/json; charset=utf-8"),
        ("Content-Length", str(len(body))),
        ("Access-Control-Allow-Origin", "*"),
    ]
    start_response(status, headers)
    return [body]


def _debug_enabled() -> bool:
    return bool(_DEBUG_FLAG) or os.getenv("API_DEBUG") in {"1", "true", "True"}


def set_debug(flag: bool) -> None:
    global _DEBUG_FLAG
    _DEBUG_FLAG = bool(flag)


def _dprint(*args) -> None:
    if _debug_enabled():
        print(*args, flush=True)


def _serve_static(start_response: Callable, rel_path: str):
    base = Path(__file__).resolve().parent.parent / "ui"
    target = (base / (rel_path or "index.html")).resolve()
    if base.resolve() not in target.parents and target != base.resolve():
        return _json_response(start_response, "404 Not Found", {"error": "not_found"})
    if not target.is_file():
        return _json_response(start_response, "404 Not Found", {"error": "not_found"})
    content_type, _ = mimetypes.guess_type(str(target))
    content_type = content_type or "application/octet-stream"
    if (
        content_type.startswith("text/")
        or content_type in {"application/javascript", "application/json"}
    ) and "charset" not in content_type:
        content_type = f"{content_type}; charset=utf-8"
    body = target.read_bytes()
    start_response(
        "200 OK",
        [("Content-Type", content_type), ("Content-Length", str(len(body)))],
    )
    return [body]


def application(environ, start_response):
    path = environ.get("PATH_INFO", "/")
    query = parse_qs(environ.get("QUERY_STRING", ""))

    def q(name: str, default: str = "") -> str:
        values = query.get(name)
        return values[0] if values else default

    def identity() -> tuple[str | None, int | None]:
        league_id = q("league_id") or None
        roster_raw = q("roster_id")
        try:
            roster_id = int(roster_raw) if roster_raw else None
        except ValueError:
            roster_id = None
        return league_id, roster_id

    def common() -> dict:
        league_id, roster_id = identity()
        mode = q("mode", "auto")
        return {
            "username": q("username", "wesnicol"),
            "season": q("season", DEFAULT_SEASON),
            "week": q("week", "this"),
            "region": q("region", "us"),
            "fresh": q("fresh", "0") in {"1", "true", "True"} or mode == "fresh",
            "cache_mode": mode,
            "league_id": league_id,
            "roster_id": roster_id,
        }

    _dprint(f"[api] GET {path} qs={query}")
    try:
        if path == "/":
            return _serve_static(start_response, "")
        if path.startswith("/ui/"):
            return _serve_static(start_response, path[len("/ui/") :])

        if path == "/health":
            return _json_response(
                start_response,
                "200 OK",
                {
                    "status": "ok",
                    "build": build_info(),
                    "ratelimit": ratelimit.format_status(),
                    "ratelimit_info": ratelimit.get_details(),
                },
            )

        if path == "/user/leagues":
            username = q("username")
            if not username:
                return _json_response(
                    start_response, "400 Bad Request", {"error": "username_required"}
                )
            data = resolve_user_leagues(username, q("season", DEFAULT_SEASON))
            status = "404 Not Found" if data.get("error") else "200 OK"
            return _json_response(start_response, status, data)

        if path == "/league/resolve":
            league_id = q("league_id")
            if not league_id:
                return _json_response(
                    start_response, "400 Bad Request", {"error": "league_id_required"}
                )
            data = resolve_league(league_id)
            status = "404 Not Found" if data.get("error") else "200 OK"
            return _json_response(start_response, status, data)

        if path == "/projections":
            return _json_response(start_response, "200 OK", compute_projections(**common()))

        if path == "/defenses":
            return _json_response(start_response, "200 OK", list_defenses(**common()))

        if path == "/best-lineup":
            params = common()
            params["target"] = q("target", "mid")
            if params["target"] not in {"floor", "mid", "ceiling"}:
                return _json_response(
                    start_response,
                    "400 Bad Request",
                    {"error": "target_must_be_floor_mid_or_ceiling"},
                )
            return _json_response(start_response, "200 OK", compute_best_lineup(**params))

        if path == "/player/odds":
            params = common()
            params["name"] = q("name")
            data = odds_details.get_player_odds_details(**params)
            return _json_response(start_response, "200 OK", data)

        return _json_response(start_response, "404 Not Found", {"error": "not_found", "path": path})
    except Exception as exc:
        if _debug_enabled():
            traceback.print_exc()
        else:
            print(f"[api] error: {exc}")
        return _json_response(
            start_response,
            "500 Internal Server Error",
            {"error": str(exc), "ratelimit": ratelimit.format_status()},
        )


def main():
    import argparse

    parser = argparse.ArgumentParser(description="Odds Fantasy API")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--debug", action="store_true")
    args = parser.parse_args()

    set_debug(args.debug)
    if args.debug:
        os.environ["API_DEBUG"] = "1"

    class ThreadingWSGIServer(ThreadingMixIn, WSGIServer):
        daemon_threads = True
        allow_reuse_address = True

    class DebugRequestHandler(WSGIRequestHandler):
        def log_message(self, format, *args):
            if _debug_enabled():
                super().log_message(format, *args)

    with make_server(
        args.host,
        args.port,
        application,
        server_class=ThreadingWSGIServer,
        handler_class=DebugRequestHandler,
    ) as httpd:
        print(f"[api] Serving on http://{args.host}:{args.port}", flush=True)

        def probe_ready():
            url = f"http://{args.host}:{args.port}/health"
            for _ in range(30):
                try:
                    with urllib.request.urlopen(url, timeout=2) as response:
                        if getattr(response, "status", 200) == 200:
                            print(f"[api] READY on http://{args.host}:{args.port}", flush=True)
                            return
                except Exception:
                    time.sleep(0.2)
            print(f"[api] READY on http://{args.host}:{args.port} (health pending)", flush=True)

        threading.Thread(target=probe_ready, daemon=True).start()
        httpd.serve_forever()


if __name__ == "__main__":
    main()
