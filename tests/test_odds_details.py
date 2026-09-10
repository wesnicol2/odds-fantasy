from unittest import TestCase, mock  # noqa: I001

from oddsfantasy.odds_details import get_player_odds_details
from oddsfantasy.planner import PlannedGame


CONTEXT = {
    "scoring_rules": {"rush_yd": 0.1},
    "info_by_alias": {
        "James Cook": {
            "full_name": "James Cook",
            "primary_position": "RB",
            "editorial_team_full_name": "Buffalo Bills",
        }
    },
    "players_odds": {
        "James Cook": {
            "draftkings": {
                "player_rush_yds": {
                    "over": {"odds": 1.9, "point": 74.5},
                    "under": {"odds": 1.9, "point": 74.5},
                },
                "player_rush_yds_alternate": {
                    "alts": {
                        "over": [{"odds": 1.4, "point": 50.0}],
                        "under": [{"odds": 3.0, "point": 50.0}],
                    }
                },
            },
            "fanduel": {
                "player_rush_yds": {
                    "over": {"odds": 1.87, "point": 75.5},
                    "under": {"odds": 1.95, "point": 75.5},
                }
            },
        }
    },
}

GAME_ODDS = {
    "bookmakers": [
        {
            "key": "draftkings",
            "markets": [
                {
                    "key": "totals",
                    "outcomes": [
                        {"name": "Over", "point": 47.5},
                        {"name": "Under", "point": 47.5},
                    ],
                },
                {
                    "key": "spreads",
                    "outcomes": [
                        {"name": "Buffalo Bills", "point": -3.5},
                        {"name": "New York Jets", "point": 3.5},
                    ],
                },
            ],
        },
        {
            "key": "fanduel",
            "markets": [
                {
                    "key": "totals",
                    "outcomes": [
                        {"name": "Over", "point": 48.5},
                        {"name": "Under", "point": 48.5},
                    ],
                },
                {
                    "key": "spreads",
                    "outcomes": [
                        {"name": "Buffalo Bills", "point": -2.5},
                        {"name": "New York Jets", "point": 2.5},
                    ],
                },
            ],
        },
    ]
}


class PlayerDetailsTest(TestCase):
    @mock.patch("oddsfantasy.odds_details._load_week_context", return_value=CONTEXT)
    def test_detail_uses_same_canonical_projection_and_source_lines(self, _mock_context):
        result = get_player_odds_details(
            username="u",
            season="2026",
            week="this",
            name="James Cook",
        )
        self.assertIsNotNone(result["projection"])
        self.assertGreater(result["projection"]["ceiling"], result["projection"]["mid"])
        self.assertGreater(len(result["projection"]["curve"]), 20)

        rush = result["markets"]["player_rush_yds"]
        self.assertEqual(len(rush["lines"]), 3)
        self.assertTrue(any(row["source"] == "alternate" for row in rush["lines"]))
        self.assertGreaterEqual(len(rush["anchors"]), 2)
        self.assertEqual(rush["graph"]["kind"], "continuous_density")
        points = rush["graph"]["points"]
        self.assertGreater(len(points), 20)
        probabilities = [point["probability"] for point in points]
        self.assertTrue(all(probability >= 0 for probability in probabilities))
        self.assertGreater(max(probabilities), 0)

    @mock.patch("oddsfantasy.odds_details._load_week_context", return_value=CONTEXT)
    def test_name_normalization_matches_suffixes(self, _mock_context):
        result = get_player_odds_details(
            username="u",
            season="2026",
            week="this",
            name="James Cook Jr.",
        )
        self.assertEqual(result["player"]["name"], "James Cook")

    @mock.patch(
        "oddsfantasy.odds_details.odds_client.get_event_player_odds", return_value=GAME_ODDS
    )
    @mock.patch("oddsfantasy.odds_details._load_week_context")
    def test_detail_includes_only_requested_week_matchup_context(
        self, mock_context, mock_game_odds
    ):
        mock_context.return_value = {
            **CONTEXT,
            "planned": {
                "game-1": PlannedGame(
                    game_id="game-1",
                    home_team="Buffalo Bills",
                    away_team="New York Jets",
                    commence_time="2026-09-13T17:00:00Z",
                    players=[
                        {
                            "alias": "James Cook",
                            "full_name": "James Cook",
                            "primary_position": "RB",
                            "editorial_team_full_name": "Buffalo Bills",
                        }
                    ],
                    markets=["player_rush_yds"],
                )
            },
        }

        result = get_player_odds_details(
            username="u",
            season="2026",
            week="this",
            name="James Cook",
        )

        self.assertEqual(
            result["matchup"],
            {
                "opponent": "New York Jets",
                "venue": "home",
                "commence_time": "2026-09-13T17:00:00Z",
                "game_total": 48.0,
                "team_spread": -3.0,
                "team_implied_total": 25.5,
                "books_used": 2,
            },
        )
        mock_game_odds.assert_called_once_with(
            event_id="game-1",
            markets="spreads,totals",
            regions="us",
            mode="auto",
        )
