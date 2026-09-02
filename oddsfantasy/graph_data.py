"""Display-only graph data derived from the canonical fitted stat distributions."""

from __future__ import annotations

from .market_math import CountDistribution

LOWER_GRAPH_QUANTILE = 0.005
UPPER_GRAPH_QUANTILE = 0.995
CONTINUOUS_GRAPH_POINTS = 121


def distribution_graph(distribution: object, market_key: str) -> dict:
    """Return the fitted stat survival curve for presentation.

    The graph answers the same question as an over bet: for a threshold ``x``,
    what probability does the fitted distribution assign to the player clearing
    that threshold?  This is intentionally presentation-only and does not
    participate in projection sampling, percentiles, means, or fantasy scoring.
    """
    if isinstance(distribution, CountDistribution):
        counts = distribution.counts
        if not counts:
            return {"kind": "survival_count", "points": []}
        maximum = max(counts)
        points = [
            {
                "x": float(count),
                "probability": round(float(distribution.sf(count)), 6),
            }
            for count in range(0, maximum + 1)
        ]
        return {"kind": "survival_count", "points": points}

    sf = getattr(distribution, "sf", None)
    quantile = getattr(distribution, "quantile", None)
    if not callable(sf) or not callable(quantile):
        return {"kind": "survival", "points": []}

    try:
        lower = max(0.0, float(quantile(LOWER_GRAPH_QUANTILE)))
        upper = max(lower, float(quantile(UPPER_GRAPH_QUANTILE)))
    except (TypeError, ValueError, OverflowError):
        return {"kind": "survival", "points": []}

    start = 0.0 if lower > 0.0 else lower
    if upper <= start:
        return {
            "kind": "survival",
            "points": [{"x": round(start, 2), "probability": round(float(sf(start)), 6)}],
        }

    count = CONTINUOUS_GRAPH_POINTS
    step = (upper - start) / (count - 1)
    points = []
    for index in range(count):
        x = start + index * step
        probability = max(0.0, min(1.0, float(sf(x))))
        points.append({"x": round(x, 2), "probability": round(probability, 6)})

    return {"kind": "survival", "points": points}
