"""Tests for multi-provider evidence orchestration."""

import unittest

from oddsfantasy.provider_contract import (
    ProviderDiagnostic,
    ProviderResult,
    QuoteSource,
    SidePrice,
    StatContractQuote,
    ThresholdPredicate,
)
from oddsfantasy.provider_service import collect_provider_evidence


class PlannedGame:
    def __init__(self):
        self.game_id = "game-1"
        self.home_team = "Miami Dolphins"
        self.away_team = "Kansas City Chiefs"
        self.commence_time = "2099-09-27T17:00:00Z"
        self.players = [
            {
                "full_name": "De'Von Achane",
                "alias": "De'Von Achane",
                "primary_position": "RB",
                "editorial_team_full_name": "Miami Dolphins",
            }
        ]
        self.markets = ["player_rush_yds", "player_rush_yds_alternate"]


class FakeProvider:
    def __init__(self, provider_id, probability):
        self.provider_id = provider_id
        self.probability = probability
        self.requests = []

    def fetch_quotes(self, request):
        self.requests.append(request)
        quote = StatContractQuote(
            source=QuoteSource(self.provider_id, self.provider_id, self.provider_id.title()),
            game_id="game-1",
            player_id="De'Von Achane",
            market_key="player_rush_yds",
            predicate=ThresholdPredicate("gte", 60),
            yes=SidePrice(self.probability),
            no=SidePrice(1.03 - self.probability),
        )
        return ProviderResult(
            provider_id=self.provider_id,
            quotes=(quote,),
            diagnostics=(
                ProviderDiagnostic(
                    self.provider_id,
                    "accepted_quotes",
                    "accepted one",
                ),
            ),
        )


class FailingProvider:
    provider_id = "kalshi"

    def fetch_quotes(self, request):
        raise RuntimeError("synthetic outage")


def odds_api_payload():
    return {
        "bookmakers": [
            {
                "key": "draftkings",
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


class ProviderServiceTest(unittest.TestCase):
    def test_all_sources_enter_same_book_map(self):
        polymarket = FakeProvider("polymarket", 0.54)
        kalshi = FakeProvider("kalshi", 0.56)
        bundle = collect_provider_evidence(
            {"game-1": odds_api_payload()},
            {"game-1": PlannedGame()},
            "fresh",
            providers={"polymarket": polymarket, "kalshi": kalshi},
            enabled_ids=("odds_api", "polymarket", "kalshi"),
        )

        books = bundle.players_odds["De'Von Achane"]
        self.assertEqual(set(books), {"draftkings", "polymarket", "kalshi"})
        self.assertEqual(bundle.providers_used, ("kalshi", "odds_api", "polymarket"))
        request = polymarket.requests[0]
        self.assertEqual(request.games[0].markets, frozenset({"player_rush_yds"}))

    def test_provider_failure_is_isolated(self):
        bundle = collect_provider_evidence(
            {"game-1": odds_api_payload()},
            {"game-1": PlannedGame()},
            "fresh",
            providers={"kalshi": FailingProvider()},
            enabled_ids=("odds_api", "kalshi"),
        )

        self.assertIn("draftkings", bundle.players_odds["De'Von Achane"])
        errors = [
            item
            for item in bundle.diagnostics
            if item["provider_id"] == "kalshi" and item["code"] == "transport_error"
        ]
        self.assertEqual(len(errors), 1)
        self.assertIn("synthetic outage", errors[0]["message"])

    def test_unknown_provider_is_visible_in_diagnostics(self):
        bundle = collect_provider_evidence(
            {},
            {},
            "fresh",
            providers={},
            enabled_ids=("mystery",),
        )
        self.assertEqual(bundle.players_odds, {})
        self.assertEqual(bundle.diagnostics[0]["code"], "unknown_provider")


if __name__ == "__main__":
    unittest.main()
