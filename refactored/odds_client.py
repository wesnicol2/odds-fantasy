from __future__ import annotations

import os
import json
import time
import threading
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from typing import Any
REQ_TIMEOUT = (5, 20)  # (connect, read) seconds

# Reuse HTTP connections for speed
_SESSION = requests.Session()
_SESSION.headers.update({"Accept": "application/json"})
_SESSION.mount("https://", HTTPAdapter(pool_connections=16, pool_maxsize=32))
_SESSION.mount("http://", HTTPAdapter(pool_connections=16, pool_maxsize=32))
from config import API_KEY, EVENTS_URL, DATA_DIR
from . import ratelimit


_CACHE_FILE = os.path.join(DATA_DIR, "odds_api_cache.json")
_META_FILE = os.path.join(DATA_DIR, "odds_api_cache_meta.json")
_CACHE_LOCK = threading.RLock()
_MEM_CACHE: dict | None = None
_META: dict | None = None

# TTL (seconds) for auto mode
ODDS_TTL = int(os.getenv("ODDS_TTL", "43200"))  # 12h default

# Debug toggle for cache timing
_DBG = os.getenv("CACHE_DEBUG") in ("1", "true", "True") or os.getenv("API_DEBUG") in ("1", "true", "True")

def _log(msg: str):
    if _DBG:
        print(f"[cache] {msg}", flush=True)


def _load_cache() -> dict:
    global _MEM_CACHE
    with _CACHE_LOCK:
        if _MEM_CACHE is not None:
            return _MEM_CACHE
        if not os.path.exists(_CACHE_FILE):
            _MEM_CACHE = {}
            _log("load: no file; mem=0")
            return _MEM_CACHE
        t0 = time.perf_counter()
        try:
            size = os.path.getsize(_CACHE_FILE)
        except Exception:
            size = -1
        try:
            with open(_CACHE_FILE, "r", encoding="utf-8") as f:
                _MEM_CACHE = json.load(f)
            dt = (time.perf_counter() - t0) * 1000.0
            _log(f"load: disk bytes={size} keys={len(_MEM_CACHE)} dt_ms={dt:.1f}")
            return _MEM_CACHE
        except Exception as e:
            _log(f"load: error {e}")
            _MEM_CACHE = {}
            return _MEM_CACHE


def _save_cache(cache: dict, url: str | None = None) -> None:
    global _MEM_CACHE
    with _CACHE_LOCK:
        _MEM_CACHE = cache
        try:
            os.makedirs(DATA_DIR, exist_ok=True)
            t0 = time.perf_counter()
            tmp = _CACHE_FILE + ".tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(cache, f, indent=2)
            os.replace(tmp, _CACHE_FILE)
            dt = (time.perf_counter() - t0) * 1000.0
            _log(f"save: keys={len(cache)} dt_ms={dt:.1f}")
        except Exception as e:
            _log(f"save: error {e}")
        # Update URL timestamp
        if url is not None:
            meta = _load_meta()
            meta[url] = int(time.time())
            try:
                with open(_META_FILE, "w", encoding="utf-8") as f:
                    json.dump(meta, f, indent=2)
            except Exception:
                pass


def _load_meta() -> dict:
    global _META
    with _CACHE_LOCK:
        if _META is not None:
            return _META
        if not os.path.exists(_META_FILE):
            _META = {}
            return _META
        try:
            with open(_META_FILE, "r", encoding="utf-8") as f:
                _META = json.load(f)
        except Exception:
            _META = {}
        return _META


def _is_fresh_enough(url: str) -> bool:
    meta = _load_meta()
    ts = meta.get(url)
    if not ts:
        return False
    age = int(time.time()) - int(ts)
    return age < ODDS_TTL


def get_nfl_events(regions: str = "us", mode: str = "auto", use_saved_data: bool | None = None) -> list[dict[str, Any]]:
    """Fetch NFL events with per-URL TTL cache.

    mode: 'auto' (TTL), 'cache' (cache-only), 'fresh' (network only)
    use_saved_data: legacy flag; when provided overrides mode mapping to 'cache'/'fresh'.
    """
    if use_saved_data is not None:
        mode = 'cache' if use_saved_data else 'fresh'
    url = f"{EVENTS_URL}?apiKey={API_KEY}&regions={regions}"
    t0 = time.perf_counter()
    cache = _load_cache()
    if mode == 'cache':
        # Strict cache-only behavior
        if url in cache:
            _log(f"events: CACHE_HIT dt_ms={(time.perf_counter()-t0)*1000.0:.1f}")
            ratelimit.update_cached("events")
            return cache[url]
        _log("events: CACHE_MISS strict")
        ratelimit.update_cached("events")
        return []
    if mode == 'auto':
        if url in cache and _is_fresh_enough(url):
            _log(f"events: TTL_HIT dt_ms={(time.perf_counter()-t0)*1000.0:.1f}")
            ratelimit.update_cached("events")
            return cache[url]
        _log("events: TTL_EXPIRED or MISS; fetching")

    # Fresh mode: bypass cache and hit network
    resp = _SESSION.get(url, timeout=REQ_TIMEOUT)
    resp.raise_for_status()
    data = resp.json()
    ratelimit.update_from_response(resp.headers, "events")
    cache[url] = data
    _save_cache(cache, url)
    _log(f"events: NETWORK dt_ms={(time.perf_counter()-t0)*1000.0:.1f}")
    return data


def get_event_player_odds(event_id: str, regions: str = "us", markets: str = "", mode: str = "auto", use_saved_data: bool | None = None):
    if use_saved_data is not None:
        mode = 'cache' if use_saved_data else 'fresh'
    url = f"{EVENTS_URL}/{event_id}/odds?apiKey={API_KEY}&regions={regions}&markets={markets}"
    t0 = time.perf_counter()
    cache = _load_cache()
    if mode == 'cache':
        if url in cache:
            _log(f"event:{event_id} CACHE_HIT dt_ms={(time.perf_counter()-t0)*1000.0:.1f}")
            ratelimit.update_cached(f"event_odds:{event_id}")
            return cache[url]
        _log(f"event:{event_id} CACHE_MISS strict")
        ratelimit.update_cached(f"event_odds:{event_id}")
        return {}
    if mode == 'auto':
        if url in cache and _is_fresh_enough(url):
            _log(f"event:{event_id} TTL_HIT dt_ms={(time.perf_counter()-t0)*1000.0:.1f}")
            ratelimit.update_cached(f"event_odds:{event_id}")
            return cache[url]

    resp = _SESSION.get(url, timeout=REQ_TIMEOUT)
    resp.raise_for_status()
    data = resp.json()
    ratelimit.update_from_response(resp.headers, f"event_odds:{event_id}")
    cache[url] = data
    _save_cache(cache, url)
    _log(f"event:{event_id} NETWORK dt_ms={(time.perf_counter()-t0)*1000.0:.1f}")
    return data
