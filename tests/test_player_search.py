"""Manual player comparison must preserve the roster odds plan and quota semantics."""

import unittest
from unittest.mock import patch

from oddsfantasy import services


class PlayerSearchTests(unittest.TestCase):
    @patch("oddsfantasy.services.sleeper_api.get_players")
    def test_search_filters_positions_and_ranks_prefixes(self, get_players):
        get_players.return_value = {
            "10": {"full_name": "River Alpha", "position": "WR", "team": "BUF"},
            "11": {"full_name": "Alpha Runner", "position": "RB", "team": "BUF"},
            "12": {"full_name": "Alpha Defense", "position": "DEF", "team": "BUF"},
        }
        result = services.search_players("alpha")["players"]
        self.assertEqual([row["id"] for row in result], ["11", "10"])
        self.assertEqual(result[0]["pos"], "RB")
        self.assertEqual(services.search_players("a")["players"], [])

    @patch("oddsfantasy.services._resolve_identity")
    @patch("oddsfantasy.services.sleeper_api.get_players")
    @patch("oddsfantasy.services.sleeper_api.get_player_enhanced_info")
    @patch("oddsfantasy.services.odds_client.get_nfl_events")
    @patch("oddsfantasy.services.resolve_week_windows")
    @patch("oddsfantasy.services.plan_relevant_games_and_markets")
    @patch("oddsfantasy.services._fetch_odds")
    @patch("oddsfantasy.services.aggregate_by_week")
    def test_external_player_is_overlay_only(
        self,
        aggregate,
        fetch,
        plan,
        windows,
        events,
        enhanced,
        players,
        resolve,
    ):
        roster = {"players": {"1": {"name": {"full": "Owned Player"}}}, "scoring_rules": {}}
        resolve.return_value = roster
        players.return_value = {"9": {"full_name": "External Player", "position": "WR"}}
        enhanced.return_value = {
            "name": {"full": "External Player"},
            "primary_position": "WR",
            "editorial_team_full_name": "Buffalo Bills",
        }
        events.return_value = []
        windows.return_value = (("a", "b"), ("c", "d"))
        plan.return_value = {"this": {}, "next": {}}
        fetch.return_value = {}
        aggregate.return_value = {}
        services._context_cache().clear()

        common = {"username": "user", "season": "2026", "week": "this"}
        original = services._load_week_context(**common)
        overlay = services._load_week_context(**common, extra_player_id="9")

        self.assertEqual(list(roster["players"]), ["1"])
        self.assertEqual(list(original["roster"]["players"]), ["1"])
        self.assertEqual(list(overlay["roster"]["players"]), ["1", "9"])
        self.assertEqual(plan.call_count, 2)
