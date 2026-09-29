"""Read-only inspection helpers for Odds Fantasy JSON caches."""

from __future__ import annotations

import hashlib
import json
import time
from pathlib import Path
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from .config import DATA_DIR

_SECRET_QUERY_KEYS = {
    "apikey",
    "api_key",
    "authorization",
    "access_token",
    "password",
    "secret",
}
_SECRET_FIELD_KEYS = _SECRET_QUERY_KEYS | {"x-api-key"}


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


def _redact(value: Any, field_name: str | None = None) -> Any:
    if field_name and field_name.lower() in _SECRET_FIELD_KEYS:
        return "[redacted]"
    if isinstance(value, dict):
        return {str(key): _redact(item, str(key)) for key, item in value.items()}
    if isinstance(value, list):
        return [_redact(item) for item in value]
    if isinstance(value, str):
        return _redact_url(value)
    return value


def _entry_metadata(value: Any, now: float) -> tuple[float | None, float | None, str]:
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
    if isinstance(payload, dict):
        iterator = ((str(key), value) for key, value in payload.items())
    elif isinstance(payload, list):
        iterator = ((f"[{index}]", value) for index, value in enumerate(payload))
    else:
        iterator = (("value", payload),)
    for key, value in iterator:
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
    path = _safe_cache_path(filename)
    if path is None:
        raise FileNotFoundError(filename)
    payload = _load(path)
    if isinstance(payload, dict):
        iterator = ((str(key), value) for key, value in payload.items())
    elif isinstance(payload, list):
        iterator = ((f"[{index}]", value) for index, value in enumerate(payload))
    else:
        iterator = (("value", payload),)
    for key, value in iterator:
        if _entry_id(key) == entry_id:
            return {
                "file": filename,
                "id": entry_id,
                "key": _redact_url(key),
                "value": _redact(value),
            }
    raise KeyError(entry_id)
