"""Regression invariants exposed by the cache-wide mathematical audit."""

import math
import unittest

from oddsfantasy.projection import project_player, survival_curve
from oddsfantasy.scoring import ScoringConfig


def independent_percentile(values: list[float], q: float) -> float:
    ordered = sorted(values)
    position = (len(ordered) - 1) * q
    lower = int(position)
    upper = min(lower + 1, len(ordered) - 1)
    fraction = position - lower
    return ordered[lower] * (1 - fraction) + ordered[upper] * fraction


class CanonicalMarketScopeTest(unittest.TestCase):
    def test_defense_and_kicker_scoring_keys_are_not_player_projection_markets(self):
        scoring = ScoringConfig.from_settings(
            {
                "int": 2,
                "sack": 1,
                "def_td": 6,
                "fgm_40_49": 4,
                "pass_int": -1,
            }
        )
        self.assertIsNone(scoring.for_market("player_def_interceptions"))
        self.assertIsNone(scoring.for_market("player_sacks"))
        self.assertIsNone(scoring.for_market("player_def_td"))
        self.assertIsNone(scoring.for_market("player_fg_made_40_49"))
        self.assertIsNotNone(scoring.for_market("player_pass_interceptions"))

    def test_defense_only_odds_cannot_create_player_projection(self):
        odds = {
            "book": {
                "player_def_interceptions": {
                    "over": {"odds": 1.9, "point": 0.5},
                    "under": {"odds": 1.9, "point": 0.5},
                }
            }
        }
        projection = project_player(odds, {"int": 2})
        self.assertFalse(projection.has_projection)
        self.assertEqual(projection.samples, [])


class NegativeFantasyPointInvariantTest(unittest.TestCase):
    def setUp(self):
        self.odds = {
            "book": {
                "player_pass_interceptions": {
                    "over": {"odds": 1.80, "point": 0.5},
                    "under": {"odds": 2.05, "point": 0.5},
                },
                "player_pass_interceptions_alternate": {
                    "alts": {
                        "over": [{"odds": 3.40, "point": 1.5}],
                        "under": [{"odds": 1.30, "point": 1.5}],
                    }
                },
            }
        }
        self.projection = project_player(self.odds, {"pass_int": -1})

    def test_negative_scoring_still_has_ordered_floor_mid_ceiling(self):
        projection = self.projection
        self.assertTrue(projection.has_projection)
        self.assertEqual(len(projection.samples), 4000)
        self.assertTrue(all(math.isfinite(value) for value in projection.samples))
        self.assertLessEqual(projection.floor, projection.mid)
        self.assertLessEqual(projection.mid, projection.ceiling)

    def test_reported_quantiles_match_independent_sample_calculation(self):
        projection = self.projection
        self.assertAlmostEqual(
            projection.floor, independent_percentile(projection.samples, 0.10), places=12
        )
        self.assertAlmostEqual(
            projection.mid, independent_percentile(projection.samples, 0.50), places=12
        )
        self.assertAlmostEqual(
            projection.ceiling, independent_percentile(projection.samples, 0.90), places=12
        )

    def test_fantasy_survival_is_monotonic_for_negative_samples(self):
        curve = survival_curve(self.projection.samples)
        probabilities = [point["survival"] for point in curve]
        self.assertTrue(
            all(a >= b for a, b in zip(probabilities, probabilities[1:], strict=False))
        )

    def test_seed_is_deterministic(self):
        repeated = project_player(self.odds, {"pass_int": -1})
        self.assertEqual(self.projection.samples, repeated.samples)
        self.assertEqual(self.projection.floor, repeated.floor)
        self.assertEqual(self.projection.mid, repeated.mid)
        self.assertEqual(self.projection.ceiling, repeated.ceiling)


if __name__ == "__main__":
    unittest.main()
