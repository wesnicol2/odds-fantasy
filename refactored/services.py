from __future__ import annotations

from typing import Dict, List, Tuple, Optional
from statistics import NormalDist
import datetime as dt
import time
import os

import sleeper_api

from .weekly_windows import compute_week_windows
from .planner import plan_relevant_games_and_markets
from .aggregator import aggregate_by_week
from .range_model import compute_fantasy_range
from . import odds_client
from . import ratelimit
from config import SLEEPER_TO_ODDSAPI_TEAM
from predicted_stats import predict_stats_for_player
from config import STAT_MARKET_MAPPING_SLEEPER, POSITION_STAT_CONFIG
from .range_model import PRIMARY_MARKET_WHITELIST


def _pick_week_window(which: str, now_utc: Optional[dt.datetime] = None):
    (this_start, this_end), (next_start, next_end) = compute_week_windows(now_utc)
    return (this_start, this_end) if which == "this" else (next_start, next_end)


def _fetch_odds(plan_by_week: Dict[str, Dict[str, object]], cache_mode: str, regions: str = "us") -> Dict[str, Dict[str, list]]:
    """Fetch event odds concurrently per week for planned games.

    Uses a small thread pool to parallelize network calls when cache misses occur.
    """
    from concurrent.futures import ThreadPoolExecutor, as_completed

    out: Dict[str, Dict[str, list]] = {"this": {}, "next": {}}
    for w in ("this", "next"):
        items = list(plan_by_week.get(w, {}).items())
        if not items:
            continue
        max_workers = min(8, max(1, len(items)))

        def task(pair):
            gid, g = pair
            markets_str = ",".join(sorted(set(g.markets)))
            print(f"[services] fetch odds week={w} game={gid} markets={len(g.markets)} regions={regions} mode={cache_mode}")
            data = odds_client.get_event_player_odds(event_id=gid, markets=markets_str, regions=regions, mode=cache_mode)
            return gid, data

        with ThreadPoolExecutor(max_workers=max_workers) as ex:
            futures = [ex.submit(task, it) for it in items]
            for fut in as_completed(futures):
                try:
                    gid, data = fut.result()
                    out[w][gid] = data
                except Exception as e:
                    print(f"[services] fetch odds error: {e}")
        print(f"[services] fetch odds week={w} complete; games={len(out[w])} rl={ratelimit.format_status()}")
    return out


