"""Defense comparison math derived from game spread and total markets."""

from __future__ import annotations

from statistics import NormalDist, median

NFL_TEAM_SCORE_SIGMA = 10.0
DEF_PTS_ALLOWED_BRACKETS: tuple[tuple[str, float | None, float | None], ...] = (
    ("pts_allow_0", None, 0.5),
    ("pts_allow_1_6", 0.5, 6.5),
    ("pts_allow_7_13", 6.5, 13.5),
    ("pts_allow_14_20", 13.5, 20.5),
    ("pts_allow_21_27", 20.5, 27.5),
    ("pts_allow_28_34", 27.5, 34.5),
    ("pts_allow_35p", 34.5, None),
)
BRACKET_LABELS: dict[str, str] = {
    "pts_allow_0": "0",
    "pts_allow_1_6": "1-6",
    "pts_allow_7_13": "7-13",
    "pts_allow_14_20": "14-20",
    "pts_allow_21_27": "21-27",
    "pts_allow_28_34": "28-34",
    "pts_allow_35p": "35+",
}
FLOOR_PERCENTILE = 0.10
CEILING_PERCENTILE = 0.90


def implied_team_total(game_total: float, team_spread: float) -> float:
    """Convert a game total and that team's spread into its implied points."""
    return game_total / 2.0 - team_spread / 2.0


def opponent_implied_breakdown(event_odds: object, opponent: str) -> dict:
    """Every book line behind the opponent implied total, plus the median it feeds.

    The ranking only needs the median, but a user asking where the number came
    from needs the exact rows it was taken over. Both come out of one pass so
    the evidence shown cannot drift from the number it explains.
    """
    if isinstance(event_odds, dict):
        events = [event_odds]
    elif isinstance(event_odds, list):
        events = [row for row in event_odds if isinstance(row, dict)]
    else:
        events = []

    books: list[dict] = []
    for event in events:
        for book in event.get("bookmakers", []) or []:
            game_total = None
            opponent_spread = None
            for market in book.get("markets", []) or []:
                key = market.get("key")
                if key == "totals":
                    for outcome in market.get("outcomes", []) or []:
                        if outcome.get("name") == "Over":
                            game_total = outcome.get("point")
                            break
                elif key == "spreads":
                    for outcome in market.get("outcomes", []) or []:
                        if outcome.get("name") == opponent:
                            opponent_spread = outcome.get("point")
                            break
            try:
                if game_total is None or opponent_spread is None:
                    continue
                parsed_total = float(game_total)
                parsed_spread = float(opponent_spread)
            except (TypeError, ValueError):
                continue
            books.append(
                {
                    "book": str(book.get("key") or book.get("title") or "unknown"),
                    "game_total": round(parsed_total, 2),
                    "opponent_spread": round(parsed_spread, 2),
                    "implied_total": round(implied_team_total(parsed_total, parsed_spread), 2),
                }
            )

    books.sort(key=lambda row: (row["implied_total"], row["book"]))
    values = [row["implied_total"] for row in books]
    return {
        "books": books,
        "book_count": len(books),
        "median": round(float(median(values)), 2) if values else None,
    }


def opponent_implied_total(event_odds: object, opponent: str) -> tuple[float | None, int]:
    """Median opponent implied total across books in one Odds API event payload."""
    breakdown = opponent_implied_breakdown(event_odds, opponent)
    return breakdown["median"], breakdown["book_count"]


def _points_allowed_value(opponent_points: float, scoring_rules: dict[str, float]) -> float:
    for key, low, high in DEF_PTS_ALLOWED_BRACKETS:
        if (low is None or opponent_points >= low) and (high is None or opponent_points < high):
            return float((scoring_rules or {}).get(key, 0.0) or 0.0)
    return 0.0


def _points_allowed_ev(mean: float, scoring_rules: dict[str, float]) -> float:
    dist = NormalDist(mu=mean, sigma=NFL_TEAM_SCORE_SIGMA)
    total = 0.0
    for key, low, high in DEF_PTS_ALLOWED_BRACKETS:
        p_low = 0.0 if low is None else dist.cdf(low)
        p_high = 1.0 if high is None else dist.cdf(high)
        total += max(0.0, p_high - p_low) * float((scoring_rules or {}).get(key, 0.0) or 0.0)
    return total


def _bracket_for(opponent_points: float) -> tuple[str, float | None, float | None]:
    for key, low, high in DEF_PTS_ALLOWED_BRACKETS:
        if (low is None or opponent_points >= low) and (high is None or opponent_points < high):
            return key, low, high
    return DEF_PTS_ALLOWED_BRACKETS[-1]


def defense_fantasy_range(
    opponent_total: float, scoring_rules: dict[str, float]
) -> tuple[float, float, float]:
    """10th/50th/90th style range using the points-allowed scoring component only."""
    dist = NormalDist(mu=opponent_total, sigma=NFL_TEAM_SCORE_SIGMA)
    opponent_low = max(0.0, dist.inv_cdf(FLOOR_PERCENTILE))
    opponent_high = max(0.0, dist.inv_cdf(CEILING_PERCENTILE))
    floor = _points_allowed_value(opponent_high, scoring_rules)
    mid = _points_allowed_ev(opponent_total, scoring_rules)
    ceiling = _points_allowed_value(opponent_low, scoring_rules)
    return floor, mid, ceiling


def defense_range_breakdown(opponent_total: float, scoring_rules: dict[str, float]) -> dict:
    """Every input behind Floor / Mid / Ceiling for one defense.

    Floor and Ceiling are single bracket lookups at one opponent-score
    percentile; Mid is a probability-weighted sum across every bracket. The
    breakdown reports each as it is actually computed rather than restating the
    result, so the shown arithmetic is the arithmetic the ranking used.
    """
    dist = NormalDist(mu=opponent_total, sigma=NFL_TEAM_SCORE_SIGMA)
    opponent_low = max(0.0, dist.inv_cdf(FLOOR_PERCENTILE))
    opponent_high = max(0.0, dist.inv_cdf(CEILING_PERCENTILE))

    def bracket_row(opponent_points: float, percentile: float) -> dict:
        key, _low, _high = _bracket_for(opponent_points)
        return {
            "opponent_points": round(opponent_points, 2),
            "percentile": percentile,
            "bracket": key,
            "bracket_label": BRACKET_LABELS.get(key, key),
            "points": round(float((scoring_rules or {}).get(key, 0.0) or 0.0), 2),
        }

    brackets: list[dict] = []
    for key, low, high in DEF_PTS_ALLOWED_BRACKETS:
        p_low = 0.0 if low is None else dist.cdf(low)
        p_high = 1.0 if high is None else dist.cdf(high)
        probability = max(0.0, p_high - p_low)
        points = float((scoring_rules or {}).get(key, 0.0) or 0.0)
        brackets.append(
            {
                "bracket": key,
                "bracket_label": BRACKET_LABELS.get(key, key),
                "probability": round(probability, 4),
                "points": round(points, 2),
                "contribution": round(probability * points, 3),
            }
        )

    return {
        "opponent_mean": round(float(opponent_total), 2),
        "sigma": NFL_TEAM_SCORE_SIGMA,
        # A defense scores least when its opponent scores most, so the defense
        # floor reads off the high opponent percentile and the ceiling the low.
        "floor": bracket_row(opponent_high, CEILING_PERCENTILE),
        "ceiling": bracket_row(opponent_low, FLOOR_PERCENTILE),
        "mid": {
            "points": round(_points_allowed_ev(opponent_total, scoring_rules), 2),
            "brackets": brackets,
        },
    }
