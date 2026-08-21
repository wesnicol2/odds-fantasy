import unittest

from refactored import range_model
from refactored.lineup import build_lineup
from refactored.prob_models import poisson_quantile

# A fairly standard Sleeper-style scoring dict, points-allowed portion only.
DEF_SCORING = {
    "pts_allow_0": 10,
    "pts_allow_1_6": 7,
    "pts_allow_7_13": 4,
    "pts_allow_14_20": 1,
    "pts_allow_21_27": 0,
    "pts_allow_28_34": -1,
    "pts_allow_35p": -4,
}


class PoissonQuantileTest(unittest.TestCase):
    def test_monotonic_in_q(self):
        lam = 3.5
        q15 = poisson_quantile(lam, 0.15)
        q50 = poisson_quantile(lam, 0.50)
        q85 = poisson_quantile(lam, 0.85)
        self.assertLessEqual(q15, q50)
        self.assertLessEqual(q50, q85)

    def test_zero_lambda(self):
        self.assertEqual(poisson_quantile(0.0, 0.5), 0.0)

    def test_median_near_mean_for_moderate_lambda(self):
        # Poisson(5) median is 5 (or very close to it)
        self.assertAlmostEqual(poisson_quantile(5.0, 0.5), 5.0, delta=1.0)


class DefenseFantasyRangeTest(unittest.TestCase):
    def test_low_opponent_total_beats_high_opponent_total(self):
        """A defense facing an opponent implied for 10 points should project
        for meaningfully more fantasy points than one facing an opponent
        implied for 30, all else equal."""
        floor_lo, mid_lo, ceil_lo = range_model.compute_defense_fantasy_range(10.0, DEF_SCORING)
        floor_hi, mid_hi, ceil_hi = range_model.compute_defense_fantasy_range(30.0, DEF_SCORING)
        self.assertGreater(mid_lo, mid_hi)

    def test_ceiling_never_below_floor(self):
        for implied_total in (3.0, 17.5, 24.0, 31.0, 45.0):
            floor, mid, ceiling = range_model.compute_defense_fantasy_range(
                implied_total, DEF_SCORING
            )
            self.assertGreaterEqual(ceiling, floor)

    def test_empty_scoring_rules_is_zero_not_error(self):
        floor, mid, ceiling = range_model.compute_defense_fantasy_range(20.0, {})
        self.assertEqual((floor, mid, ceiling), (0.0, 0.0, 0.0))


class MarketQuantilesFallbackShapeTest(unittest.TestCase):
    def test_yardage_market_uses_lognormal_shape_not_symmetric_normal(self):
        # A player expected around 60 yards with a single 49.5-yard line at
        # decent over odds should show right skew: the gap from mid->ceiling
        # should exceed the gap from floor->mid (lognormal), rather than the
        # symmetric spread a bare Normal fallback would produce.
        q15, q50, q85 = range_model._market_quantiles(
            "player_rush_yds",
            mean=60.0,
            threshold=49.5,
            p_over=0.62,
            p_under=0.42,
        )
        self.assertGreater(q15, 0.0)
        self.assertLess(q15, q50)
        self.assertLess(q50, q85)
        upper_gap = q85 - q50
        lower_gap = q50 - q15
        self.assertGreater(upper_gap, lower_gap)

    def test_count_market_uses_poisson_shape(self):
        q15, q50, q85 = range_model._market_quantiles(
            "player_receptions",
            mean=4.0,
            threshold=3.5,
            p_over=0.55,
            p_under=0.5,
        )
        self.assertLessEqual(q15, q50)
        self.assertLessEqual(q50, q85)
        self.assertGreaterEqual(q15, 0.0)

    def test_anytime_td_is_bernoulli(self):
        q15, q50, q85 = range_model._market_quantiles(
            "player_anytime_td",
            mean=0.4,
            threshold=0,
            p_over=0.4,
            p_under=0.6,
        )
        self.assertIn(q15, (0.0, 1.0))
        self.assertIn(q85, (0.0, 1.0))


class BuildLineupDefenseSlotTest(unittest.TestCase):
    def test_owned_defense_fills_def_slot(self):
        players = [
            {"name": "QB A", "pos": "QB", "floor": 10.0, "mid": 15.0, "ceiling": 20.0},
        ]
        defenses = [
            {"defense": "Buffalo Bills", "floor": 4.0, "mid": 7.0, "ceiling": 12.0},
        ]
        lineup = build_lineup(players, target="mid", defenses=defenses)
        slots = {row["slot"]: row for row in lineup["lineup"]}
        self.assertIn("DEF", slots)
        self.assertEqual(slots["DEF"]["name"], "Buffalo Bills")
        self.assertEqual(slots["DEF"]["points"], 7.0)

    def test_no_defenses_is_still_valid(self):
        players = [{"name": "QB A", "pos": "QB", "floor": 10.0, "mid": 15.0, "ceiling": 20.0}]
        lineup = build_lineup(players, target="mid", defenses=None)
        slots = {row["slot"] for row in lineup["lineup"]}
        self.assertNotIn("DEF", slots)


if __name__ == "__main__":
    unittest.main()
