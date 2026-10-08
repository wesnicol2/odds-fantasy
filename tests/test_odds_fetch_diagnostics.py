import unittest
from types import SimpleNamespace
from unittest.mock import patch

from oddsfantasy import services


class OddsFetchDiagnosticsTest(unittest.TestCase):
    @patch(
        "oddsfantasy.services.odds_client.get_event_player_odds",
        side_effect=RuntimeError("https://provider.test?apiKey=secret"),
    )
    def test_failed_game_fetch_is_preserved_as_diagnostic(self, _mock_fetch):
        result = services._fetch_odds(
            {
                "game-1": SimpleNamespace(
                    markets=["player_rush_yds", "player_anytime_td"]
                )
            },
            cache_mode="fresh",
        )

        self.assertEqual(dict(result), {})
        self.assertEqual(len(result.fetch_diagnostics), 1)
        issue = result.fetch_diagnostics[0]
        self.assertEqual(issue["provider_id"], "odds_api")
        self.assertEqual(issue["code"], "odds_api_fetch_failed")
        self.assertEqual(issue["severity"], "error")
        self.assertEqual(issue["game_id"], "game-1")
        self.assertIn("RuntimeError", issue["message"])
        self.assertNotIn("secret", issue["message"])

    def test_game_diagnostic_maps_to_only_that_games_player(self):
        game = SimpleNamespace(players=[{"alias": "Derrick Henry"}])
        context = {
            "planned": {"game-1": game},
            "provider_diagnostics": (
                {
                    "provider_id": "odds_api",
                    "code": "odds_api_fetch_failed",
                    "message": "Sportsbook player-prop fetch failed (HTTP 500).",
                    "severity": "error",
                    "game_id": "game-1",
                },
                {
                    "provider_id": "kalshi",
                    "code": "market_not_found",
                    "message": "Other player issue.",
                    "severity": "warning",
                    "game_id": "game-2",
                },
            ),
        }

        issues = services._player_data_issues(context, "Derrick Henry")

        self.assertEqual(len(issues), 1)
        self.assertEqual(services._player_data_status(issues), "fetch_failed")


if __name__ == "__main__":
    unittest.main()
