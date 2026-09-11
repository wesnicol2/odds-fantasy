"""Freeze already-started fantasy decisions while optimizing the rest of the week."""

from __future__ import annotations

import datetime as dt

from . import ratelimit, services, sleeper_api
from .lineup import DEFAULT_STARTERS, IGNORED_SLOTS, SLOT_ELIGIBILITY, build_best_lineup


def _parse_utc(value: str | None) -> dt.datetime | None:
    if not value:
        return None
    try:
        parsed = dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=dt.timezone.utc)
    return parsed.astimezone(dt.timezone.utc)


def _player_name(player_id: str, info: dict) -> str:
    position = str(info.get("primary_position") or "").upper()
    team = info.get("editorial_team_full_name")
    if position == "DEF" and team:
        return str(team)
    full_name = (info.get("name") or {}).get("full")
    return str(full_name or player_id)


def _actual_points(points: dict, player_id: str) -> float:
    value = points.get(player_id)
    if not isinstance(value, (int, float)):
        value = points.get(str(player_id))
    return float(value) if isinstance(value, (int, float)) else 0.0


def _game_start_by_team(planned: dict) -> dict[str, dt.datetime]:
    starts: dict[str, dt.datetime] = {}
    for game in (planned or {}).values():
        commence = _parse_utc(getattr(game, "commence_time", None))
        if commence is None:
            continue
        for team in (getattr(game, "home_team", None), getattr(game, "away_team", None)):
            if team:
                starts[str(team)] = commence
    return starts


def build_live_state(
    roster: dict,
    roster_positions: list[str],
    matchup: dict,
    planned: dict,
    now: dt.datetime | None = None,
) -> dict:
    """Translate Sleeper's submitted lineup into immutable started decisions.

    Game start is the lock boundary. We deliberately call the state ``locked``
    rather than ``live``/``final`` because the sources used here prove that a
    kickoff has passed, not whether the NFL game has officially ended.
    """
    current = now or dt.datetime.now(dt.timezone.utc)
    if current.tzinfo is None:
        current = current.replace(tzinfo=dt.timezone.utc)
    current = current.astimezone(dt.timezone.utc)

    roster_players = roster.get("players", {}) or {}
    starter_ids = [str(player_id) for player_id in (matchup.get("starters") or [])]
    starter_set = set(starter_ids)
    player_points = matchup.get("players_points") or {}
    starts_by_team = _game_start_by_team(planned)

    started_ids: set[str] = set()
    for raw_player_id, info in roster_players.items():
        player_id = str(raw_player_id)
        team = info.get("editorial_team_full_name")
        commence = starts_by_team.get(str(team)) if team else None
        if commence is not None and commence <= current:
            started_ids.add(player_id)

    submitted_slots = [
        str(raw or "").upper()
        for raw in (roster_positions or DEFAULT_STARTERS)
        if str(raw or "").upper() not in IGNORED_SLOTS
    ]
    locked_starters: list[dict] = []
    modeled_slot_index = 0
    for submitted_index, slot in enumerate(submitted_slots):
        if slot not in SLOT_ELIGIBILITY:
            continue
        current_modeled_index = modeled_slot_index
        modeled_slot_index += 1
        if submitted_index >= len(starter_ids):
            continue
        player_id = starter_ids[submitted_index]
        if player_id not in started_ids:
            continue
        info = roster_players.get(player_id) or roster_players.get(str(player_id)) or {}
        locked_starters.append(
            {
                "slot_index": current_modeled_index,
                "slot": slot,
                "player_id": player_id,
                "name": _player_name(player_id, info),
                "pos": str(info.get("primary_position") or "").upper() or None,
                "team": info.get("editorial_team_full_name"),
                "actual_points": _actual_points(player_points, player_id),
            }
        )

    started_rows: list[dict] = []
    for player_id in sorted(started_ids):
        info = roster_players.get(player_id) or {}
        started_rows.append(
            {
                "player_id": player_id,
                "name": _player_name(player_id, info),
                "pos": str(info.get("primary_position") or "").upper() or None,
                "team": info.get("editorial_team_full_name"),
                "actual_points": _actual_points(player_points, player_id),
                "lineup_status": "starter" if player_id in starter_set else "bench",
            }
        )

    locked_bench = [row for row in started_rows if row["lineup_status"] == "bench"]
    return {
        "locked_starters": locked_starters,
        "locked_bench": locked_bench,
        "started_players": started_rows,
        "unavailable_names": {row["name"] for row in started_rows},
    }


