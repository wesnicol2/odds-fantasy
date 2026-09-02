from unittest import TestCase, mock

from oddsfantasy.odds_details import get_player_odds_details


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

    @mock.patch("oddsfantasy.odds_details._load_week_context", return_value=CONTEXT)
    def test_name_normalization_matches_suffixes(self, _mock_context):
        result = get_player_odds_details(
            username="u",
            season="2026",
            week="this",
            name="James Cook Jr.",
        )
        self.assertEqual(result["player"]["name"], "James Cook")
