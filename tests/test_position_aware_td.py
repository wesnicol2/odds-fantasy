"""Position metadata must drive ambiguous anytime-TD scoring end to end."""

import unittest

import oddsfantasy.aggregator
from oddsfantasy.planner import PlannedGame
from oddsfantasy.projection import project_player


SCORING = {"rush_td": 5, "rec_td": 8}


def anytime_event(player: str) -> dict:
    return {
        "bookmakers": [
            {
                "key": "bookA",
                "markets": [
                    {
                        "key": "player_anytime_td",
                        "outcomes": [
                            {"description": player, "name": "Yes", "price": 2.0, "point": 0},
                            {"description": player, "name": "No", "price": 2.0, "point": 0},
                        ],
                    }
                ],
            }
        ]
    }


def plan(alias: str, position: str) -> PlannedGame:
    return PlannedGame(
        game_id="g1",
        home_team="Home",
        away_team="Away",
        commence_time="2026-09-06T00:00:00Z",
        players=[
            {
                "full_name": alias,
                "alias": alias,
                "primary_position": position,
                "editorial_team_full_name": "Home",
            }
        ],
        markets=["player_anytime_td"],
    )


class PositionMetadataTest(unittest.TestCase):
    def test_aggregator_carries_position_inside_each_book_without_new_book(self):
        player = "Beta Receiver"
        odds = oddsfantasy.aggregator.aggregate_by_week(
            {"g1": anytime_event(player)}, {"g1": plan(player, "WR")}
        )
        self.assertEqual(set(odds[player]), {"bookA"})
        self.assertEqual(
            odds[player]["bookA"][oddsfantasy.aggregator.PLAYER_POSITION_META_KEY],
            {"value": "WR"},
        )
        self.assertIn("player_anytime_td", odds[player]["bookA"])

    def test_receiver_projection_uses_receiving_td_value_from_metadata(self):
        player = "Beta Receiver"
        odds = oddsfantasy.aggregator.aggregate_by_week(
            {"g1": anytime_event(player)}, {"g1": plan(player, "WR")}
        )
        projection = project_player(odds[player], SCORING)
        self.assertAlmostEqual(projection.stats["player_anytime_td"].expected_points, 4.0)
        self.assertEqual(sorted(set(projection.samples)), [0.0, 8.0])

    def test_running_back_projection_uses_rushing_td_value_from_metadata(self):
        player = "Alpha Runner"
        odds = oddsfantasy.aggregator.aggregate_by_week(
            {"g1": anytime_event(player)}, {"g1": plan(player, "RB")}
        )
        projection = project_player(odds[player], SCORING)
        self.assertAlmostEqual(projection.stats["player_anytime_td"].expected_points, 2.5)
        self.assertEqual(sorted(set(projection.samples)), [0.0, 5.0])

    def test_explicit_position_can_audit_raw_book_data_without_metadata(self):
        raw = {
            "bookA": {
                "player_anytime_td": {
                    "over": {"odds": 2.0, "point": 0},
                    "under": {"odds": 2.0, "point": 0},
                }
            }
        }
        self.assertAlmostEqual(project_player(raw, SCORING, position="WR").mean, 4.0)
        self.assertAlmostEqual(project_player(raw, SCORING, position="RB").mean, 2.5)


if __name__ == "__main__":
    unittest.main()
