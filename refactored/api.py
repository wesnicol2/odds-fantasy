from __future__ import annotations

import json
from urllib.parse import parse_qs
import os
import mimetypes
import hashlib
import gzip
import time
import traceback
from pathlib import Path
from wsgiref.simple_server import make_server, WSGIServer, WSGIRequestHandler
from socketserver import ThreadingMixIn
from typing import Callable

from . import ratelimit
from .services import compute_projections, build_lineup, build_lineup_diffs, list_defenses, build_dashboard


def _json_response(start_response: Callable, status: str, payload: dict, headers_extra: list[tuple[str, str]] | None = None):
    body = json.dumps(payload, indent=2).encode("utf-8")
    headers = [("Content-Type", "application/json; charset=utf-8"), ("Content-Length", str(len(body))), ("Access-Control-Allow-Origin", "*")]
    if headers_extra:
        headers.extend(headers_extra)
    start_response(status, headers)
    return [body]


def _debug_enabled() -> bool:
    return os.getenv('API_DEBUG') in ('1', 'true', 'True')


def _dprint(*args):
    if _debug_enabled():
        print(*args)


def _json_response_adv(environ, start_response: Callable, payload: dict):
    """JSON response with ETag and gzip support."""
    raw = json.dumps(payload, indent=2).encode("utf-8")
    etag = 'W/"' + hashlib.md5(raw).hexdigest() + '"'
    inm = environ.get('HTTP_IF_NONE_MATCH')
    if inm and inm == etag:
        if _debug_enabled():
            _dprint(f"[api] 304 Not Modified etag={etag}")
        start_response('304 Not Modified', [('ETag', etag), ('Access-Control-Allow-Origin', '*')])
        return [b'']

    accept_enc = environ.get('HTTP_ACCEPT_ENCODING', '') or ''
    use_gzip = 'gzip' in accept_enc.lower()
    headers = [("Content-Type", "application/json; charset=utf-8"), ("ETag", etag), ("Access-Control-Allow-Origin", "*")]
    body = raw
    if use_gzip:
        body = gzip.compress(raw)
        headers.append(("Content-Encoding", "gzip"))
    headers.append(("Content-Length", str(len(body))))
    start_response('200 OK', headers)
    return [body]


def _serve_static(environ, start_response: Callable, rel_path: str):
    base = Path(__file__).resolve().parent.parent / 'ui'
    target = base / rel_path
    if rel_path == '':
        target = base / 'index.html'
    if not target.exists() or not target.is_file():
        _dprint(f"[api] static 404 /ui/{rel_path}")
        return _json_response(start_response, '404 Not Found', {"error": "not_found", "path": f"/ui/{rel_path}"})
    ctype, _ = mimetypes.guess_type(str(target))
    ctype = ctype or 'application/octet-stream'
    data = target.read_bytes()
    headers = [("Content-Type", ctype), ("Content-Length", str(len(data))), ("Access-Control-Allow-Origin", "*")]
    _dprint(f"[api] static 200 /ui/{rel_path or 'index.html'} bytes={len(data)} type={ctype}")
    start_response('200 OK', headers)
    return [data]


