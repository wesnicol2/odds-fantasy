from __future__ import annotations

from typing import Dict, Tuple

from predicted_stats import implied_probability, calculate_weighted_stat
from . import range_model
from config import STAT_MARKET_MAPPING_SLEEPER
import statistics


RB_DEBUG_MARKETS = (
    "player_rush_yds",
    "player_reception_yds",
    "player_receptions",
    "player_anytime_td",
)

WR_DEBUG_MARKETS = (
    "player_reception_yds",
    "player_receptions",
    "player_rush_yds",
    "player_anytime_td",
)

TE_DEBUG_MARKETS = (
    "player_reception_yds",
    "player_receptions",
    "player_rush_yds",
    "player_anytime_td",
)


def _median_from_by_book(by_book: Dict, market_key: str) -> Tuple[float, float, float, int]:
    over_vals = []
    under_vals = []
    thr_vals = []
    for book_key, mkts in (by_book or {}).items():
        m = mkts.get(market_key)
        if not m:
            continue
        over = m.get("over")
        under = m.get("under")
        # per-book de‑vig when both sides exist
        if over and under and over.get("odds") and under.get("odds"):
            try:
                o = implied_probability(over["odds"])
                u = implied_probability(under["odds"])
                tot = o + u
                if tot > 0:
                    over_vals.append(o / tot)
                    under_vals.append(u / tot)
            except Exception:
                pass
        else:
            if over and over.get("odds"):
                try:
                    over_vals.append(implied_probability(over["odds"]))
                except Exception:
                    pass
            if under and under.get("odds"):
                try:
                    under_vals.append(implied_probability(under["odds"]))
                except Exception:
                    pass
        pt = None
        if over and ("point" in over):
            pt = over.get("point")
        elif under and ("point" in under):
            pt = under.get("point")
        if pt is not None:
            try:
                thr_vals.append(float(pt))
            except Exception:
                pass
    med_over = statistics.median(over_vals) if over_vals else 0.0
    med_under = statistics.median(under_vals) if under_vals else 0.0
    med_thr = statistics.median(thr_vals) if thr_vals else 0.0
    samples = max(len(over_vals), len(under_vals), len(thr_vals))
    return med_over, med_under, med_thr, samples


