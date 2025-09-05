from __future__ import annotations

import argparse
from typing import Dict

import sleeper_api

from .weekly_windows import compute_week_windows
from .planner import plan_relevant_games_and_markets
from .aggregator import aggregate_by_week
from .range_model import compute_fantasy_range
from . import ratelimit
from . import odds_client
from .debug_tools import debug_rb_calculations, debug_wr_calculations, debug_te_calculations


def _print_header(msg: str):
    print("\n" + "=" * 80)
    print(msg)
    print("=" * 80)


def _print_ratelimit(tag: str = ""):
    status = ratelimit.format_status()
    if tag:
        print(f"[RateLimit] {tag} | {status}")
    else:
        print(f"[RateLimit] {status}")


def _print_plan_summary(plan_by_week: Dict[str, dict]):
    for w in ("this", "next"):
        plan = plan_by_week.get(w, {})
        games = len(plan)
        players = sum(len(g.players) for g in plan.values())
        print(f"  {w.title()} Week -> {games} games, {players} roster players involved")
        for gid, g in list(plan.items())[:5]:
            ts = g.commence_time
            print(f"    - {gid} | {g.away_team} @ {g.home_team} | {ts} | markets {len(g.markets)}")
            if g.markets:
                sample = ", ".join(g.markets[:3])
                print(f"      markets sample: {sample}")


def _fetch_event_odds_for_plan(plan_by_week: Dict[str, dict], use_saved_data: bool) -> Dict[str, Dict[str, list]]:
    out: Dict[str, Dict[str, list]] = {"this": {}, "next": {}}
    SAFE_MARKETS = {
        # widely supported
        "player_anytime_td",
        "player_receptions",
        "player_receptions_alternate",
        "player_reception_yds",
        "player_rush_yds",
        "player_rush_yds_alternate",
        "player_pass_yds",
        "player_pass_tds",
        # interceptions are commonly supported, keep as soft-safe
        "player_pass_interceptions",
    }
    for w in ("this", "next"):
        plan = plan_by_week.get(w, {})
        for gid, g in plan.items():
            markets = sorted(set(g.markets))
            markets_str = ",".join(markets)
            print(f"    Fetching odds for {w} week game {gid} | markets={len(markets)}")
            try:
                out[w][gid] = odds_client.get_event_player_odds(event_id=gid, markets=markets_str, use_saved_data=use_saved_data)
                _print_ratelimit(f"after fetch {w}:{gid}")
            except Exception as e:
                print(f"      fetch failed ({type(e).__name__}): {e}")
                # retry with safe subset
                filt = [m for m in markets if m in SAFE_MARKETS]
                if filt and filt != markets:
                    print(f"      retrying with safe markets subset ({len(filt)})")
                    try:
                        out[w][gid] = odds_client.get_event_player_odds(event_id=gid, markets=",".join(filt), use_saved_data=use_saved_data)
                        _print_ratelimit(f"after fetch (safe subset) {w}:{gid}")
                    except Exception as e2:
                        print(f"      still failed: {e2}; skipping game {gid}")
                else:
                    print(f"      no safe subset available; skipping game {gid}")
    return out


def _format_table(rows, headers):
    cols = list(zip(*([headers] + rows))) if rows else [headers]
    widths = [max(len(str(c)) for c in col) for col in cols]
    fmt = "  ".join([f"{{:<{w}}}" for w in widths])
    print(fmt.format(*headers))
    print("  ".join(["-" * w for w in widths]))
    for r in rows:
        print(fmt.format(*r))


