"""Scoring-as-configuration (docs/fantasy-projection-methodology.md §2.4).

The point of these tests is that nothing about a ruleset is baked into the
engine: values, per-reception value, bonus thresholds *and* bonus amounts all
come from the league's settings, so switching ruleset is a config change and
never a math change.
"""

import unittest

from oddsfantasy.scoring import ScoringConfig

# §2.4 -- this project's league, used as one instance of a ruleset.
LEAGUE = {
    "pass_yd": 0.04,
    "pass_td": 4,
    "pass_int": -1,
    "bonus_pass_yd_300": 5,
    "bonus_pass_yd_400": 5,
    "rush_yd": 0.1,
    "rush_td": 6,
    "bonus_rush_yd_100": 5,
    "bonus_rush_yd_200": 5,
    "rec": 0,
    "rec_yd": 0.1,
    "bonus_rec_yd_100": 5,
    "bonus_rec_yd_200": 5,
}


class ScoringValuesTest(unittest.TestCase):
    def test_values_come_from_config(self):
        scoring = ScoringConfig.from_settings(LEAGUE)
        self.assertEqual(scoring.for_market("player_rush_yds").per_unit, 0.1)
        self.assertEqual(scoring.for_market("player_pass_yds").per_unit, 0.04)
        self.assertEqual(scoring.for_market("player_pass_tds").per_unit, 4)
        self.assertEqual(scoring.for_market("player_anytime_td").per_unit, 6)

    def test_a_different_ruleset_is_a_config_change_not_a_math_change(self):
        doubled = dict(LEAGUE, pass_yd=0.08, rush_td=4)
        scoring = ScoringConfig.from_settings(doubled)
        self.assertEqual(scoring.score({"player_pass_yds": 250.0}), 20.0)
        self.assertEqual(scoring.score({"player_anytime_td": 2.0}), 8.0)

    def test_missing_value_scores_zero_rather_than_raising(self):
        scoring = ScoringConfig.from_settings({})
        self.assertEqual(scoring.score({"player_rush_yds": 120.0}), 0.0)

    def test_unmapped_market_contributes_nothing(self):
        scoring = ScoringConfig.from_settings(LEAGUE)
        self.assertIsNone(scoring.for_market("player_field_goals"))
        self.assertEqual(scoring.score({"player_field_goals": 3.0}), 0.0)

    def test_garbage_config_value_is_ignored(self):
        scoring = ScoringConfig.from_settings(dict(LEAGUE, rush_yd="lots"))
        self.assertEqual(scoring.for_market("player_rush_yds").per_unit, 0.0)


class NegativeStatTest(unittest.TestCase):
    def test_interceptions_subtract(self):
        # §4.5: a negative stat is just a negative coefficient.
        scoring = ScoringConfig.from_settings(LEAGUE)
        self.assertEqual(scoring.score({"player_pass_interceptions": 2.0}), -2.0)

    def test_interceptions_subtract_even_if_config_stores_the_magnitude(self):
        scoring = ScoringConfig.from_settings(dict(LEAGUE, pass_int=1))
        self.assertEqual(scoring.score({"player_pass_interceptions": 2.0}), -2.0)


class PPRTest(unittest.TestCase):
    def test_receptions_are_modeled_and_score_zero_in_a_non_ppr_league(self):
        # §2.4: always modeled; here the configured value is 0, so it just
        # contributes nothing.
        scoring = ScoringConfig.from_settings(LEAGUE)
        self.assertIsNotNone(scoring.for_market("player_receptions"))
        self.assertEqual(scoring.score({"player_receptions": 7.0}), 0.0)

    def test_turning_on_ppr_is_a_pure_config_change(self):
        for value, expected in ((0.5, 3.5), (1.0, 7.0)):
            scoring = ScoringConfig.from_settings(dict(LEAGUE, rec=value))
            self.assertEqual(scoring.score({"player_receptions": 7.0}), expected)


class BonusThresholdTest(unittest.TestCase):
    def test_thresholds_are_read_from_the_config_key(self):
        scoring = ScoringConfig.from_settings(LEAGUE)
        self.assertEqual(
            scoring.for_market("player_rush_yds").bonuses, ((100.0, 5.0), (200.0, 5.0))
        )
        self.assertEqual(
            scoring.for_market("player_pass_yds").bonuses, ((300.0, 5.0), (400.0, 5.0))
        )
        self.assertEqual(
            scoring.for_market("player_reception_yds").bonuses, ((100.0, 5.0), (200.0, 5.0))
        )

    def test_an_unusual_threshold_needs_no_code_change(self):
        scoring = ScoringConfig.from_settings({"rush_yd": 0.1, "bonus_rush_yd_150": 3})
        self.assertEqual(scoring.for_market("player_rush_yds").bonuses, ((150.0, 3.0),))
        self.assertEqual(scoring.score({"player_rush_yds": 149.0}), 14.9)
        self.assertAlmostEqual(scoring.score({"player_rush_yds": 150.0}), 18.0, places=9)

    def test_bonus_is_a_kink_not_a_scale(self):
        # §3.5: crossing 100 rushing yards jumps points from 10.0 to 15.0.
        scoring = ScoringConfig.from_settings(LEAGUE)
        self.assertAlmostEqual(scoring.score({"player_rush_yds": 99.9}), 9.99, places=6)
        self.assertAlmostEqual(scoring.score({"player_rush_yds": 100.0}), 15.0, places=6)

    def test_bonuses_stack(self):
        # §2.4's identity E = rate*E[stat] + sum_i amount_i * P(>= threshold_i)
        # only holds if every crossed threshold pays.
        scoring = ScoringConfig.from_settings(LEAGUE)
        self.assertAlmostEqual(scoring.score({"player_rush_yds": 210.0}), 21.0 + 10.0, places=6)

    def test_a_league_without_bonuses_gets_none(self):
        scoring = ScoringConfig.from_settings({"rush_yd": 0.1})
        self.assertEqual(scoring.for_market("player_rush_yds").bonuses, ())
        self.assertAlmostEqual(scoring.score({"player_rush_yds": 210.0}), 21.0, places=6)

    def test_bonus_on_a_stat_we_do_not_model_is_left_out(self):
        # A combined rush+rec yardage bonus isn't measured against any single
        # market, so pricing it would mean inventing a joint distribution.
        scoring = ScoringConfig.from_settings({"rush_yd": 0.1, "bonus_rush_rec_yd_100": 5})
        self.assertEqual(scoring.for_market("player_rush_yds").bonuses, ())


class StatLineScoringTest(unittest.TestCase):
    def test_scores_a_whole_stat_line(self):
        scoring = ScoringConfig.from_settings(LEAGUE)
        points = scoring.score(
            {
                "player_pass_yds": 310.0,
                "player_pass_tds": 2.0,
                "player_pass_interceptions": 1.0,
                "player_rush_yds": 40.0,
                "player_anytime_td": 1.0,
            }
        )
        # 12.4 + 5 (300 bonus) + 8 - 1 + 4 + 6
        self.assertAlmostEqual(points, 34.4, places=6)

    def test_is_scored_flags_stats_that_cannot_move_points(self):
        scoring = ScoringConfig.from_settings(LEAGUE)
        self.assertFalse(scoring.for_market("player_receptions").is_scored)
        self.assertTrue(scoring.for_market("player_rush_yds").is_scored)
        ppr = ScoringConfig.from_settings(dict(LEAGUE, rec=1.0))
        self.assertTrue(ppr.for_market("player_receptions").is_scored)


if __name__ == "__main__":
    unittest.main()
