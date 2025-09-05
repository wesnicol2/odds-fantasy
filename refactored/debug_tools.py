from __future__ import annotations

from typing import Dict, Tuple

from predicted_stats import implied_probability, calculate_weighted_stat
from . import range_model
from config import STAT_MARKET_MAPPING_SLEEPER


RB_DEBUG_MARKETS = (
    "player_rush_yds",
    "player_receptions",
    "player_anytime_td",
)


def _avg_from_by_book(by_book: Dict, market_key: str) -> Tuple[float, float, float, int]:
    over_sum = under_sum = thr_sum = 0.0
    n_over = n_under = n_thr = 0
    for book_key, mkts in (by_book or {}).items():
        m = mkts.get(market_key)
        if not m:
            continue
        over = m.get("over")
        under = m.get("under")
        if over and over.get("odds"):
            try:
                over_sum += implied_probability(over["odds"])
                n_over += 1
            except Exception:
                pass
        if under and under.get("odds"):
            try:
                under_sum += implied_probability(under["odds"])
                n_under += 1
            except Exception:
                pass
        if over and ("point" in over):
            try:
                thr_sum += float(over["point"])
                n_thr += 1
            except Exception:
                pass
    avg_over = over_sum / n_over if n_over else 0.0
    avg_under = under_sum / n_under if n_under else 0.0
    avg_thr = thr_sum / n_thr if n_thr else 0.0
    samples = max(n_over, n_under, n_thr)
    return avg_over, avg_under, avg_thr, samples


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
            avg_over = getattr(summ, "avg_over_prob", 0.0)
            avg_under = getattr(summ, "avg_under_prob", 0.0)
            avg_thr = getattr(summ, "avg_threshold", 0.0)
            samples = getattr(summ, "samples", 0)
            print(f"    Averages: over={avg_over:.4f}, under={avg_under:.4f}, threshold={avg_thr:.2f}, samples={samples}")
        else:
            avg_over, avg_under, avg_thr, samples = _avg_from_by_book(by_book, mkey)
            print(f"    Averages (computed): over={avg_over:.4f}, under={avg_under:.4f}, threshold={avg_thr:.2f}, samples={samples}")

        # 3) Normalization for vig and mean estimate (matches calculate_weighted_stat)
        total = avg_over + avg_under
        if total > 0:
            over_n = avg_over / total
            under_n = avg_under / total
        else:
            over_n = under_n = 0.5
        if avg_under == 0:
            print("    Note: No under lines; assuming 50% under for calculation")
        predicted_mean = calculate_weighted_stat(avg_over, avg_under, avg_thr)
        print(f"    Normalized probs: over_n={over_n:.4f}, under_n={under_n:.4f}; threshold={avg_thr:.2f}")
        print(f"    Predicted mean stat: {predicted_mean:.3f}")

        # 4) Quantiles 15/50/85
        q15, q50, q85 = range_model._market_quantiles(mkey, predicted_mean, avg_thr, avg_over, avg_under)
        # also show sigma used
        sigma = range_model._calc_sigma(predicted_mean, avg_thr, avg_over, avg_under) if not (mkey == "player_anytime_td" or avg_thr == 0) else None
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

