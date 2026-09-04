from __future__ import annotations

import datetime as dt
from collections.abc import Iterable
from dataclasses import dataclass

from . import odds_client
from .config import (
    POSITION_STAT_CONFIG,
    SLEEPER_ODDS_API_PLAYER_NAME_MAPPING,
    STAT_MARKET_MAPPING,
)
from .weekly_windows import in_window


@dataclass
class PlannedGame:
    game_id: str
    home_team: str
    away_team: str
    commence_time: str
    players: list[dict]
    markets: list[str]


def player_alias(full_name: str) -> str:
    return SLEEPER_ODDS_API_PLAYER_NAME_MAPPING.get(full_name, full_name)


def _normalize_market(stat_key: str) -> str | None:
    if stat_key in STAT_MARKET_MAPPING:
        return STAT_MARKET_MAPPING[stat_key]
    if stat_key.endswith("_tds") or stat_key.endswith("_tds_alternate"):
        return "player_anytime_td"
    if stat_key.endswith("_alternate"):
        if stat_key.startswith("player_receptions"):
            return "player_receptions_alternate"
        if stat_key.startswith("player_rush_yds"):
            return "player_rush_yds_alternate"
        if stat_key.startswith("player_reception_yds"):
            return "player_reception_yds_alternate"
        return None
    return stat_key


def _markets_for_positions(positions: Iterable[str]) -> list[str]:
    seen: set[str] = set()
    for pos in positions:
        for raw in POSITION_STAT_CONFIG.get(pos, []):
            normalized = _normalize_market(raw)
            if normalized:
                seen.add(normalized)
            if raw in {"player_receptions", "player_reception_yds", "player_rush_yds"}:
                alternate = _normalize_market(f"{raw}_alternate")
                if alternate:
                    seen.add(alternate)
    return sorted(seen)


def plan_relevant_games_and_markets(
    roster: dict,
    week_windows: tuple[tuple[dt.datetime, dt.datetime], tuple[dt.datetime, dt.datetime]],
    regions: str = "us",
    cache_mode: str = "auto",
    events: list[dict] | None = None,
) -> dict[str, dict[str, PlannedGame]]:
    """Plan the minimum event-odds calls needed for the roster.

    ``events`` lets a caller that already fetched the schedule avoid immediately
    fetching it a second time.
    """
    (this_start, this_end), (next_start, next_end) = week_windows
    event_rows = (
        events
        if events is not None
        else odds_client.get_nfl_events(regions=regions, mode=cache_mode)
    )

    this_events = {
        event["id"]: event
        for event in event_rows
        if in_window(event.get("commence_time"), (this_start, this_end))
    }
    next_events = {
        event["id"]: event
        for event in event_rows
        if in_window(event.get("commence_time"), (next_start, next_end))
    }

    def plan_for(events_by_id: dict[str, dict]) -> dict[str, PlannedGame]:
        plan: dict[str, PlannedGame] = {}
        for player in (roster.get("players", {}) or {}).values():
            team = player.get("editorial_team_full_name")
            pos = player.get("primary_position")
            full_name = (player.get("name", {}) or {}).get("full")
            if not team or not pos or not full_name:
                continue
            for event in events_by_id.values():
                if team not in (event.get("home_team"), event.get("away_team")):
                    continue
                game = plan.setdefault(
                    event["id"],
                    PlannedGame(
                        game_id=event["id"],
                        home_team=event["home_team"],
                        away_team=event["away_team"],
                        commence_time=event["commence_time"],
                        players=[],
                        markets=[],
                    ),
                )
                game.players.append(
                    {
                        "full_name": full_name,
                        "alias": player_alias(full_name),
                        "primary_position": pos,
                        "editorial_team_full_name": team,
                    }
                )
        for game in plan.values():
            game.markets = _markets_for_positions(
                player["primary_position"] for player in game.players
            )
        return plan

    return {"this": plan_for(this_events), "next": plan_for(next_events)}
