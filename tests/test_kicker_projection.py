"""Kicker projection coverage from sportsbook kicking-points markets."""

import unittest

from oddsfantasy.projection import KICKER_MARKET_KEY, KICKER_PROXY_NOTE, project_player
from tests.test_market_math import alt_ladder, two_way
from tests.test_scoring import LEAGUE


class KickerProjectionTest(unittest.TestCase):
    def setUp(self):
        self.odds = {
            "bookA": {
                "player_kicking_points": two_way(6.5, -110, -110),
                "player_kicking_points_alternate": alt_ladder(
                    [(4.5, -220, 180), (8.5, 180, -220)]
                ),
            }
        }

    def test_kicker_points_are_a_complete_kicker_projection(self):
        projection = project_player(self.odds, LEAGUE, position="K")

        self.assertTrue(projection.has_projection)
        self.assertEqual(set(projection.stats), {KICKER_MARKET_KEY})
        self.assertEqual(projection.required_markets, (KICKER_MARKET_KEY,))
        self.assertEqual(projection.missing_markets, ())
        self.assertEqual(projection.projection_note, KICKER_PROXY_NOTE)
        self.assertGreater(projection.mean, 0.0)
        self.assertLessEqual(projection.floor, projection.mid)
        self.assertLessEqual(projection.mid, projection.ceiling)

    def test_kicker_proxy_is_position_gated(self):
        projection = project_player(self.odds, LEAGUE, position="RB")

        self.assertNotIn(KICKER_MARKET_KEY, projection.stats)
        self.assertIsNone(projection.projection_note)

    def test_missing_kicker_points_is_unknown_not_zero(self):
        projection = project_player({}, LEAGUE, position="K")

        self.assertFalse(projection.has_projection)
        self.assertEqual(projection.required_markets, (KICKER_MARKET_KEY,))
        self.assertEqual(projection.missing_markets, (KICKER_MARKET_KEY,))
        self.assertEqual(projection.projection_note, KICKER_PROXY_NOTE)
        self.assertEqual((projection.floor, projection.mid, projection.ceiling), (0.0, 0.0, 0.0))

    def test_kicker_market_units_are_preserved_one_for_one(self):
        projection = project_player(self.odds, LEAGUE, position="K")
        stat = projection.stats[KICKER_MARKET_KEY]

        self.assertEqual(stat.values, stat.point_values)
        self.assertAlmostEqual(stat.mean, stat.expected_points, places=9)


if __name__ == "__main__":
    unittest.main()
