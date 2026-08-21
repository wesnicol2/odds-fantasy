import unittest
from unittest.mock import MagicMock, patch

from oddsfantasy import sleeper_api


def _fake_response(payload):
    resp = MagicMock()
    resp.json.return_value = payload
    resp.raise_for_status.return_value = None
    return resp


class GetLeagueTest(unittest.TestCase):
    @patch("oddsfantasy.sleeper_api.requests.get")
    def test_returns_raw_league_object(self, mock_get):
        mock_get.return_value = _fake_response(
            {
                "league_id": "123",
                "status": "pre_draft",
                "season": "2026",
                "name": "My League",
                "scoring_settings": {"rec": 1.0},
            }
        )
        league = sleeper_api.get_league("123")
        self.assertEqual(league["status"], "pre_draft")
        self.assertEqual(league["name"], "My League")
        called_url = mock_get.call_args[0][0]
        self.assertIn("/league/123", called_url)


class GetLeagueTeamsTest(unittest.TestCase):
    @patch("oddsfantasy.sleeper_api.get_league_users")
    @patch("oddsfantasy.sleeper_api.get_league_rosters")
    def test_team_name_falls_back_through_metadata_then_display_name_then_generic(
        self, mock_rosters, mock_users
    ):
        mock_rosters.return_value = [
            {"roster_id": 1, "owner_id": "u1", "metadata": {"team_name": "The Custom Name"}},
            {"roster_id": 2, "owner_id": "u2", "metadata": {}},
            {"roster_id": 3, "owner_id": "u3"},  # no metadata key at all
        ]
        mock_users.return_value = [
            {"user_id": "u1", "display_name": "Alice"},
            {"user_id": "u2", "display_name": "Bob"},
            # u3 has no matching user entry
        ]
        teams = sleeper_api.get_league_teams("123")
        by_roster = {t["roster_id"]: t for t in teams}
        self.assertEqual(by_roster[1]["team_name"], "The Custom Name")
        self.assertEqual(by_roster[2]["team_name"], "Bob")
        self.assertEqual(by_roster[3]["team_name"], "Team 3")


class GetLeagueRosterDataTest(unittest.TestCase):
    @patch("oddsfantasy.sleeper_api.get_league")
    def test_no_roster_id_returns_empty_players_but_real_scoring(self, mock_league):
        mock_league.return_value = {
            "status": "pre_draft",
            "season": "2026",
            "name": "My League",
            "scoring_settings": {"rec": 0.5},
        }
        data = sleeper_api.get_league_roster_data("123", roster_id=None)
        self.assertEqual(data["players"], {})
        self.assertEqual(data["scoring_rules"], {"rec": 0.5})
        self.assertEqual(data["status"], "pre_draft")

    @patch("oddsfantasy.sleeper_api.get_enhanced_info_for_roster")
    @patch("oddsfantasy.sleeper_api.get_league_rosters")
    @patch("oddsfantasy.sleeper_api.get_league")
    def test_roster_id_scopes_to_that_roster_only(self, mock_league, mock_rosters, mock_enhanced):
        mock_league.return_value = {
            "status": "in_season",
            "season": "2026",
            "name": "L",
            "scoring_settings": {},
        }
        mock_rosters.return_value = [
            {"roster_id": 1, "players": ["p1"]},
            {"roster_id": 2, "players": ["p2"]},
        ]
        mock_enhanced.return_value = {"p2": {"name": {"full": "Player Two"}}}

        data = sleeper_api.get_league_roster_data("123", roster_id=2)
        self.assertEqual(data["players"], {"p2": {"name": {"full": "Player Two"}}})
        mock_enhanced.assert_called_once_with({"roster_id": 2, "players": ["p2"]})


