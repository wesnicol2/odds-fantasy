import datetime as dt
import unittest

from refactored import weekly_windows as ww


def _ts(d: dt.datetime) -> str:
    return d.strftime("%Y-%m-%dT%H:%M:%SZ")


class ComputeWeekWindowsTest(unittest.TestCase):
    """compute_week_windows() had no direct tests before this -- it's the
    piece that anchors "this week"/"next week" to today's calendar date,
    and the pre-season gap bug below only shows up once you know exactly
    what it returns."""

    def test_sunday_inside_current_cycle_stays_on_current_cycle(self):
        # 2026-08-13 is a Thursday; 2026-08-16 (Sunday) is still inside that
        # Thu->Mon window, so "this" should stay anchored to 8/13.
        now = dt.datetime(2026, 8, 16)
        (this_start, this_end), (next_start, next_end) = ww.compute_week_windows(now)
        self.assertEqual(this_start, dt.datetime(2026, 8, 13))
        self.assertEqual(next_start, dt.datetime(2026, 8, 20))

    def test_tuesday_flips_to_next_thu_mon_cycle(self):
        # 2026-08-18 is a Tuesday, past the 8/13-8/17 cycle's Monday end ->
        # "this" advances to the next Thu-Mon cycle (8/20-8/24).
        now = dt.datetime(2026, 8, 18)
        (this_start, this_end), (next_start, next_end) = ww.compute_week_windows(now)
        self.assertEqual(this_start, dt.datetime(2026, 8, 20))
        self.assertEqual(next_start, dt.datetime(2026, 8, 27))

    def test_next_is_always_exactly_one_week_after_this(self):
        now = dt.datetime(2026, 8, 19)
        (this_start, _), (next_start, _) = ww.compute_week_windows(now)
        self.assertEqual(next_start - this_start, dt.timedelta(days=7))


class EarliestFutureWeekStartTest(unittest.TestCase):
    def test_none_when_no_future_events(self):
        now = dt.datetime(2026, 8, 19)
        past = {"commence_time": _ts(now - dt.timedelta(days=5))}
        self.assertIsNone(ww.earliest_future_week_start([past], now_utc=now))

    def test_none_for_empty_events(self):
        self.assertIsNone(ww.earliest_future_week_start([], now_utc=dt.datetime(2026, 8, 19)))

    def test_anchors_to_thursday_before_the_earliest_future_game(self):
        now = dt.datetime(2026, 8, 19)  # Wednesday
        earliest_game = dt.datetime(2026, 9, 10, 20, 0, 0)  # a Thursday night game
        events = [{"commence_time": _ts(earliest_game)}]
        start = ww.earliest_future_week_start(events, now_utc=now)
        self.assertEqual(start, dt.datetime(2026, 9, 10))

    def test_ignores_past_events_and_uses_the_soonest_future_one(self):
        now = dt.datetime(2026, 8, 19)
        past = {"commence_time": _ts(now - dt.timedelta(days=100))}
        soon = {"commence_time": _ts(now + dt.timedelta(days=3))}
        later = {"commence_time": _ts(now + dt.timedelta(days=30))}
        start = ww.earliest_future_week_start([later, past, soon], now_utc=now)
        self.assertEqual(start, ww._prev_weekday(now + dt.timedelta(days=3), 3))


class ResolveWeekWindowsTest(unittest.TestCase):
    """This is the exact bug: /projections and /lineup came back with
    players: [] during the pre-season gap because compute_week_windows()
    anchors to today's calendar date, and today's nearest Thu-Mon cycle had
    zero real games in it (the Odds API only lists regular-season games).
    resolve_week_windows() must fall forward to the schedule in that case,
    the same way draft_prep already does for the draft board."""

    def test_uses_calendar_window_when_it_has_a_real_game(self):
        now = dt.datetime(2026, 10, 1)  # mid-season Thursday-ish
        (calendar_this, _), _ = ww.compute_week_windows(now)
        in_season_game = {"commence_time": _ts(calendar_this + dt.timedelta(days=1))}
        result = ww.resolve_week_windows([in_season_game], now_utc=now)
        self.assertIsNotNone(result)
        (this_start, this_end), _ = result
        self.assertEqual((this_start, this_end), ww.compute_week_windows(now)[0])

    def test_falls_forward_to_schedule_when_calendar_window_is_empty(self):
        # Regression for the reported bug: today (Aug 19) is deep in the
        # pre-season gap; the calendar's nearest Thu-Mon window (~Aug 20-24)
        # has no games at all, but the season opener is ~3 weeks out.
        now = dt.datetime(2026, 8, 19)
        (calendar_this, calendar_end), _ = ww.compute_week_windows(now)
        season_opener = dt.datetime(2026, 9, 10, 20, 0, 0)
        self.assertTrue(season_opener > calendar_end)  # sanity: outside the calendar window
        events = [{"commence_time": _ts(season_opener)}]

        result = ww.resolve_week_windows(events, now_utc=now)
        self.assertIsNotNone(result)
        (this_start, this_end), (next_start, next_end) = result
        # Should NOT be the empty calendar window...
        self.assertNotEqual(this_start, calendar_this)
        # ...should instead cover the season opener.
        self.assertLessEqual(this_start, season_opener)
        self.assertLessEqual(season_opener, this_end)
        self.assertEqual(next_start - this_start, dt.timedelta(days=7))

    def test_none_when_no_games_scheduled_at_all(self):
        now = dt.datetime(2026, 8, 19)
        past_only = {"commence_time": _ts(now - dt.timedelta(days=10))}
        self.assertIsNone(ww.resolve_week_windows([past_only], now_utc=now))
        self.assertIsNone(ww.resolve_week_windows([], now_utc=now))

    def test_agrees_with_draft_prep_week1_anchor_during_the_pre_season_gap(self):
        # Both features are solving "what's the week of the soonest real
        # game" in this situation -- they should agree.
        from refactored import draft_prep

        now = dt.datetime(2026, 8, 19)
        season_opener = dt.datetime(2026, 9, 10, 20, 0, 0)
        events = [{"commence_time": _ts(season_opener)}]

        (lineup_this_start, _), _ = ww.resolve_week_windows(events, now_utc=now)
        draft_week1_start, _ = draft_prep._resolve_draft_week_window(
            events, which="this", now_utc=now
        )
        self.assertEqual(lineup_this_start, draft_week1_start)


if __name__ == "__main__":
    unittest.main()
