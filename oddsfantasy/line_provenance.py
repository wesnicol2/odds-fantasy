"""Display provenance for the sportsbook points behind a fitted stat curve."""

from __future__ import annotations

from .market_math import _book_anchors


def fair_line_points(per_bookmaker_odds: dict, market_key: str) -> list[dict]:
    """Return each book's de-vigged over probability at every paired threshold.

    This deliberately reuses the exact per-book anchor logic used by
    ``collect_anchors`` before the median consensus step. It is presentation
    metadata only: no new odds conversion or statistical model lives here.
    """
    points: list[dict] = []
    for book, markets in (per_bookmaker_odds or {}).items():
        points.extend(
            {
                "book": str(book),
                "threshold": round(float(anchor.threshold), 2),
                "survival": round(float(anchor.survival), 6),
            }
            for anchor in _book_anchors(markets or {}, market_key)
        )
    points.sort(key=lambda point: (point["threshold"], point["book"]))
    return points


def fair_probability_lookup(
    per_bookmaker_odds: dict, market_key: str
) -> dict[tuple[str, float], float]:
    """Index fair over probabilities for joining them to raw source rows."""
    return {
        (point["book"], float(point["threshold"])): float(point["survival"])
        for point in fair_line_points(per_bookmaker_odds, market_key)
    }
