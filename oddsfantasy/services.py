from __future__ import annotations

import contextlib
import datetime as dt
import os
import time

from . import draft_prep, odds_client, ratelimit, sleeper_api
from .aggregator import aggregate_by_week
from .config import POSITION_STAT_CONFIG, SLEEPER_TO_ODDSAPI_TEAM
from .lineup import build_lineup
from .planner import plan_relevant_games_and_markets
from .range_model import (
    PRIMARY_MARKET_WHITELIST,
    compute_defense_fantasy_range,
    compute_fantasy_range,
)
from .weekly_windows import compute_week_windows, resolve_week_windows

COVERAGE_MARKET_ORDER = [
    "player_anytime_td",
    "player_reception_yds",
    "player_rush_yds",
    "player_pass_yds",
    "player_pass_tds",
    "player_pass_interceptions",
    "player_receptions",
]


def _resolve_identity(
    username: str, season: str, league_id: str | None = None, roster_id: int | None = None
) -> dict:
    """Resolve {'players', 'scoring_rules', ...} for the caller's team.

    `league_id` (when given) is authoritative: an explicit league+team
    selection beats the legacy username-based "first league for this user"
    guess, which silently picks the wrong league for anyone in more than
    one. Falls back to the username/season path when league_id isn't
    provided, so existing callers keep working unchanged.
    """
    if league_id:
        return sleeper_api.get_league_roster_data(league_id, roster_id=roster_id)
    return sleeper_api.get_user_sleeper_data(username, season) or {}


def resolve_user_leagues(username: str, season: str) -> dict:
    """List a Sleeper user's leagues for a season, for the "pick your
    league" step of the identity flow. Powered by username (which everyone
    already knows) rather than requiring you to dig a league ID out of a
    Sleeper URL -- once a league is picked from this list, `resolve_league`
    and everything downstream operates on its league_id, not the username.
    """
    try:
        user_id = sleeper_api.get_user_id(username)
    except Exception as e:
        print(f"[services] resolve_user_leagues: user lookup failed for {username}: {e}")
        return {"error": "user_not_found", "username": username}
    try:
        leagues = sleeper_api.get_user_leagues(user_id, season)
    except Exception as e:
        print(f"[services] resolve_user_leagues: league lookup failed for user_id={user_id}: {e}")
        leagues = []
    return {
        "username": username,
        "user_id": user_id,
        "season": season,
        "leagues": [
            {
                "league_id": lg.get("league_id"),
                "name": lg.get("name"),
                "status": lg.get("status"),
                "season": lg.get("season"),
            }
            for lg in (leagues or [])
        ],
    }


def resolve_league(league_id: str) -> dict:
    """Given a Sleeper league ID, return everything the UI needs to drive
    the "paste your league ID -> pick your team" flow:
      - status: Sleeper's own "pre_draft" | "drafting" | "in_season" |
        "complete" -- the actual source of truth for whether the league has
        drafted yet, used to decide whether to default to the draft board
        or the weekly lineup views.
      - teams: one entry per roster, for a team picker.
    """
    try:
        league = sleeper_api.get_league(league_id)
    except Exception as e:
        print(f"[services] resolve_league: lookup failed for {league_id}: {e}")
        return {"error": "league_not_found", "league_id": league_id}
    try:
        teams = sleeper_api.get_league_teams(league_id)
    except Exception as e:
        print(f"[services] resolve_league: team list failed for {league_id}: {e}")
        teams = []
    return {
        "league_id": league_id,
        "name": league.get("name"),
        "season": league.get("season"),
        "status": league.get("status"),
        "teams": teams,
    }


def _pick_week_window(which: str, now_utc: dt.datetime | None = None):
    (this_start, this_end), (next_start, next_end) = compute_week_windows(now_utc)
    return (this_start, this_end) if which == "this" else (next_start, next_end)


# Shown whenever resolve_week_windows() finds no games at all -- neither in
# today's calendar window nor anywhere later in the odds feed (the schedule
# for the target season/week isn't posted yet). See weekly_windows.py.
NO_GAMES_SCHEDULED_MESSAGE = (
    "No scheduled games found yet for this week. Check back once the "
    "season's schedule/odds are posted."
)


