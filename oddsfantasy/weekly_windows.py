import datetime as _dt


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


def compute_week_windows(
    now_utc: _dt.datetime | None = None,
) -> tuple[tuple[_dt.datetime, _dt.datetime], tuple[_dt.datetime, _dt.datetime]]:
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
    this_thu = prev_thu if now_utc <= prev_mon_end else next_thu

    this_mon_end = this_thu + _dt.timedelta(days=4, hours=23, minutes=59, seconds=59)
    next_thu2 = this_thu + _dt.timedelta(days=7)
    next_mon_end = next_thu2 + _dt.timedelta(days=4, hours=23, minutes=59, seconds=59)

    return (this_thu, this_mon_end), (next_thu2, next_mon_end)


def in_window(ts_iso_utc: str, window: tuple[_dt.datetime, _dt.datetime]) -> bool:
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


def earliest_future_week_start(
    events: list[dict], now_utc: _dt.datetime | None = None
) -> _dt.datetime | None:
    """Thursday anchoring the earliest not-yet-started game in `events`, or
    None if there are no games left to play (e.g. schedule/odds not posted
    yet). Shared by draft_prep's "Week 1" anchoring and
    resolve_week_windows' pre-season fallback below -- both need "the week
    of the soonest real game," just for different reasons.
    """
    now_utc = now_utc or _dt.datetime.utcnow()
    future_starts: list[_dt.datetime] = []
    for e in events:
        ts = e.get("commence_time")
        if not ts:
            continue
        try:
            d = _dt.datetime.strptime(ts, "%Y-%m-%dT%H:%M:%SZ")
        except Exception:
            continue
        if d > now_utc:
            future_starts.append(d)
    if not future_starts:
        return None
    return _prev_weekday(min(future_starts), 3)


def resolve_week_windows(
    events: list[dict], now_utc: _dt.datetime | None = None
) -> tuple[tuple[_dt.datetime, _dt.datetime], tuple[_dt.datetime, _dt.datetime]] | None:
    """Like compute_week_windows, but falls forward to the schedule when
    today's calendar-anchored "this" window has no real games in it.

    compute_week_windows() alone is right for the normal in-season case (you
    want the slate relative to today), but during the pre-season gap between
    today and the season opener, today's nearest Thu-Mon cycle has no games
    at all -- the Odds API only lists regular-season games -- so the plain
    calendar window silently comes back empty. When that happens, fall
    forward to the week of the earliest scheduled game instead (same idea as
    draft_prep._resolve_draft_week_window, which anchors unconditionally
    since a draft only ever happens pre-season).

    Returns None if there are no games in `events` at all -- there's nothing
    to fall forward to.
    """
    now_utc = now_utc or _dt.datetime.utcnow()
    calendar_this, calendar_next = compute_week_windows(now_utc)
    if any(e.get("commence_time") and in_window(e["commence_time"], calendar_this) for e in events):
        return calendar_this, calendar_next

    week1_start = earliest_future_week_start(events, now_utc)
    if week1_start is None:
        return None
    this_end = week1_start + _dt.timedelta(days=4, hours=23, minutes=59, seconds=59)
    next_start = week1_start + _dt.timedelta(days=7)
    next_end = next_start + _dt.timedelta(days=4, hours=23, minutes=59, seconds=59)
    return (week1_start, this_end), (next_start, next_end)
