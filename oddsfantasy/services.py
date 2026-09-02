"""Application services for the roster projection report.

The product has one expensive data path: resolve the Sleeper roster, find its
scheduled games, fetch the needed player props, and normalize them. That week
context is cached in-process and shared by the report and player drill-down, so
opening details never repeats the same Odds API work.
"""

from __future__ import annotations

import os
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

from . import odds_client, ratelimit, sleeper_api
from .aggregator import aggregate_by_week
from .config import SLEEPER_ODDS_API_PLAYER_NAME_MAPPING
from .planner import plan_relevant_games_and_markets
from .projection import project_player, survival_curve
from .weekly_windows import resolve_week_windows

SUPPORTED_POSITIONS = {"QB", "RB", "WR", "TE"}
NO_GAMES_SCHEDULED_MESSAGE = (
    "No scheduled games found yet for this week. Check back once the season's "
    "schedule/odds are posted."
)


def _resolve_identity(
    username: str,
    season: str,
    league_id: str | None = None,
    roster_id: int | None = None,
) -> dict:
    if league_id:
        return sleeper_api.get_league_roster_data(league_id, roster_id=roster_id)
    return sleeper_api.get_user_sleeper_data(username, season) or {}


def resolve_user_leagues(username: str, season: str) -> dict:
    try:
        user_id = sleeper_api.get_user_id(username)
    except Exception as exc:
        print(f"[services] resolve_user_leagues failed for {username}: {exc}")
        return {"error": "user_not_found", "username": username}
    try:
        leagues = sleeper_api.get_user_leagues(user_id, season)
    except Exception as exc:
        print(f"[services] league lookup failed for {user_id}: {exc}")
        leagues = []
    return {
        "username": username,
        "user_id": user_id,
        "season": season,
        "leagues": [
            {
                "league_id": league.get("league_id"),
                "name": league.get("name"),
                "status": league.get("status"),
                "season": league.get("season"),
            }
            for league in leagues or []
        ],
    }


def resolve_league(league_id: str) -> dict:
    try:
        league = sleeper_api.get_league(league_id)
    except Exception as exc:
        print(f"[services] league lookup failed for {league_id}: {exc}")
        return {"error": "league_not_found", "league_id": league_id}
    try:
        teams = sleeper_api.get_league_teams(league_id)
    except Exception as exc:
        print(f"[services] team lookup failed for {league_id}: {exc}")
        teams = []
    return {
        "league_id": league_id,
        "name": league.get("name"),
        "season": league.get("season"),
        "status": league.get("status"),
        "teams": teams,
    }


def _fetch_odds(
    planned_games: dict[str, object], cache_mode: str, regions: str = "us"
) -> dict[str, object]:
    """Fetch each planned game once, concurrently."""
    if not planned_games:
        return {}

    def task(item):
        game_id, game = item
        markets = ",".join(sorted(set(game.markets)))
        data = odds_client.get_event_player_odds(
            event_id=game_id,
            markets=markets,
            regions=regions,
            mode=cache_mode,
        )
        return game_id, data

    output: dict[str, object] = {}
    workers = min(8, len(planned_games))
    with ThreadPoolExecutor(max_workers=max(1, workers)) as executor:
        futures = [executor.submit(task, item) for item in planned_games.items()]
        for future in as_completed(futures):
            try:
                game_id, data = future.result()
                output[game_id] = data
            except Exception as exc:
                print(f"[services] odds fetch failed: {exc}")
    return output


def _context_cache() -> dict:
    cache = getattr(_load_week_context, "_cache", None)
    if cache is None:
        cache = {}
        _load_week_context._cache = cache
    return cache


