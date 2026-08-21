"""Per-player and per-defense odds detail endpoints.

Backs /player/odds and /defense/odds: the drill-down view showing every
book's line for one player, plus the math that turned those lines into a
projection. Depends on services.py for identity/week/fetch helpers; the
dependency runs one way only, so services.py must not import this module.
"""

from __future__ import annotations

import datetime as dt
from statistics import NormalDist

from . import odds_client, ratelimit
from .aggregator import aggregate_by_week
from .config import STAT_MARKET_MAPPING_SLEEPER
from .planner import plan_relevant_games_and_markets
from .predicted_stats import predict_stats_for_player
from .range_model import PRIMARY_MARKET_WHITELIST
from .services import (
    NO_GAMES_SCHEDULED_MESSAGE,
    _fetch_odds,
    _implied_total,
    _resolve_identity,
)
from .weekly_windows import resolve_week_windows


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


def get_player_odds_details(
    username: str,
    season: str,
    week: str = "this",
    region: str = "us",
    name: str = "",
    cache_mode: str = "auto",
    model: str = "const",
    league_id: str | None = None,
    roster_id: int | None = None,
) -> dict:
    """Return per-book odds and market summaries used for a single player.

    Emphasizes markets by estimated impact on fantasy points (mean stat * scoring multiplier).
    """
    eff_mode = cache_mode
    events = odds_client.get_nfl_events(regions=region, mode=eff_mode)
    windows = resolve_week_windows(events)
    if windows is None:
        return {
            "player": {"name": name},
            "markets": {},
            "primary_order": [],
            "ratelimit": ratelimit.format_status(),
            "ratelimit_info": ratelimit.get_details(),
            "message": NO_GAMES_SCHEDULED_MESSAGE,
        }
    (this_start, this_end), (next_start, next_end) = windows
    # Roster & planning (to get scoring rules and player mapping)
    roster = _resolve_identity(username, season, league_id, roster_id)
    scoring_rules = roster.get("scoring_rules", {}) if roster else {}
    plan_all = plan_relevant_games_and_markets(
        roster,
        ((this_start, this_end), (next_start, next_end)),
        regions=region,
        cache_mode=eff_mode,
    )
    planned = plan_all.get(week, {})
    # Fetch odds for planned games
    odds_by_week = _fetch_odds({week: planned}, cache_mode=eff_mode, regions=region)
    ev_odds = odds_by_week.get(week, {})
    # Aggregate
    per_player_odds, per_player_summaries = aggregate_by_week(ev_odds, planned)
    # Build alias->info map
    info_by_alias: dict[str, dict] = {}
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
        return {
            "player": {"name": name},
            "markets": {},
            "primary_order": [],
            "ratelimit": ratelimit.format_status(),
            "ratelimit_info": ratelimit.get_details(),
        }

    by_book = per_player_odds.get(target_alias, {})
    market_summaries = per_player_summaries.get(target_alias, {})

    # Predicted mean stats per market (averaged over books)
    mean_stats = predict_stats_for_player(by_book)
    # Compute rough impact score = abs(mean * multiplier)
    impacts: dict[str, float] = {}
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
        from .range_model import compute_fantasy_range, compute_fantasy_range_model

        if (model or "baseline").lower() == "baseline":
            _floor, _mid, _ceil, per_market_ranges = compute_fantasy_range(
                by_book, market_summaries, scoring_rules
            )
        else:
            _floor, _mid, _ceil, per_market_ranges = compute_fantasy_range_model(
                by_book, market_summaries, scoring_rules, model=model
            )
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

    markets_out: dict[str, dict] = {}
    for mkey in set(
        list(by_book.keys())
        + list(market_summaries.keys())
        + list(mean_stats.keys())
        + list(per_market_ranges.keys())
    ):
        # Per-book rows
        books = []
        alts_out = {"over": [], "under": []}
        for book_key, mkts in by_book.items():
            sides = mkts.get(mkey, {"over": None, "under": None})
            # Collect alt lists if present
            alts = (sides or {}).get("alts")
            if alts and (isinstance(alts, dict)):
                try:
                    for it in alts.get("over") or []:
                        alts_out["over"].append(
                            {"book": book_key, "point": it.get("point"), "odds": it.get("odds")}
                        )
                    for it in alts.get("under") or []:
                        alts_out["under"].append(
                            {"book": book_key, "point": it.get("point"), "odds": it.get("odds")}
                        )
                except Exception:
                    pass
            books.append(
                {
                    "book": book_key,
                    "over": sides.get("over"),
                    "under": sides.get("under"),
                }
            )
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
            "range": (
                per_market_ranges.get(mkey)
                if m_summ is not None or mkey in per_market_ranges
                else None
            ),
            "fp_floor": f_floor,
            "fp_mid": f_mid,
            "fp_ceiling": f_ceil,
            "books": books,
        }
        # Attach alternates if present (combined across books)
        try:
            if alts_out["over"] or alts_out["under"]:
                entry["alts"] = alts_out
        except Exception:
            pass
        markets_out[mkey] = entry

    # Build debug math payload mirroring range model logic
    debug_math: dict[str, object] = {}
    try:
        # Helper: normalized p_over and sigma based on summary
        def _calc_sigma(
            mean: float, threshold: float, p_over: float, p_under: float
        ) -> tuple[float, float, float, bool]:
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
        pm_debug: dict[str, object] = {}
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
            pnorm, z, sigma, used_fallback = (
                _calc_sigma(mean, thr, pov, pun)
                if (mkey != "player_anytime_td" and thr != 0)
                else (None, None, None, False)
            )
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

        def _get_stat(qidx: int, key: str) -> float | None:
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

    def _importance_for_pos(pos: str | None, scoring: dict) -> tuple[set[str], set[str]]:
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
        elif p == "WR" or p == "TE":
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
        "vital_keys": sorted(vital_keys),
        "minor_keys": sorted(minor_keys),
        # Attach raw event odds for debugging/verification
        "raw_odds": ev_odds,
        "ratelimit": ratelimit.format_status(),
        "ratelimit_info": ratelimit.get_details(),
        "debug_math": debug_math,
    }
    return payload