def compute_projections(username: str, season: str, week: str = "this", region: str = "us", fresh: bool = False, cache_mode: str = "auto", model: str = "const") -> Dict:
    print(f"[services] compute_projections user={username} season={season} week={week} fresh={fresh}")
    # In-process TTL cache
    ttl = int(os.getenv("SERVICE_CACHE_TTL", "120"))
    _proj_cache = getattr(compute_projections, "_cache", {})
    key = (username, season, week, region, model)
    now = time.time()
    if not fresh and key in _proj_cache:
        ts, payload = _proj_cache[key]
        if now - ts < ttl:
            print(f"[services] compute_projections cache hit key={key} age={int(now-ts)}s")
            return payload
    try:
        roster = sleeper_api.get_user_sleeper_data(username, season)
    except Exception as e:
        print(f"[services] sleeper error: {e}")
        # Graceful fallback: continue with empty roster so UI can load
        return {"players": [], "ratelimit": ratelimit.format_status(), "ratelimit_info": ratelimit.get_details(), "error": "sleeper_timeout"}
    if not roster:
        return {"players": [], "ratelimit": ratelimit.format_status(), "ratelimit_info": ratelimit.get_details()}

    # Plan games only for requested week
    (this_start, this_end), (next_start, next_end) = compute_week_windows()
    eff_mode = 'fresh' if fresh else cache_mode
    plan_all = plan_relevant_games_and_markets(roster, ((this_start, this_end), (next_start, next_end)), regions=region, cache_mode=eff_mode)
    plan = {week: plan_all.get(week, {})}

    odds_by_week = _fetch_odds(plan, cache_mode=eff_mode, regions=region)
    planned = plan[week]
    ev_odds = odds_by_week.get(week, {})
    # Debug: print planned vs matched counts
    try:
        planned_players = sum(len(g.players) for g in planned.values())
    except Exception:
        planned_players = 0

    per_player_odds, per_player_summaries = aggregate_by_week(ev_odds, planned)
    try:
        matched_players = len(per_player_odds)
        print(f"[services] aggregate matched_players={matched_players} planned_players={planned_players} games={len(planned)}")
    except Exception:
        pass

    # Build info index
    info_by_alias: Dict[str, dict] = {}
    for g in planned.values():
        for p in g.players:
            info_by_alias[p["alias"]] = p

    scoring_rules = roster.get("scoring_rules", {})
    players_out: List[dict] = []

    # Helpers to diagnose missing coverage and normalize market keys
    def _norm_market_key(k: str) -> str:
        if not k:
            return k
        base = k.replace("_alternate", "")
        if base in ("player_rush_tds", "player_reception_tds"):
            return "player_anytime_td"
        return base

    def _expected_markets_for_pos(pos: str | None) -> set[str]:
        raw = POSITION_STAT_CONFIG.get(pos or "", [])
        exp = {_norm_market_key(x) for x in raw}
        # Focus on primary markets used for fantasy conversion
        return {m for m in exp if m in PRIMARY_MARKET_WHITELIST}

    def _is_ppr(scoring: dict) -> bool:
        try:
            v = float(scoring.get("rec", 0) or 0)
            return v > 0
        except Exception:
            return False

    def _importance_for_pos(pos: Optional[str], scoring: dict) -> tuple[set[str], set[str]]:
        """Return (vital_markets, minor_markets) for a given position.

        Applies PPR gating for receptions where requested.
        """
        p = (pos or "").upper()
        ppr = _is_ppr(scoring)
        vital: set[str] = set()
        minor: set[str] = set()
        if p == "QB":
            vital = {"player_pass_yds", "player_pass_tds", "player_rush_yds", "player_anytime_td"}
            minor = {"player_pass_interceptions"}
        elif p == "RB":
            vital = {"player_rush_yds", "player_anytime_td"}
            if ppr:
                vital.add("player_receptions")
            else:
                minor.add("player_receptions")
            minor.add("player_reception_yds")
        elif p == "WR":
            vital = {"player_reception_yds", "player_anytime_td"}
            if ppr:
                vital.add("player_receptions")
            else:
                minor.add("player_receptions")
            minor.add("player_rush_yds")
        elif p == "TE":
            vital = {"player_reception_yds", "player_anytime_td"}
            if ppr:
                vital.add("player_receptions")
            else:
                minor.add("player_receptions")
            minor.add("player_rush_yds")
        else:
            vital = {"player_anytime_td"}
            minor = set()
        # Constrain to whitelisted markets we actually consider
        vital &= PRIMARY_MARKET_WHITELIST
        minor &= PRIMARY_MARKET_WHITELIST
        return vital, minor

    present_aliases = set(per_player_odds.keys())
    for alias, by_book in per_player_odds.items():
        pinfo = info_by_alias.get(alias, {})
        from .range_model import compute_fantasy_range_model, compute_fantasy_range
        if (model or "baseline").lower() == "baseline":
            floor, mid, ceil, _ = compute_fantasy_range(by_book, per_player_summaries.get(alias, {}), scoring_rules)
        else:
            floor, mid, ceil, _ = compute_fantasy_range_model(by_book, per_player_summaries.get(alias, {}), scoring_rules, model=model)

        # Coverage diagnostics
        available: set[str] = set()
        for _bk, mkts in (by_book or {}).items():
            for mkey in (mkts or {}).keys():
                available.add(_norm_market_key(mkey))
        pos = pinfo.get("primary_position")
        vital_exp, minor_exp = _importance_for_pos(pos, scoring_rules)
        expected = vital_exp | minor_exp
        missing_set = (expected - available)
        missing = sorted(list(missing_set))
        missing_vital = sorted(list(missing_set & vital_exp))
        missing_minor = sorted(list(missing_set & minor_exp))
        # Summary keys; if absent, we used fallback band
        summ_keys = {_norm_market_key(k) for k in (per_player_summaries.get(alias, {}) or {}).keys()}
        fallback_set = {k for k in available if k not in summ_keys}
        fallback = sorted(list(fallback_set))
        fallback_vital = sorted(list(fallback_set & vital_exp))
        fallback_minor = sorted(list(fallback_set & minor_exp))

        players_out.append({
            "name": pinfo.get("full_name", alias),
            "pos": pos,
            "team": pinfo.get("editorial_team_full_name"),
            "floor": round(floor, 2),
            "mid": round(mid, 2),
            "ceiling": round(ceil, 2),
            "books_used": len(by_book.keys()),
            "markets_used": len(per_player_summaries.get(alias, {})),
            "incomplete": bool(missing),
            "missing_markets": missing,
            "fallback_markets": fallback,
            # Importance-aware diagnostics
            "missing_vital": missing_vital,
            "missing_minor": missing_minor,
            "fallback_vital": fallback_vital,
            "fallback_minor": fallback_minor,
            "is_critical": (len(missing_vital) > 0 or len(fallback_vital) > 0),
        })

    # Add planned roster players with no odds as incomplete entries
    for alias, pinfo in info_by_alias.items():
        if alias in present_aliases:
            continue
        # For players with no odds, mark expected markets as missing with importance split
        pos = pinfo.get("primary_position")
        vital_exp, minor_exp = _importance_for_pos(pos, scoring_rules)
        exp_all = sorted(list(vital_exp | minor_exp))
        players_out.append({
            "name": pinfo.get("full_name", alias),
            "pos": pos,
            "team": pinfo.get("editorial_team_full_name"),
            "floor": None,
            "mid": None,
            "ceiling": None,
            "books_used": 0,
            "markets_used": 0,
            "incomplete": True,
            "missing_markets": exp_all,
            "fallback_markets": [],
            "missing_vital": sorted(list(vital_exp)),
            "missing_minor": sorted(list(minor_exp)),
            "fallback_vital": [],
            "fallback_minor": [],
            "is_critical": bool(vital_exp),
        })

        # Include roster players without scheduled events as incomplete
    try:
        present_names = {p.get("name") for p in players_out}
        for p in (roster.get("players", {}) or {}).values():
            try:
                full_name = (p.get("name", {}) or {}).get("full")
                if not full_name or full_name in present_names:
                    continue
                pos = p.get("primary_position")
                team = p.get("editorial_team_full_name")
                players_out.append({
                    "name": full_name,
                    "pos": pos,
                    "team": team,
                    "floor": None,
                    "mid": None,
                    "ceiling": None,
                    "books_used": 0,
                    "markets_used": 0,
                    "incomplete": True,
                    "missing_markets": exp_all,
                    "fallback_markets": [],
                    "missing_vital": sorted(list(vital_exp)),
                    "missing_minor": sorted(list(minor_exp)),
                    "fallback_vital": [],
                    "fallback_minor": [],
                    "is_critical": bool(vital_exp),
                })
            except Exception:
                continue
    except Exception:
        pass

    # Optional debug: summarize market coverage and usage
    try:
        if os.getenv("API_DEBUG") in ("1", "true", "True"):
            # Collect raw and normalized market keys across players
            all_raw: set[str] = set()
            for _alias, by_book in per_player_odds.items():
                for _bk, mkts in (by_book or {}).items():
                    for mkey in (mkts or {}).keys():
                        all_raw.add(mkey)
            all_norm = {_norm_market_key(k) for k in all_raw}
            used_norm = {k for k in all_norm if k in PRIMARY_MARKET_WHITELIST}
            ignored_norm = sorted(list(all_norm - used_norm))
            print(f"[services][debug] markets: raw={len(all_raw)} norm={len(all_norm)} used={len(used_norm)} ignored={len(ignored_norm)}")
            if ignored_norm:
                print(f"[services][debug] markets_ignored_norm: {', '.join(sorted(list(ignored_norm)))}")

            # Per-player gaps (limit output size)
            missing_players = [p for p in players_out if p.get("incomplete")]
            print(f"[services][debug] players_with_missing={len(missing_players)} / total={len(players_out)}")
            for p in missing_players[:12]:
                miss = ", ".join(p.get("missing_markets") or [])
                fb = ", ".join(p.get("fallback_markets") or [])
                print(f"[services][debug] missing: {p.get('name')} ({p.get('pos')}) -> missing=[{miss}] fallback=[{fb}]")
    except Exception as _dbg_e:
        try:
            print(f"[services][debug] error: {str(_dbg_e)}")
        except Exception:
            pass

    # Sort by mid desc, placing missing mids (None) at the end
    players_out.sort(key=lambda x: (x.get("mid") if isinstance(x.get("mid"), (int, float)) else float("-inf")), reverse=True)
    payload = {"week": week, "players": players_out, "ratelimit": ratelimit.format_status(), "ratelimit_info": ratelimit.get_details()}
    # store in cache
    _proj_cache[key] = (now, payload)
    compute_projections._cache = _proj_cache
    return payload


