from __future__ import annotations

import datetime as _dt

from . import odds_client, sleeper_api
from .config import SLEEPER_ODDS_API_PLAYER_NAME_MAPPING, SLEEPER_TO_ODDSAPI_TEAM
from .planner import PlannedGame
from .weekly_windows import earliest_future_week_start, in_window

# Draft prep only covers positions the rest of the app already knows how to
# turn into fantasy points (see PRIMARY_MARKET_WHITELIST in range_model.py).
# Kickers/DEF aren't included here for the same reason they're excluded from
# build_lineup: no player-level market signal for K, and DEF value doesn't
# come from a per-player prop line at all (see list_defenses instead).
DRAFT_POSITIONS = ("QB", "RB", "WR", "TE")

# Conservative market set (no "_alternate" markets) to keep a draft-board
# refresh from ballooning into dozens of extra Odds API requests per game --
# see CONTRIBUTING.md's "Odds API quota awareness" section. The lognormal/
# Poisson single-line fallback in range_model.py makes a single main line a
# reasonable basis for floor/mid/ceiling, so this is a real cost/accuracy
# tradeoff, not just a shortcut.
CORE_DRAFT_MARKETS = (
    "player_anytime_td",
    "player_receptions",
    "player_reception_yds",
    "player_rush_yds",
    "player_pass_yds",
    "player_pass_tds",
    "player_pass_interceptions",
)


def _all_active_players_by_team() -> dict[str, list[dict]]:
    """Sleeper's full player DB, filtered to skill positions and grouped by
    Odds-API-style full team name. Unlike planner.py, this is NOT scoped to
    any single roster -- that's the entire point of draft prep.

    A player is included if Sleeper currently has them assigned to an NFL
    team (Sleeper clears `team` for free agents/retired players). This will
    include bench/practice-squad depth along with starters, which is fine --
    a draft board is supposed to be broad.
    """
    all_players = sleeper_api.get_players()
    by_team: dict[str, list[dict]] = {}
    for pdata in all_players.values():
        pos = pdata.get("position")
        if pos not in DRAFT_POSITIONS:
            continue
        team_abbr = pdata.get("team")
        if not team_abbr:
            continue
        full_team = SLEEPER_TO_ODDSAPI_TEAM.get(team_abbr)
        if not full_team:
            continue
        full_name = pdata.get("full_name")
        if not full_name:
            continue
        alias = SLEEPER_ODDS_API_PLAYER_NAME_MAPPING.get(full_name, full_name)
        by_team.setdefault(full_team, []).append(
            {
                "full_name": full_name,
                "alias": alias,
                "primary_position": pos,
                "editorial_team_full_name": full_team,
            }
        )
    return by_team


def _resolve_draft_week_window(
    events: list[dict],
    which: str = "this",
    now_utc: _dt.datetime | None = None,
) -> tuple[_dt.datetime, _dt.datetime] | None:
    """Resolve "Week 1" / "Week 2" for draft purposes.

    Unlike the in-season lineup flow (weekly_windows.compute_week_windows,
    anchored to "today"), a draft happens once, before the season starts --
    "today" isn't a meaningful anchor. What matters is the earliest week with
    any scheduled/priced games at all ("Week 1"), and the week after that
    ("Week 2"), no matter how far today is from kickoff. Anchoring to "today"
    instead (the original implementation) meant this silently returned
    nothing whenever today's nearest Thu-Mon cycle didn't happen to contain
    real games yet -- which is most of the pre-season.

    Returns None if there are no upcoming games in `events` at all (e.g. the
    new season's schedule/odds aren't posted yet) -- there's no "Week 1" to
    anchor to in that case.
    """
    now_utc = now_utc or _dt.datetime.utcnow()
    week1_start = earliest_future_week_start(events, now_utc)
    if week1_start is None:
        return None

    week_start = week1_start if which == "this" else week1_start + _dt.timedelta(days=7)
    week_end = week_start + _dt.timedelta(days=4, hours=23, minutes=59, seconds=59)
    return week_start, week_end


def plan_week_for_draft(
    week: str = "this", regions: str = "us", cache_mode: str = "auto"
) -> dict[str, PlannedGame]:
    """Like planner.plan_relevant_games_and_markets, but for every active
    skill player on every team playing in the target week -- not just one
    roster. Returns game_id -> PlannedGame for the requested window only.

    `week="this"` means "Week 1" (the earliest week with scheduled games)
    and `week="next"` means "Week 2" -- see _resolve_draft_week_window.
    """
    events = odds_client.get_nfl_events(regions=regions, mode=cache_mode)
    window = _resolve_draft_week_window(events, which=week)
    if window is None:
        return {}
    start, end = window

    by_team = _all_active_players_by_team()

    plan: dict[str, PlannedGame] = {}
    for e in events:
        ts = e.get("commence_time")
        if not ts or not in_window(ts, (start, end)):
            continue
        home, away = e.get("home_team"), e.get("away_team")
        players = list(by_team.get(home, [])) + list(by_team.get(away, []))
        if not players:
            continue
        plan[e["id"]] = PlannedGame(
            game_id=e["id"],
            home_team=home,
            away_team=away,
            commence_time=ts,
            players=players,
            markets=list(CORE_DRAFT_MARKETS),
        )
    return plan
