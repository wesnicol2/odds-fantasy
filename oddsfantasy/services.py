"""Application services for the projection report, defenses, and best lineup."""

from __future__ import annotations

import datetime as dt
import os
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

from . import odds_client, ratelimit, sleeper_api
from .aggregator import aggregate_by_week
from .config import (
    SLEEPER_ODDS_API_PLAYER_NAME_MAPPING,
    SLEEPER_TO_ODDSAPI_TEAM,
)
from .defense import defense_fantasy_range, opponent_implied_total
from .lineup import build_best_lineup
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
        "roster_positions": league.get("roster_positions") or [],
        "teams": teams,
    }


def _resolve_roster_positions(username: str, season: str, league_id: str | None) -> list[str]:
    try:
        if league_id:
            league = sleeper_api.get_league(league_id)
        else:
            resolved_league_id, _ = sleeper_api.get_league_id_for_user(username, season)
            league = sleeper_api.get_league(resolved_league_id) if resolved_league_id else {}
        return list((league or {}).get("roster_positions") or [])
    except Exception as exc:
        print(f"[services] roster positions lookup failed: {exc}")
        return []


def _fetch_odds(
    planned_games: dict[str, object], cache_mode: str, regions: str = "us"
) -> dict[str, object]:
    """Fetch each planned player-prop game once, concurrently."""
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
    """Load and cache the normalized source data shared by report and drill-down."""
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
            "roster_positions": roster.get("roster_positions", []),
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
        "roster_positions": roster.get("roster_positions", []),
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
    """Return the roster report: floor, mid, ceiling and actual FP curve."""
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
        "roster_positions": context.get("roster_positions") or [],
        "ratelimit": ratelimit.format_status(),
        "ratelimit_info": ratelimit.get_details(),
    }
    if context.get("message"):
        payload["message"] = context["message"]
    return payload


def _defense_ownership_map(
    username: str,
    season: str,
    league_id: str | None,
    roster_id: int | None,
) -> tuple[dict[str, dict], str | None]:
    """Map NFL team full name to its fantasy owner and identify the selected roster owner."""
    try:
        selected_owner = None
        if league_id:
            resolved_league_id = league_id
        else:
            resolved_league_id, selected_owner = sleeper_api.get_league_id_for_user(username, season)
        if not resolved_league_id:
            return {}, selected_owner

        rosters = sleeper_api.get_league_rosters(resolved_league_id) or []
        users = sleeper_api.get_league_users(resolved_league_id) or []
        display_by_owner = {
            user.get("user_id"): (user.get("display_name") or user.get("username") or user.get("user_id"))
            for user in users
        }
        if roster_id is not None:
            selected = next(
                (row for row in rosters if str(row.get("roster_id")) == str(roster_id)),
                None,
            )
            selected_owner = selected.get("owner_id") if selected else None

        players = sleeper_api.get_players()
        team_to_owner: dict[str, dict] = {}
        for roster in rosters:
            owner_id = roster.get("owner_id")
            fantasy_team = (
                (roster.get("metadata") or {}).get("team_name")
                or display_by_owner.get(owner_id)
                or f"Team {roster.get('roster_id')}"
            )
            for player_id in roster.get("players", []) or []:
                player = players.get(player_id) or {}
                if player.get("position") != "DEF":
                    continue
                team = SLEEPER_TO_ODDSAPI_TEAM.get(player.get("team"))
                if team:
                    team_to_owner[team] = {"id": owner_id, "name": fantasy_team}
        return team_to_owner, selected_owner
    except Exception as exc:
        print(f"[services] defense ownership lookup failed: {exc}")
        return {}, None


def _fetch_game_lines(events: list[dict], cache_mode: str, region: str) -> dict[str, object]:
    """Fetch spreads + totals once per game, concurrently."""
    if not events:
        return {}

    def task(event: dict):
        game_id = event["id"]
        data = odds_client.get_event_player_odds(
            event_id=game_id,
            markets="spreads,totals",
            regions=region,
            mode=cache_mode,
        )
        return game_id, data

    output: dict[str, object] = {}
    with ThreadPoolExecutor(max_workers=min(8, len(events))) as executor:
        futures = [executor.submit(task, event) for event in events]
        for future in as_completed(futures):
            try:
                game_id, data = future.result()
                output[game_id] = data
            except Exception as exc:
                print(f"[services] defense odds fetch failed: {exc}")
    return output


def _parse_commence_time(value: str) -> dt.datetime | None:
    try:
        return dt.datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ")
    except (TypeError, ValueError):
        return None


