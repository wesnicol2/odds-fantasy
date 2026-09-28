"""Contract tests for provider-neutral market evidence."""

import datetime as dt
import unittest

from oddsfantasy.provider_contract import (
    ProviderResult,
    QuoteProvenance,
    QuoteSource,
    SidePrice,
    StatContractQuote,
    ThresholdPredicate,
    normalize_predicate,
    quotes_to_players_odds,
)


class PredicateNormalizationTest(unittest.TestCase):
    def test_integer_predicates_map_to_survival_boundaries(self):
        self.assertEqual(normalize_predicate(ThresholdPredicate("gt", 74.5)), (74.5, True))
        self.assertEqual(normalize_predicate(ThresholdPredicate("gte", 75)), (74.5, True))
        self.assertEqual(normalize_predicate(ThresholdPredicate("lt", 75)), (74.5, False))
        self.assertEqual(normalize_predicate(ThresholdPredicate("lte", 74)), (74.5, False))


class CanonicalEvidenceCompatibilityTest(unittest.TestCase):
    def quote(self, source: QuoteSource, probability: float, observed: int = 0):
        return StatContractQuote(
            source=source,
            game_id="game-1",
            player_id="AJ Brown",
            market_key="player_reception_yds",
            predicate=ThresholdPredicate("gte", 75),
            yes=SidePrice(probability, native_price=probability, native_format="contract_ask"),
            no=SidePrice(
                1.04 - probability,
                native_price=1.04 - probability,
                native_format="contract_ask",
            ),
            observed_at=dt.datetime(2026, 9, 27, 17, observed, tzinfo=dt.UTC),
            provenance=QuoteProvenance(
                "event", f"market-{source.provider_id}", "AJ Brown 75+", None
            ),
        )

    def test_canonical_probability_is_preserved_and_decimal_is_compatibility_only(self):
        quote = self.quote(QuoteSource("kalshi", "kalshi", "Kalshi"), 0.55)
        players = quotes_to_players_odds(
            [ProviderResult(provider_id="kalshi", quotes=(quote,))],
            {"AJ Brown": "WR"},
        )
        row = players["AJ Brown"]["kalshi"]["player_reception_yds_alternate"]["alts"][
            "over"
        ][0]
        self.assertEqual(row["point"], 74.5)
        self.assertEqual(row["probability"], 0.55)
        self.assertAlmostEqual(row["odds"], 1 / 0.55)
        self.assertEqual(row["provider"], "kalshi")

    def test_provider_is_not_consensus_identity(self):
        direct = self.quote(QuoteSource("kalshi", "kalshi", "Kalshi"), 0.55, observed=1)
        aggregated = self.quote(QuoteSource("kalshi", "odds_api", "Kalshi"), 0.70, observed=2)
        players = quotes_to_players_odds(
            [
                ProviderResult(provider_id="odds_api", quotes=(aggregated,)),
                ProviderResult(provider_id="kalshi", quotes=(direct,)),
            ],
            {"AJ Brown": "WR"},
        )
        self.assertEqual(list(players["AJ Brown"]), ["kalshi"])
        row = players["AJ Brown"]["kalshi"]["player_reception_yds_alternate"]["alts"][
            "over"
        ][0]
        self.assertEqual(row["probability"], 0.55)
        self.assertEqual(row["provider"], "kalshi")

    def test_same_provider_can_return_many_independent_sources(self):
        draftkings = self.quote(QuoteSource("draftkings", "odds_api", "DraftKings"), 0.54)
        fanduel = self.quote(QuoteSource("fanduel", "odds_api", "FanDuel"), 0.56)
        players = quotes_to_players_odds(
            [ProviderResult(provider_id="odds_api", quotes=(draftkings, fanduel))],
            {"AJ Brown": "WR"},
        )
        self.assertEqual(set(players["AJ Brown"]), {"draftkings", "fanduel"})


if __name__ == "__main__":
    unittest.main()
