from __future__ import annotations

import json
from urllib.parse import parse_qs
from wsgiref.simple_server import make_server
from typing import Callable

from . import ratelimit
from .services import compute_projections, build_lineup, build_lineup_diffs, list_defenses


def _json_response(start_response: Callable, status: str, payload: dict, headers_extra: list[tuple[str, str]] | None = None):
    body = json.dumps(payload, indent=2).encode("utf-8")
    headers = [("Content-Type", "application/json; charset=utf-8"), ("Content-Length", str(len(body))), ("Access-Control-Allow-Origin", "*")]
    if headers_extra:
        headers.extend(headers_extra)
    start_response(status, headers)
    return [body]


def application(environ, start_response):
    path = environ.get("PATH_INFO", "/")
    method = environ.get("REQUEST_METHOD", "GET")
    qs = parse_qs(environ.get("QUERY_STRING", ""))

    def q(name: str, default: str = "") -> str:
        v = qs.get(name)
        return v[0] if v else default

    print(f"[api] {method} {path} qs={qs}")

    try:
        if path == "/health":
            return _json_response(start_response, "200 OK", {"status": "ok", "ratelimit": ratelimit.format_status()})

        if path == "/projections":
            username = q("username", "wesnicol")
            season = q("season", "2025")
            week = q("week", "this")
            region = q("region", "us")
            fresh = q("fresh", "0") in ("1", "true", "True")
            data = compute_projections(username=username, season=season, week=week, region=region, fresh=fresh)
            return _json_response(start_response, "200 OK", data)

        if path == "/lineup":
            username = q("username", "wesnicol")
            season = q("season", "2025")
            week = q("week", "this")
            target = q("target", "mid")
            fresh = q("fresh", "0") in ("1", "true", "True")
            proj = compute_projections(username=username, season=season, week=week, fresh=fresh)
            lineup = build_lineup(proj.get("players", []), target=target)
            lineup["ratelimit"] = ratelimit.format_status()
            return _json_response(start_response, "200 OK", lineup)

        if path == "/lineup/diffs":
            username = q("username", "wesnicol")
            season = q("season", "2025")
            week = q("week", "this")
            fresh = q("fresh", "0") in ("1", "true", "True")
            proj = compute_projections(username=username, season=season, week=week, fresh=fresh)
            diffs = build_lineup_diffs(proj.get("players", []))
            diffs["ratelimit"] = ratelimit.format_status()
            return _json_response(start_response, "200 OK", diffs)

        if path == "/defenses":
            username = q("username", "wesnicol")
            season = q("season", "2025")
            week = q("week", "this")
            scope = q("scope", "both")
            fresh = q("fresh", "0") in ("1", "true", "True")
            data = list_defenses(username=username, season=season, week=week, scope=scope, fresh=fresh)
            return _json_response(start_response, "200 OK", data)

        return _json_response(start_response, "404 Not Found", {"error": "not_found", "path": path})

    except Exception as e:
        print(f"[api] error: {e}")
        return _json_response(start_response, "500 Internal Server Error", {"error": str(e), "ratelimit": ratelimit.format_status()})


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Odds Fantasy API (stdlib server)")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    args = parser.parse_args()

    print("""
Starting Odds Fantasy API
Endpoints:
  GET /health
  GET /projections?username=&season=&week=this|next&fresh=0|1
  GET /lineup?username=&season=&week=this|next&target=mid|floor|ceiling&fresh=0|1
  GET /lineup/diffs?username=&season=&week=this|next&fresh=0|1
  GET /defenses?username=&season=&week=this|next&scope=owned|available|both&fresh=0|1
""")
    with make_server(args.host, args.port, application) as httpd:
        print(f"[api] Serving on http://{args.host}:{args.port}")
        httpd.serve_forever()


if __name__ == "__main__":
    main()

