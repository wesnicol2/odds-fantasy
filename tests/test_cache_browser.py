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
    (tmp_path / "other_data.json").write_text("{}", encoding="utf-8")

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


def test_cached_odds_rows_normalize_all_three_provider_caches(monkeypatch, tmp_path):
    monkeypatch.setattr(cache_browser, "DATA_DIR", str(tmp_path))
    now = time.time()

    odds_url = "https://api.the-odds-api.com/v4/events/game-1/odds?apiKey=secret"
    (tmp_path / "odds_api_cache.json").write_text(
        json.dumps(
            {
                odds_url: {
                    "bookmakers": [
                        {
                            "key": "draftkings",
                            "title": "DraftKings",
                            "markets": [
                                {
                                    "key": "player_rush_yds",
                                    "outcomes": [
                                        {
                                            "name": "Over",
                                            "description": "De'Von Achane",
                                            "price": 1.91,
                                            "point": 59.5,
                                        },
                                        {
                                            "name": "Under",
                                            "description": "De'Von Achane",
                                            "price": 1.91,
                                            "point": 59.5,
                                        },
                                    ],
                                }
                            ],
                        }
                    ]
                }
            }
        ),
        encoding="utf-8",
    )
    (tmp_path / "odds_api_cache_meta.json").write_text(
        json.dumps({odds_url: now - 30}),
        encoding="utf-8",
    )

    polymarket_market = {
        "id": "pm-market-1",
        "question": "De'Von Achane Rushing Yards O/U 59.5",
        "description": "Resolves Over if De'Von Achane records more than 59.5 rushing yards.",
        "outcomes": '["Over", "Under"]',
        "clobTokenIds": '["over-token", "under-token"]',
    }
    (tmp_path / "polymarket_provider_cache.json").write_text(
        json.dumps(
            {
                "GET https://gamma-api.polymarket.com/events/keyset": {
                    "fetched_at": now - 20,
                    "data": {"events": [{"markets": [polymarket_market]}]},
                },
                "POST https://clob.polymarket.com/prices": {
                    "fetched_at": now - 10,
                    "data": {
                        "over-token": {"BUY": "0.52"},
                        "under-token": {"BUY": "0.51"},
                    },
                },
            }
        ),
        encoding="utf-8",
    )

    (tmp_path / "kalshi_provider_cache.json").write_text(
        json.dumps(
            {
                "GET https://external-api.kalshi.com/trade-api/v2/markets": {
                    "fetched_at": now - 15,
                    "data": {
                        "markets": [
                            {
                                "ticker": "KXNFLRSHYDS-99SEP27KCMIA-ACHANE-60",
                                "event_ticker": "KXNFLRSHYDS-99SEP27KCMIA",
                                "yes_sub_title": "De'Von Achane: 60+",
                                "yes_ask_dollars": "0.53",
                                "no_ask_dollars": "0.50",
                            }
                        ]
                    },
                }
            }
        ),
        encoding="utf-8",
    )

    result = cache_browser.cached_odds_rows("achane")
    assert result["count"] == 6
    assert {row["source"] for row in result["rows"]} == {"DraftKings", "Polymarket", "Kalshi"}

    polymarket_over = next(
        row
        for row in result["rows"]
        if row["source"] == "Polymarket" and row["side"] == "Over"
    )
    assert polymarket_over["line"] == 59.5
    assert polymarket_over["probability"] == 0.52
    assert polymarket_over["price_source"] == "CLOB BUY ask"

    kalshi_yes = next(
        row for row in result["rows"] if row["source"] == "Kalshi" and row["side"] == "Yes"
    )
    assert kalshi_yes["player"] == "De'Von Achane"
    assert kalshi_yes["market"] == "Rushing yards"
    assert kalshi_yes["probability"] == 0.53

    draftkings_over = next(
        row
        for row in result["rows"]
        if row["source"] == "DraftKings" and row["side"] == "Over"
    )
    assert draftkings_over["american_odds"] == -110


def test_cached_odds_search_matches_market_name(monkeypatch, tmp_path):
    monkeypatch.setattr(cache_browser, "DATA_DIR", str(tmp_path))
    (tmp_path / "kalshi_provider_cache.json").write_text(
        json.dumps(
            {
                "request": {
                    "fetched_at": time.time(),
                    "data": {
                        "markets": [
                            {
                                "ticker": "KXNFLTD-99SEP27KCMIA-ACHANE-1",
                                "event_ticker": "KXNFLTD-99SEP27KCMIA",
                                "yes_sub_title": "De'Von Achane: 1+",
                                "yes_ask_dollars": "0.44",
                                "no_ask_dollars": "0.59",
                            }
                        ]
                    },
                }
            }
        ),
        encoding="utf-8",
    )

    result = cache_browser.cached_odds_rows("anytime touchdown")
    assert result["count"] == 2
    assert all(row["market"] == "Anytime touchdown" for row in result["rows"])
