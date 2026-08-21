"""Regression tests for the reported bug: /projections, /lineup, /defenses
and the player/defense detail endpoints came back empty during the
pre-season gap (today's calendar week has no real games yet), which the
user first mistook for a bad Odds API key. The root cause was
weekly_windows.compute_week_windows() being anchored to today's calendar
date with no fallback -- see test_weekly_windows.py for the fix itself.
These tests check that every call site actually uses the fix and surfaces a
clear message instead of a bare empty list. The detail endpoints have since
moved to odds_details.py, so they are exercised there.
"""

import unittest
from unittest.mock import patch

from oddsfantasy import odds_details, services

FAKE_ROSTER = {"players": {}, "scoring_rules": {}}


class NoGamesScheduledYetTest(unittest.TestCase):
    """odds_client.get_nfl_events() returning only past/no events is exactly
    what happens during the pre-season gap -- the Odds API simply hasn't
    posted the next real slate yet."""

    @patch("oddsfantasy.services.odds_client.get_nfl_events")
    @patch("oddsfantasy.services._resolve_identity")
    def test_compute_projections_surfaces_message_instead_of_bare_empty_list(
        self, mock_identity, mock_events
    ):
        mock_identity.return_value = FAKE_ROSTER
        mock_events.return_value = []

        result = services.compute_projections(
            username="wesnicol", season="2026", week="this", fresh=True
        )

        self.assertEqual(result["players"], [])
        self.assertIn("message", result)
        self.assertIn("No scheduled games", result["message"])

    @patch("oddsfantasy.services.odds_client.get_nfl_events")
    @patch("oddsfantasy.services._resolve_identity")
    def test_list_defenses_surfaces_message_instead_of_bare_empty_list(
        self, mock_identity, mock_events
    ):
        mock_identity.return_value = FAKE_ROSTER
        mock_events.return_value = []

        result = services.list_defenses(username="wesnicol", season="2026", week="this", fresh=True)

        self.assertEqual(result["defenses"], [])
        self.assertIn("message", result)
        self.assertIn("No scheduled games", result["message"])

    @patch("oddsfantasy.odds_details.odds_client.get_nfl_events")
    def test_get_player_odds_details_surfaces_message_instead_of_bare_empty_result(
        self, mock_events
    ):
        mock_events.return_value = []

        result = odds_details.get_player_odds_details(
            username="wesnicol", season="2026", week="this", name="Josh Allen"
        )

        self.assertEqual(result["markets"], {})
        self.assertIn("message", result)
        self.assertIn("No scheduled games", result["message"])

    @patch("oddsfantasy.odds_details.odds_client.get_nfl_events")
    def test_get_defense_odds_details_surfaces_message_instead_of_bare_empty_result(
        self, mock_events
    ):
        mock_events.return_value = []

        result = odds_details.get_defense_odds_details(
            username="wesnicol", season="2026", week="this", defense="Buffalo Bills"
        )

        self.assertEqual(result["games"], [])
        self.assertIn("message", result)
        self.assertIn("No scheduled games", result["message"])


if __name__ == "__main__":
    unittest.main()
