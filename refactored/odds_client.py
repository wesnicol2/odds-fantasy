from __future__ import annotations

import os
import json
import requests
from typing import Any

from config import API_KEY, EVENTS_URL, DATA_DIR
from . import ratelimit


_CACHE_FILE = os.path.join(DATA_DIR, "odds_api_cache.json")


def _load_cache() -> dict:
    if not os.path.exists(_CACHE_FILE):
        return {}
    try:
        with open(_CACHE_FILE, "r") as f:
            return json.load(f)
    except Exception:
        return {}


def _save_cache(cache: dict) -> None:
    try:
        os.makedirs(DATA_DIR, exist_ok=True)
        with open(_CACHE_FILE, "w") as f:
            json.dump(cache, f, indent=2)
    except Exception:
        pass


def get_nfl_events(regions: str = "us", use_saved_data: bool = True) -> list[dict[str, Any]]:
    url = f"{EVENTS_URL}?apiKey={API_KEY}&regions={regions}"
    cache = _load_cache()
    if use_saved_data and url in cache:
        ratelimit.update_cached("events")
        return cache[url]

    resp = requests.get(url)
    resp.raise_for_status()
    data = resp.json()
    ratelimit.update_from_response(resp.headers, "events")
    cache[url] = data
    _save_cache(cache)
    return data


def get_event_player_odds(event_id: str, regions: str = "us", markets: str = "", use_saved_data: bool = True):
    url = f"{EVENTS_URL}/{event_id}/odds?apiKey={API_KEY}&regions={regions}&markets={markets}"
    cache = _load_cache()
    if use_saved_data and url in cache:
        ratelimit.update_cached(f"event_odds:{event_id}")
        return cache[url]

    resp = requests.get(url)
    resp.raise_for_status()
    data = resp.json()
    ratelimit.update_from_response(resp.headers, f"event_odds:{event_id}")
    cache[url] = data
    _save_cache(cache)
    return data