def debug_rb_calculations(player_name: str, p_info: dict, by_book: Dict, market_summaries: Dict[str, object], scoring_rules: Dict[str, float]):
    pos = p_info.get("primary_position")
    if pos != "RB":
        return

    team = p_info.get("editorial_team_full_name", "")
    print(f"\n[RB DEBUG] {player_name} ({team})")

    per_market_ranges: Dict[str, Tuple[float, float, float]] = {}

    for mkey in RB_DEBUG_MARKETS:
        if (mkey not in by_book) and (mkey not in market_summaries):
            continue

        print(f"  Market: {mkey}")

        # 1) Print bookmaker lines and implied probabilities
        for book_key, mkts in sorted((by_book or {}).items()):
            market = mkts.get(mkey)
            if not market:
                continue
            over = market.get("over")
            under = market.get("under")
            over_odds = over and over.get("odds")
            under_odds = under and under.get("odds")
            over_point = over and over.get("point")
            under_point = under and under.get("point")
            over_prob = implied_probability(over_odds) if over_odds else None
            under_prob = implied_probability(under_odds) if under_odds else None
            print(f"    {book_key}: over_odds={over_odds} (p={over_prob}), under_odds={under_odds} (p={under_prob}), point={over_point if over_point is not None else under_point}")

        # 2) Averages from summaries or recompute if missing
        summ = market_summaries.get(mkey)
        if summ:
            med_over = getattr(summ, "avg_over_prob", 0.0)
            med_under = getattr(summ, "avg_under_prob", 0.0)
            med_thr = getattr(summ, "avg_threshold", 0.0)
            samples = getattr(summ, "samples", 0)
            print(f"    Medians: over={med_over:.4f}, under={med_under:.4f}, threshold={med_thr:.2f}, samples={samples}")
        else:
            med_over, med_under, med_thr, samples = _median_from_by_book(by_book, mkey)
            print(f"    Medians (computed): over={med_over:.4f}, under={med_under:.4f}, threshold={med_thr:.2f}, samples={samples}")

        # 3) Normalization for vig and mean estimate (matches calculate_weighted_stat)
        total = med_over + med_under
        if total > 0:
            over_n = med_over / total
            under_n = med_under / total
        else:
            over_n = under_n = 0.5
        if med_under == 0:
            print("    Note: No under lines; assuming 50% under for calculation")
        predicted_mean = calculate_weighted_stat(med_over, med_under, med_thr)
        print(f"    Normalized probs: over_n={over_n:.4f}, under_n={under_n:.4f}; threshold={med_thr:.2f}")
        print(f"    Predicted mean stat: {predicted_mean:.3f}")

        # 4) Quantiles 15/50/85
        q15, q50, q85 = range_model._market_quantiles(mkey, predicted_mean, med_thr, med_over, med_under)
        # also show sigma used
        sigma = range_model._calc_sigma(predicted_mean, med_thr, med_over, med_under) if not (mkey == "player_anytime_td" or med_thr == 0) else None
        if sigma is not None:
            print(f"    Sigma estimate={sigma:.4f}; q15={q15:.3f}, q50={q50:.3f}, q85={q85:.3f}")
        else:
            print(f"    Bernoulli quantiles; q15={q15:.3f}, q50={q50:.3f}, q85={q85:.3f}")

        per_market_ranges[mkey] = (q15, q50, q85)

    # 5) Fantasy point contributions (RB-relevant markets)
    if not per_market_ranges:
        print("  No RB markets found for this player.")
        return

    floor_stats = {k: v[0] for k, v in per_market_ranges.items()}
    mid_stats = {k: v[1] for k, v in per_market_ranges.items()}
    ceil_stats = {k: v[2] for k, v in per_market_ranges.items()}

    def contribs(stats: Dict[str, float]) -> Tuple[float, Dict[str, float]]:
        total = 0.0
        parts: Dict[str, float] = {}
        for mk, val in stats.items():
            rule_key = STAT_MARKET_MAPPING_SLEEPER.get(mk)
            mult = float(scoring_rules.get(rule_key, 0)) if rule_key else 0.0
            pts = val * mult
            parts[mk] = pts
            total += pts
        return total, parts

    f_total, f_parts = contribs(floor_stats)
    m_total, m_parts = contribs(mid_stats)
    c_total, c_parts = contribs(ceil_stats)

    print("  Fantasy points contributions:")
    for mk in per_market_ranges.keys():
        rk = STAT_MARKET_MAPPING_SLEEPER.get(mk, "-")
        mult = scoring_rules.get(rk, 0)
        print(f"    {mk}: rule={rk}, mult={mult} | floor={f_parts.get(mk,0):.2f}, mid={m_parts.get(mk,0):.2f}, ceil={c_parts.get(mk,0):.2f}")
    print(f"  Totals: floor={f_total:.2f}, mid={m_total:.2f}, ceil={c_total:.2f}")


