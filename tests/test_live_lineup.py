import unittest
from unittest import mock

from oddsfantasy.live_lineup import current_lineup_lock_state, normalize_game_status


class LiveLineupStateTest(unittest.TestCase):
    def setUp(self):
        self.roster_positions = ["QB", "RB", "WR", "FLEX", "K", "DEF", "BN", "BN"]
        self.players = {
            "qb-future": {"full_name": "Future QB", "position": "QB", "team": "SEA"},
            "rb-live": {"full_name": "Live RB", "position": "RB", "team": "SF"},
            "wr-final": {"full_name": "Final WR", "position": "WR", "team": "BUF"},
            "flex-future": {"full_name": "Future Flex", "position": "WR", "team": "CHI"},
            "k-live": {"full_name": "Live Kicker", "position": "K", "team": "LAR"},
            "bench-final": {"full_name": "Final Bench", "position": "RB", "team": "HOU"},
            "SF": {"full_name": "49ers", "position": "DEF", "team": "SF"},
        }
        self.matchups = [
            {
                "roster_id": 7,
                "starters": [
                    "qb-future",
                    "rb-live",
                    "wr-final",
                    "flex-future",
                    "k-live",
                    "SF",
                ],
                "players": [
                    "qb-future",
                    "rb-live",
                    "wr-final",
                    "flex-future",
                    "k-live",
                    "SF",
                    "bench-final",
                ],
                "starters_points": [0.0, 0.0, 14.5, 0.0, 5.0, 3.0],
                "players_points": {"bench-final": 22.0},
            }
        ]
        self.schedule = [
            {"week": 1, "home": "SF", "away": "LAR", "status": "in_progress"},
            {"week": 1, "home": "BUF", "away": "HOU", "status": "final"},
            {"week": 1, "home": "SEA", "away": "NE", "status": "pre_game"},
            {"week": 1, "home": "CHI", "away": "CAR", "status": "pre_game"},
        ]

    @mock.patch("oddsfantasy.live_lineup.sleeper_api.get_players")
    @mock.patch("oddsfantasy.live_lineup.sleeper_api.get_nfl_schedule")
    @mock.patch("oddsfantasy.live_lineup.sleeper_api.get_league_matchups")
    @mock.patch("oddsfantasy.live_lineup.sleeper_api.get_nfl_state")
    def test_freezes_submitted_started_slots_and_blocks_started_bench(
        self, mock_state, mock_matchups, mock_schedule, mock_players
    ):
        mock_state.return_value = {"season": "2026", "season_type": "regular", "leg": 1}
        mock_matchups.return_value = self.matchups
        mock_schedule.return_value = self.schedule
        mock_players.return_value = self.players

        result = current_lineup_lock_state(
            league_id="league",
            roster_id=7,
            season="2026",
            roster_positions=self.roster_positions,
        )

        locks = {row["player_id"]: row for row in result["locked_assignments"]}
        self.assertEqual(set(locks), {"rb-live", "wr-final", "k-live", "SF"})
        self.assertEqual(locks["rb-live"]["slot"], "RB")
        self.assertEqual(locks["rb-live"]["actual_points"], 0.0)
        self.assertEqual(locks["rb-live"]["game_status"], "live")
        self.assertEqual(locks["k-live"]["starter_index"], 4)
        self.assertEqual(locks["k-live"]["slot"], "K")
        self.assertEqual(locks["wr-final"]["game_status"], "final")
        self.assertEqual(locks["SF"]["pos"], "DEF")

        self.assertEqual(
            set(result["unavailable_player_ids"]),
            {"rb-live", "wr-final", "k-live", "SF", "bench-final"},
        )
        self.assertEqual(result["player_statuses"]["bench-final"], "final")
        self.assertNotIn("qb-future", result["unavailable_player_ids"])
        self.assertNotIn("flex-future", result["unavailable_player_ids"])

    @mock.patch("oddsfantasy.live_lineup.sleeper_api.get_league_matchups")
    @mock.patch("oddsfantasy.live_lineup.sleeper_api.get_nfl_state")
    def test_does_not_apply_current_live_state_to_another_season(
        self, mock_state, mock_matchups
    ):
        mock_state.return_value = {"season": "2026", "season_type": "regular", "leg": 1}
        result = current_lineup_lock_state(
            league_id="league",
            roster_id=7,
            season="2025",
            roster_positions=self.roster_positions,
        )
        self.assertEqual(result["locked_assignments"], [])
        mock_matchups.assert_not_called()

    def test_unknown_provider_status_does_not_false_lock(self):
        self.assertEqual(normalize_game_status("pre_game"), "upcoming")
        self.assertEqual(normalize_game_status("delayed"), "upcoming")
        self.assertEqual(normalize_game_status("in-progress"), "live")
        self.assertEqual(normalize_game_status("FINAL"), "final")


if __name__ == "__main__":
    unittest.main()
