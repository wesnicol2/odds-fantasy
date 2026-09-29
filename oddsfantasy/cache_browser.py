"""Read-only odds/cache inspection for Odds Fantasy provider caches."""

from __future__ import annotations

import hashlib
import json
import re
import time
from pathlib import Path
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from . import provider_kalshi, provider_polymarket
from .config import DATA_DIR

_SECRET_QUERY_KEYS = {
    "apikey",
    "api_key",
    "authorization",
    "access_token",
    "password",
    "secret",
}

_MARKET_LABELS = {
    "player_pass_yds": "Passing yards",
    "player_pass_tds": "Passing touchdowns",
    "player_pass_interceptions": "Interceptions",
    "player_rush_yds": "Rushing yards",
    "player_receptions": "Receptions",
    "player_reception_yds": "Receiving yards",
    "player_anytime_td": "Anytime touchdown",
    "player_kicking_points": "Kicking points",
}

_PLAYER_PREFIX_PATTERNS = (
    re.compile(r"^(?P<name>.+?)\s+(?:passing|rushing|receiving)\s+yards\b", re.I),
    re.compile(r"^(?P<name>.+?)\s+(?:passing\s+)?touchdowns?\b", re.I),
    re.compile(r"^(?P<name>.+?)\s+receptions?\b", re.I),
    re.compile(r"^will\s+(?P<name>.+?)\s+score\b", re.I),
)


def _cache_paths() -> list[Path]:
    root = Path(DATA_DIR)
    if not root.exists():
        return []
    return sorted(
        path
        for path in root.glob("*cache*.json")
        if path.is_file() and path.parent.resolve() == root.resolve()
    )


def _safe_cache_path(filename: str) -> Path | None:
    if not filename or Path(filename).name != filename:
        return None
    for path in _cache_paths():
        if path.name == filename:
            return path
    return None


def _load(path: Path) -> Any:
    with path.open(encoding="utf-8") as handle:
        return json.load(handle)


def _entry_id(key: str) -> str:
    return hashlib.sha256(key.encode("utf-8")).hexdigest()[:20]


def _redact_url(value: str) -> str:
    try:
        parts = urlsplit(value)
    except ValueError:
        return value
    if not parts.scheme or not parts.netloc or not parts.query:
        return value
    changed = False
    query: list[tuple[str, str]] = []
    for key, raw_value in parse_qsl(parts.query, keep_blank_values=True):
        if key.lower() in _SECRET_QUERY_KEYS:
            query.append((key, "[redacted]"))
            changed = True
        else:
            query.append((key, raw_value))
    if not changed:
        return value
    return urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(query), parts.fragment))


def _entry_payload(value: Any) -> tuple[float | None, Any]:
    fetched_at: float | None = None
    if isinstance(value, dict):
        raw_fetched_at = value.get("fetched_at")
        try:
            fetched_at = float(raw_fetched_at) if raw_fetched_at is not None else None
        except (TypeError, ValueError):
            fetched_at = None
        payload = value.get("data") if "data" in value else value
    else:
        payload = value
    return fetched_at, payload


def _entry_metadata(value: Any, now: float) -> tuple[float | None, float | None, str]:
    fetched_at, payload = _entry_payload(value)
    age = max(0.0, now - fetched_at) if fetched_at is not None else None
    if isinstance(payload, dict):
        summary = f"object · {len(payload)} keys"
    elif isinstance(payload, list):
        summary = f"array · {len(payload)} items"
    elif payload is None:
        summary = "null"
    else:
        summary = type(payload).__name__
    return fetched_at, age, summary


def _iter_entries(payload: Any):
    if isinstance(payload, dict):
        return ((str(key), value) for key, value in payload.items())
    if isinstance(payload, list):
        return ((f"[{index}]", value) for index, value in enumerate(payload))
    return iter((("value", payload),))


def _walk_dicts(value: Any):
    if isinstance(value, dict):
        yield value
        for child in value.values():
            yield from _walk_dicts(child)
    elif isinstance(value, list):
        for child in value:
            yield from _walk_dicts(child)