def build_lineup(players: List[dict], target: str = "mid") -> Dict:
    """Build lineup: QB1, WR2, RB2, FLEX1 (from WR/RB/TE), then BENCH.

    Always include players with zero projection in BENCH.
    """
    print(f"[services] build_lineup target={target}")
    buckets: Dict[str, List[dict]] = {"QB": [], "RB": [], "WR": [], "TE": []}
    for p in players:
        if p.get("pos") in buckets:
            buckets[p["pos"]].append(p)
    for pos in buckets:
        # Ensure None values do not break sort comparisons
        buckets[pos].sort(key=lambda x: (float(x.get(target)) if isinstance(x.get(target), (int, float)) else 0.0), reverse=True)

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

    starters = {
        "QB": take("QB", 1),
        "WR": take("WR", 2),
        "RB": take("RB", 2),
        "TE": take("TE", 1),
    }
    # FLEX best remaining WR/RB/TE
    flex_pool = []
    for pos in ("WR", "RB", "TE"):
        for item in buckets.get(pos, []):
            if item["name"] not in used:
                flex_pool.append(item)
    flex_pool.sort(key=lambda x: (float(x.get(target)) if isinstance(x.get(target), (int, float)) else 0.0), reverse=True)
    flex = flex_pool[:1]
    for f in flex:
        used.add(f["name"])  # mark used for bench

    rows = []
    total = 0.0
    def add_slot(slot: str, p: dict):
        nonlocal total
        def _num(v):
            try:
                if v is None:
                    return 0.0
                return float(v)
            except Exception:
                return 0.0
        pts = _num(p.get(target, 0.0))
        total += pts
        rows.append({
            "slot": slot,
            "name": p["name"],
            "pos": p["pos"],
            # keep team in payload for future, UI may ignore it
            "team": p.get("team"),
            "points": round(pts, 2),
            # include full trio for UI rendering
            "floor": round(_num(p.get("floor", 0.0)), 2),
            "mid": round(_num(p.get("mid", 0.0)), 2),
            "ceiling": round(_num(p.get("ceiling", 0.0)), 2),
        })

    # Order: QB, WR, WR, RB, RB, TE, FLEX
    for p in starters["QB"]: add_slot("QB", p)
    if len(starters["WR"]) > 0: add_slot("WR", starters["WR"][0])
    if len(starters["WR"]) > 1: add_slot("WR", starters["WR"][1])
    if len(starters["RB"]) > 0: add_slot("RB", starters["RB"][0])
    if len(starters["RB"]) > 1: add_slot("RB", starters["RB"][1])
    for p in starters["TE"]: add_slot("TE", p)
    for p in flex: add_slot("FLEX", p)

    # Bench: remaining players by target (include zeros)
    bench: List[dict] = []
    for pos in ("QB", "WR", "RB", "TE"):
        for item in buckets.get(pos, []):
            if item["name"] not in used:
                bench.append(item)
    bench.sort(key=lambda x: (float(x.get(target)) if isinstance(x.get(target), (int, float)) else 0.0), reverse=True)

    def _num(v):
        try:
            if v is None:
                return 0.0
            return float(v)
        except Exception:
            return 0.0

    for b in bench:
        rows.append({
            "slot": "BENCH",
            "name": b["name"],
            "pos": b["pos"],
            "team": b.get("team"),
            "points": round(_num(b.get(target, 0.0)), 2),
            "floor": round(_num(b.get("floor", 0.0)), 2),
            "mid": round(_num(b.get("mid", 0.0)), 2),
            "ceiling": round(_num(b.get("ceiling", 0.0)), 2),
        })

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


