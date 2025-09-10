from __future__ import annotations

from typing import Dict, Tuple
from dataclasses import dataclass
from statistics import NormalDist

from predicted_stats import predict_stats_for_player
from config import STAT_MARKET_MAPPING_SLEEPER


PRIMARY_MARKET_WHITELIST = {
    # Passing
    "player_pass_yds",
    "player_pass_tds",
    "player_pass_interceptions",
    # Rushing
    "player_rush_yds",
    "player_rush_tds",  # rarely available, most TDs via anytime_td
    # Receiving
    "player_receptions",
    "player_reception_yds",
    "player_reception_tds",
    # Combined
    "player_anytime_td",
}


def _calc_sigma(mean: float, threshold: float, p_over: float, p_under: float) -> float:
    # Normalize for vig
    total = (p_over or 0.0) + (p_under or 0.0)
    if total > 0:
        p = p_over / total
    else:
        p = 0.5
    # Convert to z; clamp to avoid infinities at 0/1
    p = min(max(p, 1e-4), 1 - 1e-4)
    z = NormalDist().inv_cdf(p)
    if abs(z) < 1e-6:
        return max(abs(threshold) * 0.25, 1.0)
    sigma = abs((mean - threshold) / z)
    return max(sigma, 1e-6)


def _market_quantiles(
    key: str,
    mean: float,
    threshold: float,
    p_over: float,
    p_under: float,
) -> Tuple[float, float, float]:
    # Special-case binary markets (anytime TD modeled as 0/1)
    if key == "player_anytime_td" or threshold == 0:
        p = p_over if (p_over or 0) > 0 else 0.5
        # Bernoulli quantiles for X in {0,1} at 15/50/85 percentiles
        q15 = 0.0 if 0.15 <= 1 - p else 1.0
        q50 = 0.0 if 0.50 <= 1 - p else 1.0
        q85 = 0.0 if 0.85 <= 1 - p else 1.0
        return q15, mean, q85  # use mean for mid to retain smoother ordering

    sigma = _calc_sigma(mean, threshold, p_over, p_under)
    q15 = mean + NormalDist().inv_cdf(0.15) * sigma
    q50 = mean  # mid = mean estimate
    q85 = mean + NormalDist().inv_cdf(0.85) * sigma
    # Prevent negative quantities for count-like/yardage stats
    if any(s in key for s in ("_yds", "_tds", "receptions")):
        q15 = max(0.0, q15)
        q50 = max(0.0, q50)
        q85 = max(0.0, q85)
    return q15, q50, q85


def _fantasy_points(stats: Dict[str, float], scoring_rules: Dict[str, float]) -> float:
    total = 0.0
    for market_key, value in stats.items():
        if market_key not in STAT_MARKET_MAPPING_SLEEPER:
            continue
        rule_key = STAT_MARKET_MAPPING_SLEEPER[market_key]
        if rule_key in scoring_rules:
            try:
                mult = float(scoring_rules[rule_key])
            except Exception:
                continue
            total += value * mult
    return total


def compute_fantasy_range(
    per_bookmaker_odds: Dict,
    market_summaries: Dict[str, object],  # MarketSummary-like with fields
    scoring_rules: Dict[str, float],
) -> Tuple[float, float, float, Dict[str, Tuple[float, float, float]]]:
    """Compute floor, mid, ceiling fantasy points using odds-derived stats.

    Returns (floor, mid, ceiling, per_market_ranges).
    per_market_ranges maps market_key -> (q10, q50, q90) of the stat.
    """
    # 1) Predict mean stats per market
    mean_stats_all = predict_stats_for_player(per_bookmaker_odds)

    # 2) Build per-market ranges, focusing on primary markets only
    per_market_ranges: Dict[str, Tuple[float, float, float]] = {}
    for key, mean_val in mean_stats_all.items():
        use_key = key
        if key not in PRIMARY_MARKET_WHITELIST:
            # use alternates only if the base isnâ€™t present at all
            base_key = key.replace("_alternate", "")
            if base_key in mean_stats_all:
                continue
            if base_key != key:
                use_key = base_key
        summ = market_summaries.get(key) or market_summaries.get(use_key)
        if summ is None:
            # Fallback: Â±20% band around mean
            q10 = max(0.0, mean_val * 0.8)
            q50 = max(0.0, mean_val)
            q90 = max(0.0, mean_val * 1.2)
        else:
            q10, q50, q90 = _market_quantiles(
                use_key,
                mean=mean_val,
                threshold=getattr(summ, "avg_threshold", 0.0),
                p_over=getattr(summ, "avg_over_prob", 0.0),
                p_under=getattr(summ, "avg_under_prob", 0.0),
            )
        per_market_ranges[use_key] = (q10, q50, q90)

    # 3) Convert ranges to fantasy points
    floor_stats = {k: v[0] for k, v in per_market_ranges.items()}
    mid_stats = {k: v[1] for k, v in per_market_ranges.items()}
    ceil_stats = {k: v[2] for k, v in per_market_ranges.items()}

    # Special handling: anytime TD represents a 0/1 indicator. Convert to TD count.
    # Scoring rules already handle the right multiplier (e.g., 6 for TD).

    floor_fp = _fantasy_points(floor_stats, scoring_rules)
    mid_fp = _fantasy_points(mid_stats, scoring_rules)
    ceil_fp = _fantasy_points(ceil_stats, scoring_rules)
    return floor_fp, mid_fp, ceil_fp, per_market_ranges

