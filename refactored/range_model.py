from __future__ import annotations

from statistics import NormalDist

from config import STAT_MARKET_MAPPING_SLEEPER
from predicted_stats import predict_stats_for_player

from .prob_models import (  # type: ignore
    _fit_lognormal_from_two_points,
    _lognormal_quantile,
    _poisson_fit_lambda,
    get_model_registry,
    poisson_quantile,
)

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
    p = p_over / total if total > 0 else 0.5
    # Convert to z; clamp to avoid infinities at 0/1
    p = min(max(p, 1e-4), 1 - 1e-4)
    z = NormalDist().inv_cdf(p)
    if abs(z) < 1e-6:
        return max(abs(threshold) * 0.25, 1.0)
    sigma = abs((mean - threshold) / z)
    return max(sigma, 1e-6)


def _is_count_market(key: str) -> bool:
    k = (key or "").lower()
    if "receptions" in k:
        return True
    if k.endswith("_tds"):
        return True
    return bool(k.endswith("_interceptions"))


def _market_quantiles(
    key: str,
    mean: float,
    threshold: float,
    p_over: float,
    p_under: float,
) -> tuple[float, float, float]:
    # Special-case binary markets (anytime TD modeled as 0/1)
    if key == "player_anytime_td" or threshold == 0:
        p = p_over if (p_over or 0) > 0 else 0.5
        # Bernoulli quantiles for X in {0,1} at 15/50/85 percentiles
        q15 = 0.0 if 1 - p >= 0.15 else 1.0
        q50 = 0.0 if 1 - p >= 0.50 else 1.0
        q85 = 0.0 if 1 - p >= 0.85 else 1.0
        return q15, mean, q85  # use mean for mid to retain smoother ordering

    # Single-line fallback (no alternates / not enough anchors for a full CDF fit).
    # We only have one (threshold, p_over) market observation, so we shape the
    # implied distribution to match how the stat actually behaves rather than
    # always assuming Normal: yardage stats are right-skewed (lognormal),
    # count stats (receptions, TDs, INTs) are discrete and Poisson-shaped.
    # We fall back to Normal only if the shape-specific fit fails outright.
    total = (p_over or 0.0) + (p_under or 0.0)
    p = (p_over / total) if total > 0 else 0.5
    p = min(max(p, 1e-4), 1 - 1e-4)
    f_at_threshold = 1.0 - p  # P(X <= threshold), since p = P(X > threshold)

    if _is_count_market(key):
        lam = _poisson_fit_lambda([(max(0, round(threshold)), f_at_threshold)])
        if lam is not None and lam > 0:
            q15 = poisson_quantile(lam, 0.15)
            q50 = poisson_quantile(lam, 0.50)
            q85 = poisson_quantile(lam, 0.85)
            return q15, q50, q85
    elif "_yds" in key:
        fit = _fit_lognormal_from_two_points(
            max(threshold, 1e-6), f_at_threshold, max(mean, 1e-6), 0.5
        )
        if fit is not None:
            mu, sigma_log = fit
            q15 = _lognormal_quantile(mu, sigma_log, 0.15)
            q50 = _lognormal_quantile(mu, sigma_log, 0.50)
            q85 = _lognormal_quantile(mu, sigma_log, 0.85)
            return q15, q50, q85

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


