"""Regression coverage for weeks whose schedule has not been posted yet."""

import unittest
from unittest.mock import patch

from oddsfantasy import odds_details, services

FAKE_ROSTER = {"players": {}, "scoring_rules": {}}


class NoGamesScheduledYetTest(unittest.TestCase):
    def setUp(self):
        if hasattr(services._load_week_context, "_cache"):
            services._load_week_context._cache = {}

    @patch("oddsfantasy.services.odds_client.get_nfl_events")
    @patch("oddsfantasy.services._resolve_identity")
    def test_compute_projections_surfaces_message(self, mock_identity, mock_events):
        mock_identity.return_value = FAKE_ROSTER
        mock_events.return_value = []
        result = services.compute_projections(
            username="wesnicol",
            season="2026",
            week="this",
            fresh=True,
        )
        self.assertEqual(result["players"], [])
        self.assertIn("No scheduled games", result["message"])

    @patch("oddsfantasy.services.odds_client.get_nfl_events")
    @patch("oddsfantasy.services._resolve_identity")
    def test_player_details_surfaces_same_message(self, mock_identity, mock_events):
        mock_identity.return_value = FAKE_ROSTER
        mock_events.return_value = []
        result = odds_details.get_player_odds_details(
            username="wesnicol",
            season="2026",
            week="this",
            name="Josh Allen",
            fresh=True,
        )
        self.assertIsNone(result["projection"])
        self.assertEqual(result["markets"], {})
        self.assertIn("No scheduled games", result["message"])


if __name__ == "__main__":
    unittest.main()
