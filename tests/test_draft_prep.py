import datetime as dt
import unittest
from unittest.mock import patch

from oddsfantasy import draft_prep
from oddsfantasy.weekly_windows import earliest_future_week_start

FAKE_SLEEPER_PLAYERS = {
    "1": {"full_name": "Josh Allen", "position": "QB", "team": "BUF"},
    "2": {"full_name": "James Cook", "position": "RB", "team": "BUF"},
    "3": {
        "full_name": "Some Kicker",
        "position": "K",
        "team": "BUF",
    },  # excluded: not a draft position
    "4": {"full_name": "Free Agent Guy", "position": "WR", "team": None},  # excluded: no team
    "5": {
        "full_name": "Retired Guy",
        "position": "RB",
        "team": "ZZZ",
    },  # excluded: unmapped team abbr
    "6": {"full_name": "Patrick Mahomes", "position": "QB", "team": "KC"},
}


class ActivePlayersByTeamTest(unittest.TestCase):
    @patch("oddsfantasy.draft_prep.sleeper_api.get_players")
    def test_filters_to_skill_positions_with_a_mapped_team(self, mock_get_players):
        mock_get_players.return_value = FAKE_SLEEPER_PLAYERS
        by_team = draft_prep._all_active_players_by_team()

        self.assertIn("Buffalo Bills", by_team)
        self.assertIn("Kansas City Chiefs", by_team)
        names = {p["full_name"] for p in by_team["Buffalo Bills"]}
        self.assertEqual(names, {"Josh Allen", "James Cook"})
        # No team with only excluded players should show up at all
        self.assertNotIn(None, by_team)


def _ts(d: dt.datetime) -> str:
    return d.strftime("%Y-%m-%dT%H:%M:%SZ")


class ResolveDraftWeekWindowTest(unittest.TestCase):
    """Draft weeks are anchored to the earliest scheduled game, not to
    "today" -- a draft happens once, before the season starts, so "today"
    isn't a meaningful reference point the way it is for the in-season
    lineup views (weekly_windows.compute_week_windows)."""

    def test_none_when_no_upcoming_games(self):
        now = dt.datetime(2026, 8, 19)
        past_game = {"commence_time": _ts(now - dt.timedelta(days=5))}
        self.assertIsNone(
            draft_prep._resolve_draft_week_window([past_game], which="this", now_utc=now)
        )

    def test_week1_anchors_to_earliest_future_game_not_today(self):
        # "Today" is deep in the off-season; the earliest real game is over
        # a month out. Week 1 should anchor to that game, not to today.
        now = dt.datetime(2026, 8, 19)
        earliest_game = dt.datetime(2026, 9, 10, 20, 0, 0)  # ~3 weeks out
        events = [{"commence_time": _ts(earliest_game)}]

        window = draft_prep._resolve_draft_week_window(events, which="this", now_utc=now)
        self.assertIsNotNone(window)
        start, end = window
        self.assertLessEqual(start, earliest_game)
        self.assertLessEqual(earliest_game, end)
        # Window should NOT be anchored anywhere near "today"
        self.assertGreater(start, now + dt.timedelta(days=14))

    def test_week2_is_exactly_one_week_after_week1(self):
        now = dt.datetime(2026, 8, 19)
        earliest_game = dt.datetime(2026, 9, 10, 20, 0, 0)
        events = [{"commence_time": _ts(earliest_game)}]

        week1_start, _ = draft_prep._resolve_draft_week_window(events, which="this", now_utc=now)
        week2_start, _ = draft_prep._resolve_draft_week_window(events, which="next", now_utc=now)
        self.assertEqual(week2_start - week1_start, dt.timedelta(days=7))


class PlanWeekForDraftTest(unittest.TestCase):
    @patch("oddsfantasy.draft_prep.odds_client.get_nfl_events")
    @patch("oddsfantasy.draft_prep.sleeper_api.get_players")
    def test_builds_plan_for_week1_and_week2_separately(self, mock_get_players, mock_get_events):
        mock_get_players.return_value = FAKE_SLEEPER_PLAYERS
        now = dt.datetime.utcnow()
        # Anchor the fixture to the Thu-Mon slate the planner will actually
        # resolve, rather than to a bare "now + N days" offset. A fixed offset
        # makes this test depend on the weekday it runs on: two days in seven
        # it lands on a Tue/Wed, which is outside any Thu-Mon window, and
        # plan_week_for_draft correctly returns nothing. Real NFL games never
        # fall there, so the fixture -- not the planner -- was wrong.
        week1_start = earliest_future_week_start(
            [{"commence_time": _ts(now + dt.timedelta(days=10))}], now
        )
        week1_ts = _ts(week1_start + dt.timedelta(days=1))
        week2_ts = _ts(week1_start + dt.timedelta(days=8))
        mock_get_events.return_value = [
            {
                "id": "game-week1",
                "home_team": "Buffalo Bills",
                "away_team": "Kansas City Chiefs",
                "commence_time": week1_ts,
            },
            {
                "id": "game-week2",
                "home_team": "Buffalo Bills",
                "away_team": "Kansas City Chiefs",
                "commence_time": week2_ts,
            },
            {
                "id": "game-no-relevant-players",
                "home_team": "Some Other Team",
                "away_team": "Another Team",
                "commence_time": week1_ts,
            },
        ]

        week1_plan = draft_prep.plan_week_for_draft(week="this")
        week2_plan = draft_prep.plan_week_for_draft(week="next")

        self.assertIn("game-week1", week1_plan)
        self.assertNotIn("game-week2", week1_plan)
        self.assertNotIn("game-no-relevant-players", week1_plan)

        self.assertIn("game-week2", week2_plan)
        self.assertNotIn("game-week1", week2_plan)

        game = week1_plan["game-week1"]
        self.assertEqual(set(game.markets), set(draft_prep.CORE_DRAFT_MARKETS))
        player_names = {p["full_name"] for p in game.players}
        self.assertEqual(player_names, {"Josh Allen", "James Cook", "Patrick Mahomes"})

    @patch("oddsfantasy.draft_prep.odds_client.get_nfl_events")
    def test_empty_plan_when_no_games_scheduled_yet(self, mock_get_events):
        mock_get_events.return_value = []
        self.assertEqual(draft_prep.plan_week_for_draft(week="this"), {})


if __name__ == "__main__":
    unittest.main()
