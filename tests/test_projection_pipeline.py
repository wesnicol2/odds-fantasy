"""End-to-end roster + sportsbook odds -> canonical player report."""

import datetime as dt
import unittest
from unittest.mock import patch

from oddsfantasy import services


def _next_sunday() -> dt.datetime:
    now = dt.datetime.utcnow().replace(hour=17, minute=0, second=0, microsecond=0)
    return now + dt.timedelta(days=(6 - now.weekday()) % 7 or 7)


FUTURE_GAME = _next_sunday()
EVENT = {
    "id": "evt1",
    "home_team": "Buffalo Bills",
    "away_team": "Miami Dolphins",
    "commence_time": FUTURE_GAME.strftime("%Y-%m-%dT%H:%M:%SZ"),
}
ROSTER = {
    "scoring_rules": {
        "rush_yd": 0.1,
        "rush_td": 5,
        "rec": 0.5,
        "rec_yd": 0.1,
        "rec_td": 8,
    },
    "players": {
        "1": {
            "name": {"full": "James Cook"},
            "primary_position": "RB",
            "editorial_team_full_name": "Buffalo Bills",
        },
        "2": {
            "name": {"full": "Bye Week WR"},
            "primary_position": "WR",
            "editorial_team_full_name": "Seattle Seahawks",
        },
        "3": {
            "name": {"full": "Bills D/ST"},
            "primary_position": "DEF",
            "editorial_team_full_name": "Buffalo Bills",
        },
        "4": {
            "name": {"full": "Beta Receiver"},
            "primary_position": "WR",
            "editorial_team_full_name": "Buffalo Bills",
        },
        "5": {
            "name": {"full": "Partial Receiver"},
            "primary_position": "WR",
            "editorial_team_full_name": "Buffalo Bills",
        },
    },
}


def outcome(name, price, point=None, description="James Cook"):
    row = {"name": name, "price": price, "description": description}
    if point is not None:
        row["point"] = point
    return row


EVENT_ODDS = [
    {
        "id": "evt1",
        "bookmakers": [
            {
                "key": "draftkings",
                "markets": [
                    {
                        "key": "player_rush_yds",
                        "outcomes": [
                            outcome("Over", 1.87, 74.5),
                            outcome("Under", 1.95, 74.5),
                        ],
                    },
                    {
                        "key": "player_rush_yds_alternate",
                        "outcomes": [
                            outcome("Over", 1.22, 40),
                            outcome("Under", 4.3, 40),
                            outcome("Over", 2.45, 100),
                            outcome("Under", 1.57, 100),
                        ],
                    },
                    {
                        "key": "player_receptions",
                        "outcomes": [
                            outcome("Over", 1.83, 3.5),
                            outcome("Under", 1.98, 3.5),
                            outcome("Over", 1.9, 4.5, description="Beta Receiver"),
                            outcome("Under", 1.9, 4.5, description="Beta Receiver"),
                        ],
                    },
                    {
                        "key": "player_reception_yds",
                        "outcomes": [
                            outcome("Over", 1.9, 28.5),
                            outcome("Under", 1.9, 28.5),
                            outcome("Over", 1.9, 55.5, description="Beta Receiver"),
                            outcome("Under", 1.9, 55.5, description="Beta Receiver"),
                        ],
                    },
                    {
                        "key": "player_anytime_td",
                        "outcomes": [
                            outcome("Yes", 2.2),
                            outcome("No", 1.7),
                            outcome("Yes", 2.0, description="Beta Receiver"),
                            outcome("No", 2.0, description="Beta Receiver"),
                            outcome("Yes", 2.5, description="Partial Receiver"),
                            outcome("No", 1.6, description="Partial Receiver"),
                        ],
                    },
                ],
            }
        ],
    }
]


class ProjectionPipelineTest(unittest.TestCase):
    def _run(self):
        if hasattr(services._load_week_context, "_cache"):
            services._load_week_context._cache = {}
        with (
            patch("oddsfantasy.services._resolve_identity", return_value=ROSTER),
            patch("oddsfantasy.services.odds_client.get_nfl_events", return_value=[EVENT]),
            patch("oddsfantasy.services._fetch_odds", return_value={"evt1": EVENT_ODDS}),
        ):
            return services.compute_projections(
                username="wesnicol", season="2026", week="this", fresh=True
            )

    def test_report_contains_skill_players_only(self):
        players = self._run()["players"]
        self.assertEqual(
            {player["name"] for player in players},
            {"James Cook", "Bye Week WR", "Beta Receiver", "Partial Receiver"},
        )

    def test_projected_player_has_ordered_numbers_and_curve(self):
        player = next(row for row in self._run()["players"] if row["name"] == "James Cook")
        self.assertTrue(player["has_projection"])
        self.assertEqual(player["coverage_status"], "complete")
        self.assertEqual(player["missing_markets"], [])
        self.assertLess(player["floor"], player["mid"])
        self.assertLess(player["mid"], player["ceiling"])
        self.assertGreater(len(player["curve"]), 20)
        self.assertGreaterEqual(
            player["curve"][0]["survival"],
            player["curve"][-1]["survival"],
        )

    def test_receiver_anytime_td_uses_receiving_td_scoring(self):
        player = next(row for row in self._run()["players"] if row["name"] == "Beta Receiver")
        self.assertTrue(player["has_projection"])
        # The 50% anytime-TD line contributes 4 expected points at this
        # receiver's configured 8-point receiving-TD value, on top of receiving
        # yards/receptions. Using the RB/QB 5-point TD value would be lower.
        self.assertGreater(player["mean"], 9.0)
        self.assertGreater(player["ceiling"], player["mid"])
        self.assertGreaterEqual(
            player["curve"][0]["survival"],
            player["curve"][-1]["survival"],
        )

    def test_no_lines_does_not_fabricate_zero_projection(self):
        player = next(row for row in self._run()["players"] if row["name"] == "Bye Week WR")
        self.assertFalse(player["has_projection"])
        self.assertEqual(player["coverage_status"], "missing")
        self.assertIsNone(player["floor"])
        self.assertIsNone(player["mid"])
        self.assertIsNone(player["ceiling"])
        self.assertIn("player_reception_yds", player["missing_markets"])
        self.assertIn("player_anytime_td", player["missing_markets"])

    def test_partial_core_markets_are_unknown_and_excluded(self):
        player = next(
            row for row in self._run()["players"] if row["name"] == "Partial Receiver"
        )
        self.assertFalse(player["has_projection"])
        self.assertEqual(player["coverage_status"], "partial")
        self.assertGreater(player["markets_used"], 0)
        self.assertEqual(player["missing_markets"], ["player_reception_yds", "player_receptions"])
        self.assertIsNone(player["floor"])
        self.assertIsNone(player["mid"])
        self.assertIsNone(player["ceiling"])
        self.assertEqual(player["curve"], [])


if __name__ == "__main__":
    unittest.main()