def _json_list(value: object) -> list[str]:
    if isinstance(value, list):
        return [str(item) for item in value]
    if not isinstance(value, str):
        return []
    try:
        parsed = json.loads(value)
    except ValueError:
        return []
    return [str(item) for item in parsed] if isinstance(parsed, list) else []


def _probability(value: object) -> float | None:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    return parsed if 0.0 < parsed <= 1.0 else None


def _decimal(value: object) -> float | None:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    return parsed if parsed > 1.0 else None


def _american_from_decimal(decimal_odds: float | None) -> int | None:
    if decimal_odds is None or decimal_odds <= 1.0:
        return None
    if decimal_odds >= 2.0:
        return round((decimal_odds - 1.0) * 100.0)
    return round(-100.0 / (decimal_odds - 1.0))


def _price_fields(probability: float | None, decimal_odds: float | None = None) -> dict[str, Any]:
    if decimal_odds is None and probability is not None:
        decimal_odds = 1.0 / probability
    if probability is None and decimal_odds is not None:
        probability = 1.0 / decimal_odds
    return {
        "probability": probability,
        "decimal_odds": decimal_odds,
        "american_odds": _american_from_decimal(decimal_odds),
    }


def _age_seconds(now: float, fetched_at: float | None) -> float | None:
    return max(0.0, now - fetched_at) if fetched_at is not None else None


def _market_label(market_key: str | None, raw_title: str) -> str:
    if market_key:
        base = market_key.removesuffix("_alternate")
        if base in _MARKET_LABELS:
            suffix = " · alternate" if market_key.endswith("_alternate") else ""
            return f"{_MARKET_LABELS[base]}{suffix}"
        return base.replace("player_", "").replace("_", " ").title()
    return raw_title or "Unknown market"


def _infer_player(raw_title: str) -> str:
    title = raw_title.strip()
    for pattern in _PLAYER_PREFIX_PATTERNS:
        match = pattern.search(title)
        if match:
            return match.group("name").strip(" :-")
    if ":" in title:
        prefix = title.split(":", 1)[0].strip()
        if 1 < len(prefix.split()) <= 5:
            return prefix
    return ""


def _row_id(*parts: object) -> str:
    raw = "|".join(str(part or "") for part in parts)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:20]


def _odds_api_rows(path: Path, now: float) -> list[dict[str, Any]]:
    payload = _load(path)
    meta_path = Path(DATA_DIR) / "odds_api_cache_meta.json"
    try:
        meta = _load(meta_path) if meta_path.exists() else {}
    except (OSError, ValueError):
        meta = {}
    rows: list[dict[str, Any]] = []
    for cache_key, cached_value in _iter_entries(payload):
        fetched_at = None
        try:
            fetched_at = float(meta.get(cache_key)) if isinstance(meta, dict) and meta.get(cache_key) else None
        except (TypeError, ValueError):
            fetched_at = None
        _, data = _entry_payload(cached_value)
        if not isinstance(data, dict):
            continue
        for bookmaker in data.get("bookmakers") or []:
            if not isinstance(bookmaker, dict):
                continue
            source = str(bookmaker.get("title") or bookmaker.get("key") or "Sportsbook")
            for market in bookmaker.get("markets") or []:
                if not isinstance(market, dict):
                    continue
                market_key = str(market.get("key") or "")
                market_name = _market_label(market_key, market_key)
                for outcome in market.get("outcomes") or []:
                    if not isinstance(outcome, dict):
                        continue
                    decimal_odds = _decimal(outcome.get("price"))
                    side = str(outcome.get("name") or "")
                    player = str(outcome.get("description") or "")
                    line = outcome.get("point")
                    raw_title = " · ".join(
                        part
                        for part in (
                            player,
                            market_name,
                            f"{side} {line}" if line is not None else side,
                        )
                        if part
                    )
                    rows.append(
                        {
                            "id": _row_id("odds_api", source, market_key, player, side, line),
                            "provider": "Odds API",
                            "source": source,
                            "player": player,
                            "market": market_name,
                            "market_key": market_key,
                            "side": side,
                            "line": line,
                            **_price_fields(None, decimal_odds),
                            "price_source": "Sportsbook price",
                            "raw_title": raw_title,
                            "cache_file": path.name,
                            "fetched_at": fetched_at,
                            "age_seconds": _age_seconds(now, fetched_at),
                        }
                    )
    return rows


