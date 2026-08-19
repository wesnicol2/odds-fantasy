import os
import sys
import unittest
from unittest.mock import patch

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from refactored import draft_prep

FAKE_SLEEPER_PLAYERS = {
    "1": {"full_name": "Josh Allen", "position": "QB", "team": "BUF"},
    "2": {"full_name": "James Cook", "position": "RB", "team": "BUF"},
    "3": {"full_name": "Some Kicker", "position": "K", "team": "BUF"},  # excluded: not a draft position
    "4": {"full_name": "Free Agent Guy", "position": "WR", "team": None},  # excluded: no team
    "5": {"full_name": "Retired Guy", "position": "RB", "team": "ZZZ"},  # excluded: unmapped team abbr
    "6": {"full_name": "Patrick Mahomes", "position": "QB", "team": "KC"},
}


class ActivePlayersByTeamTest(unittest.TestCase):
    @patch("refactored.draft_prep.sleeper_api.get_players")
    def test_filters_to_skill_positions_with_a_mapped_team(self, mock_get_players):
        mock_get_players.return_value = FAKE_SLEEPER_PLAYERS
        by_team = draft_prep._all_active_players_by_team()

        self.assertIn("Buffalo Bills", by_team)
        self.assertIn("Kansas City Chiefs", by_team)
        names = {p["full_name"] for p in by_team["Buffalo Bills"]}
        self.assertEqual(names, {"Josh Allen", "James Cook"})
        # No team with only excluded players should show up at all
        self.assertNotIn(None, by_team)


class PlanWeekForDraftTest(unittest.TestCase):
    @patch("refactored.draft_prep.odds_client.get_nfl_events")
    @patch("refactored.draft_prep.sleeper_api.get_players")
    def test_builds_plan_only_for_in_window_games_with_players(self, mock_get_players, mock_get_events):
        mock_get_players.return_value = FAKE_SLEEPER_PLAYERS
        from refactored.weekly_windows import compute_week_windows
        (this_start, this_end), _ = compute_week_windows()
        in_window_ts = (this_start.replace(hour=13)).strftime("%Y-%m-%dT%H:%M:%SZ")
        out_of_window_ts = (this_end.replace(year=this_end.year + 1)).strftime("%Y-%m-%dT%H:%M:%SZ")
        mock_get_events.return_value = [
            {
                "id": "game-in-window",
                "home_team": "Buffalo Bills",
                "away_team": "Kansas City Chiefs",
                "commence_time": in_window_ts,
            },
            {
                "id": "game-out-of-window",
                "home_team": "Buffalo Bills",
                "away_team": "Kansas City Chiefs",
                "commence_time": out_of_window_ts,
            },
            {
                "id": "game-no-relevant-players",
                "home_team": "Some Other Team",
                "away_team": "Another Team",
                "commence_time": in_window_ts,
            },
        ]

        plan = draft_prep.plan_week_for_draft(week="this")

        self.assertIn("game-in-window", plan)
        self.assertNotIn("game-out-of-window", plan)
        self.assertNotIn("game-no-relevant-players", plan)
        game = plan["game-in-window"]
        self.assertEqual(set(game.markets), set(draft_prep.CORE_DRAFT_MARKETS))
        player_names = {p["full_name"] for p in game.players}
        self.assertEqual(player_names, {"Josh Allen", "James Cook", "Patrick Mahomes"})


if __name__ == "__main__":
    unittest.main()