def application(environ, start_response):
    path = environ.get("PATH_INFO", "/")
    method = environ.get("REQUEST_METHOD", "GET")
    qs = parse_qs(environ.get("QUERY_STRING", ""))

    def q(name: str, default: str = "") -> str:
        v = qs.get(name)
        return v[0] if v else default

    _dprint(f"[api] {method} {path} qs={qs}")

    try:
        if path == "/":
            return _serve_static(environ, start_response, '')

        if path.startswith('/ui/'):
            rel = path[len('/ui/'):]
            return _serve_static(environ, start_response, rel)

        if path == "/health":
            _dprint("[api] GET /health")
            return _json_response(start_response, "200 OK", {"status": "ok", "ratelimit": ratelimit.format_status(), "ratelimit_info": ratelimit.get_details()})

        if path == "/projections":
            username = q("username", "wesnicol")
            season = q("season", "2025")
            week = q("week", "this")
            region = q("region", "us")
            fresh = q("fresh", "0") in ("1", "true", "True")
            t0 = time.time()
            _dprint(f"[api] projections user={username} season={season} week={week} region={region} fresh={fresh}")
            data = compute_projections(username=username, season=season, week=week, region=region, fresh=fresh)
            _dprint(f"[api] projections done players={len(data.get('players', []))} dt={(time.time()-t0):.2f}s")
            return _json_response(start_response, "200 OK", data)

        if path == "/lineup":
            username = q("username", "wesnicol")
            season = q("season", "2025")
            week = q("week", "this")
            target = q("target", "mid")
            fresh = q("fresh", "0") in ("1", "true", "True")
            t0 = time.time()
            _dprint(f"[api] lineup user={username} season={season} week={week} target={target} fresh={fresh}")
            proj = compute_projections(username=username, season=season, week=week, fresh=fresh)
            lineup = build_lineup(proj.get("players", []), target=target)
            lineup["ratelimit"] = ratelimit.format_status()
            lineup["ratelimit_info"] = ratelimit.get_details()
            _dprint(f"[api] lineup done rows={len(lineup.get('lineup', []))} total={lineup.get('total_points')} dt={(time.time()-t0):.2f}s")
            return _json_response(start_response, "200 OK", lineup)

        if path == "/lineup/diffs":
            username = q("username", "wesnicol")
            season = q("season", "2025")
            week = q("week", "this")
            fresh = q("fresh", "0") in ("1", "true", "True")
            t0 = time.time()
            _dprint(f"[api] lineup/diffs user={username} season={season} week={week} fresh={fresh}")
            proj = compute_projections(username=username, season=season, week=week, fresh=fresh)
            diffs = build_lineup_diffs(proj.get("players", []))
            diffs["ratelimit"] = ratelimit.format_status()
            diffs["ratelimit_info"] = ratelimit.get_details()
            _dprint(f"[api] lineup/diffs done from={len(diffs.get('from', {}).get('lineup', []))} floor_changes={len(diffs.get('floor_changes', []))} ceiling_changes={len(diffs.get('ceiling_changes', []))} dt={(time.time()-t0):.2f}s")
            return _json_response(start_response, "200 OK", diffs)

        if path == "/defenses":
            username = q("username", "wesnicol")
            season = q("season", "2025")
            week = q("week", "this")
            scope = q("scope", "both")
            fresh = q("fresh", "0") in ("1", "true", "True")
            t0 = time.time()
            _dprint(f"[api] defenses user={username} season={season} week={week} scope={scope} fresh={fresh}")
            data = list_defenses(username=username, season=season, week=week, scope=scope, fresh=fresh)
            _dprint(f"[api] defenses done rows={len(data.get('defenses', []))} dt={(time.time()-t0):.2f}s")
            return _json_response(start_response, "200 OK", data)

        if path == "/dashboard":
            username = q("username", "wesnicol")
            season = q("season", "2025")
            region = q("region", "us")
            fresh = q("fresh", "0") in ("1", "true", "True")
            t0 = time.time()
            _dprint(f"[api] dashboard user={username} season={season} region={region} fresh={fresh}")
            data = build_dashboard(username=username, season=season, region=region, fresh=fresh)
            _dprint(f"[api] dashboard done rl={data.get('ratelimit')} dt={(time.time()-t0):.2f}s")
            return _json_response_adv(environ, start_response, data)

        return _json_response(start_response, "404 Not Found", {"error": "not_found", "path": path})

    except Exception as e:
        if _debug_enabled():
            _dprint("[api] error:")
            traceback.print_exc()
        else:
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
    class ThreadingWSGIServer(ThreadingMixIn, WSGIServer):
        daemon_threads = True

    with make_server(args.host, args.port, application, server_class=ThreadingWSGIServer, handler_class=WSGIRequestHandler) as httpd:
        print(f"[api] Serving (threaded) on http://{args.host}:{args.port}")
        httpd.serve_forever()


if __name__ == "__main__":
    main()
