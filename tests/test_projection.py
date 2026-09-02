"""Player-level projection: scoring sampled stat distributions into one FP curve."""

import unittest

from oddsfantasy.projection import DEFAULT_DRAWS, percentile, project_player, survival_curve
from oddsfantasy.scoring import ScoringConfig
from tests.test_market_math import DOC_RUSH_YDS_BOOK, alt_ladder, two_way
from tests.test_scoring import LEAGUE

DOC_RUSHER = {"bookA": DOC_RUSH_YDS_BOOK}


class PercentileTest(unittest.TestCase):
    def test_interpolates_between_neighbours(self):
        self.assertEqual(percentile([0.0, 10.0], 0.5), 5.0)

    def test_edges_and_degenerate_inputs(self):
        self.assertEqual(percentile([], 0.5), 0.0)
        self.assertEqual(percentile([3.0], 0.9), 3.0)
        self.assertEqual(percentile([1.0, 2.0, 3.0], 0.0), 1.0)
        self.assertEqual(percentile([1.0, 2.0, 3.0], 1.0), 3.0)

    def test_survival_curve_is_compact_and_monotone(self):
        curve = survival_curve([0.0, 1.0, 2.0, 3.0], points=4)
        self.assertEqual(len(curve), 4)
        self.assertEqual(curve[0]["survival"], 1.0)
        self.assertTrue(
            all(
                a["survival"] >= b["survival"]
                for a, b in zip(curve, curve[1:], strict=True)
            )
        )


class ContinuousStatProjectionTest(unittest.TestCase):
    def setUp(self):
        self.projection = project_player(DOC_RUSHER, LEAGUE)

    def test_expected_points_match_the_doc(self):
        self.assertAlmostEqual(self.projection.mean, 9.2, delta=0.6)

    def test_floor_mid_ceiling_are_ordered_and_plausible(self):
        self.assertLess(self.projection.floor, self.projection.mid)
        self.assertLess(self.projection.mid, self.projection.ceiling)
        self.assertAlmostEqual(self.projection.mid, 7.6, delta=1.5)
        self.assertAlmostEqual(self.projection.ceiling, 18.1, delta=2.5)

    def test_the_bonus_widens_the_gap_to_the_ceiling(self):
        without_bonus = {k: v for k, v in LEAGUE.items() if not k.startswith("bonus_rush")}
        plain = project_player(DOC_RUSHER, without_bonus)
        self.assertGreater(
            self.projection.ceiling - self.projection.mid,
            plain.ceiling - plain.mid,
        )
        self.assertGreater(self.projection.mean, plain.mean)

    def test_bonus_expectation_is_priced_in_not_scaled(self):
        stat = self.projection.stats["player_rush_yds"]
        self.assertGreater(stat.expected_points, 0.1 * stat.distribution.mean())

    def test_stat_range_is_the_yardage_curve(self):
        floor, mid, ceiling = self.projection.stats["player_rush_yds"].stat_range
        self.assertLess(floor, mid)
        self.assertLess(mid, ceiling)
        self.assertAlmostEqual(mid, 75.9, delta=2.0)
        self.assertAlmostEqual(ceiling, 131.0, delta=6.0)


class CountStatProjectionTest(unittest.TestCase):
    def setUp(self):
        self.scorer = {
            "bookA": {
                "player_anytime_td": {
                    "over": {"odds": 1 / 0.55, "point": 0},
                    "under": {"odds": 1 / 0.45, "point": 0},
                },
                "player_anytime_td_alternate": {
                    "alts": {
                        "over": [{"odds": 1 / 0.18, "point": 2}],
                        "under": [{"odds": 1 / 0.82, "point": 2}],
                    }
                },
            }
        }

    def test_expected_td_points_match_the_doc(self):
        projection = project_player(self.scorer, LEAGUE)
        self.assertAlmostEqual(projection.mean, 4.38, places=6)

    def test_the_curve_has_exactly_the_posted_outcomes(self):
        projection = project_player(self.scorer, LEAGUE)
        self.assertEqual(sorted(set(projection.samples)), [0.0, 6.0, 12.0])

    def test_anytime_only_does_not_invent_a_two_td_game(self):
        anytime_only = {
            "bookA": {
                "player_anytime_td": {
                    "over": {"odds": 1 / 0.55, "point": 0},
                    "under": {"odds": 1 / 0.45, "point": 0},
                }
            }
        }
        projection = project_player(anytime_only, LEAGUE)
        self.assertEqual(sorted(set(projection.samples)), [0.0, 6.0])
        self.assertAlmostEqual(projection.mean, 6 * 0.55, places=6)
        self.assertEqual(projection.ceiling, 6.0)

    def test_the_two_plus_line_is_where_the_ceiling_mass_lives(self):
        with_two_plus = project_player(self.scorer, LEAGUE)
        anytime_only = project_player(
            {"bookA": {"player_anytime_td": self.scorer["bookA"]["player_anytime_td"]}},
            LEAGUE,
        )
        self.assertGreater(with_two_plus.ceiling, anytime_only.ceiling)