def list_defenses(username: str, season: str, week: str = "this", scope: str = "both", fresh: bool = False, cache_mode: str = "auto", region: str = "us") -> Dict:
    print(f"[services] list_defenses user={username} season={season} week={week} scope={scope} fresh={fresh}")
    # In-process TTL cache
    ttl = int(os.getenv("SERVICE_CACHE_TTL", "120"))
    _def_cache = getattr(list_defenses, "_cache", {})
    key = (username, season, week, scope)
    now = time.time()
    if not fresh and key in _def_cache:
        ts, payload = _def_cache[key]
        if now - ts < ttl:
            print(f"[services] list_defenses cache hit key={key} age={int(now-ts)}s")
            return payload
    (this_start, this_end), (next_start, next_end) = compute_week_windows()
    start, end = ((this_start, this_end) if week == "this" else (next_start, next_end))

    owned, available = _def_teams_for_user(username, season)
    team_list: List[Tuple[str, str]] = []
    if scope in ("owned", "both"):
        team_list += [(t, "owned") for t in owned]
    if scope in ("available", "both"):
        team_list += [(t, "available") for t in available]

    # Filter events in window
    eff_mode = 'fresh' if fresh else cache_mode
    events = odds_client.get_nfl_events(regions=region, mode=eff_mode)
    window_events = [e for e in events if start <= dt.datetime.strptime(e['commence_time'], "%Y-%m-%dT%H:%M:%SZ") <= end]

    # Prefetch odds per event once to avoid duplicate calls per team
    ev_odds_map = {}
    for e in window_events:
        gid = e["id"]
        try:
            ev_odds_map[gid] = odds_client.get_event_player_odds(gid, markets="spreads,totals", regions=region, mode=eff_mode)
        except Exception as exc:
            print(f"[services] defenses: fetch odds failed game={gid} err={exc}")
            ev_odds_map[gid] = None

    out_rows: List[dict] = []
    for team, source in team_list:
        # Find events where this team plays
        for e in window_events:
            if team not in (e.get("home_team"), e.get("away_team")):
                continue
            gid = e["id"]
            opp = e["away_team"] if e["home_team"] == team else e["home_team"]
            odds = ev_odds_map.get(gid)
            # Collect per-book implied totals for opponent
            implieds: List[float] = []
            # Normalize event structure: list or dict
            ev_obj = None
            if isinstance(odds, list) and odds:
                ev_obj = odds[0]
            elif isinstance(odds, dict):
                ev_obj = odds
            else:
                ev_obj = None
            if ev_obj is None:
                print(f"[services] defenses: no odds for game={gid} team={team}")
                continue
            books = ev_obj.get("bookmakers", [])
            print(f"[services] defenses: team={team} opp={opp} game={gid} books={len(books)}")
            for book in books:
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
            if not implieds:
                print(f"[services] defenses: no implied totals computed for team={team} game={gid}")
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
    payload = {"week": week, "defenses": out_rows, "ratelimit": ratelimit.format_status(), "ratelimit_info": ratelimit.get_details()}
    _def_cache[key] = (now, payload)
    list_defenses._cache = _def_cache
    return payload


