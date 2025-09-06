from __future__ import annotations

from typing import Dict, List, Tuple, Optional
import datetime as dt

import sleeper_api

from .weekly_windows import compute_week_windows
from .planner import plan_relevant_games_and_markets
from .aggregator import aggregate_by_week
from .range_model import compute_fantasy_range
from . import odds_client
from . import ratelimit
from config import SLEEPER_TO_ODDSAPI_TEAM


def _pick_week_window(which: str, now_utc: Optional[dt.datetime] = None):
    (this_start, this_end), (next_start, next_end) = compute_week_windows(now_utc)
    return (this_start, this_end) if which == "this" else (next_start, next_end)


def _fetch_odds(plan_by_week: Dict[str, Dict[str, object]], use_saved_data: bool) -> Dict[str, Dict[str, list]]:
    out: Dict[str, Dict[str, list]] = {"this": {}, "next": {}}
    for w in ("this", "next"):
        for gid, g in plan_by_week.get(w, {}).items():
            markets_str = ",".join(sorted(set(g.markets)))
            print(f"[services] fetch odds week={w} game={gid} markets={len(g.markets)}")
            out[w][gid] = odds_client.get_event_player_odds(event_id=gid, markets=markets_str, use_saved_data=use_saved_data)
            print(f"[services] ratelimit: {ratelimit.format_status()}")
    return out


def compute_projections(username: str, season: str, week: str = "this", region: str = "us", fresh: bool = False) -> Dict:
    print(f"[services] compute_projections user={username} season={season} week={week} fresh={fresh}")
    roster = sleeper_api.get_user_sleeper_data(username, season)
    if not roster:
        return {"players": [], "ratelimit": ratelimit.format_status()}

    # Plan games only for requested week
    (this_start, this_end), (next_start, next_end) = compute_week_windows()
    plan_all = plan_relevant_games_and_markets(roster, ((this_start, this_end), (next_start, next_end)), regions=region, use_saved_data=(not fresh))
    plan = {week: plan_all.get(week, {})}

    odds_by_week = _fetch_odds(plan, use_saved_data=(not fresh))
    planned = plan[week]
    ev_odds = odds_by_week.get(week, {})

    per_player_odds, per_player_summaries = aggregate_by_week(ev_odds, planned)

    # Build info index
    info_by_alias: Dict[str, dict] = {}
    for g in planned.values():
        for p in g.players:
            info_by_alias[p["alias"]] = p

    scoring_rules = roster.get("scoring_rules", {})
    players_out: List[dict] = []

    for alias, by_book in per_player_odds.items():
        pinfo = info_by_alias.get(alias, {})
        floor, mid, ceil, _ = compute_fantasy_range(by_book, per_player_summaries.get(alias, {}), scoring_rules)
        players_out.append({
            "name": pinfo.get("full_name", alias),
            "pos": pinfo.get("primary_position"),
            "team": pinfo.get("editorial_team_full_name"),
            "floor": round(floor, 2),
            "mid": round(mid, 2),
            "ceiling": round(ceil, 2),
            "books_used": len(by_book.keys()),
            "markets_used": len(per_player_summaries.get(alias, {})),
        })

    # Sort by mid desc
    players_out.sort(key=lambda x: x["mid"], reverse=True)
    return {"week": week, "players": players_out, "ratelimit": ratelimit.format_status()}


def build_lineup(players: List[dict], target: str = "mid") -> Dict:
    """Build lineup: QB1, RB2, WR2, TE1, FLEX1 (from WR/RB/TE)."""
    print(f"[services] build_lineup target={target}")
    buckets: Dict[str, List[dict]] = {"QB": [], "RB": [], "WR": [], "TE": []}
    for p in players:
        if p.get("pos") in buckets:
            buckets[p["pos"]].append(p)
    for pos in buckets:
        buckets[pos].sort(key=lambda x: x.get(target, 0.0), reverse=True)

    used = set()
    def take(pos: str, n: int) -> List[dict]:
        out = []
        for item in buckets.get(pos, []):
            if item["name"] not in used:
                out.append(item)
                used.add(item["name"])
                if len(out) == n:
                    break
        return out

    lineup = {
        "QB": take("QB", 1),
        "RB": take("RB", 2),
        "WR": take("WR", 2),
        "TE": take("TE", 1),
    }
    # FLEX best remaining WR/RB/TE
    flex_pool = []
    for pos in ("WR", "RB", "TE"):
        for item in buckets.get(pos, []):
            if item["name"] not in used:
                flex_pool.append(item)
    flex_pool.sort(key=lambda x: x.get(target, 0.0), reverse=True)
    lineup["FLEX"] = flex_pool[:1]

    rows = []
    total = 0.0
    def add_slot(slot: str, p: dict):
        nonlocal total
        pts = float(p.get(target, 0.0))
        total += pts
        rows.append({"slot": slot, "name": p["name"], "pos": p["pos"], "team": p.get("team"), "points": round(pts, 2)})

    for p in lineup["QB"]: add_slot("QB", p)
    for p in lineup["RB"]: add_slot("RB", p)
    for p in lineup["WR"]: add_slot("WR", p)
    for p in lineup["TE"]: add_slot("TE", p)
    for p in lineup["FLEX"]: add_slot("FLEX", p)

    return {"target": target, "lineup": rows, "total_points": round(total, 2)}