def _fetch_odds(
    plan_by_week: dict[str, dict[str, object]], cache_mode: str, regions: str = "us"
) -> dict[str, dict[str, list]]:
    """Fetch event odds concurrently per week for planned games.

    Uses a small thread pool to parallelize network calls when cache misses occur.
    """
    from concurrent.futures import ThreadPoolExecutor, as_completed

    out: dict[str, dict[str, list]] = {"this": {}, "next": {}}
    for w in ("this", "next"):
        items = list(plan_by_week.get(w, {}).items())
        if not items:
            continue
        max_workers = min(8, max(1, len(items)))

        def task(pair, w=w):
            gid, g = pair
            markets_str = ",".join(sorted(set(g.markets)))
            print(
                f"[services] fetch odds week={w} game={gid} markets={len(g.markets)} regions={regions} mode={cache_mode}"
            )
            data = odds_client.get_event_player_odds(
                event_id=gid, markets=markets_str, regions=regions, mode=cache_mode
            )
            return gid, data

        with ThreadPoolExecutor(max_workers=max_workers) as ex:
            futures = [ex.submit(task, it) for it in items]
            for fut in as_completed(futures):
                try:
                    gid, data = fut.result()
                    out[w][gid] = data
                except Exception as e:
                    print(f"[services] fetch odds error: {e}")
        print(
            f"[services] fetch odds week={w} complete; games={len(out[w])} rl={ratelimit.format_status()}"
        )
    return out


