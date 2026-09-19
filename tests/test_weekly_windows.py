import datetime as dt
import unittest

from oddsfantasy import weekly_windows as ww


def _ts(d: dt.datetime) -> str:
    return d.strftime("%Y-%m-%dT%H:%M:%SZ")


class ComputeWeekWindowsTest(unittest.TestCase):
    """Direct coverage for Eastern-time Thursday-to-Monday NFL windows."""

    def test_sunday_inside_current_cycle_stays_on_current_cycle(self):
        now = dt.datetime(2026, 8, 16)
        (this_start, this_end), (next_start, next_end) = ww.compute_week_windows(now)
        self.assertEqual(this_start, dt.datetime(2026, 8, 13, 4))
        self.assertEqual(this_end, dt.datetime(2026, 8, 18, 3, 59, 59))
        self.assertEqual(next_start, dt.datetime(2026, 8, 20, 4))
        self.assertEqual(next_end, dt.datetime(2026, 8, 25, 3, 59, 59))

    def test_tuesday_morning_eastern_flips_to_next_thu_mon_cycle(self):
        now = dt.datetime(2026, 8, 18, 12)
        (this_start, _), (next_start, _) = ww.compute_week_windows(now)
        self.assertEqual(this_start, dt.datetime(2026, 8, 20, 4))
        self.assertEqual(next_start, dt.datetime(2026, 8, 27, 4))

    def test_monday_night_kickoff_after_midnight_utc_remains_in_current_week(self):
        now = dt.datetime(2026, 9, 18, 18)
        current, _ = ww.compute_week_windows(now)
        monday_night_kickoff = "2026-09-22T00:15:00Z"
        self.assertTrue(ww.in_window(monday_night_kickoff, current))
        self.assertEqual(current[1], dt.datetime(2026, 9, 22, 3, 59, 59))

    def test_next_is_always_exactly_one_week_after_this_outside_dst_change(self):
        now = dt.datetime(2026, 8, 19)
        (this_start, _), (next_start, _) = ww.compute_week_windows(now)
        self.assertEqual(next_start - this_start, dt.timedelta(days=7))

    def test_dst_change_keeps_monday_end_at_local_end_of_day(self):
        now = dt.datetime(2026, 10, 30, 18)
        (this_start, this_end), _ = ww.compute_week_windows(now)
        self.assertEqual(this_start, dt.datetime(2026, 10, 29, 4))
        self.assertEqual(this_end, dt.datetime(2026, 11, 3, 4, 59, 59))


class EarliestFutureWeekStartTest(unittest.TestCase):
    def test_none_when_no_future_events(self):
        now = dt.datetime(2026, 8, 19)
        past = {"commence_time": _ts(now - dt.timedelta(days=5))}
        self.assertIsNone(ww.earliest_future_week_start([past], now_utc=now))

    def test_none_for_empty_events(self):
        self.assertIsNone(ww.earliest_future_week_start([], now_utc=dt.datetime(2026, 8, 19)))

    def test_anchors_to_eastern_thursday_before_the_earliest_future_game(self):
        now = dt.datetime(2026, 8, 19)
        earliest_game = dt.datetime(2026, 9, 10, 20, 0, 0)
        events = [{"commence_time": _ts(earliest_game)}]
        start = ww.earliest_future_week_start(events, now_utc=now)
        self.assertEqual(start, dt.datetime(2026, 9, 10, 4))

    def test_ignores_past_events_and_uses_the_soonest_future_one(self):
        now = dt.datetime(2026, 8, 19)
        past = {"commence_time": _ts(now - dt.timedelta(days=100))}
        soon = {"commence_time": _ts(now + dt.timedelta(days=3))}
        later = {"commence_time": _ts(now + dt.timedelta(days=30))}
        start = ww.earliest_future_week_start([later, past, soon], now_utc=now)
        self.assertEqual(start, dt.datetime(2026, 8, 20, 4))


class ResolveWeekWindowsTest(unittest.TestCase):
    """Regression coverage for the pre-season gap with no current-week games."""

    def test_uses_calendar_window_when_it_has_a_real_game(self):
        now = dt.datetime(2026, 10, 1, 12)
        (calendar_this, _), _ = ww.compute_week_windows(now)
        in_season_game = {"commence_time": _ts(calendar_this + dt.timedelta(days=1))}
        result = ww.resolve_week_windows([in_season_game], now_utc=now)
        self.assertIsNotNone(result)
        (this_start, this_end), _ = result
        self.assertEqual((this_start, this_end), ww.compute_week_windows(now)[0])

    def test_falls_forward_to_schedule_when_calendar_window_is_empty(self):
        now = dt.datetime(2026, 8, 19)
        (calendar_this, calendar_end), _ = ww.compute_week_windows(now)
        season_opener = dt.datetime(2026, 9, 10, 20, 0, 0)
        self.assertTrue(season_opener > calendar_end)
        events = [{"commence_time": _ts(season_opener)}]

        result = ww.resolve_week_windows(events, now_utc=now)
        self.assertIsNotNone(result)
        (this_start, this_end), (next_start, next_end) = result
        self.assertNotEqual(this_start, calendar_this)
        self.assertLessEqual(this_start, season_opener)
        self.assertLessEqual(season_opener, this_end)
        self.assertTrue(ww.in_window(_ts(season_opener), (this_start, this_end)))
        self.assertGreater(next_start, this_start)
        self.assertGreater(next_end, next_start)

    def test_none_when_no_games_scheduled_at_all(self):
        now = dt.datetime(2026, 8, 19)
        past_only = {"commence_time": _ts(now - dt.timedelta(days=10))}
        self.assertIsNone(ww.resolve_week_windows([past_only], now_utc=now))
        self.assertIsNone(ww.resolve_week_windows([], now_utc=now))


if __name__ == "__main__":
    unittest.main()
