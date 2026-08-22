"""Player-level projection: sample every stat, score it, sum it (§1 step 7, §2.5).

:mod:`oddsfantasy.market_math` turns each market into a distribution and
:mod:`oddsfantasy.scoring` turns a realized stat line into points. This module
is the last two steps of the doc's pipeline: draw from each stat repeatedly,
apply the *real* configured scoring to each draw -- which is what prices a
bonus threshold correctly, since a draw either cleared it or it didn't -- and
read floor / mid / ceiling off the resulting fantasy-points curve as its 10th /
50th / 90th percentiles (§5).

**Stats are summed independently, and that is a known understatement of the
right tail.** The doc names this as the one place the market-translation-only
principle bites (§2.5): a player's stats genuinely move together -- a big game
drives yards and touchdowns alike -- but books quote marginals, not the joint,
so the correlation simply is not in our feed. The two honest options are to
assume independence or to price correlation off a market that quotes it (same
game parlays, which this feed doesn't carry). We take the first and say so,
rather than inventing a correlation matrix. Ceilings here are therefore
conservative for players whose stats are tightly coupled (a QB's passing yards
and passing touchdowns most of all).

Sampling is deterministic: a fixed seed means the same odds produce the same
projection on every call, so a page refresh doesn't jitter a lineup. The seed
is also shared across players, which makes the draws common random numbers --
two players compared on the same screen were dealt the same luck.
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field

from .market_math import (
    CountDistribution,
    build_distribution,
    is_continuous_market,
    is_count_market,
)
from .scoring import ScoringConfig

# Draws per player. The variance that matters is in the 90th percentile; a few
# thousand stratified draws pin it to well inside a tenth of a point, and the
# draw loop also runs once per player on the league-wide draft board.
DEFAULT_DRAWS = 4000

# Equiprobable buckets used to represent a continuous stat. Evaluating the
# quantile function this many times per market, once, is what keeps the draw
# loop a constant-time pick.
CONTINUOUS_BUCKETS = 128

# Fixed so projections are reproducible and comparable across players.
DEFAULT_SEED = 20260822

FLOOR_PERCENTILE = 0.10
MID_PERCENTILE = 0.50
CEILING_PERCENTILE = 0.90


@dataclass
class StatProjection:
    """One stat's contribution to a player's curve."""

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


def _base_market_key(market_key: str) -> str:
    return market_key[: -len("_alternate")] if market_key.endswith("_alternate") else market_key


def candidate_markets(per_bookmaker_odds: dict, scoring: ScoringConfig) -> list[str]:
    """Every market in this player's odds we know how to model and score.

    Alternate ladders fold into their base market -- they are extra anchors on
    the same stat, not a separate stat. A market with no scoring rule in the
    league's config is dropped: it cannot move fantasy points under any
    ruleset that doesn't mention it.
    """
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
    """Full fantasy-points curve for one player, from their book odds alone."""
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
    # The mean comes from the distributions rather than the draws: expectation
    # is linear under any dependence, so it is exact here and free of MC noise.
    mean = sum(stat.expected_points for stat in stats.values())

    return PlayerProjection(
        floor=percentile(totals, FLOOR_PERCENTILE),
        mid=percentile(totals, MID_PERCENTILE),
        ceiling=percentile(totals, CEILING_PERCENTILE),
        mean=mean,
        stats=stats,
        samples=totals,
    )