def _polymarket_rows(path: Path, now: float) -> list[dict[str, Any]]:
    payload = _load(path)
    token_prices: dict[str, tuple[float, float | None]] = {}
    entries: list[tuple[float | None, Any]] = []
    for _, cached_value in _iter_entries(payload):
        fetched_at, data = _entry_payload(cached_value)
        entries.append((fetched_at, data))
        if not isinstance(data, dict):
            continue
        for token_id, price_row in data.items():
            if not isinstance(price_row, dict):
                continue
            probability = _probability(price_row.get("BUY"))
            if probability is not None:
                token_prices[str(token_id)] = (probability, fetched_at)

    rows: list[dict[str, Any]] = []
    seen: set[str] = set()
    for fetched_at, data in entries:
        for market in _walk_dicts(data):
            outcomes = _json_list(market.get("outcomes"))
            token_ids = _json_list(market.get("clobTokenIds"))
            if not outcomes or len(outcomes) != len(token_ids):
                continue
            raw_title = str(
                market.get("question")
                or market.get("title")
                or market.get("groupItemTitle")
                or market.get("slug")
                or ""
            ).strip()
            description = str(market.get("description") or "").strip()
            combined_text = f"{raw_title} {description}".strip()
            market_key = provider_polymarket._market_key(combined_text)
            predicate = provider_polymarket._predicate(combined_text, market_key) if market_key else None
            line = predicate.value if predicate is not None else None
            player = _infer_player(raw_title)
            display_prices = _json_list(market.get("outcomePrices"))
            market_id = str(market.get("id") or market.get("slug") or raw_title)

            for index, (outcome, token_id) in enumerate(zip(outcomes, token_ids, strict=True)):
                probability = None
                price_fetched_at = fetched_at
                price_source = "No cached executable price"
                token_price = token_prices.get(token_id)
                if token_price is not None:
                    probability, price_fetched_at = token_price
                    price_source = "CLOB BUY ask"
                elif index < len(display_prices):
                    probability = _probability(display_prices[index])
                    if probability is not None:
                        price_source = "Gamma displayed price"
                row_key = _row_id("polymarket", market_id, outcome, token_id)
                if row_key in seen:
                    continue
                seen.add(row_key)
                rows.append(
                    {
                        "id": row_key,
                        "provider": "Polymarket",
                        "source": "Polymarket",
                        "player": player,
                        "market": _market_label(market_key, raw_title),
                        "market_key": market_key or "",
                        "side": outcome,
                        "line": line,
                        **_price_fields(probability),
                        "price_source": price_source,
                        "raw_title": raw_title,
                        "cache_file": path.name,
                        "fetched_at": price_fetched_at,
                        "age_seconds": _age_seconds(now, price_fetched_at),
                    }
                )
    return rows


def _kalshi_market_key(market: dict[str, Any]) -> str | None:
    ticker = str(market.get("event_ticker") or market.get("ticker") or "")
    for market_key, series in provider_kalshi.SERIES_BY_MARKET.items():
        if ticker.startswith(series):
            return market_key
    return None


def _kalshi_rows(path: Path, now: float) -> list[dict[str, Any]]:
    payload = _load(path)
    rows: list[dict[str, Any]] = []
    seen: set[str] = set()
    for _, cached_value in _iter_entries(payload):
        fetched_at, data = _entry_payload(cached_value)
        for market in _walk_dicts(data):
            if not isinstance(market, dict) or not market.get("ticker"):
                continue
            if not any(
                field in market
                for field in (
                    "yes_ask_dollars",
                    "no_ask_dollars",
                    "yes_bid_dollars",
                    "no_bid_dollars",
                )
            ):
                continue
            raw_title = str(
                market.get("yes_sub_title")
                or market.get("subtitle")
                or market.get("title")
                or market.get("ticker")
                or ""
            )
            parsed_label = provider_kalshi._market_label(market)
            player = parsed_label[0] if parsed_label else _infer_player(raw_title)
            line = parsed_label[1] if parsed_label else None
            market_key = _kalshi_market_key(market)
            ticker = str(market.get("ticker") or raw_title)

            for side in ("yes", "no"):
                probability = provider_kalshi._ask(market, side)
                if market.get(f"{side}_ask_dollars") is not None:
                    price_source = "Contract ask"
                elif probability is not None:
                    price_source = "Derived ask from opposite bid"
                else:
                    price_source = "No cached executable price"
                row_key = _row_id("kalshi", ticker, side)
                if row_key in seen:
                    continue
                seen.add(row_key)
                rows.append(
                    {
                        "id": row_key,
                        "provider": "Kalshi",
                        "source": "Kalshi",
                        "player": player,
                        "market": _market_label(market_key, raw_title),
                        "market_key": market_key or "",
                        "side": side.title(),
                        "line": line,
                        **_price_fields(probability),
                        "price_source": price_source,
                        "raw_title": raw_title,
                        "cache_file": path.name,
                        "fetched_at": fetched_at,
                        "age_seconds": _age_seconds(now, fetched_at),
                    }
                )
    return rows


