"""Deterministic contract tests for the Kalshi player-prop adapter."""

import unittest

from oddsfantasy.provider_contract import GameRef, GameRequest, PlayerRef, ProviderRequest
from oddsfantasy.provider_kalshi import KalshiProvider


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
    def __init__(self, payload=None, fail_on_get=False):
        self.payload = payload or {}
        self.fail_on_get = fail_on_get
        self.calls = []
        self.headers = {}

    def mount(self, *args, **kwargs):
        return None

    def get(self, url, params=None, timeout=None):
        if self.fail_on_get:
            raise AssertionError("network should not be called")
        self.calls.append((url, params, timeout))
        return FakeResponse(self.payload)


def request(markets=frozenset({"player_rush_yds"}), cache_mode="fresh"):
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
        games=(GameRequest(game=game, players=(player,), markets=markets),),
        cache_mode=cache_mode,
    )


class KalshiProviderTest(unittest.TestCase):
    def test_open_market_becomes_canonical_probability_quote(self):
        payload = {
            "markets": [
                {
                    "ticker": "KXNFLRSHYDS-99SEP27KCMIA-ACHANE-60",
                    "event_ticker": "KXNFLRSHYDS-99SEP27KCMIA",
                    "yes_sub_title": "De'Von Achane: 60+",
                    "yes_ask_dollars": "0.53",
                    "no_ask_dollars": "0.50",
                    "rules_primary": "Resolves Yes at 60 or more rushing yards.",
                    "updated_time": "2099-09-27T15:00:00Z",
                }
            ]
        }
        session = FakeSession(payload)
        result = KalshiProvider(session=session, cache=MemoryCache()).fetch_quotes(request())

        self.assertEqual(len(result.quotes), 1)
        quote = result.quotes[0]
        self.assertEqual(quote.source.source_id, "kalshi")
        self.assertEqual(quote.source.provider_id, "kalshi")
        self.assertEqual(quote.player_id, "De'Von Achane")
        self.assertEqual(quote.market_key, "player_rush_yds")
        self.assertEqual(quote.predicate.operator, "gte")
        self.assertEqual(quote.predicate.value, 60)
        self.assertEqual(quote.yes.implied_probability, 0.53)
        self.assertEqual(quote.no.implied_probability, 0.50)
        self.assertIn("60 or more", quote.provenance.raw_rules)
        self.assertEqual(session.calls[0][1]["event_ticker"], "KXNFLRSHYDS-99SEP27KCMIA")

    def test_complement_of_opposite_bid_can_supply_missing_ask(self):
        payload = {
            "markets": [
                {
                    "ticker": "KXNFLRSHYDS-99SEP27KCMIA-ACHANE-60",
                    "yes_sub_title": "De'Von Achane: 60+",
                    "yes_bid_dollars": "0.51",
                    "no_bid_dollars": "0.46",
                }
            ]
        }
        result = KalshiProvider(session=FakeSession(payload), cache=MemoryCache()).fetch_quotes(
            request()
        )
        quote = result.quotes[0]
        self.assertAlmostEqual(quote.yes.implied_probability, 0.54)
        self.assertAlmostEqual(quote.no.implied_probability, 0.49)

    def test_unsupported_market_does_not_make_provider_call(self):
        session = FakeSession(fail_on_get=True)
        result = KalshiProvider(session=session, cache=MemoryCache()).fetch_quotes(
            request(frozenset({"player_kicking_points"}))
        )
        self.assertEqual(result.quotes, ())
        self.assertEqual(session.calls, [])

    def test_cache_only_miss_is_diagnostic_not_network_call(self):
        session = FakeSession(fail_on_get=True)
        result = KalshiProvider(session=session, cache=MemoryCache()).fetch_quotes(
            request(cache_mode="cache")
        )
        self.assertEqual(result.quotes, ())
        self.assertIn("cache_miss", {diagnostic.code for diagnostic in result.diagnostics})


if __name__ == "__main__":
    unittest.main()
