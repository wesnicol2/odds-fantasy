import json
import time

import pytest

from oddsfantasy import cache_browser


def test_cache_index_lists_cache_files_and_redacts_request_keys(monkeypatch, tmp_path):
    monkeypatch.setattr(cache_browser, "DATA_DIR", str(tmp_path))
    now = time.time()
    cache_path = tmp_path / "odds_api_cache.json"
    cache_path.write_text(
        json.dumps(
            {
                "https://api.example.test/events?apiKey=top-secret&regions=us": {
                    "fetched_at": now - 30,
                    "data": [{"id": "event-1"}],
                }
            }
        ),
        encoding="utf-8",
    )
    (tmp_path / "not_cache_data.json").write_text("{}", encoding="utf-8")

    files = cache_browser.list_cache_files()["files"]
    assert [item["name"] for item in files] == ["odds_api_cache.json"]
    assert files[0]["entry_count"] == 1

    entries = cache_browser.list_cache_entries("odds_api_cache.json")["entries"]
    assert len(entries) == 1
    assert "top-secret" not in entries[0]["key"]
    assert "redacted" in entries[0]["key"]
    assert entries[0]["summary"] == "array · 1 items"
    assert entries[0]["age_seconds"] is not None


def test_cache_inspector_rejects_path_traversal(monkeypatch, tmp_path):
    monkeypatch.setattr(cache_browser, "DATA_DIR", str(tmp_path))
    (tmp_path / "safe_cache.json").write_text("{}", encoding="utf-8")

    with pytest.raises(FileNotFoundError):
        cache_browser.list_cache_entries("../safe_cache.json")


def test_cache_entry_lookup_returns_metadata_only(monkeypatch, tmp_path):
    monkeypatch.setattr(cache_browser, "DATA_DIR", str(tmp_path))
    (tmp_path / "polymarket_provider_cache.json").write_text(
        json.dumps(
            {"GET https://example.test/markets": {"fetched_at": time.time(), "data": {"x": 1}}}
        ),
        encoding="utf-8",
    )

    entry = cache_browser.list_cache_entries("polymarket_provider_cache.json")["entries"][0]
    detail = cache_browser.get_cache_entry("polymarket_provider_cache.json", entry["id"])

    assert detail["key"] == "GET https://example.test/markets"
    assert detail["summary"] == "object · 1 keys"
    assert "value" not in detail
