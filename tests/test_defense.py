import datetime as dt
import unittest
from unittest.mock import patch

from oddsfantasy import services
from oddsfantasy.defense import (
    defense_fantasy_range,
    defense_range_breakdown,
    implied_team_total,
    opponent_implied_breakdown,
    opponent_implied_total,
)

DEF_SCORING = {
    "pts_allow_0": 10,
    "pts_allow_1_6": 7,
    "pts_allow_7_13": 4,
    "pts_allow_14_20": 1,
    "pts_allow_21_27": 0,
    "pts_allow_28_34": -1,
    "pts_allow_35p": -4,
}


BOOK_LINES = {
    "bookmakers": [
        {
            "key": "draftkings",
            "markets": [
                {"key": "totals", "outcomes": [{"name": "Over", "point": 47.5}]},
                {"key": "spreads", "outcomes": [{"name": "Miami Dolphins", "point": 3.5}]},
            ],
        },
        {
            "key": "fanduel",
            "markets": [
                {"key": "totals", "outcomes": [{"name": "Over", "point": 48.5}]},
                {"key": "spreads", "outcomes": [{"name": "Miami Dolphins", "point": 2.5}]},
            ],
        },
    ]
}


class ImpliedBreakdownTest(unittest.TestCase):
    """The evidence behind the number must be the evidence the number used."""

    def setUp(self):
        self.breakdown = opponent_implied_breakdown(BOOK_LINES, "Miami Dolphins")

    def test_every_book_carries_the_inputs_and_its_own_result(self):
        self.assertEqual(self.breakdown["book_count"], 2)
        by_book = {row["book"]: row for row in self.breakdown["books"]}
        self.assertEqual(
            by_book["draftkings"],
            {
                "book": "draftkings",
                "game_total": 47.5,
                "opponent_spread": 3.5,
                "implied_total": 22.0,
            },
        )
        for row in self.breakdown["books"]:
            self.assertAlmostEqual(
                row["implied_total"],
                implied_team_total(row["game_total"], row["opponent_spread"]),
                places=2,
            )

    def test_median_matches_the_ranked_number(self):
        implied, books = opponent_implied_total(BOOK_LINES, "Miami Dolphins")
        self.assertEqual(self.breakdown["median"], implied)
        self.assertEqual(self.breakdown["book_count"], books)

    def test_no_usable_lines_is_none_with_no_rows(self):
        empty = opponent_implied_breakdown({"bookmakers": []}, "Miami Dolphins")
        self.assertIsNone(empty["median"])
        self.assertEqual(empty["books"], [])


class RangeBreakdownTest(unittest.TestCase):
    def setUp(self):
        self.breakdown = defense_range_breakdown(22.5, DEF_SCORING)

    def test_breakdown_reproduces_the_ranked_range(self):
        floor, mid, ceiling = defense_fantasy_range(22.5, DEF_SCORING)
        self.assertAlmostEqual(self.breakdown["floor"]["points"], floor, places=2)
        self.assertAlmostEqual(self.breakdown["mid"]["points"], mid, places=2)
        self.assertAlmostEqual(self.breakdown["ceiling"]["points"], ceiling, places=2)

    def test_floor_reads_the_high_opponent_percentile(self):
        """A defense scores least when its opponent scores most."""
        self.assertEqual(self.breakdown["floor"]["percentile"], 0.90)
        self.assertEqual(self.breakdown["ceiling"]["percentile"], 0.10)
        self.assertGreater(
            self.breakdown["floor"]["opponent_points"],
            self.breakdown["ceiling"]["opponent_points"],
        )

    def test_shown_contributions_add_up_to_the_shown_mid(self):
        total = sum(row["contribution"] for row in self.breakdown["mid"]["brackets"])
        self.assertAlmostEqual(total, self.breakdown["mid"]["points"], places=2)

    def test_bracket_probabilities_cover_every_outcome_once(self):
        total = sum(row["probability"] for row in self.breakdown["mid"]["brackets"])
        self.assertAlmostEqual(total, 1.0, places=3)


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