def build_dashboard(
    username: str,
    season: str,
    region: str = "us",
    fresh: bool = False,
    cache_mode: str = "auto",
    weeks: str = "both",  # 'this' | 'next' | 'both'
    def_scope: str = "owned",  # 'owned' | 'available' | 'both'
    include_players: bool = True,
    model: str = "const",
) -> Dict:
    """Build a single payload for UI: lineups and defenses with optional scoping.

    Structure:
    {
      "lineups": {
         "this": {"mid": {...}, "floor": {...}, "ceiling": {...}},
         "next": {"mid": {...}, "floor": {...}, "ceiling": {...}}
      },
      "defenses": {"this": {...}, "next": {...}},
      "ratelimit": str,
      "ratelimit_info": {...}
    }
    """
    print(f"[services] build_dashboard user={username} season={season} fresh={fresh} weeks={weeks} def_scope={def_scope} inc_players={include_players}")

    # Projections scoped by weeks
    proj_this = None
    proj_next = None
    if weeks in ("this", "both"):
        proj_this = compute_projections(username=username, season=season, week="this", region=region, fresh=fresh, cache_mode=('fresh' if fresh else cache_mode), model=model)
    if weeks in ("next", "both"):
        proj_next = compute_projections(username=username, season=season, week="next", region=region, fresh=fresh, cache_mode=('fresh' if fresh else cache_mode), model=model)

    # Build lineups from one projections call per week
    lineups = {"this": None, "next": None}
    if proj_this is not None:
        lineups["this"] = {
            "mid": build_lineup(proj_this.get("players", []), target="mid"),
            "floor": build_lineup(proj_this.get("players", []), target="floor"),
            "ceiling": build_lineup(proj_this.get("players", []), target="ceiling"),
        }
    if proj_next is not None:
        lineups["next"] = {
            "mid": build_lineup(proj_next.get("players", []), target="mid"),
            "floor": build_lineup(proj_next.get("players", []), target="floor"),
            "ceiling": build_lineup(proj_next.get("players", []), target="ceiling"),
        }

    # Defenses scoped by weeks and scope parameter
    defs_this = None
    defs_next = None
    if weeks in ("this", "both"):
        defs_this = list_defenses(username=username, season=season, week="this", scope=def_scope, fresh=fresh, cache_mode=('fresh' if fresh else cache_mode))
    if weeks in ("next", "both"):
        defs_next = list_defenses(username=username, season=season, week="next", scope=def_scope, fresh=fresh, cache_mode=('fresh' if fresh else cache_mode))

    # Choose latest ratelimit info
    rl_info = ratelimit.get_details()

    payload = {
        "lineups": lineups,
        "defenses": {"this": defs_this, "next": defs_next},
        "projections": {
            "this": {"players": (proj_this.get("players", []) if (include_players and proj_this is not None) else [])},
            "next": {"players": (proj_next.get("players", []) if (include_players and proj_next is not None) else [])},
        },
        "ratelimit": ratelimit.format_status(),
        "ratelimit_info": rl_info,
    }
    print(f"[services] build_dashboard complete; rl={payload['ratelimit']}")
    return payload


def _norm_name(s: str) -> str:
    try:
        s = (s or "").lower()
        import re
        s = re.sub(r"[\.'`-]", " ", s)
        s = re.sub(r"[^a-z0-9 ]", "", s)
        s = re.sub(r"\s+", " ", s).strip()
        toks = [t for t in s.split(" ") if t not in ("jr", "sr", "ii", "iii", "iv", "v")]
        return " ".join(toks)
    except Exception:
        return s or ""