class ResolveUserLeaguesTest(unittest.TestCase):
    @patch("oddsfantasy.services.sleeper_api.get_user_leagues")
    @patch("oddsfantasy.services.sleeper_api.get_user_id")
    def test_returns_trimmed_league_list(self, mock_user_id, mock_leagues):
        from oddsfantasy.services import resolve_user_leagues

        mock_user_id.return_value = "u123"
        mock_leagues.return_value = [
            {
                "league_id": "L1",
                "name": "Dynasty Dudes",
                "status": "in_season",
                "season": "2026",
                "extra_junk": True,
            },
            {"league_id": "L2", "name": "Redraft Rivals", "status": "pre_draft", "season": "2026"},
        ]
        result = resolve_user_leagues("wesnicol", "2026")
        self.assertEqual(result["user_id"], "u123")
        self.assertEqual(len(result["leagues"]), 2)
        self.assertEqual(
            result["leagues"][0],
            {"league_id": "L1", "name": "Dynasty Dudes", "status": "in_season", "season": "2026"},
        )
        mock_leagues.assert_called_once_with("u123", "2026")

    @patch("oddsfantasy.services.sleeper_api.get_user_id")
    def test_unknown_username_returns_error_not_exception(self, mock_user_id):
        from oddsfantasy.services import resolve_user_leagues

        mock_user_id.side_effect = Exception("404 not found")
        result = resolve_user_leagues("nobody", "2026")
        self.assertEqual(result["error"], "user_not_found")

    @patch("oddsfantasy.services.sleeper_api.get_user_leagues")
    @patch("oddsfantasy.services.sleeper_api.get_user_id")
    def test_no_leagues_for_season_returns_empty_list_not_error(self, mock_user_id, mock_leagues):
        from oddsfantasy.services import resolve_user_leagues

        mock_user_id.return_value = "u123"
        mock_leagues.return_value = []
        result = resolve_user_leagues("wesnicol", "2019")
        self.assertNotIn("error", result)
        self.assertEqual(result["leagues"], [])


class CurrentNflSeasonTest(unittest.TestCase):
    def test_current_season_matches_expected_default(self):
        # Sanity check against the real clock rather than hardcoding a
        # brittle expected year -- just verify the Jan/Feb-is-still-last-
        # season rule is actually applied.
        from oddsfantasy import config

        now = __import__("datetime").datetime.utcnow()
        expected = str(now.year if now.month >= 3 else now.year - 1)
        self.assertEqual(config.current_nfl_season(), expected)
        self.assertEqual(config.DEFAULT_SEASON, expected)


class ResolveIdentityPriorityTest(unittest.TestCase):
    """When both a league_id and a username/season are available, league_id
    must win -- it's explicit and unambiguous, whereas username-based
    resolution silently guesses "first league for this user" and can pick
    the wrong league for anyone in more than one."""

    @patch("oddsfantasy.services.sleeper_api.get_user_sleeper_data")
    @patch("oddsfantasy.services.sleeper_api.get_league_roster_data")
    def test_league_id_takes_priority_over_username(self, mock_league_roster, mock_user_data):
        from oddsfantasy.services import _resolve_identity

        mock_league_roster.return_value = {"players": {}, "scoring_rules": {"rec": 1.0}}
        result = _resolve_identity("someuser", "2025", league_id="LEAGUE123", roster_id=5)
        mock_league_roster.assert_called_once_with("LEAGUE123", roster_id=5)
        mock_user_data.assert_not_called()
        self.assertEqual(result["scoring_rules"], {"rec": 1.0})

    @patch("oddsfantasy.services.sleeper_api.get_user_sleeper_data")
    @patch("oddsfantasy.services.sleeper_api.get_league_roster_data")
    def test_falls_back_to_username_when_no_league_id(self, mock_league_roster, mock_user_data):
        from oddsfantasy.services import _resolve_identity

        mock_user_data.return_value = {"players": {}, "scoring_rules": {"pass_td": 4.0}}
        result = _resolve_identity("someuser", "2025")
        mock_user_data.assert_called_once_with("someuser", "2025")
        mock_league_roster.assert_not_called()
        self.assertEqual(result["scoring_rules"], {"pass_td": 4.0})


if __name__ == "__main__":
    unittest.main()