def compute_projections(
    username: str,
    season: str,
    week: str = "this",
    region: str = "us",
    fresh: bool = False,
    cache_mode: str = "auto",
    model: str = "const",
    league_id: str | None = None,
    roster_id: int | None = None,
) -> dict:
    print(
        f"[services] compute_projections user={username} season={season} week={week} fresh={fresh} league_id={league_id} roster_id={roster_id}"
    )
    # In-process TTL cache
    ttl = int(os.getenv("SERVICE_CACHE_TTL", "120"))
    _proj_cache = getattr(compute_projections, "_cache", {})
    key = (username, season, week, region, model, league_id, roster_id)
    now = time.time()
    if not fresh and key in _proj_cache:
        ts, payload = _proj_cache[key]
        if now - ts < ttl:
            print(f"[services] compute_projections cache hit key={key} age={int(now - ts)}s")
            return payload
    try:
        roster = _resolve_identity(username, season, league_id, roster_id)
    except Exception as e:
        print(f"[services] sleeper error: {e}")
        # Graceful fallback: continue with empty roster so UI can load
        return {
            "players": [],
            "ratelimit": ratelimit.format_status(),
            "ratelimit_info": ratelimit.get_details(),
            "error": "sleeper_timeout",
        }
    if not roster:
        return {
            "players": [],
            "ratelimit": ratelimit.format_status(),
            "ratelimit_info": ratelimit.get_details(),
        }

    # Plan games only for requested week
    eff_mode = "fresh" if fresh else cache_mode
    events = odds_client.get_nfl_events(regions=region, mode=eff_mode)
    windows = resolve_week_windows(events)
    if windows is None:
        return {
            "players": [],
            "ratelimit": ratelimit.format_status(),
            "ratelimit_info": ratelimit.get_details(),
            "message": NO_GAMES_SCHEDULED_MESSAGE,
        }
    (this_start, this_end), (next_start, next_end) = windows
    plan_all = plan_relevant_games_and_markets(
        roster,
        ((this_start, this_end), (next_start, next_end)),
        regions=region,
        cache_mode=eff_mode,
    )
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
        print(
            f"[services] aggregate matched_players={matched_players} planned_players={planned_players} games={len(planned)}"
        )
    except Exception:
        pass

    # Build info index
    info_by_alias: dict[str, dict] = {}
    for g in planned.values():
        for p in g.players:
            info_by_alias[p["alias"]] = p

    scoring_rules = roster.get("scoring_rules", {})
    players_out: list[dict] = []

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

    def _importance_for_pos(pos: str | None, scoring: dict) -> tuple[set[str], set[str]]:
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
        elif p == "WR" or p == "TE":
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
        vital_exp, minor_exp = _importance_for_pos(pinfo.get("primary_position"), scoring_rules)
        vital_exp, minor_exp = _importance_for_pos(pinfo.get("primary_position"), scoring_rules)
        from .range_model import compute_fantasy_range, compute_fantasy_range_model

        if (model or "baseline").lower() == "baseline":
            floor, mid, ceil, _ = compute_fantasy_range(
                by_book, per_player_summaries.get(alias, {}), scoring_rules
            )
        else:
            floor, mid, ceil, _ = compute_fantasy_range_model(
                by_book, per_player_summaries.get(alias, {}), scoring_rules, model=model
            )

        # Coverage diagnostics
        available: set[str] = set()
        for mkts in (by_book or {}).values():
            for mkey in mkts or {}:
                available.add(_norm_market_key(mkey))
        pos = pinfo.get("primary_position")
        vital_exp, minor_exp = _importance_for_pos(pos, scoring_rules)
        expected = vital_exp | minor_exp
        missing_set = expected - available
        missing = sorted(missing_set)
        missing_vital = sorted(missing_set & vital_exp)
        missing_minor = sorted(missing_set & minor_exp)
        # Summary keys; if absent, we used fallback band
        summ_keys = {_norm_market_key(k) for k in (per_player_summaries.get(alias, {}) or {})}
        fallback_set = {k for k in available if k not in summ_keys}
        fallback = sorted(fallback_set)
        fallback_vital = sorted(fallback_set & vital_exp)
        fallback_minor = sorted(fallback_set & minor_exp)

        players_out.append(
            {
                "name": pinfo.get("full_name", alias),
                "pos": pos,
                "team": pinfo.get("editorial_team_full_name"),
                "alias": alias,
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
                "vital_markets": sorted(vital_exp),
                "minor_markets": sorted(minor_exp),
            }
        )

    # Add planned roster players with no odds as incomplete entries
    for alias, pinfo in info_by_alias.items():
        if alias in present_aliases:
            continue
        # For players with no odds, mark expected markets as missing with importance split
        pos = pinfo.get("primary_position")
        vital_exp, minor_exp = _importance_for_pos(pos, scoring_rules)
        exp_all = sorted(vital_exp | minor_exp)
        players_out.append(
            {
                "name": pinfo.get("full_name", alias),
                "pos": pos,
                "team": pinfo.get("editorial_team_full_name"),
                "alias": alias,
                "floor": None,
                "mid": None,
                "ceiling": None,
                "books_used": 0,
                "markets_used": 0,
                "incomplete": True,
                "missing_markets": exp_all,
                "fallback_markets": [],
                "missing_vital": sorted(vital_exp),
                "missing_minor": sorted(minor_exp),
                "fallback_vital": [],
                "fallback_minor": [],
                "is_critical": bool(vital_exp),
                "vital_markets": sorted(vital_exp),
                "minor_markets": sorted(minor_exp),
            }
        )

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
                alias = p.get("alias") or p.get("player_id") or full_name
                players_out.append(
                    {
                        "name": full_name,
                        "pos": pos,
                        "team": team,
                        "alias": alias,
                        "floor": None,
                        "mid": None,
                        "ceiling": None,
                        "books_used": 0,
                        "markets_used": 0,
                        "incomplete": True,
                        "missing_markets": exp_all,
                        "fallback_markets": [],
                        "missing_vital": sorted(vital_exp),
                        "missing_minor": sorted(minor_exp),
                        "fallback_vital": [],
                        "fallback_minor": [],
                        "is_critical": bool(vital_exp),
                        "vital_markets": sorted(vital_exp),
                        "minor_markets": sorted(minor_exp),
                    }
                )
            except Exception:
                continue
    except Exception:
        pass

    # Optional debug: summarize market coverage and usage
    try:
        if os.getenv("API_DEBUG") in ("1", "true", "True"):
            # Collect raw and normalized market keys across players
            all_raw: set[str] = set()
            for by_book in per_player_odds.values():
                for mkts in (by_book or {}).values():
                    for mkey in mkts or {}:
                        all_raw.add(mkey)
            all_norm = {_norm_market_key(k) for k in all_raw}
            used_norm = {k for k in all_norm if k in PRIMARY_MARKET_WHITELIST}
            ignored_norm = sorted(all_norm - used_norm)
            print(
                f"[services][debug] markets: raw={len(all_raw)} norm={len(all_norm)} used={len(used_norm)} ignored={len(ignored_norm)}"
            )
            if ignored_norm:
                print(f"[services][debug] markets_ignored_norm: {', '.join(sorted(ignored_norm))}")

            # Per-player gaps (limit output size)
            missing_players = [p for p in players_out if p.get("incomplete")]
            print(
                f"[services][debug] players_with_missing={len(missing_players)} / total={len(players_out)}"
            )
            for p in missing_players[:12]:
                miss = ", ".join(p.get("missing_markets") or [])
                fb = ", ".join(p.get("fallback_markets") or [])
                print(
                    f"[services][debug] missing: {p.get('name')} ({p.get('pos')}) -> missing=[{miss}] fallback=[{fb}]"
                )
    except Exception as _dbg_e:
        with contextlib.suppress(Exception):
            print(f"[services][debug] error: {_dbg_e!s}")

    # Sort by mid desc, placing missing mids (None) at the end
    players_out.sort(
        key=lambda x: x.get("mid") if isinstance(x.get("mid"), (int, float)) else float("-inf"),
        reverse=True,
    )

    def _blank_coverage_counts() -> dict[str, int]:
        return dict.fromkeys(COVERAGE_MARKET_ORDER, 0)

    def _market_has_line(entry: object) -> bool:
        if not isinstance(entry, dict):
            return bool(entry)
        if entry.get("over"):
            return True
        if entry.get("under"):
            return True
        alts = entry.get("alts")
        if isinstance(alts, dict):
            over_alts = alts.get("over")
            if over_alts:
                return True
            under_alts = alts.get("under")
            if under_alts:
                return True
        return False

    coverage_counts: dict[str, dict[str, int]] = {}
    for alias, books in per_player_odds.items():
        tracker = {market: set() for market in COVERAGE_MARKET_ORDER}
        for book_key, mkts in (books or {}).items():
            for raw_key, rec in (mkts or {}).items():
                norm_key = _norm_market_key(raw_key)
                if norm_key in tracker and _market_has_line(rec):
                    tracker[norm_key].add(book_key)
        coverage_counts[alias] = {market: len(book_keys) for market, book_keys in tracker.items()}

    for alias, mkts in (per_player_summaries or {}).items():
        current = coverage_counts.setdefault(alias, _blank_coverage_counts())
        for raw_key, summary in (mkts or {}).items():
            norm_key = _norm_market_key(raw_key)
            if norm_key not in current:
                continue
            try:
                samples = int(getattr(summary, "samples", 0) or 0)
            except Exception:
                samples = 0
            if samples > current[norm_key]:
                current[norm_key] = samples

    coverage_rows: list[dict] = []
    seen_aliases: set[str] = set()
    for pdata in players_out:
        alias = pdata.get("alias")
        counts = _blank_coverage_counts()
        if alias and alias in coverage_counts:
            src_counts = coverage_counts.get(alias, {})
            for market in COVERAGE_MARKET_ORDER:
                try:
                    counts[market] = int(src_counts.get(market, 0) or 0)
                except Exception:
                    counts[market] = 0
            seen_aliases.add(alias)
        pdata_vital: set[str] = set()
        for _item in pdata.get("vital_markets") or []:
            try:
                _mk = _norm_market_key(_item)
            except Exception:
                _mk = None
            if _mk:
                pdata_vital.add(_mk)
        pdata_minor: set[str] = set()
        for _item in pdata.get("minor_markets") or []:
            try:
                _mk2 = _norm_market_key(_item)
            except Exception:
                _mk2 = None
            if _mk2:
                pdata_minor.add(_mk2)
        if not pdata_vital and not pdata_minor:
            alt_pos = pdata.get("pos")
            alt_vital, alt_minor = _importance_for_pos(alt_pos, scoring_rules)
            pdata_vital = set(alt_vital)
            pdata_minor = set(alt_minor)
        coverage_rows.append(
            {
                "alias": alias,
                "name": pdata.get("name"),
                "pos": pdata.get("pos"),
                "team": pdata.get("team"),
                "markets": counts,
                "total_books": int(sum(counts.values())),
                "incomplete": bool(pdata.get("incomplete")),
                "vital_markets": sorted(pdata_vital),
                "minor_markets": sorted(pdata_minor),
            }
        )

    for alias, counts_dict in coverage_counts.items():
        if not alias or alias in seen_aliases:
            continue
        fallback_counts = _blank_coverage_counts()
        for market in COVERAGE_MARKET_ORDER:
            try:
                fallback_counts[market] = int(counts_dict.get(market, 0) or 0)
            except Exception:
                fallback_counts[market] = 0
        pinfo = info_by_alias.get(alias, {})
        vital_exp, minor_exp = _importance_for_pos(pinfo.get("primary_position"), scoring_rules)
        coverage_rows.append(
            {
                "alias": alias,
                "name": pinfo.get("full_name", alias),
                "pos": pinfo.get("primary_position"),
                "team": pinfo.get("editorial_team_full_name"),
                "markets": fallback_counts,
                "total_books": int(sum(fallback_counts.values())),
                "incomplete": True,
                "vital_markets": sorted(vital_exp),
                "minor_markets": sorted(minor_exp),
            }
        )

    payload = {
        "week": week,
        "players": players_out,
        "ratelimit": ratelimit.format_status(),
        "ratelimit_info": ratelimit.get_details(),
        "book_coverage": {
            "markets": list(COVERAGE_MARKET_ORDER),
            "rows": coverage_rows,
        },
    }
    # store in cache
    _proj_cache[key] = (now, payload)
    compute_projections._cache = _proj_cache
    return payload