def cached_odds_rows(query: str = "") -> dict[str, Any]:
    """Flatten supported provider caches into searchable, sanitized odds rows."""
    now = time.time()
    rows: list[dict[str, Any]] = []
    parsers = {
        "odds_api_cache.json": _odds_api_rows,
        "polymarket_provider_cache.json": _polymarket_rows,
        "kalshi_provider_cache.json": _kalshi_rows,
    }
    for path in _cache_paths():
        parser = parsers.get(path.name)
        if parser is None:
            continue
        try:
            rows.extend(parser(path, now))
        except (OSError, ValueError):
            continue

    needle = query.strip().lower()
    if needle:
        rows = [
            row
            for row in rows
            if needle
            in " ".join(
                str(row.get(field) or "")
                for field in (
                    "player",
                    "market",
                    "market_key",
                    "provider",
                    "source",
                    "side",
                    "raw_title",
                )
            ).lower()
        ]

    rows.sort(
        key=lambda row: (
            str(row.get("player") or row.get("raw_title") or "").lower(),
            str(row.get("market") or "").lower(),
            str(row.get("provider") or "").lower(),
            str(row.get("source") or "").lower(),
            str(row.get("side") or "").lower(),
        )
    )
    return {"rows": rows, "count": len(rows)}


def list_cache_files() -> dict[str, Any]:
    files: list[dict[str, Any]] = []
    for path in _cache_paths():
        stat = path.stat()
        try:
            payload = _load(path)
            entry_count = len(payload) if isinstance(payload, (dict, list)) else 1
            parse_error = None
        except (OSError, ValueError) as exc:
            entry_count = 0
            parse_error = str(exc)
        files.append(
            {
                "name": path.name,
                "bytes": stat.st_size,
                "modified_at": stat.st_mtime,
                "entry_count": entry_count,
                "parse_error": parse_error,
            }
        )
    return {"files": files}


def list_cache_entries(filename: str) -> dict[str, Any]:
    path = _safe_cache_path(filename)
    if path is None:
        raise FileNotFoundError(filename)
    payload = _load(path)
    now = time.time()
    entries: list[dict[str, Any]] = []
    for key, value in _iter_entries(payload):
        fetched_at, age_seconds, summary = _entry_metadata(value, now)
        entries.append(
            {
                "id": _entry_id(key),
                "key": _redact_url(key),
                "fetched_at": fetched_at,
                "age_seconds": age_seconds,
                "summary": summary,
            }
        )
    entries.sort(key=lambda item: item["key"])
    return {"file": filename, "entries": entries}


def get_cache_entry(filename: str, entry_id: str) -> dict[str, Any]:
    """Return metadata for one cache entry without exposing its stored payload."""
    path = _safe_cache_path(filename)
    if path is None:
        raise FileNotFoundError(filename)
    payload = _load(path)
    now = time.time()
    for key, value in _iter_entries(payload):
        if _entry_id(key) != entry_id:
            continue
        fetched_at, age_seconds, summary = _entry_metadata(value, now)
        return {
            "file": filename,
            "id": entry_id,
            "key": _redact_url(key),
            "fetched_at": fetched_at,
            "age_seconds": age_seconds,
            "summary": summary,
        }
    raise KeyError(entry_id)
