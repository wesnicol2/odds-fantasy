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


def implied_team_total(game_total: float, team_spread: float) -> float:
    """Convert a game total and that team's spread into its implied points."""
    return game_total / 2.0 - team_spread / 2.0


def opponent_implied_total(event_odds: object, opponent: str) -> tuple[float | None, int]:
    """Median opponent implied total across books in one Odds API event payload."""
    if isinstance(event_odds, dict):
        events = [event_odds]
    elif isinstance(event_odds, list):
        events = [row for row in event_odds if isinstance(row, dict)]
    else:
        events = []

    implieds: list[float] = []
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
                if game_total is not None and opponent_spread is not None:
                    implieds.append(implied_team_total(float(game_total), float(opponent_spread)))
            except (TypeError, ValueError):
                continue

    if not implieds:
        return None, 0
    return float(median(implieds)), len(implieds)


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


def defense_fantasy_range(
    opponent_total: float, scoring_rules: dict[str, float]
) -> tuple[float, float, float]:
    """10th/50th/90th style range using the points-allowed scoring component only."""
    dist = NormalDist(mu=opponent_total, sigma=NFL_TEAM_SCORE_SIGMA)
    opponent_low = max(0.0, dist.inv_cdf(0.10))
    opponent_high = max(0.0, dist.inv_cdf(0.90))
    floor = _points_allowed_value(opponent_high, scoring_rules)
    mid = _points_allowed_ev(opponent_total, scoring_rules)
    ceiling = _points_allowed_value(opponent_low, scoring_rules)
    return floor, mid, ceiling