def _fantasy_points(stats: dict[str, float], scoring_rules: dict[str, float]) -> float:
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
            # Ensure interceptions subtract points, regardless of league sign convention
            if market_key == "player_pass_interceptions":
                mult = -abs(mult)
            total += value * mult
    # Threshold bonuses for yardage milestones using available stat values
    try:
        rec_yd = float(stats.get("player_reception_yds", 0.0) or 0.0)
        if rec_yd >= 200 and ("bonus_rec_yd_200" in scoring_rules):
            total += float(scoring_rules["bonus_rec_yd_200"]) or 0.0
        elif rec_yd >= 100 and ("bonus_rec_yd_100" in scoring_rules):
            total += float(scoring_rules["bonus_rec_yd_100"]) or 0.0
    except Exception:
        pass
    try:
        rush_yd = float(stats.get("player_rush_yds", 0.0) or 0.0)
        if rush_yd >= 200 and ("bonus_rush_yd_200" in scoring_rules):
            total += float(scoring_rules["bonus_rush_yd_200"]) or 0.0
        elif rush_yd >= 100 and ("bonus_rush_yd_100" in scoring_rules):
            total += float(scoring_rules["bonus_rush_yd_100"]) or 0.0
    except Exception:
        pass
    try:
        pass_yd = float(stats.get("player_pass_yds", 0.0) or 0.0)
        if pass_yd >= 400 and ("bonus_pass_yd_400" in scoring_rules):
            total += float(scoring_rules["bonus_pass_yd_400"]) or 0.0
        elif pass_yd >= 300 and ("bonus_pass_yd_300" in scoring_rules):
            total += float(scoring_rules["bonus_pass_yd_300"]) or 0.0
    except Exception:
        pass
    return total


def compute_fantasy_range(
    per_bookmaker_odds: dict,
    market_summaries: dict[str, object],  # MarketSummary-like with fields
    scoring_rules: dict[str, float],
) -> tuple[float, float, float, dict[str, tuple[float, float, float]]]:
    """Compute floor, mid, ceiling fantasy points using odds-derived stats.

    Returns (floor, mid, ceiling, per_market_ranges).
    per_market_ranges maps market_key -> (q10, q50, q90) of the stat.
    """
    # 1) Predict mean stats per market
    mean_stats_all = predict_stats_for_player(per_bookmaker_odds)

    # 2) Build per-market ranges, focusing on primary markets only
    per_market_ranges: dict[str, tuple[float, float, float]] = {}
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