def get_player_odds_details(username: str, season: str, week: str = "this", region: str = "us", name: str = "", cache_mode: str = "auto", model: str = "baseline") -> Dict:
    """Return per-book odds and market summaries used for a single player.

    Emphasizes markets by estimated impact on fantasy points (mean stat * scoring multiplier).
    """
    (this_start, this_end), (next_start, next_end) = compute_week_windows()
    eff_mode = cache_mode
    # Roster & planning (to get scoring rules and player mapping)
    roster = sleeper_api.get_user_sleeper_data(username, season)
    scoring_rules = roster.get("scoring_rules", {}) if roster else {}
    windows = (this_start, this_end) if week == "this" else (next_start, next_end)
    plan_all = plan_relevant_games_and_markets(roster, ((this_start, this_end), (next_start, next_end)), regions=region, cache_mode=eff_mode)
    planned = plan_all.get(week, {})
    # Fetch odds for planned games
    odds_by_week = _fetch_odds({week: planned}, cache_mode=eff_mode, regions=region)
    ev_odds = odds_by_week.get(week, {})
    # Aggregate
    per_player_odds, per_player_summaries = aggregate_by_week(ev_odds, planned)
    # Build alias->info map
    info_by_alias: Dict[str, dict] = {}
    for g in planned.values():
        for p in g.players:
            info_by_alias[p["alias"]] = p
    # Resolve name -> alias (exact or normalized)
    target_alias = None
    n_target = _norm_name(name)
    for alias, pinfo in info_by_alias.items():
        full = pinfo.get("full_name", alias)
        if full == name:
            target_alias = alias
            break
    if target_alias is None:
        for alias, pinfo in info_by_alias.items():
            full = pinfo.get("full_name", alias)
            if _norm_name(full) == n_target:
                target_alias = alias
                break
    if target_alias is None:
        return {"player": {"name": name}, "markets": {}, "primary_order": [], "ratelimit": ratelimit.format_status(), "ratelimit_info": ratelimit.get_details()}

    by_book = per_player_odds.get(target_alias, {})
    market_summaries = per_player_summaries.get(target_alias, {})

    # Predicted mean stats per market (averaged over books)
    mean_stats = predict_stats_for_player(by_book)
    # Compute rough impact score = abs(mean * multiplier)
    impacts: Dict[str, float] = {}
    for mkey, mean_val in mean_stats.items():
        rule = STAT_MARKET_MAPPING_SLEEPER.get(mkey)
        mult = 0.0
        try:
            if rule and (rule in scoring_rules):
                mult = float(scoring_rules[rule])
        except Exception:
            mult = 0.0
        impacts[mkey] = abs((mean_val or 0.0) * (mult or 0.0))
    order = sorted(impacts.keys(), key=lambda k: impacts[k], reverse=True)
    primary = order[:5]

    # Build per-market details
    # Also compute per-market stat quantiles and fantasy point contributions
    try:
        from .range_model import compute_fantasy_range_model, compute_fantasy_range
        if (model or "baseline").lower() == "baseline":
            _floor, _mid, _ceil, per_market_ranges = compute_fantasy_range(by_book, market_summaries, scoring_rules)
        else:
            _floor, _mid, _ceil, per_market_ranges = compute_fantasy_range_model(by_book, market_summaries, scoring_rules, model=model)
    except Exception:
        per_market_ranges = {}

    def _fp_triplet_for_market(mkey: str) -> tuple[float, float, float]:
        try:
            rng = per_market_ranges.get(mkey)
            if rng is None:
                return 0.0, 0.0, 0.0
            q10, q50, q90 = rng
            rule = STAT_MARKET_MAPPING_SLEEPER.get(mkey)
            if not rule or rule not in scoring_rules:
                return 0.0, 0.0, 0.0
            mult = float(scoring_rules.get(rule, 0.0) or 0.0)
            if mkey == "player_pass_interceptions":
                mult = -abs(mult)
            return round(q10 * mult, 2), round(q50 * mult, 2), round(q90 * mult, 2)
        except Exception:
            return 0.0, 0.0, 0.0
    markets_out: Dict[str, dict] = {}
    for mkey in set(list(by_book.keys()) + list(market_summaries.keys()) + list(mean_stats.keys()) + list(per_market_ranges.keys())):
        # Per-book rows
        books = []
        alts_out = {"over": [], "under": []}
        for book_key, mkts in by_book.items():
            sides = mkts.get(mkey, {"over": None, "under": None})
            # Collect alt lists if present
            alts = (sides or {}).get("alts")
            if alts and (isinstance(alts, dict)):
                try:
                    for it in (alts.get("over") or []):
                        alts_out["over"].append({"book": book_key, "point": it.get("point"), "odds": it.get("odds")})
                    for it in (alts.get("under") or []):
                        alts_out["under"].append({"book": book_key, "point": it.get("point"), "odds": it.get("odds")})
                except Exception:
                    pass
            books.append({
                "book": book_key,
                "over": sides.get("over"),
                "under": sides.get("under"),
            })
        summ = market_summaries.get(mkey)
        m_summ = None
        if summ is not None:
            m_summ = {
                "avg_threshold": getattr(summ, "avg_threshold", 0.0),
                "avg_over_prob": getattr(summ, "avg_over_prob", 0.0),
                "avg_under_prob": getattr(summ, "avg_under_prob", 0.0),
                "samples": getattr(summ, "samples", 0),
            }
        f_floor, f_mid, f_ceil = _fp_triplet_for_market(mkey)
        entry = {
            "summary": m_summ,
            "mean_stat": mean_stats.get(mkey),
            "impact_score": impacts.get(mkey, 0.0),
            "range": (per_market_ranges.get(mkey) if m_summ is not None or mkey in per_market_ranges else None),
            "fp_floor": f_floor,
            "fp_mid": f_mid,
            "fp_ceiling": f_ceil,
            "books": books,
        }
        # Attach alternates if present (combined across books)
        try:
            if (alts_out["over"] or alts_out["under"]):
                entry["alts"] = alts_out
        except Exception:
            pass
        markets_out[mkey] = entry

    # Build debug math payload mirroring range model logic
    debug_math: Dict[str, object] = {}
    try:
        # Helper: normalized p_over and sigma based on summary
        def _calc_sigma(mean: float, threshold: float, p_over: float, p_under: float) -> tuple[float, float, float, bool]:
            total = (p_over or 0.0) + (p_under or 0.0)
            p = (p_over / total) if total > 0 else 0.5
            # Clamp away from 0/1 to avoid inf
            p = min(max(p, 1e-4), 1 - 1e-4)
            z = NormalDist().inv_cdf(p)
            if abs(z) < 1e-6:
                sigma = max(abs(threshold) * 0.25, 1.0)
                return p, z, sigma, True
            sigma = abs((mean - threshold) / z)
            sigma = max(sigma, 1e-6)
            return p, z, sigma, False

        # Per-market details
        pm_debug: Dict[str, object] = {}
        for mkey, mdata in markets_out.items():
            summ = mdata.get("summary") or {}
            thr = float(summ.get("avg_threshold") or 0.0)
            pov = float(summ.get("avg_over_prob") or 0.0)
            pun = float(summ.get("avg_under_prob") or 0.0)
            mean = float(mdata.get("mean_stat") or 0.0)
            rng = per_market_ranges.get(mkey) or (None, None, None)
            q15, q50, q85 = (None, None, None)
            if rng and isinstance(rng, (list, tuple)) and len(rng) == 3:
                q15, q50, q85 = rng
            pnorm, z, sigma, used_fallback = _calc_sigma(mean, thr, pov, pun) if (mkey != "player_anytime_td" and thr != 0) else (None, None, None, False)
            # FP contributions for this market
            rule = STAT_MARKET_MAPPING_SLEEPER.get(mkey)
            mult = float(scoring_rules.get(rule, 0.0) or 0.0) if rule else 0.0
            if mkey == "player_pass_interceptions":
                mult = -abs(mult)
            fp_floor = round((q15 or 0.0) * mult, 4) if q15 is not None else None
            fp_mid = round((q50 or 0.0) * mult, 4) if q50 is not None else None
            fp_ceil = round((q85 or 0.0) * mult, 4) if q85 is not None else None
            pm_debug[mkey] = {
                "threshold": thr,
                "avg_over_prob": pov,
                "avg_under_prob": pun,
                "p_over_norm": pnorm,
                "z": z,
                "sigma": sigma,
                "sigma_fallback": used_fallback,
                "mean": mean,
                "q15": q15,
                "q50": q50,
                "q85": q85,
                "multiplier_key": rule,
                "multiplier": mult,
                "fp_floor": fp_floor,
                "fp_mid": fp_mid,
                "fp_ceil": fp_ceil,
            }

        # Yardage bonuses at each level
        def _bonus_pass(y: float) -> float:
            try:
                if y is None:
                    return 0.0
                if y >= 400 and ("bonus_pass_yd_400" in scoring_rules):
                    return float(scoring_rules["bonus_pass_yd_400"]) or 0.0
                if y >= 300 and ("bonus_pass_yd_300" in scoring_rules):
                    return float(scoring_rules["bonus_pass_yd_300"]) or 0.0
            except Exception:
                return 0.0
            return 0.0
        def _bonus_rush(y: float) -> float:
            try:
                if y is None:
                    return 0.0
                if y >= 200 and ("bonus_rush_yd_200" in scoring_rules):
                    return float(scoring_rules["bonus_rush_yd_200"]) or 0.0
                if y >= 100 and ("bonus_rush_yd_100" in scoring_rules):
                    return float(scoring_rules["bonus_rush_yd_100"]) or 0.0
            except Exception:
                return 0.0
            return 0.0
        def _bonus_rec(y: float) -> float:
            try:
                if y is None:
                    return 0.0
                if y >= 200 and ("bonus_rec_yd_200" in scoring_rules):
                    return float(scoring_rules["bonus_rec_yd_200"]) or 0.0
                if y >= 100 and ("bonus_rec_yd_100" in scoring_rules):
                    return float(scoring_rules["bonus_rec_yd_100"]) or 0.0
            except Exception:
                return 0.0
            return 0.0

        def _get_stat(qidx: int, key: str) -> Optional[float]:
            rng = per_market_ranges.get(key)
            if not rng:
                return None
            try:
                return float(rng[qidx])
            except Exception:
                return None

        b_floor = (
            (_bonus_rec(_get_stat(0, "player_reception_yds")) or 0.0)
            + (_bonus_rush(_get_stat(0, "player_rush_yds")) or 0.0)
            + (_bonus_pass(_get_stat(0, "player_pass_yds")) or 0.0)
        )
        b_mid = (
            (_bonus_rec(_get_stat(1, "player_reception_yds")) or 0.0)
            + (_bonus_rush(_get_stat(1, "player_rush_yds")) or 0.0)
            + (_bonus_pass(_get_stat(1, "player_pass_yds")) or 0.0)
        )
        b_ceil = (
            (_bonus_rec(_get_stat(2, "player_reception_yds")) or 0.0)
            + (_bonus_rush(_get_stat(2, "player_rush_yds")) or 0.0)
            + (_bonus_pass(_get_stat(2, "player_pass_yds")) or 0.0)
        )

        debug_math = {
            "scoring_rules": scoring_rules,
            "stat_market_map": STAT_MARKET_MAPPING_SLEEPER,
            "mean_stats": mean_stats,
            "per_market": pm_debug,
            "bonuses": {"floor": b_floor, "mid": b_mid, "ceiling": b_ceil},
            "totals": {"floor": _floor, "mid": _mid, "ceiling": _ceil},
        }
    except Exception:
        debug_math = {}

    pinfo = info_by_alias.get(target_alias, {})
    # Importance classification (vital vs minor) with PPR gating
    def _is_ppr(sc: dict) -> bool:
        try:
            return float(sc.get("rec", 0) or 0) > 0
        except Exception:
            return False
    def _importance_for_pos(pos: Optional[str], scoring: dict) -> tuple[set[str], set[str]]:
        p = (pos or "").upper()
        ppr = _is_ppr(scoring)
        vital: set[str] = set()
        minor: set[str] = set()
        if p == "QB":
            vital = {"player_pass_yds", "player_pass_tds", "player_rush_yds", "player_anytime_td"}
            minor = {"player_pass_interceptions"}
        elif p == "RB":
            vital = {"player_rush_yds", "player_anytime_td"}
            (vital.add("player_receptions") if ppr else minor.add("player_receptions"))
            minor.add("player_reception_yds")
        elif p == "WR":
            vital = {"player_reception_yds", "player_anytime_td"}
            (vital.add("player_receptions") if ppr else minor.add("player_receptions"))
            minor.add("player_rush_yds")
        elif p == "TE":
            vital = {"player_reception_yds", "player_anytime_td"}
            (vital.add("player_receptions") if ppr else minor.add("player_receptions"))
            minor.add("player_rush_yds")
        else:
            vital = {"player_anytime_td"}
        # Constrain to whitelist
        vital &= PRIMARY_MARKET_WHITELIST
        minor &= PRIMARY_MARKET_WHITELIST
        return vital, minor
    vital_keys, minor_keys = _importance_for_pos(pinfo.get("primary_position"), scoring_rules)
    payload = {
        "player": {
            "name": pinfo.get("full_name", name or target_alias),
            "pos": pinfo.get("primary_position"),
            "team": pinfo.get("editorial_team_full_name"),
        },
        "markets": markets_out,
        "primary_order": primary,
        "all_order": order,
        "vital_keys": sorted(list(vital_keys)),
        "minor_keys": sorted(list(minor_keys)),
        # Attach raw event odds for debugging/verification
        "raw_odds": ev_odds,
        "ratelimit": ratelimit.format_status(),
        "ratelimit_info": ratelimit.get_details(),
        "debug_math": debug_math,
    }
    return payload