def compute_draft_board(
    username: str,
    season: str,
    week: str = "this",
    region: str = "us",
    fresh: bool = False,
    cache_mode: str = "auto",
    model: str = "const",
    positions: list[str] | None = None,
    league_id: str | None = None,
    roster_id: int | None = None,
) -> dict:
    """Floor/mid/ceiling for every active skill player on every team playing
    in the target week -- not scoped to any roster. Meant for pre-draft prep,
    when there's no roster to scope to yet (or the league's roster is still
    empty). Reuses the exact same odds-devig -> quantile -> fantasy-points
    pipeline as compute_projections(); the only real difference is where the
    player list comes from (oddsfantasy/draft_prep.py, sourced from Sleeper's
    full player DB) and that it uses a smaller, quota-conscious market set.

    Only `scoring_rules` is needed here (there's no roster to scope the
    player list to -- that's the whole point), so this works fine with just
    a league_id and no roster_id, i.e. before a team has been picked.
    """
    print(
        f"[services] compute_draft_board season={season} week={week} fresh={fresh} positions={positions} league_id={league_id}"
    )
    try:
        roster = _resolve_identity(username, season, league_id, roster_id)
    except Exception as e:
        print(f"[services] draft_board: sleeper scoring lookup failed: {e}")
        roster = None
    scoring_rules = (roster or {}).get("scoring_rules", {}) if roster else {}

    eff_mode = "fresh" if fresh else cache_mode
    plan = draft_prep.plan_week_for_draft(week=week, regions=region, cache_mode=eff_mode)
    odds_by_week = _fetch_odds({week: plan}, cache_mode=eff_mode, regions=region)
    ev_odds = odds_by_week.get(week, {})

    per_player_odds, per_player_summaries = aggregate_by_week(ev_odds, plan)

    info_by_alias: dict[str, dict] = {}
    for g in plan.values():
        for p in g.players:
            info_by_alias[p["alias"]] = p

    from .range_model import compute_fantasy_range_model

    pos_filter = {p.upper() for p in positions} if positions else None
    board: list[dict] = []
    for alias, by_book in per_player_odds.items():
        pinfo = info_by_alias.get(alias, {})
        pos = pinfo.get("primary_position")
        if pos_filter and pos not in pos_filter:
            continue
        if (model or "baseline").lower() == "baseline":
            floor, mid, ceil, _ = compute_fantasy_range(
                by_book, per_player_summaries.get(alias, {}), scoring_rules
            )
        else:
            floor, mid, ceil, _ = compute_fantasy_range_model(
                by_book, per_player_summaries.get(alias, {}), scoring_rules, model=model
            )
        board.append(
            {
                "name": pinfo.get("full_name", alias),
                "pos": pos,
                "team": pinfo.get("editorial_team_full_name"),
                "floor": round(floor, 2),
                "mid": round(mid, 2),
                "ceiling": round(ceil, 2),
                "books_used": len(by_book.keys()),
                "markets_used": len(per_player_summaries.get(alias, {})),
            }
        )

    board.sort(key=lambda r: r["mid"], reverse=True)

    # Surface the actual resolved date range so "Week 1"/"Week 2" is never
    # ambiguous -- these are schedule-anchored (earliest games found), not
    # anchored to today, so they won't line up with the calendar in any
    # obvious way. See draft_prep._resolve_draft_week_window.
    window_start = window_end = None
    if plan:
        game_starts = sorted(g.commence_time for g in plan.values())
        window_start, window_end = game_starts[0], game_starts[-1]

    payload = {
        "week": week,
        "window_start": window_start,
        "window_end": window_end,
        "players": board,
        "ratelimit": ratelimit.format_status(),
        "ratelimit_info": ratelimit.get_details(),
    }
    if not plan:
        payload["message"] = (
            "No scheduled games found yet for this window. Draft-board weeks "
            "are anchored to the earliest games in the odds feed, not "
            "today's date -- check back once the season's schedule/odds are "
            "posted (usually a couple weeks before Week 1)."
        )
    print(
        f"[services] compute_draft_board done players={len(board)} window=({window_start}..{window_end})"
    )
    return payload