def _resolve_league_and_roster(
    username: str,
    season: str,
    league_id: str | None,
    roster_id: int | None,
) -> tuple[str | None, int | None]:
    if league_id and roster_id is not None:
        return league_id, roster_id
    if league_id:
        return league_id, None
    resolved_league_id, user_id = sleeper_api.get_league_id_for_user(username, season)
    if not resolved_league_id:
        return None, None
    rosters = sleeper_api.get_league_rosters(resolved_league_id) or []
    selected = next((row for row in rosters if row.get("owner_id") == user_id), None)
    selected_roster_id = selected.get("roster_id") if selected else None
    return resolved_league_id, selected_roster_id


def load_live_state(
    *,
    username: str,
    season: str,
    week: str,
    league_id: str | None,
    roster_id: int | None,
    context: dict,
    roster_positions: list[str],
) -> dict:
    """Best-effort current-week lock state; failure never blocks projections."""
    empty = {
        "locked_starters": [],
        "locked_bench": [],
        "started_players": [],
        "unavailable_names": set(),
    }
    if week != "this":
        return empty
    try:
        resolved_league_id, resolved_roster_id = _resolve_league_and_roster(
            username, season, league_id, roster_id
        )
        if not resolved_league_id or resolved_roster_id is None:
            return empty
        state = sleeper_api.get_nfl_state() or {}
        nfl_week = state.get("week")
        if not isinstance(nfl_week, int) or nfl_week < 1:
            return empty
        matchups = sleeper_api.get_league_matchups(resolved_league_id, nfl_week) or []
        matchup = next(
            (
                row
                for row in matchups
                if str(row.get("roster_id")) == str(resolved_roster_id)
            ),
            None,
        )
        if not matchup:
            return empty
        return build_live_state(
            context.get("roster") or {},
            roster_positions,
            matchup,
            context.get("planned") or {},
        )
    except Exception as exc:
        print(f"[live_lineup] live Sleeper state unavailable: {exc}")
        return empty


def compute_projections(**params) -> dict:
    """Normal projections plus actionability metadata for already-started players."""
    payload = services.compute_projections(**params)
    context = services._load_week_context(**params)
    roster_positions = (
        services._resolve_roster_positions(
            params.get("username", ""), params.get("season", ""), params.get("league_id")
        )
        or payload.get("roster_positions")
        or []
    )
    live = load_live_state(
        username=params.get("username", ""),
        season=params.get("season", ""),
        week=params.get("week", "this"),
        league_id=params.get("league_id"),
        roster_id=params.get("roster_id"),
        context=context,
        roster_positions=roster_positions,
    )
    by_name = {row["name"]: row for row in live["started_players"]}
    players = []
    for player in payload.get("players", []):
        state = by_name.get(player.get("name"))
        players.append(
            {
                **player,
                "locked": state is not None,
                "lineup_status": state.get("lineup_status") if state else None,
                "actual_points": state.get("actual_points") if state else None,
            }
        )
    result = dict(payload)
    result["players"] = players
    result["started_count"] = len(live["started_players"])
    return result


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
    """Best remaining lineup after freezing every submitted slot whose game began."""
    common = {
        "username": username,
        "season": season,
        "week": week,
        "region": region,
        "fresh": fresh,
        "cache_mode": cache_mode,
        "league_id": league_id,
        "roster_id": roster_id,
    }
    projections = services.compute_projections(**common)
    defenses = services.list_defenses(**common)
    roster_positions = services._resolve_roster_positions(username, season, league_id) or None
    context = services._load_week_context(**common)
    live = load_live_state(
        username=username,
        season=season,
        week=week,
        league_id=league_id,
        roster_id=roster_id,
        context=context,
        roster_positions=roster_positions or [],
    )
    owned_defenses = [
        defense
        for defense in defenses.get("defenses", [])
        if defense.get("owned_by_current") and defense.get(target) is not None
    ]
    result = build_best_lineup(
        projections.get("players", []),
        target=target,
        roster_positions=roster_positions,
        defenses=owned_defenses,
        locked_starters=live["locked_starters"],
        unavailable_names=set(live["unavailable_names"]),
    )
    result.update(
        {
            "week": week,
            "locked_bench": live["locked_bench"],
            "ratelimit": ratelimit.format_status(),
            "ratelimit_info": ratelimit.get_details(),
            "defense_note": defenses.get("note"),
        }
    )
    return result
