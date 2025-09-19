from __future__ import annotations

import json
from urllib.parse import parse_qs
import os
import mimetypes
import hashlib
import gzip
import time
import threading
import urllib.request
import urllib.error
import traceback
import sys
from pathlib import Path
from wsgiref.simple_server import make_server, WSGIServer, WSGIRequestHandler
from socketserver import ThreadingMixIn
from typing import Callable

from . import ratelimit
from . import services  # for detail endpoints
from .services import compute_projections, compute_book_coverage, build_lineup, build_lineup_diffs, list_defenses, build_dashboard

# Module-level debug flag (defaults to False). Can be enabled via --debug CLI.
_DEBUG_FLAG = False

# Ensure immediate console output (line-buffered stdout/stderr)
try:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(line_buffering=True, write_through=True)
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(line_buffering=True, write_through=True)
except Exception:
    pass


def _json_response(start_response: Callable, status: str, payload: dict, headers_extra: list[tuple[str, str]] | None = None):
    body = json.dumps(payload, indent=2).encode("utf-8")
    headers = [("Content-Type", "application/json; charset=utf-8"), ("Content-Length", str(len(body))), ("Access-Control-Allow-Origin", "*")]
    if headers_extra:
        headers.extend(headers_extra)
    start_response(status, headers)
    return [body]


def _debug_enabled() -> bool:
    # Allow CLI flag to take precedence; env var remains as a fallback
    return bool(_DEBUG_FLAG) or os.getenv('API_DEBUG') in ('1', 'true', 'True')


def set_debug(flag: bool) -> None:
    global _DEBUG_FLAG
    _DEBUG_FLAG = bool(flag)


