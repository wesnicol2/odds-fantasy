from __future__ import annotations

from typing import Dict, List

import sleeper_api
from config import SLEEPER_TO_ODDSAPI_TEAM, SLEEPER_ODDS_API_PLAYER_NAME_MAPPING
from .planner import PlannedGame
from .weekly_windows import compute_week_windows, in_window
from . import odds_client

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


def _all_active_players_by_team() -> Dict[str, List[dict]]:
    """Sleeper's full player DB, filtered to skill positions and grouped by
    Odds-API-style full team name. Unlike planner.py, this is NOT scoped to
    any single roster -- that's the entire point of draft prep.

    A player is included if Sleeper currently has them assigned to an NFL
    team (Sleeper clears `team` for free agents/retired players). This will
    include bench/practice-squad depth along with starters, which is fine --
    a draft board is supposed to be broad.
    """
    all_players = sleeper_api.get_players()
    by_team: Dict[str, List[dict]] = {}
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
        by_team.setdefault(full_team, []).append({
            "full_name": full_name,
            "alias": alias,
            "primary_position": pos,
            "editorial_team_full_name": full_team,
        })
    return by_team


def plan_week_for_draft(week: str = "this", regions: str = "us", cache_mode: str = "auto") -> Dict[str, PlannedGame]:
    """Like planner.plan_relevant_games_and_markets, but for every active
    skill player on every team playing in the target week -- not just one
    roster. Returns game_id -> PlannedGame for the requested window only.
    """
    (this_start, this_end), (next_start, next_end) = compute_week_windows()
    start, end = (this_start, this_end) if week == "this" else (next_start, next_end)

    events = odds_client.get_nfl_events(regions=regions, mode=cache_mode)
    by_team = _all_active_players_by_team()

    plan: Dict[str, PlannedGame] = {}
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