def debug_wr_calculations(player_name: str, p_info: dict, by_book: Dict, market_summaries: Dict[str, object], scoring_rules: Dict[str, float]):
    pos = p_info.get("primary_position")
    if pos != "WR":
        return

    team = p_info.get("editorial_team_full_name", "")
    print(f"\n[WR DEBUG] {player_name} ({team})")

    per_market_ranges: Dict[str, Tuple[float, float, float]] = {}

    for mkey in WR_DEBUG_MARKETS:
        if (mkey not in by_book) and (mkey not in market_summaries):
            continue

        print(f"  Market: {mkey}")

        # 1) Per-book lines and probabilities
        for book_key, mkts in sorted((by_book or {}).items()):
            market = mkts.get(mkey)
            if not market:
                continue
            over = market.get("over")
            under = market.get("under")
            over_odds = over and over.get("odds")
            under_odds = under and under.get("odds")
            over_point = over and over.get("point")
            under_point = under and under.get("point")
            over_prob = implied_probability(over_odds) if over_odds else None
            under_prob = implied_probability(under_odds) if under_odds else None
            print(f"    {book_key}: over_odds={over_odds} (p={over_prob}), under_odds={under_odds} (p={under_prob}), point={over_point if over_point is not None else under_point}")

        # 2) Medians (de‑vigged) from summaries or compute
        summ = market_summaries.get(mkey)
        if summ:
            med_over = getattr(summ, "avg_over_prob", 0.0)
            med_under = getattr(summ, "avg_under_prob", 0.0)
            med_thr = getattr(summ, "avg_threshold", 0.0)
            samples = getattr(summ, "samples", 0)
            print(f"    Medians: over={med_over:.4f}, under={med_under:.4f}, threshold={med_thr:.2f}, samples={samples}")
        else:
            med_over, med_under, med_thr, samples = _median_from_by_book(by_book, mkey)
            print(f"    Medians (computed): over={med_over:.4f}, under={med_under:.4f}, threshold={med_thr:.2f}, samples={samples}")

        # 3) Normalize and mean estimate
        total = med_over + med_under
        if total > 0:
            over_n = med_over / total
            under_n = med_under / total
        else:
            over_n = under_n = 0.5
        if med_under == 0:
            print("    Note: No under lines; assuming 50% under for calculation")
        predicted_mean = calculate_weighted_stat(med_over, med_under, med_thr)
        print(f"    Normalized probs: over_n={over_n:.4f}, under_n={under_n:.4f}; threshold={med_thr:.2f}")
        print(f"    Predicted mean stat: {predicted_mean:.3f}")

        # 4) Quantiles
        q15, q50, q85 = range_model._market_quantiles(mkey, predicted_mean, med_thr, med_over, med_under)
        sigma = range_model._calc_sigma(predicted_mean, med_thr, med_over, med_under) if not (mkey == "player_anytime_td" or med_thr == 0) else None
        if sigma is not None:
            print(f"    Sigma estimate={sigma:.4f}; q15={q15:.3f}, q50={q50:.3f}, q85={q85:.3f}")
        else:
            print(f"    Bernoulli quantiles; q15={q15:.3f}, q50={q50:.3f}, q85={q85:.3f}")

        per_market_ranges[mkey] = (q15, q50, q85)

    if not per_market_ranges:
        print("  No WR markets found for this player.")
        return

    # Fantasy contributions (using your scoring)
    floor_stats = {k: v[0] for k, v in per_market_ranges.items()}
    mid_stats = {k: v[1] for k, v in per_market_ranges.items()}
    ceil_stats = {k: v[2] for k, v in per_market_ranges.items()}

    def contribs(stats: Dict[str, float]):
        total = 0.0
        parts: Dict[str, float] = {}
        for mk, val in stats.items():
            rule_key = STAT_MARKET_MAPPING_SLEEPER.get(mk)
            mult = float(scoring_rules.get(rule_key, 0)) if rule_key else 0.0
            pts = val * mult
            parts[mk] = pts
            total += pts
        return total, parts

    f_total, f_parts = contribs(floor_stats)
    m_total, m_parts = contribs(mid_stats)
    c_total, c_parts = contribs(ceil_stats)

    print("  Fantasy points contributions:")
    for mk in per_market_ranges.keys():
        rk = STAT_MARKET_MAPPING_SLEEPER.get(mk, "-")
        mult = scoring_rules.get(rk, 0)
        print(f"    {mk}: rule={rk}, mult={mult} | floor={f_parts.get(mk,0):.2f}, mid={m_parts.get(mk,0):.2f}, ceil={c_parts.get(mk,0):.2f}")
    print(f"  Totals: floor={f_total:.2f}, mid={m_total:.2f}, ceil={c_total:.2f}")


