"""Live-week roster state for freezing fantasy decisions that are no longer legal."""

from __future__ import annotations

from . import sleeper_api
from .config import SLEEPER_TO_ODDSAPI_TEAM

IGNORED_ROSTER_SLOTS = {"BN", "IR", "TAXI"}
LIVE_GAME_STATUSES = {"in_progress", "inprogress", "live", "halftime"}
FINAL_GAME_STATUSES = {"final", "complete", "completed", "post_game", "postgame"}


def normalize_game_status(value: object) -> str:
    """Collapse provider game states into the only states lineup decisions need."""
    raw = str(value or "").strip().lower().replace("-", "_").replace(" ", "_")
    if raw in LIVE_GAME_STATUSES:
        return "live"
    if raw in FINAL_GAME_STATUSES:
        return "final"
    # Unknown states are intentionally treated as actionable. A false unlock is
    # visible and short-lived; a false lock could tell the user a legal move is impossible.
    return "upcoming"


def _submitted_slots(roster_positions: list[str] | None) -> list[str]:
    """Sleeper's starters array follows roster_positions with bench-like slots removed."""
    return [
        str(slot or "").upper()
        for slot in (roster_positions or [])
        if str(slot or "").upper() not in IGNORED_ROSTER_SLOTS
    ]


def _player_context(player_id: str, players: dict) -> dict:
    data = players.get(player_id) or {}
    team_abbr = data.get("team")
    position = str(data.get("position") or "").upper()
    full_team = SLEEPER_TO_ODDSAPI_TEAM.get(team_abbr)

    # Sleeper uses team abbreviations as DEF player IDs. Keep a useful row even
    # if that team entry is missing from the player metadata cache.
    if not team_abbr and player_id in SLEEPER_TO_ODDSAPI_TEAM:
        team_abbr = player_id
        full_team = SLEEPER_TO_ODDSAPI_TEAM[player_id]
        position = "DEF"

    name = data.get("full_name") or data.get("name")
    if position == "DEF" and full_team:
        name = full_team
    return {
        "player_id": player_id,
        "name": name or player_id,
        "pos": position or ("DEF" if full_team and player_id == team_abbr else ""),
        "team": full_team,
        "team_abbr": team_abbr,
    }


def _empty_state() -> dict:
    return {
        "locked_assignments": [],
        "unavailable_player_ids": [],
        "week": None,
        "season": None,
    }


def current_lineup_lock_state(
    league_id: str | None,
    roster_id: int | None,
    season: str,
    roster_positions: list[str] | None,
) -> dict:
    """Return submitted starters that are locked plus every already-started roster player.

    Locking is based on NFL game state, never fantasy points: a player can be
    correctly locked at 0.0. The submitted starter index is carried through so
    FLEX and other multi-position slots are frozen exactly where the user put them.
    """
    if not league_id or roster_id is None:
        return _empty_state()

    try:
        nfl_state = sleeper_api.get_nfl_state() or {}
        current_week = int(nfl_state.get("leg") or nfl_state.get("week") or 0)
        current_season = str(nfl_state.get("season") or season)
        if current_week <= 0 or (season and current_season != str(season)):
            return _empty_state()

        matchup_rows = sleeper_api.get_league_matchups(league_id, current_week) or []
        matchup = next(
            (row for row in matchup_rows if str(row.get("roster_id")) == str(roster_id)),
            None,
        )
        if not matchup:
            return _empty_state()

        season_type = str(nfl_state.get("season_type") or "regular").lower()
        if season_type not in {"regular", "post", "pre", "off"}:
            season_type = "regular"
        schedule = sleeper_api.get_nfl_schedule(current_season, season_type) or []
        statuses_by_team: dict[str, str] = {}
        for game in schedule:
            try:
                game_week = int(game.get("week") or 0)
            except (TypeError, ValueError):
                continue
            if game_week != current_week:
                continue
            status = normalize_game_status(game.get("status"))
            for team in (game.get("home"), game.get("away")):
                if team:
                    statuses_by_team[str(team)] = status

        players = sleeper_api.get_players()

        def context_for(raw_player_id: object) -> dict:
            return _player_context(str(raw_player_id), players)

        def status_for(raw_player_id: object) -> str:
            context = context_for(raw_player_id)
            team_abbr = context.get("team_abbr")
            return statuses_by_team.get(str(team_abbr), "upcoming") if team_abbr else "upcoming"

        matchup_players = [str(player_id) for player_id in (matchup.get("players") or [])]
        unavailable = sorted(
            player_id
            for player_id in matchup_players
            if status_for(player_id) in {"live", "final"}
        )

        starters = [str(player_id) for player_id in (matchup.get("starters") or [])]
        starter_points = matchup.get("starters_points") or []
        players_points = matchup.get("players_points") or {}
        slots = _submitted_slots(roster_positions)
        locked_assignments: list[dict] = []

        for starter_index, player_id in enumerate(starters):
            if not player_id or player_id == "0" or starter_index >= len(slots):
                continue
            game_status = status_for(player_id)
            if game_status not in {"live", "final"}:
                continue

            actual = None
            if starter_index < len(starter_points):
                candidate = starter_points[starter_index]
                if isinstance(candidate, (int, float)):
                    actual = float(candidate)
            if actual is None:
                candidate = players_points.get(player_id)
                if isinstance(candidate, (int, float)):
                    actual = float(candidate)
            if actual is None:
                actual = 0.0

            locked_assignments.append(
                {
                    "starter_index": starter_index,
                    "slot": slots[starter_index],
                    **context_for(player_id),
                    "actual_points": round(actual, 2),
                    "game_status": game_status,
                }
            )

        return {
            "locked_assignments": locked_assignments,
            "unavailable_player_ids": unavailable,
            "week": current_week,
            "season": current_season,
        }
    except Exception as exc:
        # Live state should refine the optimizer, not make the entire weekly app
        # unavailable when Sleeper's auxiliary state endpoints have a transient issue.
        print(f"[live_lineup] live lineup state failed: {exc}")
        return _empty_state()
