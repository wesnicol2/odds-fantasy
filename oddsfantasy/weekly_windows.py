import datetime as _dt
from zoneinfo import ZoneInfo

_NFL_TZ = ZoneInfo("America/New_York")
_UTC = _dt.UTC


def _as_utc_aware(value: _dt.datetime) -> _dt.datetime:
    """Interpret naive inputs as UTC and normalize aware inputs to UTC."""
    if value.tzinfo is None:
        return value.replace(tzinfo=_UTC)
    return value.astimezone(_UTC)


def _to_utc_naive(value: _dt.datetime) -> _dt.datetime:
    """Return a UTC timestamp in the repo's historical naive-datetime shape."""
    return value.astimezone(_UTC).replace(tzinfo=None)


def _next_weekday(base: _dt.datetime, weekday: int) -> _dt.datetime:
    """Return the next occurrence of weekday (Mon=0..Sun=6) at local midnight.

    If base is already the desired weekday, returns that day at 00:00 while
    preserving the datetime's timezone information.
    """
    base = base.replace(hour=0, minute=0, second=0, microsecond=0)
    delta = (weekday - base.weekday()) % 7
    return base + _dt.timedelta(days=delta)


def _prev_weekday(base: _dt.datetime, weekday: int) -> _dt.datetime:
    base = base.replace(hour=0, minute=0, second=0, microsecond=0)
    delta = (base.weekday() - weekday) % 7
    return base - _dt.timedelta(days=delta)


def _window_from_eastern_thursday(
    thursday: _dt.datetime,
) -> tuple[_dt.datetime, _dt.datetime]:
    """Convert Thu 00:00 -> Mon 23:59:59 Eastern into naive UTC bounds."""
    thursday = thursday.astimezone(_NFL_TZ).replace(
        hour=0, minute=0, second=0, microsecond=0
    )
    monday_end = (thursday + _dt.timedelta(days=4)).replace(hour=23, minute=59, second=59)
    return _to_utc_naive(thursday), _to_utc_naive(monday_end)


def compute_week_windows(
    now_utc: _dt.datetime | None = None,
) -> tuple[tuple[_dt.datetime, _dt.datetime], tuple[_dt.datetime, _dt.datetime]]:
    """Compute NFL Thu->Mon windows using U.S. Eastern calendar days.

    Odds API kickoff timestamps are UTC, but NFL Monday-night games can begin
    after 00:00 UTC on Tuesday. Defining the fantasy week with UTC calendar
    days therefore drops late Monday games. The canonical week is Thursday
    00:00 through Monday 23:59:59 in America/New_York, converted back to the
    naive UTC timestamps used by the rest of this module.
    """
    now = _as_utc_aware(now_utc or _dt.datetime.now(_UTC))
    now_eastern = now.astimezone(_NFL_TZ)

    prev_thu = _prev_weekday(now_eastern, 3)
    next_thu = _next_weekday(now_eastern, 3)
    prev_mon_end = (prev_thu + _dt.timedelta(days=4)).replace(
        hour=23, minute=59, second=59
    )

    this_thu = prev_thu if now_eastern <= prev_mon_end else next_thu
    next_thu2 = this_thu + _dt.timedelta(days=7)

    return (
        _window_from_eastern_thursday(this_thu),
        _window_from_eastern_thursday(next_thu2),
    )


def in_window(ts_iso_utc: str, window: tuple[_dt.datetime, _dt.datetime]) -> bool:
    """Check if an ISO UTC timestamp falls inside [start, end] inclusive."""
    start, end = window
    try:
        parsed = _dt.datetime.strptime(ts_iso_utc, "%Y-%m-%dT%H:%M:%SZ")
    except Exception:
        ts = ts_iso_utc.rstrip("Z")
        parsed = _dt.datetime.fromisoformat(ts)
        if parsed.tzinfo is not None:
            parsed = _to_utc_naive(parsed)
    return start <= parsed <= end


def earliest_future_week_start(
    events: list[dict], now_utc: _dt.datetime | None = None
) -> _dt.datetime | None:
    """UTC timestamp for Thursday 00:00 Eastern of the next scheduled NFL week."""
    now = _to_utc_naive(_as_utc_aware(now_utc or _dt.datetime.now(_UTC)))
    future_starts: list[_dt.datetime] = []
    for event in events:
        ts = event.get("commence_time")
        if not ts:
            continue
        try:
            kickoff = _dt.datetime.strptime(ts, "%Y-%m-%dT%H:%M:%SZ")
        except Exception:
            continue
        if kickoff > now:
            future_starts.append(kickoff)
    if not future_starts:
        return None

    earliest_utc = min(future_starts).replace(tzinfo=_UTC)
    earliest_eastern = earliest_utc.astimezone(_NFL_TZ)
    week_thursday = _prev_weekday(earliest_eastern, 3)
    return _to_utc_naive(week_thursday)


def resolve_week_windows(
    events: list[dict], now_utc: _dt.datetime | None = None
) -> tuple[tuple[_dt.datetime, _dt.datetime], tuple[_dt.datetime, _dt.datetime]] | None:
    """Use the Eastern-time calendar week, falling forward to the next real slate."""
    now_utc = now_utc or _dt.datetime.now(_UTC)
    calendar_this, calendar_next = compute_week_windows(now_utc)
    if any(
        event.get("commence_time") and in_window(event["commence_time"], calendar_this)
        for event in events
    ):
        return calendar_this, calendar_next

    week1_start = earliest_future_week_start(events, now_utc)
    if week1_start is None:
        return None

    week1_eastern = week1_start.replace(tzinfo=_UTC).astimezone(_NFL_TZ)
    next_week_eastern = week1_eastern + _dt.timedelta(days=7)
    return (
        _window_from_eastern_thursday(week1_eastern),
        _window_from_eastern_thursday(next_week_eastern),
    )