def get_defense_odds_details(
    username: str,
    season: str,
    week: str = "this",
    defense: str = "",
    cache_mode: str = "auto",
    region: str = "us",
) -> dict:
    """Return per-book totals/spreads and implied totals for opponent against this defense.

    Sorted by implied total ascending per game, includes medians.
    """
    eff_mode = cache_mode
    events = odds_client.get_nfl_events(regions=region, mode=eff_mode)
    windows = resolve_week_windows(events)
    if windows is None:
        return {
            "defense": defense,
            "week": week,
            "games": [],
            "raw_odds": {},
            "ratelimit": ratelimit.format_status(),
            "ratelimit_info": ratelimit.get_details(),
            "message": NO_GAMES_SCHEDULED_MESSAGE,
        }
    (this_start, this_end), (next_start, next_end) = windows
    # Window and events
    start, end = (this_start, this_end) if week == "this" else (next_start, next_end)
    window_events = [
        e
        for e in events
        if start <= dt.datetime.strptime(e["commence_time"], "%Y-%m-%dT%H:%M:%SZ") <= end
    ]
    # Find games with this defense
    games = [e for e in window_events if defense in (e.get("home_team"), e.get("away_team"))]
    details = []
    raw_map: dict[str, object] = {}
    for e in games:
        gid = e["id"]
        opp = e["away_team"] if e["home_team"] == defense else e["home_team"]
        ev_odds = odds_client.get_event_player_odds(
            gid, markets="spreads,totals", regions=region, mode=eff_mode
        )
        # Normalize
        ev_obj = (
            ev_odds[0]
            if isinstance(ev_odds, list) and ev_odds
            else (ev_odds if isinstance(ev_odds, dict) else None)
        )
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
            books_rows.append(
                {
                    "book": book.get("key"),
                    "total_point": total_pt,
                    "opponent_spread": opp_spread,
                    "opponent_implied": impl,
                }
            )
        median = None
        if implieds:
            implieds.sort()
            median = (
                implieds[len(implieds) // 2]
                if len(implieds) % 2 == 1
                else (implieds[len(implieds) // 2 - 1] + implieds[len(implieds) // 2]) / 2
            )
        details.append(
            {
                "game_id": gid,
                "opponent": opp,
                "commence_time": e.get("commence_time"),
                "books": books_rows,
                "implied_total_median": median,
            }
        )
    # Sort games by implied total ascending
    details.sort(
        key=lambda g: (
            g.get("implied_total_median") if g.get("implied_total_median") is not None else 9999
        )
    )
    return {
        "defense": defense,
        "week": week,
        "games": details,
        # Attach raw event odds map keyed by game id
        "raw_odds": raw_map,
        "ratelimit": ratelimit.format_status(),
        "ratelimit_info": ratelimit.get_details(),
    }