def compute_book_coverage(
    username: str,
    season: str,
    week: str = "this",
    region: str = "us",
    fresh: bool = False,
    cache_mode: str = "auto",
    model: str = "const",
    league_id: str | None = None,
    roster_id: int | None = None,
) -> dict:
    data = compute_projections(
        username=username,
        season=season,
        week=week,
        region=region,
        fresh=fresh,
        cache_mode=cache_mode,
        model=model,
        league_id=league_id,
        roster_id=roster_id,
    )
    coverage = data.get("book_coverage") or {}
    markets = list(coverage.get("markets") or COVERAGE_MARKET_ORDER)
    rows_out: list[dict] = []
    for row in coverage.get("rows") or []:
        raw_markets = row.get("markets") or {}
        markets_map = dict.fromkeys(COVERAGE_MARKET_ORDER, 0)
        for market in COVERAGE_MARKET_ORDER:
            try:
                markets_map[market] = int(raw_markets.get(market, 0) or 0)
            except Exception:
                markets_map[market] = 0
        for extra_key, extra_val in raw_markets.items() if hasattr(raw_markets, "items") else []:
            if extra_key not in markets_map:
                try:
                    markets_map[extra_key] = int(extra_val or 0)
                except Exception:
                    markets_map[extra_key] = 0
        total = int(sum(markets_map.values()))
        vital_list = [str(v) for v in (row.get("vital_markets") or [])]
        minor_list = [str(v) for v in (row.get("minor_markets") or [])]
        rows_out.append(
            {
                "alias": row.get("alias"),
                "name": row.get("name"),
                "pos": row.get("pos"),
                "team": row.get("team"),
                "markets": markets_map,
                "total_books": total,
                "incomplete": bool(row.get("incomplete")),
                "vital_markets": vital_list,
                "minor_markets": minor_list,
            }
        )
    return {
        "week": data.get("week", week),
        "coverage": {
            "markets": markets,
            "rows": rows_out,
        },
        "ratelimit": data.get("ratelimit"),
        "ratelimit_info": data.get("ratelimit_info"),
    }


