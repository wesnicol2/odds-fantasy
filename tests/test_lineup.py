import unittest

from oddsfantasy.lineup import build_best_lineup


class BestLineupTest(unittest.TestCase):
    def setUp(self):
        self.players = [
            {"name": "QB Safe", "pos": "QB", "floor": 18, "mid": 20, "ceiling": 23},
            {"name": "QB Boom", "pos": "QB", "floor": 10, "mid": 19, "ceiling": 30},
            {"name": "RB 1", "pos": "RB", "floor": 12, "mid": 18, "ceiling": 24},
            {"name": "RB 2", "pos": "RB", "floor": 11, "mid": 17, "ceiling": 23},
            {"name": "RB 3", "pos": "RB", "floor": 9, "mid": 16, "ceiling": 28},
            {"name": "WR 1", "pos": "WR", "floor": 13, "mid": 19, "ceiling": 25},
            {"name": "WR 2", "pos": "WR", "floor": 10, "mid": 18, "ceiling": 27},
            {"name": "TE 1", "pos": "TE", "floor": 8, "mid": 12, "ceiling": 20},
            {
                "name": "K Market",
                "pos": "K",
                "floor": 6,
                "mid": 8,
                "ceiling": 12,
                "projection_note": "kicker proxy",
            },
        ]
        self.defenses = [
            {
                "defense": "Buffalo Bills",
                "floor": -1,
                "mid": 3,
                "ceiling": 7,
            }
        ]
        self.slots = ["QB", "RB", "RB", "WR", "WR", "TE", "FLEX", "K", "DEF", "BN", "BN"]

    def test_uses_actual_slots_including_kicker(self):
        result = build_best_lineup(
            self.players, target="mid", roster_positions=self.slots, defenses=self.defenses
        )
        self.assertEqual(len(result["lineup"]), 9)
        self.assertEqual(result["unmodeled_slots"], [])
        self.assertEqual(result["unfilled_slots"], [])
        self.assertIn("Buffalo Bills", {row["name"] for row in result["lineup"]})
        kicker = next(row for row in result["lineup"] if row["slot"] == "K")
        self.assertEqual(kicker["name"], "K Market")
        self.assertEqual(kicker["projection_note"], "kicker proxy")
        self.assertEqual(sum(row["points"] for row in result["lineup"]), result["total_points"])
        self.assertEqual(
            [row["slot_index"] for row in result["lineup"]],
            [0, 1, 2, 3, 4, 5, 6, 7, 8],
        )

    def test_missing_kicker_is_unfilled_not_unmodeled_or_zero(self):
        players = [player for player in self.players if player["pos"] != "K"]
        result = build_best_lineup(
            players, target="mid", roster_positions=self.slots, defenses=self.defenses
        )

        self.assertEqual(result["unmodeled_slots"], [])
        self.assertEqual(result["unfilled_slots"], ["K"])
        self.assertFalse(any(row["slot"] == "K" for row in result["lineup"]))

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
        self.assertEqual(pressure[0]["slot_index"], 0)
        self.assertEqual(pressure[0]["displaces_slot"], "QB")
        self.assertEqual(pressure[0]["displaces_slot_index"], 0)

    def test_partial_coverage_player_still_competes_for_lineup(self):
        players = [
            {
                "name": "Full RB",
                "pos": "RB",
                "floor": 10,
                "mid": 15,
                "ceiling": 20,
                "coverage_status": "complete",
                "missing_markets": [],
            },
            {
                "name": "Partial RB",
                "pos": "RB",
                "floor": 12,
                "mid": 18,
                "ceiling": 24,
                "coverage_status": "partial",
                "missing_markets": ["player_receptions"],
            },
        ]

        result = build_best_lineup(players, target="mid", roster_positions=["RB"])

        self.assertEqual(result["lineup"][0]["name"], "Partial RB")
        self.assertEqual(result["lineup"][0]["coverage_status"], "partial")
        self.assertEqual(result["lineup"][0]["missing_markets"], ["player_receptions"])

    def test_incomplete_non_starters_remain_on_coverage_watch(self):
        players = [
            {
                "name": "Starter RB",
                "pos": "RB",
                "floor": 10,
                "mid": 20,
                "ceiling": 25,
                "coverage_status": "complete",
                "missing_markets": [],
            },
            {
                "name": "Partial Bench",
                "pos": "RB",
                "floor": 8,
                "mid": 16,
                "ceiling": 22,
                "coverage_status": "partial",
                "missing_markets": ["player_receptions"],
            },
            {
                "name": "Unknown Bench",
                "pos": "RB",
                "floor": None,
                "mid": None,
                "ceiling": None,
                "coverage_status": "missing",
                "missing_markets": ["player_rush_yds", "player_reception_yds"],
            },
        ]

        result = build_best_lineup(players, target="mid", roster_positions=["RB"])
        watch = {row["name"]: row for row in result["coverage_watch"]}

        self.assertEqual(set(watch), {"Partial Bench", "Unknown Bench"})
        self.assertTrue(watch["Partial Bench"]["has_projection"])
        self.assertFalse(watch["Unknown Bench"]["has_projection"])
        self.assertEqual(watch["Partial Bench"]["missing_markets"], ["player_receptions"])

    def test_bench_pressure_tracks_destination_slot_through_reshuffle(self):
        players = [
            {"name": "Alpha RB", "pos": "RB", "floor": 10, "mid": 17, "ceiling": 22},
            {"name": "Gamma RB", "pos": "RB", "floor": 9, "mid": 16, "ceiling": 21},
            {"name": "Beta WR", "pos": "WR", "floor": 8, "mid": 15, "ceiling": 20},
            {"name": "Delta WR", "pos": "WR", "floor": 11, "mid": 20, "ceiling": 25},
        ]
        result = build_best_lineup(
            players,
            target="mid",
            roster_positions=["RB", "WR", "FLEX"],
        )
        beta = next(row for row in result["bench_pressure"] if row["name"] == "Beta WR")

        self.assertEqual(beta["slot"], "WR")
        self.assertEqual(beta["slot_index"], 1)
        self.assertEqual(beta["displaces"], "Gamma RB")
        self.assertEqual(beta["displaces_slot"], "FLEX")
        self.assertEqual(beta["displaces_slot_index"], 2)


if __name__ == "__main__":
    unittest.main()
