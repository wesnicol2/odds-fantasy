from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Tuple, Iterable
import datetime as _dt

from . import odds_client
from config import POSITION_STAT_CONFIG, SLEEPER_ODDS_API_PLAYER_NAME_MAPPING, STAT_MARKET_MAPPING
from .weekly_windows import in_window


@dataclass
class PlannedGame:
    game_id: str
    home_team: str
    away_team: str
    commence_time: str  # ISO Z
    players: List[dict]
    markets: List[str]


def _player_alias(full_name: str) -> str:
    return SLEEPER_ODDS_API_PLAYER_NAME_MAPPING.get(full_name, full_name)


def _normalize_market(stat_key: str) -> str | None:
    # Map via explicit mapping when available
    if stat_key in STAT_MARKET_MAPPING:
        return STAT_MARKET_MAPPING[stat_key]

    # Unify any TD markets (rush/rec + alternates) to anytime TD
    if stat_key.endswith("_tds") or stat_key.endswith("_tds_alternate"):
        return "player_anytime_td"

    # Allow alternates only for receptions and rush_yds to avoid 422s
    if stat_key.endswith("_alternate"):
        if stat_key.startswith("player_receptions"):
            return "player_receptions_alternate"
        if stat_key.startswith("player_rush_yds"):
            return "player_rush_yds_alternate"
        return None

    # Pass-through if already an Odds API key
    return stat_key


def _markets_for_positions(positions: Iterable[str]) -> List[str]:
    seen: set[str] = set()
    for pos in positions:
        for raw in POSITION_STAT_CONFIG.get(pos, []):
            norm = _normalize_market(raw)
            if norm:
                seen.add(norm)
    return sorted(seen)


def plan_relevant_games_and_markets(
    roster: dict,
    week_windows: Tuple[Tuple[_dt.datetime, _dt.datetime], Tuple[_dt.datetime, _dt.datetime]],
    regions: str = "us",
    use_saved_data: bool | None = None,
    cache_mode: str = "auto",
) -> Dict[str, Dict[str, PlannedGame]]:
    """Plan minimal event-odds calls by week window.

    Returns a dict with keys 'this' and 'next', each mapping game_id -> PlannedGame.
    """
    (this_start, this_end), (next_start, next_end) = week_windows
    # Backward-compat: map use_saved_data to cache_mode when provided
    if use_saved_data is not None:
        cache_mode = 'cache' if use_saved_data else 'fresh'
    events = odds_client.get_nfl_events(regions=regions, mode=cache_mode)

    # Index events by window
    this_events: dict[str, dict] = {}
    next_events: dict[str, dict] = {}
    for e in events:
        ts = e.get("commence_time")
        if in_window(ts, (this_start, this_end)):
            this_events[e["id"]] = e
        elif in_window(ts, (next_start, next_end)):
            next_events[e["id"]] = e

    def plan_for(events_by_id: dict[str, dict]) -> Dict[str, PlannedGame]:
        plan: Dict[str, PlannedGame] = {}
        # Group roster players by events they participate in
        for p in roster.get("players", {}).values():
            team = p.get("editorial_team_full_name")
            pos = p.get("primary_position")
            full_name = p.get("name", {}).get("full")
            alias = _player_alias(full_name)
            if not team or not pos or not full_name:
                continue
            for e in events_by_id.values():
                if team not in (e.get("home_team"), e.get("away_team")):
                    continue
                gid = e["id"]
                if gid not in plan:
                    plan[gid] = PlannedGame(
                        game_id=gid,
                        home_team=e["home_team"],
                        away_team=e["away_team"],
                        commence_time=e["commence_time"],
                        players=[],
                        markets=[],
                    )
                plan[gid].players.append({
                    "full_name": full_name,
                    "alias": alias,
                    "primary_position": pos,
                    "editorial_team_full_name": team,
                })

        # Determine minimal markets per game (union of player position markets)
        for gid, g in plan.items():
            positions = [p["primary_position"] for p in g.players]
            g.markets = _markets_for_positions(positions)

        return plan

    return {
        "this": plan_for(this_events),
        "next": plan_for(next_events),
    }
