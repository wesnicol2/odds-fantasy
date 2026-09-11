import unittest

from oddsfantasy.lineup import build_best_lineup


class BestLineupTest(unittest.TestCase):
    def setUp(self):
        self.players = [
            {
                "player_id": "qb-safe",
                "name": "QB Safe",
                "pos": "QB",
                "floor": 18,
                "mid": 20,
                "ceiling": 23,
            },
            {
                "player_id": "qb-boom",
                "name": "QB Boom",
                "pos": "QB",
                "floor": 10,
                "mid": 19,
                "ceiling": 30,
            },
            {
                "player_id": "rb-1",
                "name": "RB 1",
                "pos": "RB",
                "floor": 12,
                "mid": 18,
                "ceiling": 24,
            },
            {
                "player_id": "rb-2",
                "name": "RB 2",
                "pos": "RB",
                "floor": 11,
                "mid": 17,
                "ceiling": 23,
            },
            {
                "player_id": "rb-3",
                "name": "RB 3",
                "pos": "RB",
                "floor": 9,
                "mid": 16,
                "ceiling": 28,
            },
            {
                "player_id": "wr-1",
                "name": "WR 1",
                "pos": "WR",
                "floor": 13,
                "mid": 19,
                "ceiling": 25,
            },
            {
                "player_id": "wr-2",
                "name": "WR 2",
                "pos": "WR",
                "floor": 10,
                "mid": 18,
                "ceiling": 27,
            },
            {
                "player_id": "te-1",
                "name": "TE 1",
                "pos": "TE",
                "floor": 8,
                "mid": 12,
                "ceiling": 20,
            },
        ]
        self.defenses = [
            {
                "defense": "Buffalo Bills",
                "abbr": "BUF",
                "floor": -1,
                "mid": 3,
                "ceiling": 7,
            }
        ]
        self.slots = ["QB", "RB", "RB", "WR", "WR", "TE", "FLEX", "K", "DEF", "BN", "BN"]

    def test_uses_actual_slots_and_flags_unmodeled_kicker(self):
        result = build_best_lineup(
            self.players, target="mid", roster_positions=self.slots, defenses=self.defenses
        )
        self.assertEqual(len(result["lineup"]), 8)
        self.assertEqual(result["unmodeled_slots"], ["K"])
        self.assertIn("Buffalo Bills", {row["name"] for row in result["lineup"]})
        self.assertEqual(sum(row["points"] for row in result["lineup"]), result["total_points"])

    def test_ceiling_can_choose_a_different_qb(self):
        floor = build_best_lineup(
            self.players, target="floor", roster_positions=self.slots, defenses=self.defenses
        )
        ceiling = build_best_lineup(
            self.players, target="ceiling", roster_positions=self.slots, defenses=self.defenses
        )
        floor_qb = next(row for row in floor["lineup"] if row["slot"] == "QB")
        ceiling_qb = next(row for row in ceiling["lineup"] if row["slot"] == "QB")
        self.assertEqual(floor_qb["name"], "QB Safe")
        self.assertEqual(ceiling_qb["name"], "QB Boom")

    def test_flex_assignment_is_globally_optimized(self):
        result = build_best_lineup(
            self.players, target="ceiling", roster_positions=self.slots, defenses=self.defenses
        )
        starters = {row["name"] for row in result["lineup"]}
        self.assertIn("RB 3", starters)
        self.assertIn("WR 2", starters)

    def test_bench_pressure_is_optimizer_opportunity_cost(self):
        result = build_best_lineup(
            self.players, target="mid", roster_positions=self.slots, defenses=self.defenses
        )
        pressure = result["bench_pressure"]
        self.assertEqual([row["name"] for row in pressure], ["QB Boom"])
        self.assertEqual(pressure[0]["delta_to_lineup"], 1.0)
        self.assertEqual(pressure[0]["displaces"], "QB Safe")
        self.assertEqual(pressure[0]["slot"], "QB")
        self.assertEqual(pressure[0]["displaces_slot"], "QB")

    def test_locked_starter_stays_in_submitted_slot_and_uses_actual_points(self):
        result = build_best_lineup(
            self.players,
            target="mid",
            roster_positions=self.slots,
            defenses=self.defenses,
            locked_assignments=[
                {
                    "starter_index": 0,
                    "slot": "QB",
                    "player_id": "qb-boom",
                    "name": "QB Boom",
                    "pos": "QB",
                    "team": "Example",
                    "actual_points": 4.25,
                    "game_status": "live",
                }
            ],
            unavailable_player_ids={"qb-boom"},
        )
        qb = next(row for row in result["lineup"] if row["slot"] == "QB")
        self.assertEqual(qb["name"], "QB Boom")
        self.assertTrue(qb["locked"])
        self.assertEqual(qb["points"], 4.25)
        self.assertEqual(qb["game_status"], "live")
        self.assertEqual(result["locked_points"], 4.25)
        self.assertEqual(result["locked_count"], 1)
        self.assertEqual(result["remaining_slots"], 8)
        self.assertAlmostEqual(
            result["total_points"], result["locked_points"] + result["remaining_points"]
        )
        self.assertNotIn("QB Safe", [row["name"] for row in result["bench_pressure"]])

    def test_started_bench_player_is_not_an_actionable_recommendation(self):
        players = [
            {
                "player_id": "starter",
                "name": "Sunday Starter",
                "pos": "QB",
                "floor": 10,
                "mid": 20,
                "ceiling": 25,
            },
            {
                "player_id": "played-bench",
                "name": "Thursday Bench Boom",
                "pos": "QB",
                "floor": 15,
                "mid": 30,
                "ceiling": 40,
            },
            {
                "player_id": "open-bench",
                "name": "Sunday Bench",
                "pos": "QB",
                "floor": 8,
                "mid": 19,
                "ceiling": 28,
            },
        ]
        result = build_best_lineup(
            players,
            target="mid",
            roster_positions=["QB", "BN", "BN"],
            unavailable_player_ids={"played-bench"},
        )
        self.assertEqual(result["lineup"][0]["name"], "Sunday Starter")
        self.assertEqual([row["name"] for row in result["bench_pressure"]], ["Sunday Bench"])
        self.assertEqual(result["locked_bench_count"], 1)

    def test_locked_unmodeled_kicker_is_shown_not_reported_as_unmodeled(self):
        result = build_best_lineup(
            self.players,
            target="mid",
            roster_positions=self.slots,
            defenses=self.defenses,
            locked_assignments=[
                {
                    "starter_index": 7,
                    "slot": "K",
                    "player_id": "k-1",
                    "name": "Thursday Kicker",
                    "pos": "K",
                    "team": "Example",
                    "actual_points": 11.0,
                    "game_status": "final",
                }
            ],
            unavailable_player_ids={"k-1"},
        )
        kicker = next(row for row in result["lineup"] if row["slot"] == "K")
        self.assertTrue(kicker["locked"])
        self.assertEqual(kicker["actual_points"], 11.0)
        self.assertNotIn("K", result["unmodeled_slots"])


if __name__ == "__main__":
    unittest.main()