def _implied_total(game_total: float, team_spread: float) -> float:
    return game_total / 2.0 - team_spread / 2.0


def _def_ownership_map(
    username: str, season: str, league_id: str | None = None, roster_id: int | None = None
) -> tuple[dict, str | None]:
    """Return (team_fullname -> {id, name}, current_owner_id).

    current_owner_id identifies "you" for the owned_by_current flag in
    list_defenses -- resolved from the explicit roster_id when a league_id
    is given (the authoritative path, since it doesn't depend on guessing
    which of a user's leagues is the right one), or from the legacy
    username-based Sleeper user_id lookup otherwise.
    """
    try:
        user_id = None
        if league_id:
            lid = league_id
        else:
            lid, user_id = sleeper_api.get_league_id_for_user(username, season)
        if not lid:
            return {}, None
        rosters = sleeper_api.get_league_rosters(lid)
        users = sleeper_api.get_league_users(lid)

        current_owner_id = user_id
        if league_id and roster_id is not None:
            match = next((r for r in (rosters or []) if r.get("roster_id") == roster_id), None)
            current_owner_id = match.get("owner_id") if match else None

        # Map owner_id -> display name (fallback to username/id)
        owner_name: dict = {}
        for u in users or []:
            name = u.get("display_name") or u.get("username") or u.get("user_id")
            owner_name[u.get("user_id")] = name
        # All players metadata to identify DEF and team abbr
        all_players = sleeper_api.get_players()
        team_to_owner: dict = {}
        for r in rosters or []:
            oid = r.get("owner_id")
            disp = owner_name.get(oid) or (oid or "unknown")
            for pid in r.get("players", []) or []:
                try:
                    pdata = all_players.get(pid) or {}
                    if pdata.get("position") != "DEF":
                        continue
                    abbr = pdata.get("team")
                    full = SLEEPER_TO_ODDSAPI_TEAM.get(abbr)
                    if full:
                        team_to_owner[full] = {"id": oid, "name": disp}
                except Exception:
                    continue
        return team_to_owner, current_owner_id
    except Exception as e:
        print(f"[services] def ownership mapping error: {e}")
        return {}, None


