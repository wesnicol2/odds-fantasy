"""Display-only graph data derived from the canonical fitted stat distributions."""

from __future__ import annotations

from .market_math import CountDistribution

LOWER_GRAPH_QUANTILE = 0.005
UPPER_GRAPH_QUANTILE = 0.995
CONTINUOUS_GRAPH_POINTS = 101


def distribution_graph(distribution: object, market_key: str) -> dict:
    """Return a probability curve from an already-fitted stat distribution.

    The graph is deliberately a survival view rather than a PMF/density view:
    x is a stat threshold and y is the fitted probability of reaching/exceeding
    that threshold. That puts the sportsbook over/under anchors on the same
    visual coordinate system as the fitted curve.

    This is presentation only. It does not participate in projection sampling,
    percentiles, means, fantasy scoring, or distribution fitting.
    """
    if isinstance(distribution, CountDistribution):
        if not distribution.counts:
            return {"kind": "survival_step", "points": []}
        highest = max(distribution.counts)
        points = [
            {"x": float(count), "probability": round(float(distribution.sf(count)), 6)}
            for count in range(1, highest + 1)
        ]
        return {"kind": "survival_step", "points": points}

    sf = getattr(distribution, "sf", None)
    quantile = getattr(distribution, "quantile", None)
    if not callable(sf) or not callable(quantile):
        return {"kind": "survival", "points": []}

    try:
        lower = max(0.0, float(quantile(LOWER_GRAPH_QUANTILE)))
        upper = max(lower, float(quantile(UPPER_GRAPH_QUANTILE)))
    except (TypeError, ValueError, OverflowError):
        return {"kind": "survival", "points": []}

    if upper <= lower:
        return {
            "kind": "survival",
            "points": [{"x": round(lower, 2), "probability": round(float(sf(lower)), 6)}],
        }

    fitted_xs = [float(value) for value in getattr(distribution, "xs", [])]
    step = (upper - lower) / (CONTINUOUS_GRAPH_POINTS - 1)
    xs = {lower + i * step for i in range(CONTINUOUS_GRAPH_POINTS)}
    xs.update(value for value in fitted_xs if lower <= value <= upper)
    points = []
    for x in sorted(xs):
        points.append({"x": round(x, 2), "probability": round(float(sf(x)), 6)})
    return {"kind": "survival", "points": points}