def debug_te_calculations(player_name: str, p_info: dict, by_book: Dict, market_summaries: Dict[str, object], scoring_rules: Dict[str, float]):
    pos = p_info.get("primary_position")
    if pos != "TE":
        return

    team = p_info.get("editorial_team_full_name", "")
    print(f"\n[TE DEBUG] {player_name} ({team})")

    per_market_ranges: Dict[str, Tuple[float, float, float]] = {}

    for mkey in TE_DEBUG_MARKETS:
        if (mkey not in by_book) and (mkey not in market_summaries):
            continue

        print(f"  Market: {mkey}")

        # 1) Per-book lines and probabilities
        for book_key, mkts in sorted((by_book or {}).items()):
            market = mkts.get(mkey)
            if not market:
                continue
            over = market.get("over")
            under = market.get("under")
            over_odds = over and over.get("odds")
            under_odds = under and under.get("odds")
            over_point = over and over.get("point")
            under_point = under and under.get("point")
            over_prob = implied_probability(over_odds) if over_odds else None
            under_prob = implied_probability(under_odds) if under_odds else None
            print(f"    {book_key}: over_odds={over_odds} (p={over_prob}), under_odds={under_odds} (p={under_prob}), point={over_point if over_point is not None else under_point}")

        # 2) Medians (de‑vigged)
        summ = market_summaries.get(mkey)
        if summ:
            med_over = getattr(summ, "avg_over_prob", 0.0)
            med_under = getattr(summ, "avg_under_prob", 0.0)
            med_thr = getattr(summ, "avg_threshold", 0.0)
            samples = getattr(summ, "samples", 0)
            print(f"    Medians: over={med_over:.4f}, under={med_under:.4f}, threshold={med_thr:.2f}, samples={samples}")
        else:
            med_over, med_under, med_thr, samples = _median_from_by_book(by_book, mkey)
            print(f"    Medians (computed): over={med_over:.4f}, under={med_under:.4f}, threshold={med_thr:.2f}, samples={samples}")

        # 3) Normalize and mean estimate
        total = med_over + med_under
        if total > 0:
            over_n = med_over / total
            under_n = med_under / total
        else:
            over_n = under_n = 0.5
        if med_under == 0:
            print("    Note: No under lines; assuming 50% under for calculation")
        predicted_mean = calculate_weighted_stat(med_over, med_under, med_thr)
        print(f"    Normalized probs: over_n={over_n:.4f}, under_n={under_n:.4f}; threshold={med_thr:.2f}")
        print(f"    Predicted mean stat: {predicted_mean:.3f}")

        # 4) Quantiles
        q15, q50, q85 = range_model._market_quantiles(mkey, predicted_mean, med_thr, med_over, med_under)
        sigma = range_model._calc_sigma(predicted_mean, med_thr, med_over, med_under) if not (mkey == "player_anytime_td" or med_thr == 0) else None
        if sigma is not None:
            print(f"    Sigma estimate={sigma:.4f}; q15={q15:.3f}, q50={q50:.3f}, q85={q85:.3f}")
        else:
            print(f"    Bernoulli quantiles; q15={q15:.3f}, q50={q50:.3f}, q85={q85:.3f}")

        per_market_ranges[mkey] = (q15, q50, q85)

    if not per_market_ranges:
        print("  No TE markets found for this player.")
        return

    # Fantasy contributions
    floor_stats = {k: v[0] for k, v in per_market_ranges.items()}
    mid_stats = {k: v[1] for k, v in per_market_ranges.items()}
    ceil_stats = {k: v[2] for k, v in per_market_ranges.items()}

    def contribs(stats: Dict[str, float]):
        total = 0.0
        parts: Dict[str, float] = {}
        for mk, val in stats.items():
            rule_key = STAT_MARKET_MAPPING_SLEEPER.get(mk)
            mult = float(scoring_rules.get(rule_key, 0)) if rule_key else 0.0
            pts = val * mult
            parts[mk] = pts
            total += pts
        return total, parts

    f_total, f_parts = contribs(floor_stats)
    m_total, m_parts = contribs(mid_stats)
    c_total, c_parts = contribs(ceil_stats)

    print("  Fantasy points contributions:")
    for mk in per_market_ranges.keys():
        rk = STAT_MARKET_MAPPING_SLEEPER.get(mk, "-")
        mult = scoring_rules.get(rk, 0)
        print(f"    {mk}: rule={rk}, mult={mult} | floor={f_parts.get(mk,0):.2f}, mid={m_parts.get(mk,0):.2f}, ceil={c_parts.get(mk,0):.2f}")
    print(f"  Totals: floor={f_total:.2f}, mid={m_total:.2f}, ceil={c_total:.2f}")
