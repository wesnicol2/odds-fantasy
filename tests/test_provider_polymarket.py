"""Deterministic contract tests for the Polymarket player-prop adapter."""

import unittest

from oddsfantasy.provider_contract import GameRef, GameRequest, PlayerRef, ProviderRequest
from oddsfantasy.provider_polymarket import PolymarketProvider


class MemoryCache:
    def __init__(self):
        self.entries = {}

    def get(self, key, mode):
        if mode == "fresh":
            return None
        return self.entries.get(key)

    def put(self, key, data):
        self.entries[key] = data


class FakeResponse:
    def __init__(self, data):
        self.data = data

    def raise_for_status(self):
        return None

    def json(self):
        return self.data


class FakeSession:
    def __init__(self):
        self.headers = {}
        self.get_calls = []
        self.post_calls = []

    def mount(self, *args, **kwargs):
        return None

    def get(self, url, params=None, timeout=None):
        self.get_calls.append((url, params or {}, timeout))
        if "/events/slug/" in url:
            return FakeResponse(
                {
                    "id": "game-event",
                    "gameId": "nfl-game-id",
                    "slug": "nfl-kc-mia-2099-09-27",
                    "markets": [],
                }
            )
        if url.endswith("/events/keyset"):
            return FakeResponse(
                {
                    "events": [
                        {
                            "id": "player-props",
                            "gameId": "nfl-game-id",
                            "closed": False,
                            "markets": [
                                {
                                    "id": "market-1",
                                    "question": "De'Von Achane Rushing Yards O/U 59.5",
                                    "description": (
                                        "This market will resolve to Over if De'Von Achane "
                                        "records more than 59.5 rushing yards."
                                    ),
                                    "outcomes": '["Over", "Under"]',
                                    "clobTokenIds": '["over-token", "under-token"]',
                                    "closed": False,
                                    "updatedAt": "2099-09-27T15:00:00Z",
                                }
                            ],
                        }
                    ]
                }
            )
        raise AssertionError(f"unexpected GET {url}")

    def post(self, url, json=None, timeout=None):
        self.post_calls.append((url, json, timeout))
        return FakeResponse(
            {
                "over-token": {"BUY": "0.52"},
                "under-token": {"BUY": "0.51"},
            }
        )


def request(cache_mode="fresh"):
    player = PlayerRef(
        player_id="De'Von Achane",
        full_name="De'Von Achane",
        team="Miami Dolphins",
        position="RB",
    )
    game = GameRef(
        game_id="game-1",
        home_team="Miami Dolphins",
        away_team="Kansas City Chiefs",
        commence_time="2099-09-27T17:00:00Z",
    )
    return ProviderRequest(
        games=(
            GameRequest(
                game=game,
                players=(player,),
                markets=frozenset({"player_rush_yds"}),
            ),
        ),
        cache_mode=cache_mode,
    )


class PolymarketProviderTest(unittest.TestCase):
    def test_game_linked_player_prop_uses_executable_buy_prices(self):
        session = FakeSession()
        result = PolymarketProvider(session=session, cache=MemoryCache()).fetch_quotes(request())

        self.assertEqual(len(result.quotes), 1)
        quote = result.quotes[0]
        self.assertEqual(quote.source.source_id, "polymarket")
        self.assertEqual(quote.source.provider_id, "polymarket")
        self.assertEqual(quote.player_id, "De'Von Achane")
        self.assertEqual(quote.market_key, "player_rush_yds")
        self.assertEqual(quote.predicate.operator, "gt")
        self.assertEqual(quote.predicate.value, 59.5)
        self.assertEqual(quote.yes.implied_probability, 0.52)
        self.assertEqual(quote.no.implied_probability, 0.51)
        self.assertEqual(quote.yes.native_format, "contract_ask")
        self.assertTrue(any("/events/keyset" in call[0] for call in session.get_calls))
        self.assertEqual(
            {row["token_id"] for row in session.post_calls[0][1]},
            {"over-token", "under-token"},
        )
        self.assertTrue(all(row["side"] == "BUY" for row in session.post_calls[0][1]))

    def test_cache_only_miss_is_diagnostic_not_transport_failure(self):
        session = FakeSession()
        result = PolymarketProvider(session=session, cache=MemoryCache()).fetch_quotes(
            request(cache_mode="cache")
        )
        self.assertEqual(result.quotes, ())
        self.assertEqual(session.get_calls, [])
        self.assertEqual(session.post_calls, [])
        self.assertIn("cache_miss", {diagnostic.code for diagnostic in result.diagnostics})


if __name__ == "__main__":
    unittest.main()