def get_defense_odds_details(username: str, season: str, week: str = "this", defense: str = "", cache_mode: str = "auto", region: str = "us") -> Dict:
    """Return per-book totals/spreads and implied totals for opponent against this defense.

    Sorted by implied total ascending per game, includes medians.
    """
    (this_start, this_end), (next_start, next_end) = compute_week_windows()
    eff_mode = cache_mode
    # Window and events
    start, end = ((this_start, this_end) if week == "this" else (next_start, next_end))
    events = odds_client.get_nfl_events(regions=region, mode=eff_mode)
    window_events = [e for e in events if start <= dt.datetime.strptime(e['commence_time'], "%Y-%m-%dT%H:%M:%SZ") <= end]
    # Find games with this defense
    games = [e for e in window_events if defense in (e.get("home_team"), e.get("away_team"))]
    details = []
    raw_map: Dict[str, object] = {}
    for e in games:
        gid = e["id"]
        opp = e["away_team"] if e["home_team"] == defense else e["home_team"]
        ev_odds = odds_client.get_event_player_odds(gid, markets="spreads,totals", regions=region, mode=eff_mode)
        # Normalize
        ev_obj = ev_odds[0] if isinstance(ev_odds, list) and ev_odds else (ev_odds if isinstance(ev_odds, dict) else None)
        if not ev_obj:
            continue
        raw_map[gid] = ev_obj
        books_rows = []
        implieds = []
        for book in ev_obj.get("bookmakers", []):
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
            impl = None
            try:
                if total_pt is not None and opp_spread is not None:
                    impl = _implied_total(float(total_pt), float(opp_spread))
                    implieds.append(impl)
            except Exception:
                impl = None
            books_rows.append({
                "book": book.get("key"),
                "total_point": total_pt,
                "opponent_spread": opp_spread,
                "opponent_implied": impl,
            })
        median = None
        if implieds:
            implieds.sort()
            median = implieds[len(implieds)//2] if len(implieds) % 2 == 1 else (implieds[len(implieds)//2 -1] + implieds[len(implieds)//2])/2
        details.append({
            "game_id": gid,
            "opponent": opp,
            "commence_time": e.get("commence_time"),
            "books": books_rows,
            "implied_total_median": median,
        })
    # Sort games by implied total ascending
    details.sort(key=lambda g: (g.get("implied_total_median") if g.get("implied_total_median") is not None else 9999))
    return {
        "defense": defense,
        "week": week,
        "games": details,
        # Attach raw event odds map keyed by game id
        "raw_odds": raw_map,
        "ratelimit": ratelimit.format_status(),
        "ratelimit_info": ratelimit.get_details(),
    }