def build_lineup_diffs(players: List[dict]) -> Dict:
    base = build_lineup(players, target="mid")
    floor = build_lineup(players, target="floor")
    ceil = build_lineup(players, target="ceiling")

    def diff(from_rows: List[dict], to_rows: List[dict]) -> List[dict]:
        out = []
        by_slot_from = {r["slot"]: r for r in from_rows}
        by_slot_to = {r["slot"]: r for r in to_rows}
        for slot in by_slot_from.keys():
            if by_slot_from[slot]["name"] != by_slot_to[slot]["name"]:
                out.append({
                    "slot": slot,
                    "from": by_slot_from[slot]["name"],
                    "to": by_slot_to[slot]["name"],
                })
        return out

    return {
        "from": base,
        "floor_changes": diff(base["lineup"], floor["lineup"]),
        "ceiling_changes": diff(base["lineup"], ceil["lineup"]),
    }


def _implied_total(game_total: float, team_spread: float) -> float:
    return game_total / 2.0 - team_spread / 2.0


def _def_teams_for_user(username: str, season: str) -> Tuple[List[str], List[str]]:
    """Return (owned_DEF_fullnames, available_DEF_fullnames) as OddsAPI team names."""
    # Owned defenses
    roster = sleeper_api.get_user_sleeper_data(username, season)
    owned = []
    for pid, pdata in roster.get("players", {}).items():
        if pdata.get("primary_position") == "DEF":
            team = pdata.get("editorial_team_full_name")
            if team:
                owned.append(team)

    # Available defenses
    avail_map = sleeper_api.get_available_defenses(username, season)
    available = []
    for pid, pdata in avail_map.items():
        abbr = pdata.get("team")
        full = SLEEPER_TO_ODDSAPI_TEAM.get(abbr)
        if full:
            available.append(full)

    return owned, available


def list_defenses(username: str, season: str, week: str = "this", scope: str = "both", fresh: bool = False) -> Dict:
    print(f"[services] list_defenses user={username} season={season} week={week} scope={scope} fresh={fresh}")
    (this_start, this_end), (next_start, next_end) = compute_week_windows()
    start, end = ((this_start, this_end) if week == "this" else (next_start, next_end))

    owned, available = _def_teams_for_user(username, season)
    team_list: List[Tuple[str, str]] = []
    if scope in ("owned", "both"):
        team_list += [(t, "owned") for t in owned]
    if scope in ("available", "both"):
        team_list += [(t, "available") for t in available]

    # Filter events in window
    events = odds_client.get_nfl_events()
    window_events = [e for e in events if start <= dt.datetime.strptime(e['commence_time'], "%Y-%m-%dT%H:%M:%SZ") <= end]

    out_rows: List[dict] = []
    for team, source in team_list:
        # Find events where this team plays
        for e in window_events:
            if team not in (e.get("home_team"), e.get("away_team")):
                continue
            gid = e["id"]
            opp = e["away_team"] if e["home_team"] == team else e["home_team"]
            odds = odds_client.get_event_player_odds(gid, markets="spreads,totals", use_saved_data=(not fresh))
            # Collect per-book implied totals for opponent
            implieds: List[float] = []
            for book in (odds[0].get("bookmakers", []) if isinstance(odds, list) and odds else []):
                total_pt = None
                opp_spread = None
                for m in book.get("markets", []):
                    if m.get("key") == "totals":
                        for o in m.get("outcomes", []):
                            if o.get("name") == "Over":
                                total_pt = o.get("point")
                    if m.get("key") == "spreads":
                        for o in m.get("outcomes", []):
                            if o.get("name") == opp:
                                opp_spread = o.get("point")
                try:
                    if total_pt is not None and opp_spread is not None:
                        implieds.append(_implied_total(float(total_pt), float(opp_spread)))
                except Exception:
                    pass
            if implieds:
                implieds.sort()
                mid = implieds[len(implieds)//2] if len(implieds) % 2 == 1 else (implieds[len(implieds)//2 -1] + implieds[len(implieds)//2])/2
                out_rows.append({
                    "defense": team,
                    "opponent": opp,
                    "game_date": e["commence_time"],
                    "implied_total_median": round(mid, 2),
                    "book_count": len(implieds),
                    "source": source,
                })

    # Sort ascending by implied total (lower is better for defense)
    out_rows.sort(key=lambda r: (r["implied_total_median"], -r["book_count"]))
    return {"week": week, "defenses": out_rows, "ratelimit": ratelimit.format_status()}