def _load_week_context(
    username: str,
    season: str,
    week: str = "this",
    region: str = "us",
    fresh: bool = False,
    cache_mode: str = "auto",
    league_id: str | None = None,
    roster_id: int | None = None,
) -> dict:
    """Load and cache the normalized source data shared by all report views."""
    ttl = int(os.getenv("SERVICE_CACHE_TTL", "120"))
    key = (username, season, week, region, league_id, roster_id)
    now = time.time()
    cache = _context_cache()
    if not fresh and key in cache:
        cached_at, context = cache[key]
        if now - cached_at < ttl:
            return context

    try:
        roster = _resolve_identity(username, season, league_id, roster_id)
    except Exception as exc:
        print(f"[services] Sleeper lookup failed: {exc}")
        return {
            "error": "sleeper_timeout",
            "roster": {},
            "players_odds": {},
            "planned": {},
        }
    if not roster:
        return {"roster": {}, "players_odds": {}, "planned": {}}

    effective_mode = "fresh" if fresh else cache_mode
    events = odds_client.get_nfl_events(regions=region, mode=effective_mode)
    windows = resolve_week_windows(events)
    if windows is None:
        context = {
            "roster": roster,
            "scoring_rules": roster.get("scoring_rules", {}),
            "players_odds": {},
            "planned": {},
            "message": NO_GAMES_SCHEDULED_MESSAGE,
        }
        cache[key] = (now, context)
        return context

    planned_all = plan_relevant_games_and_markets(
        roster,
        windows,
        regions=region,
        cache_mode=effective_mode,
        events=events,
    )
    planned = planned_all.get(week, {})
    event_odds = _fetch_odds(planned, cache_mode=effective_mode, regions=region)
    players_odds = aggregate_by_week(event_odds, planned)

    info_by_alias: dict[str, dict] = {}
    for game in planned.values():
        for player in game.players:
            info_by_alias[player["alias"]] = player

    context = {
        "roster": roster,
        "scoring_rules": roster.get("scoring_rules", {}),
        "players_odds": players_odds,
        "planned": planned,
        "info_by_alias": info_by_alias,
    }
    cache[key] = (now, context)
    return context


def _roster_skill_players(roster: dict) -> list[dict]:
    rows: list[dict] = []
    for player in (roster.get("players", {}) or {}).values():
        name = (player.get("name", {}) or {}).get("full")
        pos = (player.get("primary_position") or "").upper()
        if not name or pos not in SUPPORTED_POSITIONS:
            continue
        rows.append(
            {
                "name": name,
                "alias": SLEEPER_ODDS_API_PLAYER_NAME_MAPPING.get(name, name),
                "pos": pos,
                "team": player.get("editorial_team_full_name"),
            }
        )
    return rows


def compute_projections(
    username: str,
    season: str,
    week: str = "this",
    region: str = "us",
    fresh: bool = False,
    cache_mode: str = "auto",
    league_id: str | None = None,
    roster_id: int | None = None,
) -> dict:
    """Return the one roster report: floor, mid, ceiling and actual FP curve."""
    context = _load_week_context(
        username=username,
        season=season,
        week=week,
        region=region,
        fresh=fresh,
        cache_mode=cache_mode,
        league_id=league_id,
        roster_id=roster_id,
    )
    if context.get("error"):
        return {
            "week": week,
            "players": [],
            "error": context["error"],
            "ratelimit": ratelimit.format_status(),
            "ratelimit_info": ratelimit.get_details(),
        }

    roster = context.get("roster") or {}
    scoring_rules = context.get("scoring_rules") or {}
    players_odds = context.get("players_odds") or {}
    rows: list[dict] = []

    for player in _roster_skill_players(roster):
        by_book = players_odds.get(player["alias"], {})
        projection = project_player(by_book, scoring_rules) if by_book else None
        has_projection = bool(projection and projection.has_projection)
        rows.append(
            {
                **player,
                "floor": round(projection.floor, 2) if has_projection else None,
                "mid": round(projection.mid, 2) if has_projection else None,
                "ceiling": round(projection.ceiling, 2) if has_projection else None,
                "mean": round(projection.mean, 2) if has_projection else None,
                "curve": survival_curve(projection.samples) if has_projection else [],
                "books_used": len(by_book),
                "markets_used": len(projection.stats) if has_projection else 0,
                "has_projection": has_projection,
            }
        )

    rows.sort(
        key=lambda row: row["mid"] if isinstance(row.get("mid"), (int, float)) else float("-inf"),
        reverse=True,
    )
    payload = {
        "week": week,
        "players": rows,
        "ratelimit": ratelimit.format_status(),
        "ratelimit_info": ratelimit.get_details(),
    }
    if context.get("message"):
        payload["message"] = context["message"]
    return payload
