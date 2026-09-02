import datetime as dt
import unittest
from unittest.mock import patch

from oddsfantasy import services
from oddsfantasy.defense import defense_fantasy_range, implied_team_total, opponent_implied_total

DEF_SCORING = {
    "pts_allow_0": 10,
    "pts_allow_1_6": 7,
    "pts_allow_7_13": 4,
    "pts_allow_14_20": 1,
    "pts_allow_21_27": 0,
    "pts_allow_28_34": -1,
    "pts_allow_35p": -4,
}


class DefenseMathTest(unittest.TestCase):
    def test_implied_team_total(self):
        self.assertEqual(implied_team_total(45.0, 10.0), 17.5)

    def test_extracts_median_across_books(self):
        payload = {
            "bookmakers": [
                {
                    "markets": [
                        {"key": "totals", "outcomes": [{"name": "Over", "point": 45}]},
                        {
                            "key": "spreads",
                            "outcomes": [
                                {"name": "Miami Dolphins", "point": 10},
                                {"name": "Buffalo Bills", "point": -10},
                            ],
                        },
                    ]
                },
                {
                    "markets": [
                        {"key": "totals", "outcomes": [{"name": "Over", "point": 44}]},
                        {
                            "key": "spreads",
                            "outcomes": [
                                {"name": "Miami Dolphins", "point": 9},
                                {"name": "Buffalo Bills", "point": -9},
                            ],
                        },
                    ]
                },
            ]
        }
        implied, books = opponent_implied_total(payload, "Miami Dolphins")
        self.assertEqual(books, 2)
        self.assertAlmostEqual(implied, 17.5)

    def test_lower_opponent_total_is_better_for_defense(self):
        _, low_mid, _ = defense_fantasy_range(14, DEF_SCORING)
        _, high_mid, _ = defense_fantasy_range(30, DEF_SCORING)
        self.assertGreater(low_mid, high_mid)


class DefenseServiceTest(unittest.TestCase):
    def setUp(self):
        if hasattr(services.list_defenses, "_cache"):
            services.list_defenses._cache = {}

    def test_lists_all_defenses_sorted_and_marks_ownership(self):
        game_time = dt.datetime(2026, 9, 6, 17, 0)
        events = [
            {
                "id": "game1",
                "home_team": "Buffalo Bills",
                "away_team": "Miami Dolphins",
                "commence_time": "2026-09-06T17:00:00Z",
            }
        ]
        lines = {
            "game1": {
                "bookmakers": [
                    {
                        "markets": [
                            {"key": "totals", "outcomes": [{"name": "Over", "point": 45}]},
                            {
                                "key": "spreads",
                                "outcomes": [
                                    {"name": "Miami Dolphins", "point": 10},
                                    {"name": "Buffalo Bills", "point": -10},
                                ],
                            },
                        ]
                    }
                ]
            }
        }
        windows = (
            (game_time - dt.timedelta(hours=1), game_time + dt.timedelta(hours=1)),
            (game_time + dt.timedelta(days=7), game_time + dt.timedelta(days=8)),
        )
        ownership = {
            "Buffalo Bills": {"id": "me", "name": "Dat Tight End"},
            "Miami Dolphins": {"id": "other", "name": "Other Team"},
        }

        with (
            patch("oddsfantasy.services.odds_client.get_nfl_events", return_value=events),
            patch("oddsfantasy.services.resolve_week_windows", return_value=windows),
            patch("oddsfantasy.services._fetch_game_lines", return_value=lines),
            patch(
                "oddsfantasy.services._defense_ownership_map",
                return_value=(ownership, "me"),
            ),
            patch(
                "oddsfantasy.services._resolve_identity",
                return_value={"scoring_rules": DEF_SCORING},
            ),
        ):
            payload = services.list_defenses(
                username="wesnicol",
                season="2026",
                week="this",
                league_id="L1",
                roster_id=7,
                fresh=True,
            )

        self.assertEqual(len(payload["defenses"]), 32)
        self.assertEqual(payload["defenses"][0]["defense"], "Buffalo Bills")
        buffalo = next(row for row in payload["defenses"] if row["defense"] == "Buffalo Bills")
        miami = next(row for row in payload["defenses"] if row["defense"] == "Miami Dolphins")
        self.assertEqual(buffalo["implied_total"], 17.5)
        self.assertTrue(buffalo["owned_by_current"])
        self.assertTrue(miami["taken"])
        self.assertFalse(miami["owned_by_current"])
        self.assertEqual(payload["defenses"][-1]["opponent"], "BYE")


if __name__ == "__main__":
    unittest.main()