def compute_fantasy_range_model(
    per_bookmaker_odds: dict,
    market_summaries: dict[str, object],
    scoring_rules: dict[str, float],
    model: str = "baseline",
) -> tuple[float, float, float, dict[str, tuple[float, float, float]]]:
    model = (model or "baseline").lower()
    if model == "baseline":
        return compute_fantasy_range(per_bookmaker_odds, market_summaries, scoring_rules)

    # 1) Predict mean stats per market (used for fallback + sigma estimation)
    mean_stats_all = predict_stats_for_player(per_bookmaker_odds)

    # 2) Build per-market ranges via model quantiles where possible
    reg = get_model_registry()
    model_func = reg.get(model)
    per_market_ranges: dict[str, tuple[float, float, float]] = {}
    for key, mean_val in mean_stats_all.items():
        use_key = key
        if key not in PRIMARY_MARKET_WHITELIST:
            base_key = key.replace("_alternate", "")
            if base_key in mean_stats_all:
                continue
            if base_key != key:
                use_key = base_key
        summ = market_summaries.get(key) or market_summaries.get(use_key)
        if summ is None:
            q10 = max(0.0, mean_val * 0.8)
            q50 = max(0.0, mean_val)
            q90 = max(0.0, mean_val * 1.2)
            per_market_ranges[use_key] = (q10, q50, q90)
            continue
        # Fallback quantiles via parametric
        fallback_q = _market_quantiles(
            use_key,
            mean=mean_val,
            threshold=getattr(summ, "avg_threshold", 0.0),
            p_over=getattr(summ, "avg_over_prob", 0.0),
            p_under=getattr(summ, "avg_under_prob", 0.0),
        )
        q10 = q50 = q90 = None
        if model_func and use_key != "player_anytime_td":
            try:
                q = model_func(per_bookmaker_odds, use_key, fallback_q)
                if q:
                    q10, q50, q90 = q
            except Exception:
                q10 = q50 = q90 = None
        if q10 is None:
            q10, q50, q90 = fallback_q
        per_market_ranges[use_key] = (q10, q50, q90)

    # 3) Convert ranges to FP with mixed-mode bonuses (EV ramp for yards, discrete for TD/steps)
    floor_stats = {k: v[0] for k, v in per_market_ranges.items()}
    mid_stats = {k: v[1] for k, v in per_market_ranges.items()}
    ceil_stats = {k: v[2] for k, v in per_market_ranges.items()}

    # Remove yardage step bonuses from base scoring
    base_scoring = dict(scoring_rules or {})
    for bk in (
        "bonus_rush_yd_100",
        "bonus_rush_yd_200",
        "bonus_rec_yd_100",
        "bonus_rec_yd_200",
        "bonus_pass_yd_300",
        "bonus_pass_yd_400",
    ):
        if bk in base_scoring:
            base_scoring.pop(bk, None)

    floor_fp = _fantasy_points(floor_stats, base_scoring)
    mid_fp = _fantasy_points(mid_stats, base_scoring)
    ceil_fp = _fantasy_points(ceil_stats, base_scoring)

    # EV ramp for all yardage (pass/rush/rec) on floor/mid; discrete at ceiling
    def _expected_bonus_for(key: str, levels: list[tuple[float, str]]) -> float:
        try:
            summ = market_summaries.get(key)
            if not summ:
                return 0.0
            mean = float(mid_stats.get(key, 0.0) or 0.0)
            sigma = _calc_sigma(
                mean,
                getattr(summ, "avg_threshold", 0.0) or 0.0,
                getattr(summ, "avg_over_prob", 0.0) or 0.0,
                getattr(summ, "avg_under_prob", 0.0) or 0.0,
            )
            if sigma <= 0:
                return 0.0
            dist = NormalDist(mu=mean, sigma=sigma)
            total = 0.0
            for thr, bonus_key in levels:
                if bonus_key in (scoring_rules or {}):
                    try:
                        bval = float(scoring_rules.get(bonus_key, 0.0) or 0.0)
                    except Exception:
                        bval = 0.0
                    if bval != 0.0:
                        try:
                            p = max(0.0, 1.0 - float(dist.cdf(thr)))
                        except Exception:
                            p = 0.0
                        total += bval * p
            return total
        except Exception:
            return 0.0

    def _discrete_bonus(value: float, levels: list[tuple[float, str]]) -> float:
        try:
            awarded = 0.0
            for thr, key in sorted(levels, key=lambda x: x[0]):
                if key in (scoring_rules or {}) and value >= thr:
                    try:
                        awarded = float(scoring_rules.get(key, 0.0) or 0.0)
                    except Exception:
                        awarded = 0.0
            return awarded
        except Exception:
            return 0.0

    # Yardage bonuses
    rush_ev = _expected_bonus_for(
        "player_rush_yds", [(100.0, "bonus_rush_yd_100"), (200.0, "bonus_rush_yd_200")]
    )
    rec_ev = _expected_bonus_for(
        "player_reception_yds", [(100.0, "bonus_rec_yd_100"), (200.0, "bonus_rec_yd_200")]
    )
    pass_ev = _expected_bonus_for(
        "player_pass_yds", [(300.0, "bonus_pass_yd_300"), (400.0, "bonus_pass_yd_400")]
    )
    floor_fp += rush_ev + rec_ev + pass_ev
    mid_fp += rush_ev + rec_ev + pass_ev
    ceil_fp += _discrete_bonus(
        float(ceil_stats.get("player_rush_yds", 0.0) or 0.0),
        [(100.0, "bonus_rush_yd_100"), (200.0, "bonus_rush_yd_200")],
    )
    ceil_fp += _discrete_bonus(
        float(ceil_stats.get("player_reception_yds", 0.0) or 0.0),
        [(100.0, "bonus_rec_yd_100"), (200.0, "bonus_rec_yd_200")],
    )
    ceil_fp += _discrete_bonus(
        float(ceil_stats.get("player_pass_yds", 0.0) or 0.0),
        [(300.0, "bonus_pass_yd_300"), (400.0, "bonus_pass_yd_400")],
    )

    return floor_fp, mid_fp, ceil_fp, per_market_ranges


