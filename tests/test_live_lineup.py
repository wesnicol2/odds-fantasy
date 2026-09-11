import datetime as dt
import unittest
from types import SimpleNamespace

from oddsfantasy.lineup import build_best_lineup
from oddsfantasy.live_lineup import build_live_state


class LockedLineupOptimizerTest(unittest.TestCase):
    def test_started_starter_stays_in_submitted_slot_and_uses_actual_points(self):
        players = [
            {
                "name": "Alpha Back",
                "pos": "RB",
                "team": "A",
                "floor": 15,
                "mid": 20,
                "ceiling": 25,
            },
            {
                "name": "Thursday Back",
                "pos": "RB",
                "team": "B",
                "floor": 2,
                "mid": 5,
                "ceiling": 9,
            },
            {
                "name": "Sunday Receiver",
                "pos": "WR",
                "team": "C",
                "floor": 10,
                "mid": 15,
                "ceiling": 20,
            },
        ]

        result = build_best_lineup(
            players,
            target="mid",
            roster_positions=["RB", "FLEX"],
            locked_starters=[
                {
                    "slot_index": 1,
                    "name": "Thursday Back",
                    "pos": "RB",
                    "team": "B",
                    "actual_points": 3.0,
                }
            ],
            unavailable_names={"Thursday Back"},
        )

        self.assertEqual([row["name"] for row in result["lineup"]], ["Alpha Back", "Thursday Back"])
        locked = result["lineup"][1]
        self.assertEqual(locked["slot"], "FLEX")
        self.assertTrue(locked["locked"])
        self.assertEqual(locked["points"], 3.0)
        self.assertEqual(result["actual_points"], 3.0)
        self.assertEqual(result["remaining_projected_points"], 20.0)
        self.assertEqual(result["total_points"], 23.0)
        self.assertEqual(result["decisions_remaining"], 1)

    def test_started_bench_player_cannot_be_recommended_after_kickoff(self):
        players = [
            {
                "name": "Sunday Back",
                "pos": "RB",
                "team": "A",
                "floor": 8,
                "mid": 10,
                "ceiling": 14,
            },
            {
                "name": "Thursday Bench Boom",
                "pos": "RB",
                "team": "B",
                "floor": 20,
                "mid": 30,
                "ceiling": 40,
            },
        ]

        result = build_best_lineup(
            players,
            target="mid",
            roster_positions=["RB"],
            unavailable_names={"Thursday Bench Boom"},
        )

        self.assertEqual(result["lineup"][0]["name"], "Sunday Back")
        self.assertNotIn(
            "Thursday Bench Boom", {row["name"] for row in result["bench_pressure"]}
        )


class LiveStateTest(unittest.TestCase):
    def test_submitted_started_slots_and_bench_are_classified_from_kickoff(self):
        now = dt.datetime(2026, 9, 10, 20, 0, tzinfo=dt.timezone.utc)
        roster = {
            "players": {
                "a": {
                    "name": {"full": "Started Back"},
                    "primary_position": "RB",
                    "editorial_team_full_name": "Team A",
                },
                "b": {
                    "name": {"full": "Started Flex"},
                    "primary_position": "WR",
                    "editorial_team_full_name": "Team B",
                },
                "c": {
                    "name": {"full": "Started Bench"},
                    "primary_position": "RB",
                    "editorial_team_full_name": "Team A",
                },
                "future": {
                    "name": {"full": "Sunday Player"},
                    "primary_position": "WR",
                    "editorial_team_full_name": "Team C",
                },
                "k": {
                    "name": {"full": "Kicker"},
                    "primary_position": "K",
                    "editorial_team_full_name": "Team B",
                },
            }
        }
        planned = {
            "started": SimpleNamespace(
                home_team="Team A",
                away_team="Team B",
                commence_time="2026-09-10T19:00:00Z",
            ),
            "future": SimpleNamespace(
                home_team="Team C",
                away_team="Team D",
                commence_time="2026-09-13T17:00:00Z",
            ),
        }
        matchup = {
            "starters": ["a", "b", "k"],
            "players_points": {"a": 8.5, "b": 4.0, "c": 19.0, "k": 6.0},
        }

        state = build_live_state(
            roster,
            ["RB", "FLEX", "K", "BN"],
            matchup,
            planned,
            now=now,
        )

        self.assertEqual(
            [(row["slot_index"], row["name"]) for row in state["locked_starters"]],
            [(0, "Started Back"), (1, "Started Flex")],
        )
        self.assertEqual(state["locked_starters"][0]["actual_points"], 8.5)
        self.assertEqual([row["name"] for row in state["locked_bench"]], ["Started Bench"])
        self.assertIn("Kicker", state["unavailable_names"])
        self.assertNotIn("Sunday Player", state["unavailable_names"])


if __name__ == "__main__":
    unittest.main()
