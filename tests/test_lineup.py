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


if __name__ == "__main__":
    unittest.main()