class NegativeStatProjectionTest(unittest.TestCase):
    def test_interceptions_shift_the_curve_left(self):
        passer = {
            "bookA": {
                "player_pass_yds": two_way(249.5, -115, -105),
                "player_pass_interceptions": two_way(0.5, -140, 110),
            }
        }
        clean = {"bookA": {"player_pass_yds": two_way(249.5, -115, -105)}}
        self.assertLess(
            project_player(passer, LEAGUE).mean,
            project_player(clean, LEAGUE).mean,
        )

    def test_more_interception_lines_deepen_the_floor(self):
        one_line = {"bookA": {"player_pass_interceptions": two_way(0.5, -140, 110)}}
        two_lines = {
            "bookA": {
                "player_pass_interceptions": two_way(0.5, -140, 110),
                "player_pass_interceptions_alternate": alt_ladder([(2, 260, -340)]),
            }
        }
        self.assertLess(
            project_player(two_lines, LEAGUE).floor,
            project_player(one_line, LEAGUE).floor,
        )
        self.assertEqual(project_player(two_lines, LEAGUE).ceiling, 0.0)


class AggregationTest(unittest.TestCase):
    def setUp(self):
        self.player = {
            "bookA": dict(
                DOC_RUSH_YDS_BOOK,
                player_anytime_td={
                    "over": {"odds": 1 / 0.55, "point": 0},
                    "under": {"odds": 1 / 0.45, "point": 0},
                },
                player_receptions=two_way(2.5, -130, 105),
            )
        }

    def test_expected_points_are_the_sum_of_the_stats(self):
        projection = project_player(self.player, LEAGUE)
        self.assertAlmostEqual(
            projection.mean,
            sum(stat.expected_points for stat in projection.stats.values()),
            places=9,
        )

    def test_every_modeled_stat_shows_up(self):
        projection = project_player(self.player, LEAGUE)
        self.assertEqual(
            set(projection.stats),
            {"player_rush_yds", "player_anytime_td", "player_receptions"},
        )

    def test_alternate_ladders_fold_into_their_base_market(self):
        projection = project_player(DOC_RUSHER, LEAGUE)
        self.assertEqual(set(projection.stats), {"player_rush_yds"})

    def test_adding_a_stat_raises_the_curve(self):
        rush_only = project_player(DOC_RUSHER, LEAGUE)
        with_tds = project_player(self.player, LEAGUE)
        self.assertGreater(with_tds.mean, rush_only.mean)
        self.assertGreater(with_tds.ceiling, rush_only.ceiling)

    def test_ppr_turns_receptions_into_points_with_no_math_change(self):
        non_ppr = project_player(self.player, LEAGUE)
        ppr = project_player(self.player, dict(LEAGUE, rec=1.0))
        receptions = ppr.stats["player_receptions"]
        self.assertEqual(non_ppr.stats["player_receptions"].expected_points, 0.0)
        self.assertGreater(receptions.expected_points, 0.0)
        self.assertAlmostEqual(ppr.mean - non_ppr.mean, receptions.expected_points, places=9)
        self.assertGreater(ppr.floor, non_ppr.floor)

    def test_floor_mid_ceiling_are_percentiles_of_one_curve(self):
        projection = project_player(self.player, LEAGUE)
        self.assertEqual(len(projection.samples), DEFAULT_DRAWS)
        self.assertAlmostEqual(
            projection.floor,
            percentile(projection.samples, 0.10),
            places=9,
        )
        self.assertAlmostEqual(
            projection.mid,
            percentile(projection.samples, 0.50),
            places=9,
        )
        self.assertAlmostEqual(
            projection.ceiling,
            percentile(projection.samples, 0.90),
            places=9,
        )

    def test_sampling_is_deterministic(self):
        first = project_player(self.player, LEAGUE)
        second = project_player(self.player, LEAGUE)
        self.assertEqual(
            (first.floor, first.mid, first.ceiling),
            (second.floor, second.mid, second.ceiling),
        )

    def test_sampling_error_is_small(self):
        default = project_player(self.player, LEAGUE)
        alternate = project_player(self.player, LEAGUE, seed=987654321)
        self.assertAlmostEqual(default.ceiling, alternate.ceiling, delta=0.5)
        self.assertAlmostEqual(default.mid, alternate.mid, delta=0.5)

    def test_accepts_a_prebuilt_scoring_config(self):
        config = ScoringConfig.from_settings(LEAGUE)
        self.assertEqual(
            project_player(self.player, config).mean,
            project_player(self.player, LEAGUE).mean,
        )

    def test_no_odds_is_zero_not_an_error(self):
        blank = project_player({}, LEAGUE)
        self.assertFalse(blank.has_projection)
        self.assertEqual(
            (blank.floor, blank.mid, blank.ceiling, blank.mean),
            (0.0, 0.0, 0.0, 0.0),
        )
        self.assertEqual(blank.per_market_ranges, {})

    def test_unscored_junk_market_is_ignored(self):
        noisy = {
            "bookA": dict(
                DOC_RUSH_YDS_BOOK,
                player_field_goals=two_way(1.5, -110, -110),
            )
        }
        self.assertEqual(set(project_player(noisy, LEAGUE).stats), {"player_rush_yds"})


if __name__ == "__main__":
    unittest.main()