def _dprint(*args):
    if _debug_enabled():
        print(*args, flush=True)


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
    # Ensure UTF-8 charset for textual types to avoid replacement characters (�)
    if ctype.startswith('text/') or ctype in ('application/javascript', 'application/json'):
        if 'charset' not in ctype:
            ctype = f"{ctype}; charset=utf-8"
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
            model = q("model", "const")
            fresh = q("fresh", "0") in ("1", "true", "True")
            mode = q("mode", "auto")
            t0 = time.time()
            _dprint(f"[api] projections user={username} season={season} week={week} region={region} mode={mode} model={model} fresh={fresh}")
            data = compute_projections(username=username, season=season, week=week, region=region, fresh=fresh, cache_mode=('fresh' if fresh else mode), model=model)
            _dprint(f"[api] projections done players={len(data.get('players', []))} dt={(time.time()-t0):.2f}s")
            return _json_response(start_response, "200 OK", data)

        if path == "/book-coverage":
            username = q("username", "wesnicol")
            season = q("season", "2025")
            week = q("week", "this")
            region = q("region", "us")
            model = q("model", "const")
            fresh = q("fresh", "0") in ("1", "true", "True")
            mode = q("mode", "auto")
            t0 = time.time()
            _dprint(f"[api] book-coverage user={username} season={season} week={week} region={region} mode={mode} model={model} fresh={fresh}")
            data = compute_book_coverage(username=username, season=season, week=week, region=region, fresh=fresh, cache_mode=('fresh' if fresh else mode), model=model)
            rows = len((data.get('coverage') or {}).get('rows', []))
            _dprint(f"[api] book-coverage done rows={rows} dt={(time.time()-t0):.2f}s")
            return _json_response(start_response, "200 OK", data)

        if path == "/lineup":
            username = q("username", "wesnicol")
            season = q("season", "2025")
            week = q("week", "this")
            target = q("target", "mid")
            region = q("region", "us")
            model = q("model", "const")
            fresh = q("fresh", "0") in ("1", "true", "True")
            mode = q("mode", "auto")
            t0 = time.time()
            _dprint(f"[api] lineup user={username} season={season} week={week} target={target} region={region} mode={mode} model={model} fresh={fresh}")
            proj = compute_projections(username=username, season=season, week=week, region=region, fresh=fresh, cache_mode=('fresh' if fresh else mode), model=model)
            lineup = build_lineup(proj.get("players", []), target=target)
            lineup["ratelimit"] = ratelimit.format_status()
            lineup["ratelimit_info"] = ratelimit.get_details()
            _dprint(f"[api] lineup done rows={len(lineup.get('lineup', []))} total={lineup.get('total_points')} dt={(time.time()-t0):.2f}s")
            return _json_response(start_response, "200 OK", lineup)

        if path == "/lineup/diffs":
            username = q("username", "wesnicol")
            season = q("season", "2025")
            week = q("week", "this")
            region = q("region", "us")
            model = q("model", "const")
            fresh = q("fresh", "0") in ("1", "true", "True")
            mode = q("mode", "auto")
            t0 = time.time()
            _dprint(f"[api] lineup/diffs user={username} season={season} week={week} region={region} mode={mode} model={model} fresh={fresh}")
            proj = compute_projections(username=username, season=season, week=week, region=region, fresh=fresh, cache_mode=('fresh' if fresh else mode), model=model)
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
            region = q("region", "us")
            fresh = q("fresh", "0") in ("1", "true", "True")
            mode = q("mode", "auto")
            t0 = time.time()
            _dprint(f"[api] defenses user={username} season={season} week={week} scope={scope} region={region} mode={mode} fresh={fresh}")
            data = list_defenses(username=username, season=season, week=week, scope=scope, fresh=fresh, cache_mode=('fresh' if fresh else mode), region=region)
            _dprint(f"[api] defenses done rows={len(data.get('defenses', []))} dt={(time.time()-t0):.2f}s")
            return _json_response(start_response, "200 OK", data)

        if path == "/player/odds":
            username = q("username", "wesnicol")
            season = q("season", "2025")
            week = q("week", "this")
            region = q("region", "us")
            name = q("name", "")
            model = q("model", "const")
            mode = q("mode", "auto")
            t0 = time.time()
            _dprint(f"[api] player/odds user={username} season={season} week={week} name={name} model={model} mode={mode}")
            data = services.get_player_odds_details(username=username, season=season, week=week, region=region, name=name, cache_mode=mode, model=model)
            _dprint(f"[api] player/odds done markets={len(data.get('markets', {}))} dt={(time.time()-t0):.2f}s")
            return _json_response(start_response, "200 OK", data)

        if path == "/defense/odds":
            username = q("username", "wesnicol")
            season = q("season", "2025")
            week = q("week", "this")
            defense = q("defense", "")
            region = q("region", "us")
            mode = q("mode", "auto")
            t0 = time.time()
            _dprint(f"[api] defense/odds user={username} season={season} week={week} defense={defense} region={region} mode={mode}")
            data = services.get_defense_odds_details(username=username, season=season, week=week, defense=defense, cache_mode=mode, region=region)
            _dprint(f"[api] defense/odds done games={len(data.get('games', []))} dt={(time.time()-t0):.2f}s")
            return _json_response(start_response, "200 OK", data)

        if path == "/dashboard":
            username = q("username", "wesnicol")
            season = q("season", "2025")
            region = q("region", "us")
            model = q("model", "const")
            fresh = q("fresh", "0") in ("1", "true", "True")
            mode = q("mode", "auto")
            weeks = q("weeks", "this")  # default lighter workload
            def_scope = q("def_scope", "owned")
            include_players = q("include_players", "1") in ("1", "true", "True")
            t0 = time.time()
            _dprint(f"[api] dashboard user={username} season={season} region={region} mode={mode} model={model} fresh={fresh} weeks={weeks} def_scope={def_scope} include_players={include_players}")
            data = build_dashboard(username=username, season=season, region=region, fresh=fresh, cache_mode=('fresh' if fresh else mode), weeks=weeks, def_scope=def_scope, include_players=include_players, model=model)
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
    parser.add_argument("--debug", action="store_true", help="Enable verbose API debug logging")
    args = parser.parse_args()

    # Set module debug flag from CLI
    set_debug(args.debug)
    if args.debug:
        # propagate to submodules that read env directly
        os.environ['API_DEBUG'] = '1'

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
        allow_reuse_address = True

    class DebugRequestHandler(WSGIRequestHandler):
        def log_message(self, format, *args):  # noqa: A003
            if _debug_enabled():
                try:
                    msg = format % args
                except Exception:
                    msg = str(format)
                reqline = getattr(self, 'requestline', '-')
                try:
                    peer = self.address_string()
                except Exception:
                    peer = '-'
                print(f"[api] {peer} \"{reqline}\" {msg}", flush=True)

    with make_server(args.host, args.port, application, server_class=ThreadingWSGIServer, handler_class=DebugRequestHandler) as httpd:
        print(f"[api] Serving (threaded) on http://{args.host}:{args.port}", flush=True)
        print(f"[api] Debug logging: {'ON' if _debug_enabled() else 'OFF'} (use --debug to enable)", flush=True)
        print("[api] UI: / -> index.html, static under /ui/*", flush=True)
        # Background readiness probe: checks /health and prints READY once reachable
        def _probe_ready(host: str, port: int):
            url = f"http://{host}:{port}/health"
            for _ in range(30):  # ~6s max
                try:
                    with urllib.request.urlopen(url, timeout=2) as resp:
                        status = getattr(resp, 'status', 200)
                        if status == 200:
                            print(f"[api] READY on http://{host}:{port} (health {status})", flush=True)
                            return
                except Exception:
                    time.sleep(0.2)
                    continue
            # If we couldn't reach health in time, still signal readiness of the socket
            print(f"[api] READY on http://{host}:{port} (health not reachable yet)", flush=True)

        threading.Thread(target=_probe_ready, args=(args.host, args.port), daemon=True).start()
        httpd.serve_forever()


if __name__ == "__main__":
    main()
