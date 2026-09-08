"""Display-only graph data derived from the canonical fitted stat distributions."""

from __future__ import annotations

from .market_math import CountDistribution

LOWER_GRAPH_QUANTILE = 0.005
# Keep the comparison chart focused on the main body of the fitted distribution.
# Heavy-tailed fits can place the 99th+ percentile hundreds of yards beyond the
# useful comparison range even when that tail contains very little probability.
UPPER_GRAPH_QUANTILE = 0.95
CONTINUOUS_GRAPH_POINTS = 101
LOW_GRANULARITY_MAX_THRESHOLD = 4

# These count metrics have enough useful integer support to compare exact outcomes.
# Additional high-granularity count markets can join this set without changing the
# frontend chart contract.
HIGH_GRANULARITY_COUNT_MARKETS = {
    "player_receptions",
    "player_rush_attempts",
    "player_touches",
}


def _is_high_granularity_count_market(market_key: str) -> bool:
    key = (market_key or "").lower()
    return key in HIGH_GRANULARITY_COUNT_MARKETS or key.endswith(("_rush_attempts", "_touches"))


def _discrete_probability_graph(distribution: CountDistribution) -> dict:
    if not distribution.counts:
        return {"kind": "discrete_pmf", "points": []}
    highest = max(distribution.counts)
    points = [
        {
            "x": float(count),
            "probability": round(float(distribution.pmf.get(count, 0.0)), 6),
        }
        for count in range(0, highest + 1)
    ]
    return {"kind": "discrete_pmf", "points": points}


def _threshold_gauge_graph(distribution: CountDistribution) -> dict:
    if not distribution.counts:
        return {"kind": "threshold_gauge", "points": []}
    highest = min(max(distribution.counts), LOW_GRANULARITY_MAX_THRESHOLD)
    points = [
        {"x": float(count), "probability": round(float(distribution.sf(count)), 6)}
        for count in range(1, highest + 1)
    ]
    return {"kind": "threshold_gauge", "points": points}


def _continuous_density_graph(distribution: object) -> dict:
    sf = getattr(distribution, "sf", None)
    quantile = getattr(distribution, "quantile", None)
    if not callable(sf) or not callable(quantile):
        return {"kind": "continuous_density", "points": []}

    try:
        lower = max(0.0, float(quantile(LOWER_GRAPH_QUANTILE)))
        upper = max(lower, float(quantile(UPPER_GRAPH_QUANTILE)))
    except (TypeError, ValueError, OverflowError):
        return {"kind": "continuous_density", "points": []}

    if upper <= lower:
        return {"kind": "continuous_density", "points": []}

    step = (upper - lower) / (CONTINUOUS_GRAPH_POINTS - 1)
    half_width = max(step / 2.0, 1e-6)
    fitted_xs = [float(value) for value in getattr(distribution, "xs", [])]
    xs = {lower + i * step for i in range(CONTINUOUS_GRAPH_POINTS)}
    xs.update(value for value in fitted_xs if lower <= value <= upper)

    points = []
    for x in sorted(xs):
        left = max(0.0, x - half_width)
        right = x + half_width
        width = right - left
        try:
            mass = max(0.0, float(sf(left)) - float(sf(right)))
        except (TypeError, ValueError, OverflowError):
            continue
        density = mass / width if width > 0 else 0.0
        points.append({"x": round(x, 2), "probability": round(density, 6)})
    return {"kind": "continuous_density", "points": points}


def distribution_graph(distribution: object, market_key: str) -> dict:
    """Return the display projection appropriate for the fitted stat distribution.

    The backend distribution remains canonical. This helper only changes how that
    already-fitted distribution is projected for comparison:

    * yardage-like continuous stats -> probability density over values;
    * high-granularity count stats -> exact discrete probability mass P(X = x);
    * low-granularity count stats -> threshold probabilities P(X >= x).

    It never refits sportsbook evidence and never participates in sampling,
    percentiles, means, fantasy scoring, or distribution fitting.
    """
    if isinstance(distribution, CountDistribution):
        if _is_high_granularity_count_market(market_key):
            return _discrete_probability_graph(distribution)
        return _threshold_gauge_graph(distribution)

    return _continuous_density_graph(distribution)