def list_defenses(
    username: str,
    season: str,
    week: str = "this",
    fresh: bool = False,
    cache_mode: str = "auto",
    region: str = "us",
    league_id: str | None = None,
    roster_id: int | None = None,
) -> dict:
    """All NFL defenses sorted by the opponent's median implied team total."""
    ttl = int(os.getenv("SERVICE_CACHE_TTL", "120"))
    cache = getattr(list_defenses, "_cache", {})
    key = (username, season, week, region, league_id, roster_id)
    now = time.time()
    if not fresh and key in cache:
        cached_at, payload = cache[key]
        if now - cached_at < ttl:
            return payload

    effective_mode = "fresh" if fresh else cache_mode
    events = odds_client.get_nfl_events(regions=region, mode=effective_mode)
    windows = resolve_week_windows(events)
    if windows is None:
        return {
            "week": week,
            "defenses": [],
            "message": NO_GAMES_SCHEDULED_MESSAGE,
            "ratelimit": ratelimit.format_status(),
            "ratelimit_info": ratelimit.get_details(),
        }

    (this_start, this_end), (next_start, next_end) = windows
    start, end = (this_start, this_end) if week == "this" else (next_start, next_end)
    window_events = []
    for event in events:
        commence = _parse_commence_time(event.get("commence_time"))
        if commence is not None and start <= commence <= end:
            window_events.append(event)

    game_lines = _fetch_game_lines(window_events, effective_mode, region)
    ownership, selected_owner = _defense_ownership_map(username, season, league_id, roster_id)
    try:
        scoring = _resolve_identity(username, season, league_id, roster_id).get("scoring_rules", {})
    except Exception:
        scoring = {}

    games_by_team: dict[str, dict] = {}
    for event in window_events:
        home = event.get("home_team")
        away = event.get("away_team")
        if home and away:
            games_by_team[home] = {"event": event, "opponent": away}
            games_by_team[away] = {"event": event, "opponent": home}

    abbreviations = {full: abbr for abbr, full in SLEEPER_TO_ODDSAPI_TEAM.items()}
    rows: list[dict] = []
    for team in SLEEPER_TO_ODDSAPI_TEAM.values():
        owner = ownership.get(team)
        game = games_by_team.get(team)
        implied = None
        book_count = 0
        opponent = "BYE"
        game_date = None
        floor = mid = ceiling = None
        if game:
            opponent = game["opponent"]
            event = game["event"]
            game_date = event.get("commence_time")
            implied, book_count = opponent_implied_total(game_lines.get(event.get("id")), opponent)
            if implied is not None:
                floor, mid, ceiling = defense_fantasy_range(implied, scoring)

        rows.append(
            {
                "defense": team,
                "abbr": abbreviations.get(team),
                "opponent": opponent,
                "game_date": game_date,
                "implied_total": round(implied, 2) if implied is not None else None,
                "book_count": book_count,
                "taken": bool(owner),
                "owner": owner.get("name") if owner else None,
                "owned_by_current": bool(owner and owner.get("id") == selected_owner),
                "floor": round(floor, 2) if floor is not None else None,
                "mid": round(mid, 2) if mid is not None else None,
                "ceiling": round(ceiling, 2) if ceiling is not None else None,
            }
        )

    rows.sort(
        key=lambda row: (
            row["implied_total"] is None,
            row["implied_total"] if row["implied_total"] is not None else float("inf"),
            row["defense"],
        )
    )
    payload = {
        "week": week,
        "defenses": rows,
        "note": "DEF fantasy ranges use only the points-allowed component implied by spread/total markets.",
        "ratelimit": ratelimit.format_status(),
        "ratelimit_info": ratelimit.get_details(),
    }
    cache[key] = (now, payload)
    list_defenses._cache = cache
    return payload


def compute_best_lineup(
    username: str,
    season: str,
    week: str = "this",
    target: str = "mid",
    fresh: bool = False,
    cache_mode: str = "auto",
    region: str = "us",
    league_id: str | None = None,
    roster_id: int | None = None,
) -> dict:
    """Best modeled starting lineup for floor, mid, or ceiling."""
    projections = compute_projections(
        username=username,
        season=season,
        week=week,
        region=region,
        fresh=fresh,
        cache_mode=cache_mode,
        league_id=league_id,
        roster_id=roster_id,
    )
    defenses = list_defenses(
        username=username,
        season=season,
        week=week,
        region=region,
        fresh=fresh,
        cache_mode=cache_mode,
        league_id=league_id,
        roster_id=roster_id,
    )
    owned_defenses = [
        defense
        for defense in defenses.get("defenses", [])
        if defense.get("owned_by_current") and defense.get(target) is not None
    ]
    result = build_best_lineup(
        projections.get("players", []),
        target=target,
        roster_positions=_resolve_roster_positions(username, season, league_id) or None,
        defenses=owned_defenses,
    )
    result.update(
        {
            "week": week,
            "ratelimit": ratelimit.format_status(),
            "ratelimit_info": ratelimit.get_details(),
            "defense_note": defenses.get("note"),
        }
    )
    return result
