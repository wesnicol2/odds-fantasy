"""Core projection coverage must include every normally scored path."""

import unittest

from oddsfantasy.projection import required_projection_markets
from oddsfantasy.scoring import ScoringConfig


class ProjectionCompletenessTest(unittest.TestCase):
    def test_qb_requires_anytime_td_for_rushing_touchdowns(self):
        scoring = ScoringConfig.from_settings(
            {
                "pass_yd": 0.04,
                "pass_td": 4,
                "pass_int": -1,
                "rush_yd": 0.1,
                "rush_td": 6,
            }
        )

        required = required_projection_markets(scoring, "QB")

        self.assertIn("player_pass_yds", required)
        self.assertIn("player_pass_tds", required)
        self.assertIn("player_pass_interceptions", required)
        self.assertIn("player_rush_yds", required)
        self.assertIn("player_anytime_td", required)


if __name__ == "__main__":
    unittest.main()
