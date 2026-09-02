"""Build the canonical fantasy-points probability curve for one player.

Each sportsbook market is reconstructed in :mod:`oddsfantasy.market_math`, each
sampled stat is scored with the league rules in :mod:`oddsfantasy.scoring`, and
the stat point values are summed into one player-level distribution.  Floor,
mid and ceiling are the 10th, 50th and 90th percentiles of that same curve.
"""

from __future__ import annotations

import bisect
import random
from dataclasses import dataclass, field

from .market_math import CountDistribution, build_distribution, is_continuous_market, is_count_market
from .scoring import ScoringConfig

DEFAULT_DRAWS = 4000
CONTINUOUS_BUCKETS = 128
DEFAULT_SEED = 20260822

FLOOR_PERCENTILE = 0.10
MID_PERCENTILE = 0.50
CEILING_PERCENTILE = 0.90


@dataclass
class StatProjection:
    market_key: str
    distribution: object
    stat_range: tuple[float, float, float]
    expected_points: float
    point_values: list[float] = field(default_factory=list)
    cumulative_weights: list[float] = field(default_factory=list)


@dataclass
class PlayerProjection:
    floor: float
    mid: float
    ceiling: float
    mean: float
    stats: dict[str, StatProjection] = field(default_factory=dict)
    samples: list[float] = field(default_factory=list)

    @property
    def per_market_ranges(self) -> dict[str, tuple[float, float, float]]:
        return {key: stat.stat_range for key, stat in self.stats.items()}

    @property
    def has_projection(self) -> bool:
        return bool(self.stats and self.samples)


def percentile(sorted_values: list[float], q: float) -> float:
    """Linear-interpolated percentile of an already-sorted list."""
    n = len(sorted_values)
    if n == 0:
        return 0.0
    if n == 1:
        return sorted_values[0]
    position = (n - 1) * min(max(q, 0.0), 1.0)
    lower = int(position)
    upper = min(lower + 1, n - 1)
    fraction = position - lower
    return sorted_values[lower] * (1.0 - fraction) + sorted_values[upper] * fraction


def survival_curve(samples: list[float], points: int = 61) -> list[dict[str, float]]:
    """Compact ``P(FP >= x)`` curve from the exact projection samples.

    The UI needs dozens of points, not all 4,000 Monte Carlo samples.  This
    downsampling is display-only: floor/mid/ceiling continue to come from the
    complete sample set.
    """
    if not samples:
        return []
    values = samples if samples == sorted(samples) else sorted(samples)
    lo = min(0.0, values[0])
    hi = values[-1]
    if hi <= lo:
        return [{"x": round(lo, 2), "survival": 1.0}]
    count = max(2, int(points))
    step = (hi - lo) / (count - 1)
    n = len(values)
    out: list[dict[str, float]] = []
    for i in range(count):
        x = lo + i * step
        idx = bisect.bisect_left(values, x)
        out.append({"x": round(x, 2), "survival": round((n - idx) / n, 4)})
    return out


def _base_market_key(market_key: str) -> str:
    return market_key[: -len("_alternate")] if market_key.endswith("_alternate") else market_key


def candidate_markets(per_bookmaker_odds: dict, scoring: ScoringConfig) -> list[str]:
    """Markets present in the feed that the methodology can model and score."""
    keys: set[str] = set()
    for markets in (per_bookmaker_odds or {}).values():
        for market_key in markets or {}:
            keys.add(_base_market_key(str(market_key)))
    modeled = [k for k in sorted(keys) if is_count_market(k) or is_continuous_market(k)]
    return [k for k in modeled if scoring.for_market(k) is not None]


def build_stat_projection(
    per_bookmaker_odds: dict,
    market_key: str,
    scoring: ScoringConfig,
) -> StatProjection | None:
    stat_scoring = scoring.for_market(market_key)
    if stat_scoring is None:
        return None
    distribution = build_distribution(per_bookmaker_odds, market_key)
    if distribution is None:
        return None

    buckets = 0 if isinstance(distribution, CountDistribution) else CONTINUOUS_BUCKETS
    values, weights = distribution.support(buckets)
    if not values:
        return None

    point_values = [stat_scoring.points_for(v) for v in values]
    expected_points = sum(p * w for p, w in zip(point_values, weights, strict=True))

    cumulative: list[float] = []
    running = 0.0
    for weight in weights:
        running += weight
        cumulative.append(running)

    stat_range = (
        float(distribution.quantile(FLOOR_PERCENTILE)),
        float(distribution.quantile(MID_PERCENTILE)),
        float(distribution.quantile(CEILING_PERCENTILE)),
    )
    return StatProjection(
        market_key=market_key,
        distribution=distribution,
        stat_range=stat_range,
        expected_points=expected_points,
        point_values=point_values,
        cumulative_weights=cumulative,
    )


def project_player(
    per_bookmaker_odds: dict,
    scoring_rules: dict | ScoringConfig,
    draws: int = DEFAULT_DRAWS,
    seed: int = DEFAULT_SEED,
) -> PlayerProjection:
    """Full fantasy-points curve for one player, from their sportsbook odds."""
    scoring = (
        scoring_rules
        if isinstance(scoring_rules, ScoringConfig)
        else ScoringConfig.from_settings(scoring_rules)
    )

    stats: dict[str, StatProjection] = {}
    for market_key in candidate_markets(per_bookmaker_odds, scoring):
        try:
            stat = build_stat_projection(per_bookmaker_odds, market_key, scoring)
        except Exception:
            stat = None
        if stat is not None:
            stats[market_key] = stat

    if not stats:
        return PlayerProjection(floor=0.0, mid=0.0, ceiling=0.0, mean=0.0)

    per_stat_draws: list[list[float]] = []
    for index, stat in enumerate(stats.values()):
        rng = random.Random(seed + index * 7919)
        per_stat_draws.append(
            rng.choices(stat.point_values, cum_weights=stat.cumulative_weights, k=draws)
        )

    totals = sorted(map(sum, zip(*per_stat_draws, strict=True)))
    mean = sum(stat.expected_points for stat in stats.values())

    return PlayerProjection(
        floor=percentile(totals, FLOOR_PERCENTILE),
        mid=percentile(totals, MID_PERCENTILE),
        ceiling=percentile(totals, CEILING_PERCENTILE),
        mean=mean,
        stats=stats,
        samples=totals,
    )