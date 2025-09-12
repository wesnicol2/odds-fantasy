import datetime as _dt
from typing import Tuple


def _next_weekday(base: _dt.datetime, weekday: int) -> _dt.datetime:
    """Return the next occurrence of weekday (Mon=0..Sun=6) at 00:00, based on UTC.

    If base is already the desired weekday, returns that day at 00:00.
    """
    base = base.replace(hour=0, minute=0, second=0, microsecond=0)
    delta = (weekday - base.weekday()) % 7
    return base + _dt.timedelta(days=delta)


def _prev_weekday(base: _dt.datetime, weekday: int) -> _dt.datetime:
    base = base.replace(hour=0, minute=0, second=0, microsecond=0)
    delta = (base.weekday() - weekday) % 7
    return base - _dt.timedelta(days=delta)


def compute_week_windows(now_utc: _dt.datetime | None = None) -> Tuple[Tuple[_dt.datetime, _dt.datetime], Tuple[_dt.datetime, _dt.datetime]]:
    """Compute [Thu 00:00 -> Mon 23:59:59] windows.

    Rule: "This weekend" covers the current Thu->Mon cycle until Tuesday; on Tuesday it flips to the
    very next Thu->Mon.
    """
    if now_utc is None:
        now_utc = _dt.datetime.utcnow()

    # Identify the last and next Thursday anchors
    prev_thu = _prev_weekday(now_utc, 3)
    next_thu = _next_weekday(now_utc, 3)
    prev_mon_end = prev_thu + _dt.timedelta(days=4, hours=23, minutes=59, seconds=59)

    # If we are still within (or before end of) the current Thu->Mon window, use that as "this"
    # Otherwise (Tue and onward past Monday end), advance to the next Thu->Mon
    if now_utc <= prev_mon_end:
        this_thu = prev_thu
    else:
        this_thu = next_thu

    this_mon_end = this_thu + _dt.timedelta(days=4, hours=23, minutes=59, seconds=59)
    next_thu2 = this_thu + _dt.timedelta(days=7)
    next_mon_end = next_thu2 + _dt.timedelta(days=4, hours=23, minutes=59, seconds=59)

    return (this_thu, this_mon_end), (next_thu2, next_mon_end)


def in_window(ts_iso_utc: str, window: Tuple[_dt.datetime, _dt.datetime]) -> bool:
    """Check if an ISO timestamp (with trailing Z) falls inside [start,end] inclusive.

    TheOddsAPI returns e.g. '2025-09-07T17:00:00Z'.
    """
    start, end = window
    try:
        dt = _dt.datetime.strptime(ts_iso_utc, "%Y-%m-%dT%H:%M:%SZ")
    except Exception:
        # Best effort parse for variants (strip Z or microseconds)
        ts = ts_iso_utc.rstrip("Z")
        dt = _dt.datetime.fromisoformat(ts)
    return start <= dt <= end
