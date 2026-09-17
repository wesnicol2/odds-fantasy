"""Regression tests for configured stat -> Odds API market planning."""

import unittest

from oddsfantasy.planner import _markets_for_positions, _normalize_market


class PlannerMarketMappingTest(unittest.TestCase):
    def test_qb_alternate_passing_markets_are_requested_as_themselves(self):
        self.assertEqual(
            _normalize_market("player_pass_yds_alternate"),
            "player_pass_yds_alternate",
        )
        self.assertEqual(
            _normalize_market("player_pass_tds_alternate"),
            "player_pass_tds_alternate",
        )

    def test_rushing_touchdown_config_stays_pooled_into_anytime_td(self):
        self.assertEqual(_normalize_market("player_rush_tds"), "player_anytime_td")
        self.assertEqual(
            _normalize_market("player_rush_tds_alternate"),
            "player_anytime_td",
        )

    def test_qb_plan_contains_main_and_alternate_passing_markets(self):
        markets = set(_markets_for_positions(["QB"]))
        self.assertIn("player_pass_yds", markets)
        self.assertIn("player_pass_yds_alternate", markets)
        self.assertIn("player_pass_tds", markets)
        self.assertIn("player_pass_tds_alternate", markets)
        self.assertIn("player_pass_interceptions", markets)


if __name__ == "__main__":
    unittest.main()
