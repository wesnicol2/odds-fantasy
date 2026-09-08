"""Display-only graph data derived from the canonical fitted stat distributions."""

from __future__ import annotations

import math

from .market_math import CountDistribution

LOWER_GRAPH_QUANTILE = 0.005
# Keep the comparison chart focused on the main body of the fitted distribution.
# Heavy-tailed fits can place the 99th+ percentile hundreds of yards beyond the
# useful comparison range even when that tail contains very little probability.
UPPER_GRAPH_QUANTILE = 0.95
CONTINUOUS_GRAPH_POINTS = 181
CONTINUOUS_KDE_SAMPLES = 257
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


def _continuous_samples(quantile: object) -> list[float]:
    if not callable(quantile):
        return []
    samples: list[float] = []
    for index in range(CONTINUOUS_KDE_SAMPLES):
        u = (index + 0.5) / CONTINUOUS_KDE_SAMPLES
        try:
            value = max(0.0, float(quantile(u)))
        except (TypeError, ValueError, OverflowError):
            continue
        if math.isfinite(value):
            samples.append(value)
    return samples


def _continuous_bandwidth(
    samples: list[float],
    quantile: object,
    step: float,
    span: float,
) -> float:
    if not samples:
        return max(step, 1e-6)

    mean = sum(samples) / len(samples)
    variance = sum((value - mean) ** 2 for value in samples) / len(samples)
    std = math.sqrt(max(0.0, variance))

    iqr_scale = 0.0
    if callable(quantile):
        try:
            q25 = float(quantile(0.25))
            q75 = float(quantile(0.75))
            if math.isfinite(q25) and math.isfinite(q75) and q75 > q25:
                iqr_scale = (q75 - q25) / 1.34
        except (TypeError, ValueError, OverflowError):
            pass

    positive_scales = [value for value in (std, iqr_scale) if value > 0]
    scale = min(positive_scales) if positive_scales else max(span / 8.0, step)
    silverman = 0.9 * scale * (len(samples) ** -0.2)

    # The graph is a display projection, so the bandwidth deliberately spans more
    # than one render step. This removes narrow spikes/holes caused by sparse or
    # locally flat sportsbook anchors without changing the canonical distribution
    # used for projections, means, percentiles, or scoring.
    minimum = max(step * 1.5, 0.75)
    maximum = max(minimum, span * 0.08)
    return min(max(silverman, minimum), maximum)


def _reflected_gaussian_density(x: float, samples: list[float], bandwidth: float) -> float:
    if not samples or bandwidth <= 0:
        return 0.0
    inverse = 1.0 / (len(samples) * bandwidth * math.sqrt(2.0 * math.pi))
    total = 0.0
    for value in samples:
        direct = (x - value) / bandwidth
        reflected = (x + value) / bandwidth
        total += math.exp(-0.5 * direct * direct) + math.exp(-0.5 * reflected * reflected)
    return max(0.0, total * inverse)


def _continuous_density_graph(distribution: object) -> dict:
    quantile = getattr(distribution, "quantile", None)
    if not callable(quantile):
        return {"kind": "continuous_density", "points": []}

    try:
        lower = max(0.0, float(quantile(LOWER_GRAPH_QUANTILE)))
        upper = max(lower, float(quantile(UPPER_GRAPH_QUANTILE)))
    except (TypeError, ValueError, OverflowError):
        return {"kind": "continuous_density", "points": []}

    if not math.isfinite(lower) or not math.isfinite(upper) or upper <= lower:
        return {"kind": "continuous_density", "points": []}

    samples = _continuous_samples(quantile)
    if not samples:
        return {"kind": "continuous_density", "points": []}

    step = (upper - lower) / (CONTINUOUS_GRAPH_POINTS - 1)
    bandwidth = _continuous_bandwidth(samples, quantile, step, upper - lower)
    points = [
        {
            "x": round(lower + index * step, 2),
            "probability": round(
                _reflected_gaussian_density(lower + index * step, samples, bandwidth),
                6,
            ),
        }
        for index in range(CONTINUOUS_GRAPH_POINTS)
    ]
    return {"kind": "continuous_density", "points": points}


def distribution_graph(distribution: object, market_key: str) -> dict:
    """Return the display projection appropriate for the fitted stat distribution.

    The backend distribution remains canonical. This helper only changes how that
    already-fitted distribution is projected for comparison:

    * yardage-like continuous stats -> smoothed probability density over values;
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