def list_defenses(
    username: str,
    season: str,
    week: str = "this",
    scope: str = "both",
    fresh: bool = False,
    cache_mode: str = "auto",
    region: str = "us",
    league_id: str | None = None,
    roster_id: int | None = None,
) -> dict:
    print(
        f"[services] list_defenses user={username} season={season} week={week} scope={scope} fresh={fresh} league_id={league_id} roster_id={roster_id}"
    )
    # In-process TTL cache
    ttl = int(os.getenv("SERVICE_CACHE_TTL", "120"))
    _def_cache = getattr(list_defenses, "_cache", {})
    key = (username, season, week, scope, league_id, roster_id)
    now = time.time()
    if not fresh and key in _def_cache:
        ts, payload = _def_cache[key]
        if now - ts < ttl:
            print(f"[services] list_defenses cache hit key={key} age={int(now - ts)}s")
            return payload
    eff_mode = "fresh" if fresh else cache_mode
    events = odds_client.get_nfl_events(regions=region, mode=eff_mode)
    windows = resolve_week_windows(events)
    if windows is None:
        return {
            "defenses": [],
            "ratelimit": ratelimit.format_status(),
            "ratelimit_info": ratelimit.get_details(),
            "message": NO_GAMES_SCHEDULED_MESSAGE,
        }
    (this_start, this_end), (next_start, next_end) = windows
    start, end = (this_start, this_end) if week == "this" else (next_start, next_end)

    # Scoring rules for converting opponent implied totals into DEF fantasy points
    try:
        roster_for_scoring = _resolve_identity(username, season, league_id, roster_id)
        scoring_rules = (roster_for_scoring or {}).get("scoring_rules", {})
    except Exception as e:
        print(f"[services] defenses: scoring rules lookup failed: {e}")
        scoring_rules = {}

    # Build ownership map across entire league
    team_to_owner, current_uid = _def_ownership_map(username, season, league_id, roster_id)
    # All teams (full names)
    all_teams = list(SLEEPER_TO_ODDSAPI_TEAM.values())
    # Scope handling remains, but default 'both' -> include all
    include_owned = scope in ("owned", "both")
    include_avail = scope in ("available", "both")
    team_list: list[tuple[str, str]] = []
    for t in all_teams:
        has_owner = t in team_to_owner
        if has_owner and include_owned:
            team_list.append((t, "owned"))
        elif (not has_owner) and include_avail:
            team_list.append((t, "available"))

    # Filter events in window
    window_events = [
        e
        for e in events
        if start <= dt.datetime.strptime(e["commence_time"], "%Y-%m-%dT%H:%M:%SZ") <= end
    ]

    # Prefetch odds per event once to avoid duplicate calls per team
    ev_odds_map = {}
    for e in window_events:
        gid = e["id"]
        try:
            ev_odds_map[gid] = odds_client.get_event_player_odds(
                gid, markets="spreads,totals", regions=region, mode=eff_mode
            )
        except Exception as exc:
            print(f"[services] defenses: fetch odds failed game={gid} err={exc}")
            ev_odds_map[gid] = None

    out_rows: list[dict] = []
    for team, source in team_list:
        # Find events where this team plays
        for e in window_events:
            if team not in (e.get("home_team"), e.get("away_team")):
                continue
            gid = e["id"]
            opp = e["away_team"] if e["home_team"] == team else e["home_team"]
            odds = ev_odds_map.get(gid)
            # Collect per-book implied totals for opponent
            implieds: list[float] = []
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
                n = len(implieds)
                med = (
                    implieds[n // 2]
                    if n % 2 == 1
                    else (implieds[n // 2 - 1] + implieds[n // 2]) / 2
                )
                def_floor, def_mid, def_ceiling = compute_defense_fantasy_range(med, scoring_rules)
                owner_info = team_to_owner.get(team) or {}
                out_rows.append(
                    {
                        "defense": team,
                        "opponent": opp,
                        "game_date": e["commence_time"],
                        "implied_total_median": round(med, 2),
                        "book_count": len(implieds),
                        "source": source,
                        "owner": owner_info.get("name"),
                        "owned_by_current": bool(owner_info)
                        and (owner_info.get("id") == current_uid),
                        "floor": round(def_floor, 2),
                        "mid": round(def_mid, 2),
                        "ceiling": round(def_ceiling, 2),
                    }
                )

    # Sort ascending by implied total (lower is better for defense)
    out_rows.sort(key=lambda r: (r["implied_total_median"], -r["book_count"]))
    payload = {
        "week": week,
        "defenses": out_rows,
        "ratelimit": ratelimit.format_status(),
        "ratelimit_info": ratelimit.get_details(),
    }
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
    league_id: str | None = None,
    roster_id: int | None = None,
) -> dict:
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
    print(
        f"[services] build_dashboard user={username} season={season} fresh={fresh} weeks={weeks} def_scope={def_scope} inc_players={include_players}"
    )

    # Projections scoped by weeks
    proj_this = None
    proj_next = None
    if weeks in ("this", "both"):
        proj_this = compute_projections(
            username=username,
            season=season,
            week="this",
            region=region,
            fresh=fresh,
            cache_mode=("fresh" if fresh else cache_mode),
            model=model,
            league_id=league_id,
            roster_id=roster_id,
        )
    if weeks in ("next", "both"):
        proj_next = compute_projections(
            username=username,
            season=season,
            week="next",
            region=region,
            fresh=fresh,
            cache_mode=("fresh" if fresh else cache_mode),
            model=model,
            league_id=league_id,
            roster_id=roster_id,
        )

    # Defenses scoped by weeks and scope parameter
    defs_this = None
    defs_next = None
    if weeks in ("this", "both"):
        defs_this = list_defenses(
            username=username,
            season=season,
            week="this",
            scope=def_scope,
            fresh=fresh,
            cache_mode=("fresh" if fresh else cache_mode),
            league_id=league_id,
            roster_id=roster_id,
        )
    if weeks in ("next", "both"):
        defs_next = list_defenses(
            username=username,
            season=season,
            week="next",
            scope=def_scope,
            fresh=fresh,
            cache_mode=("fresh" if fresh else cache_mode),
            league_id=league_id,
            roster_id=roster_id,
        )

    def _owned(defs_payload: dict | None) -> list[dict]:
        rows = (defs_payload or {}).get("defenses", []) or []
        return [d for d in rows if d.get("source") == "owned" or d.get("owned_by_current")]

    # Build lineups from one projections call per week (DEF included when owned)
    lineups = {"this": None, "next": None}
    if proj_this is not None:
        owned_this = _owned(defs_this)
        lineups["this"] = {
            "mid": build_lineup(proj_this.get("players", []), target="mid", defenses=owned_this),
            "floor": build_lineup(
                proj_this.get("players", []), target="floor", defenses=owned_this
            ),
            "ceiling": build_lineup(
                proj_this.get("players", []), target="ceiling", defenses=owned_this
            ),
        }
    if proj_next is not None:
        owned_next = _owned(defs_next)
        lineups["next"] = {
            "mid": build_lineup(proj_next.get("players", []), target="mid", defenses=owned_next),
            "floor": build_lineup(
                proj_next.get("players", []), target="floor", defenses=owned_next
            ),
            "ceiling": build_lineup(
                proj_next.get("players", []), target="ceiling", defenses=owned_next
            ),
        }

    # Choose latest ratelimit info
    rl_info = ratelimit.get_details()

    payload = {
        "lineups": lineups,
        "defenses": {"this": defs_this, "next": defs_next},
        "projections": {
            "this": {
                "players": (
                    proj_this.get("players", [])
                    if (include_players and proj_this is not None)
                    else []
                )
            },
            "next": {
                "players": (
                    proj_next.get("players", [])
                    if (include_players and proj_next is not None)
                    else []
                )
            },
        },
        "ratelimit": ratelimit.format_status(),
        "ratelimit_info": rl_info,
    }
    print(f"[services] build_dashboard complete; rl={payload['ratelimit']}")
    return payload
