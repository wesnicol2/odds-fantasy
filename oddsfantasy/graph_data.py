"""Display-only graph data derived from the canonical fitted stat distributions."""

from __future__ import annotations

import math

from .market_math import CountDistribution

YARDAGE_BUCKET_WIDTH = 5.0
DEFAULT_BUCKET_WIDTH = 1.0
LOWER_GRAPH_QUANTILE = 0.005
UPPER_GRAPH_QUANTILE = 0.995


def bucket_width_for_market(market_key: str) -> float:
    """Choose a readable display bucket without changing the fitted distribution."""
    return YARDAGE_BUCKET_WIDTH if (market_key or "").endswith("_yds") else DEFAULT_BUCKET_WIDTH


def distribution_graph(distribution: object, market_key: str) -> dict:
    """Return probability-at-x display points from an already-fitted distribution.

    Count markets use their exact PMF. Continuous markets use fixed-width buckets
    centered on x and evaluate probability mass with the distribution's own CDF.
    This function is presentation only; it does not participate in projection
    sampling, percentiles, means, or fantasy scoring.
    """
    if isinstance(distribution, CountDistribution):
        values, weights = distribution.support()
        return {
            "kind": "exact_count",
            "bucket_width": 1.0,
            "points": [
                {"x": round(float(value), 2), "probability": round(float(weight), 6)}
                for value, weight in zip(values, weights, strict=True)
            ],
        }

    cdf = getattr(distribution, "cdf", None)
    quantile = getattr(distribution, "quantile", None)
    if not callable(cdf) or not callable(quantile):
        return {"kind": "bucket", "bucket_width": DEFAULT_BUCKET_WIDTH, "points": []}

    width = bucket_width_for_market(market_key)
    try:
        lower = max(0.0, float(quantile(LOWER_GRAPH_QUANTILE)))
        upper = max(lower, float(quantile(UPPER_GRAPH_QUANTILE)))
    except (TypeError, ValueError, OverflowError):
        return {"kind": "bucket", "bucket_width": width, "points": []}

    start = math.floor(lower / width) * width
    end = math.ceil(upper / width) * width
    half = width / 2.0
    points: list[dict[str, float]] = []
    x = start
    while x <= end + 1e-9:
        left = max(0.0, x - half)
        right = x + half
        probability = max(0.0, min(1.0, float(cdf(right)) - float(cdf(left))))
        points.append({"x": round(x, 2), "probability": round(probability, 6)})
        x += width

    return {"kind": "bucket", "bucket_width": width, "points": points}