def run(username: str, season: str, use_saved_data: bool, region: str, debug_positions: set[str] | None = None):
    # Step 1: Roster
    _print_header("Step 1/5: Fetch roster from Sleeper")
    roster = sleeper_api.get_user_sleeper_data(username, season)
    if not roster:
        print("No roster found.")
        return
    players = roster.get("players", {})
    print(f"Fetched {len(players)} players. Example:")
    for pid, p in list(players.items())[:5]:
        print(f"  - {p['name']['full']} | {p.get('primary_position')} | {p.get('editorial_team_full_name')}")
    # Positions breakdown
    pos_counts = {}
    for p in players.values():
        pos = p.get('primary_position') or 'UNK'
        pos_counts[pos] = pos_counts.get(pos, 0) + 1
    if pos_counts:
        print("  Positions:")
        for pos in sorted(pos_counts.keys()):
            print(f"    {pos}: {pos_counts[pos]}")

    # Step 2: Week windows
    _print_header("Step 2/5: Determine this and next week windows (Thu->Mon)")
    (this_start, this_end), (next_start, next_end) = compute_week_windows()
    print(f"  This week: {this_start.isoformat()}Z -> {this_end.isoformat()}Z")
    print(f"  Next week: {next_start.isoformat()}Z -> {next_end.isoformat()}Z")
    _print_ratelimit("after windows")

    # Step 3: Plan minimal event-odds calls
    _print_header("Step 3/5: Plan relevant games and markets")
    plan_by_week = plan_relevant_games_and_markets(
        roster,
        ((this_start, this_end), (next_start, next_end)),
        regions=region,
        use_saved_data=use_saved_data,
    )
    _print_plan_summary(plan_by_week)
    _print_ratelimit("after planning")

    # Step 4: Fetch odds only for planned games
    _print_header("Step 4/5: Fetch event odds (cached by default)")
    odds_by_week = _fetch_event_odds_for_plan(plan_by_week, use_saved_data=use_saved_data)
    for w in ("this", "next"):
        print(f"  {w.title()} Week -> fetched odds for {len(odds_by_week[w])} games")
    _print_ratelimit("after fetch")

    # Step 5: Aggregate and compute ranges
    _print_header("Step 5/5: Predict floor/mid/ceiling fantasy points")
    for w in ("this", "next"):
        planned = plan_by_week.get(w, {})
        ev_odds = odds_by_week.get(w, {})
        per_player_odds, per_player_summaries = aggregate_by_week(ev_odds, planned)
        rows = []
        info_by_alias = {}
        for g in planned.values():
            for p in g.players:
                info_by_alias[p["alias"]] = p

        for alias, by_book in per_player_odds.items():
            p_info = info_by_alias.get(alias, {})
            scoring_rules = roster.get("scoring_rules", {})
            floor, mid, ceil, _ = compute_fantasy_range(by_book, per_player_summaries.get(alias, {}), scoring_rules)
            rows.append([
                p_info.get("full_name", alias),
                p_info.get("primary_position", ""),
                p_info.get("editorial_team_full_name", ""),
                f"{floor:.2f}",
                f"{mid:.2f}",
                f"{ceil:.2f}",
            ])

            # Optional detailed debug per position
            if debug_positions:
                pos = (p_info.get("primary_position") or "").upper()
                try:
                    if "RB" in debug_positions and pos == "RB":
                        debug_rb_calculations(p_info.get("full_name", alias), p_info, by_book, per_player_summaries.get(alias, {}), scoring_rules)
                    if "WR" in debug_positions and pos == "WR":
                        debug_wr_calculations(p_info.get("full_name", alias), p_info, by_book, per_player_summaries.get(alias, {}), scoring_rules)
                    if "TE" in debug_positions and pos == "TE":
                        debug_te_calculations(p_info.get("full_name", alias), p_info, by_book, per_player_summaries.get(alias, {}), scoring_rules)
                except Exception as e:
                    print(f"[DEBUG] error while debugging {p_info.get('full_name', alias)} ({pos}): {e}")

        rows.sort(key=lambda r: float(r[4]), reverse=True)
        print(f"{w.title()} Week Projections (players with available markets): {len(rows)}")
        if rows:
            _format_table(rows, headers=("Player", "Pos", "Team", "Floor", "Mid", "Ceiling"))
        else:
            print("  No player markets found in this window.")
        # Debug summary of markets aggregated
        total_markets = sum(len(mkts) for mkts in per_player_summaries.values())
        unique_markets = set()
        for mkts in per_player_summaries.values():
            unique_markets.update(mkts.keys())
        print(f"  Markets summarized: {total_markets} across {len(unique_markets)} unique keys")
        _print_ratelimit(f"after projections {w}")


def main():
    parser = argparse.ArgumentParser(description="Fantasy odds pipeline with debug steps")
    parser.add_argument("--username", default="wesnicol", help="Sleeper username")
    parser.add_argument("--season", default="2025", help="Season year, e.g. 2025")
    parser.add_argument("--region", default="us", help="Odds API region, default 'us'")
    parser.add_argument("--fresh", action="store_true", help="Fetch fresh odds (ignore cache)")
    parser.add_argument("--debug-positions", default="", help="Comma-separated positions to debug in detail (e.g., RB,WR)")
    args = parser.parse_args()

    dbg = {p.strip().upper() for p in args.debug_positions.split(',')} if args.debug_positions else set()
    if "" in dbg:
        dbg.discard("")
    run(username=args.username, season=args.season, use_saved_data=not args.fresh, region=args.region, debug_positions=dbg if dbg else None)


if __name__ == "__main__":
    main()