# --- Defense / Special Teams -------------------------------------------------
#
# There's no player-prop-style market for "team sacks" or "team takeaways" on
# The Odds API, so unlike offensive skill players we can't build a de-vigged
# quantile curve for a defense's own stat line. What the market *does* give us
# is the opponent's implied point total (from spread+total), which is a real,
# priced signal for defensive scoring environment: it's just also a
# deliberately partial one. It only feeds the points-allowed scoring bracket;
# sacks/INT/fumble-recovery/defensive-TD points are not modeled and will read
# as 0 here. That's a known, documented gap (see README), not a bug.

# Empirical standard deviation of an NFL team's final score around its
# Vegas-implied mean. ~9-10 points is the commonly cited figure; we use 10 as
# a slightly conservative (wider) spread.
NFL_TEAM_SCORE_SIGMA = 10.0

# (scoring_rules key, inclusive lower bound, exclusive upper bound) for
# Sleeper's standard points-allowed brackets. Bounds use the midpoint between
# adjacent integer scores so a Normal CDF can assign probability mass cleanly.
DEF_PTS_ALLOWED_BRACKETS: tuple[tuple[str, float | None, float | None], ...] = (
    ("pts_allow_0", None, 0.5),
    ("pts_allow_1_6", 0.5, 6.5),
    ("pts_allow_7_13", 6.5, 13.5),
    ("pts_allow_14_20", 13.5, 20.5),
    ("pts_allow_21_27", 20.5, 27.5),
    ("pts_allow_28_34", 27.5, 34.5),
    ("pts_allow_35p", 34.5, None),
)


def _pts_allowed_ev(mean_opp_pts: float, sigma: float, scoring_rules: dict[str, float]) -> float:
    """Expected points-allowed bonus, integrating bracket probability over a Normal(mean, sigma)."""
    dist = NormalDist(mu=mean_opp_pts, sigma=sigma)
    total = 0.0
    for key, lo, hi in DEF_PTS_ALLOWED_BRACKETS:
        p_lo = 0.0 if lo is None else dist.cdf(lo)
        p_hi = 1.0 if hi is None else dist.cdf(hi)
        prob = max(0.0, p_hi - p_lo)
        val = float((scoring_rules or {}).get(key, 0.0) or 0.0)
        total += prob * val
    return total


def _pts_allowed_bracket_value(opp_pts: float, scoring_rules: dict[str, float]) -> float:
    """Points-allowed bonus for a single realized opponent point total."""
    for key, lo, hi in DEF_PTS_ALLOWED_BRACKETS:
        lo_ok = (lo is None) or (opp_pts >= lo)
        hi_ok = (hi is None) or (opp_pts < hi)
        if lo_ok and hi_ok:
            return float((scoring_rules or {}).get(key, 0.0) or 0.0)
    return 0.0


def compute_defense_fantasy_range(
    opponent_implied_total: float,
    scoring_rules: dict[str, float],
) -> tuple[float, float, float]:
    """Floor/mid/ceiling fantasy points for a DEF, from the opponent's implied total.

    Mid uses the full expected value across points-allowed brackets. Floor and
    ceiling evaluate the bracket at the opponent's 85th/15th-percentile score
    respectively (opponent scoring MORE is worse for our defense -> floor;
    opponent scoring LESS is better -> ceiling), mirroring how offensive
    floor/ceiling is computed elsewhere in this module.
    """
    sigma = NFL_TEAM_SCORE_SIGMA
    mid = _pts_allowed_ev(opponent_implied_total, sigma, scoring_rules)
    z15 = NormalDist().inv_cdf(0.15)
    z85 = NormalDist().inv_cdf(0.85)
    opp_low = max(0.0, opponent_implied_total + z15 * sigma)
    opp_high = max(0.0, opponent_implied_total + z85 * sigma)
    ceiling = _pts_allowed_bracket_value(opp_low, scoring_rules)
    floor = _pts_allowed_bracket_value(opp_high, scoring_rules)
    return floor, mid, ceiling
