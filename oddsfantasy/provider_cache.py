"""Small provider-owned JSON cache with Odds Fantasy cache-mode semantics."""

from __future__ import annotations

import json
import os
import threading
import time
from typing import Any

from .config import DATA_DIR


class JsonProviderCache:
    def __init__(self, provider_id: str, ttl: int):
        self.provider_id = provider_id
        self.ttl = ttl
        self.path = os.path.join(DATA_DIR, f"{provider_id}_provider_cache.json")
        self._lock = threading.RLock()
        self._loaded = False
        self._entries: dict[str, dict[str, Any]] = {}

    def _load(self) -> None:
        if self._loaded:
            return
        with self._lock:
            if self._loaded:
                return
            try:
                with open(self.path, encoding="utf-8") as handle:
                    raw = json.load(handle)
                self._entries = raw if isinstance(raw, dict) else {}
            except (OSError, ValueError):
                self._entries = {}
            self._loaded = True

    def get(self, key: str, mode: str) -> Any | None:
        self._load()
        if mode == "fresh":
            return None
        entry = self._entries.get(key)
        if not isinstance(entry, dict) or "data" not in entry:
            return None
        if mode == "cache":
            return entry["data"]
        try:
            age = time.time() - float(entry.get("fetched_at", 0))
        except (TypeError, ValueError):
            return None
        return entry["data"] if age < self.ttl else None

    def put(self, key: str, data: Any) -> None:
        self._load()
        with self._lock:
            self._entries[key] = {"fetched_at": time.time(), "data": data}
            try:
                os.makedirs(DATA_DIR, exist_ok=True)
                tmp = f"{self.path}.tmp"
                with open(tmp, "w", encoding="utf-8") as handle:
                    json.dump(self._entries, handle, separators=(",", ":"))
                os.replace(tmp, self.path)
            except OSError:
                # The cache is an optimization; a read-only filesystem must not
                # turn valid provider evidence into an application failure.
                pass
