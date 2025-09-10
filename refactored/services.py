from __future__ import annotations

from typing import Dict, List, Tuple, Optional
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
from config import STAT_MARKET_MAPPING_SLEEPER


def _pick_week_window(which: str, now_utc: Optional[dt.datetime] = None):
    (this_start, this_end), (next_start, next_end) = compute_week_windows(now_utc)
    return (this_start, this_end) if which == "this" else (next_start, next_end)


def _fetch_odds(plan_by_week: Dict[str, Dict[str, object]], cache_mode: str) -> Dict[str, Dict[str, list]]:
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
            print(f"[services] fetch odds week={w} game={gid} markets={len(g.markets)} mode={cache_mode}")
            data = odds_client.get_event_player_odds(event_id=gid, markets=markets_str, mode=cache_mode)
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


def compute_projections(username: str, season: str, week: str = "this", region: str = "us", fresh: bool = False, cache_mode: str = "auto") -> Dict:
    print(f"[services] compute_projections user={username} season={season} week={week} fresh={fresh}")
    # In-process TTL cache
    ttl = int(os.getenv("SERVICE_CACHE_TTL", "120"))
    _proj_cache = getattr(compute_projections, "_cache", {})
    key = (username, season, week, region)
    now = time.time()
    if not fresh and key in _proj_cache:
        ts, payload = _proj_cache[key]
        if now - ts < ttl:
            print(f"[services] compute_projections cache hit key={key} age={int(now-ts)}s")
            return payload
    roster = sleeper_api.get_user_sleeper_data(username, season)
    if not roster:
        return {"players": [], "ratelimit": ratelimit.format_status(), "ratelimit_info": ratelimit.get_details()}

    # Plan games only for requested week
    (this_start, this_end), (next_start, next_end) = compute_week_windows()
    eff_mode = 'fresh' if fresh else cache_mode
    plan_all = plan_relevant_games_and_markets(roster, ((this_start, this_end), (next_start, next_end)), regions=region, cache_mode=eff_mode)
    plan = {week: plan_all.get(week, {})}

    odds_by_week = _fetch_odds(plan, cache_mode=eff_mode)
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
    payload = {"week": week, "players": players_out, "ratelimit": ratelimit.format_status(), "ratelimit_info": ratelimit.get_details()}
    # store in cache
    _proj_cache[key] = (now, payload)
    compute_projections._cache = _proj_cache
    return payload


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
        rows.append({
            "slot": slot,
            "name": p["name"],
            "pos": p["pos"],
            # keep team in payload for future, UI may ignore it
            "team": p.get("team"),
            "points": round(pts, 2),
            # include full trio for UI rendering
            "floor": round(float(p.get("floor", 0.0)), 2),
            "mid": round(float(p.get("mid", 0.0)), 2),
            "ceiling": round(float(p.get("ceiling", 0.0)), 2),
        })

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


def list_defenses(username: str, season: str, week: str = "this", scope: str = "both", fresh: bool = False, cache_mode: str = "auto") -> Dict:
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
    events = odds_client.get_nfl_events(mode=eff_mode)
    window_events = [e for e in events if start <= dt.datetime.strptime(e['commence_time'], "%Y-%m-%dT%H:%M:%SZ") <= end]

    # Prefetch odds per event once to avoid duplicate calls per team
    ev_odds_map = {}
    for e in window_events:
        gid = e["id"]
        try:
            ev_odds_map[gid] = odds_client.get_event_player_odds(gid, markets="spreads,totals", mode=eff_mode)
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
        proj_this = compute_projections(username=username, season=season, week="this", region=region, fresh=fresh, cache_mode=('fresh' if fresh else cache_mode))
    if weeks in ("next", "both"):
        proj_next = compute_projections(username=username, season=season, week="next", region=region, fresh=fresh, cache_mode=('fresh' if fresh else cache_mode))

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


def get_player_odds_details(username: str, season: str, week: str = "this", region: str = "us", name: str = "", cache_mode: str = "auto") -> Dict:
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
    odds_by_week = _fetch_odds({week: planned}, cache_mode=eff_mode)
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
    markets_out: Dict[str, dict] = {}
    for mkey in set(list(by_book.keys()) + list(market_summaries.keys()) + list(mean_stats.keys())):
        # Per-book rows
        books = []
        for book_key, mkts in by_book.items():
            sides = mkts.get(mkey, {"over": None, "under": None})
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
        markets_out[mkey] = {
            "summary": m_summ,
            "mean_stat": mean_stats.get(mkey),
            "impact_score": impacts.get(mkey, 0.0),
            "books": books,
        }

    pinfo = info_by_alias.get(target_alias, {})
    payload = {
        "player": {
            "name": pinfo.get("full_name", name or target_alias),
            "pos": pinfo.get("primary_position"),
            "team": pinfo.get("editorial_team_full_name"),
        },
        "markets": markets_out,
        "primary_order": primary,
        "all_order": order,
        "ratelimit": ratelimit.format_status(),
        "ratelimit_info": ratelimit.get_details(),
    }
    return payload


def get_defense_odds_details(username: str, season: str, week: str = "this", defense: str = "", cache_mode: str = "auto") -> Dict:
    """Return per-book totals/spreads and implied totals for opponent against this defense.

    Sorted by implied total ascending per game, includes medians.
    """
    (this_start, this_end), (next_start, next_end) = compute_week_windows()
    eff_mode = cache_mode
    # Window and events
    start, end = ((this_start, this_end) if week == "this" else (next_start, next_end))
    events = odds_client.get_nfl_events(mode=eff_mode)
    window_events = [e for e in events if start <= dt.datetime.strptime(e['commence_time'], "%Y-%m-%dT%H:%M:%SZ") <= end]
    # Find games with this defense
    games = [e for e in window_events if defense in (e.get("home_team"), e.get("away_team"))]
    details = []
    for e in games:
        gid = e["id"]
        opp = e["away_team"] if e["home_team"] == defense else e["home_team"]
        ev_odds = odds_client.get_event_player_odds(gid, markets="spreads,totals", mode=eff_mode)
        # Normalize
        ev_obj = ev_odds[0] if isinstance(ev_odds, list) and ev_odds else (ev_odds if isinstance(ev_odds, dict) else None)
        if not ev_obj:
            continue
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
        "ratelimit": ratelimit.format_status(),
        "ratelimit_info": ratelimit.get_details(),
    }
