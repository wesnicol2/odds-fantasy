"""Odds -> probability -> distribution, per the methodology doc (§2.1-§2.3, §3, §4).

This module is steps 1-4 of the doc's pipeline for a single stat:

1. odds -> implied probability
2. de-vig each book's two-way line -> that book's fair P(over)
3. combine books by taking the **median** of the fair probabilities
4. reconstruct the distribution from the resulting anchors

Two reconstructions come out the far end, matching the doc's split:

* :class:`ContinuousDistribution` for yardage-type stats -- monotone cubic
  (PCHIP) between anchors, lognormal tails beyond them (§2.3, §3.4). Rushing,
  receiving and passing yards share it exactly; only the fitted anchors differ.
* :class:`CountDistribution` for small-integer stats -- the cumulative lines
  *are* the survival curve, so the distribution is read off by differencing
  adjacent lines, with the top posted line scored at its floor (§4.2). No
  parametric fit is involved unless the ladder is too sparse to difference.

Nothing here knows about fantasy scoring; that is :mod:`oddsfantasy.scoring`.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from statistics import NormalDist, median

from .prob_models import (
    _fit_lognormal_from_two_points,
    _lognormal_quantile,
    _pav_isotonic,
    _pchip_inverse_cdf,
    _pchip_slopes,
    _poisson_fit_lambda,
)

# Continuous (yardage-type) markets: identical reconstruction, different anchors.
CONTINUOUS_MARKETS = {
    "player_pass_yds",
    "player_rush_yds",
    "player_reception_yds",
}

# Small-integer markets whose posted cumulative lines are the survival curve.
COUNT_MARKETS = {
    "player_anytime_td",
    "player_pass_tds",
    "player_rush_tds",
    "player_reception_tds",
    "player_pass_interceptions",
    "player_receptions",
}

# Probabilities are clamped this far from 0/1 before any inverse-normal call.
_EPS = 1e-6

# How many integer buckets above the highest *fitted* count anchor we are
# willing to enumerate when a sparse ladder forces a parametric fill.
_MAX_COUNT = 12

# A tail is fitted through the two outermost anchors, which only pins a shape
# if those anchors actually differ in probability. Two books quoting nearly the
# same price at slightly different lines say almost nothing about the slope,
# and fitting to them produces an absurd tail, so the fit walks inward for a
# pair separated by at least this much probability. This is a numerical
# stability floor, not a modelling knob -- it changes which anchors the fit
# uses, never what the anchors say.
_MIN_TAIL_F_GAP = 0.02

# Shape assumption of last resort, used only where the market determines no
# width at all: the spread the pre-existing single-line model falls back to.
_ASSUMED_CV = 0.25


def american_to_probability(odds: float | int | None) -> float | None:
    """Implied probability of American odds (§3.2).

    The live feed is decimal (The Odds API's default format, which is what
    :func:`decimal_to_probability` handles). This exists because the doc's
    worked examples are quoted in American odds, and being able to run those
    numbers through the real code is what makes them a check on it.
    """
    try:
        value = float(odds)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None
    if value == 0:
        return None
    if value < 0:
        return (-value) / ((-value) + 100.0)
    return 100.0 / (value + 100.0)


def decimal_to_probability(odds: float | int | None) -> float | None:
    """Implied probability of decimal odds -- 1/odds (§3.2)."""
    try:
        value = float(odds)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None
    if value <= 0:
        return None
    return 1.0 / value


def devig_proportional(p_over_raw: float, p_under_raw: float) -> tuple[float, float] | None:
    """Strip a book's margin proportionally: each side divided by their sum (§2.1).

    Returns (fair P(over), fair P(under)), which sum to 1 by construction.
    """
    total = (p_over_raw or 0.0) + (p_under_raw or 0.0)
    if total <= 0:
        return None
    return p_over_raw / total, p_under_raw / total


@dataclass(frozen=True)
class Anchor:
    """One point on the survival curve: P(stat > threshold) = survival."""

    threshold: float
    survival: float


def _sides_from_market(market: dict) -> list[tuple[float, float | None, float | None]]:
    """Flatten one book's entry for a market into (point, over_odds, under_odds) rows.

    Handles both shapes the aggregator produces: a main line
    (``{"over": {...}, "under": {...}}``) and an alternate ladder
    (``{"alts": {"over": [...], "under": [...]}}``).
    """
    rows: list[tuple[float, float | None, float | None]] = []
    if not isinstance(market, dict):
        return rows

    alts = market.get("alts")
    if isinstance(alts, dict):
        under_by_point: dict[float, float] = {}
        for item in alts.get("under") or []:
            try:
                under_by_point[float(item.get("point"))] = float(item.get("odds"))
            except (TypeError, ValueError):
                continue
        seen: set[float] = set()
        for item in alts.get("over") or []:
            try:
                point = float(item.get("point"))
                over_odds = float(item.get("odds"))
            except (TypeError, ValueError):
                continue
            seen.add(point)
            rows.append((point, over_odds, under_by_point.get(point)))
        for point, under_odds in under_by_point.items():
            if point not in seen:
                rows.append((point, None, under_odds))
        return rows

    over = market.get("over") or {}
    under = market.get("under") or {}
    if not over and not under:
        return rows
    point = over.get("point") if "point" in over else under.get("point")
    try:
        point = float(point if point is not None else 0.0)
    except (TypeError, ValueError):
        return rows
    over_odds = over.get("odds")
    under_odds = under.get("odds")
    rows.append(
        (
            point,
            float(over_odds) if over_odds else None,
            float(under_odds) if under_odds else None,
        )
    )
    return rows


def _book_anchors(book_markets: dict, market_key: str) -> list[Anchor]:
    """Fair P(over) at every threshold one book posts for a market (§2.1).

    A two-way line is de-vigged proportionally. A one-sided rung of an
    alternate ladder ("125+" with no under) can't be de-vigged as a two-way
    market, so it is corrected by that same book's *own* measured overround on
    this market -- its margin, taken from its two-way lines, not a constant we
    picked. If the book posts no two-way line here, the raw implied probability
    is used and simply carries the vig.
    """
    rows: list[tuple[float, float | None, float | None]] = []
    for key in (market_key, f"{market_key}_alternate"):
        entry = (book_markets or {}).get(key)
        if entry:
            rows.extend(_sides_from_market(entry))

    overrounds: list[float] = []
    for _point, over_odds, under_odds in rows:
        p_over = decimal_to_probability(over_odds)
        p_under = decimal_to_probability(under_odds)
        if p_over is not None and p_under is not None:
            overrounds.append(p_over + p_under)
    overround = median(overrounds) if overrounds else 1.0
    if overround <= 0:
        overround = 1.0

    anchors: list[Anchor] = []
    for point, over_odds, under_odds in rows:
        p_over = decimal_to_probability(over_odds)
        p_under = decimal_to_probability(under_odds)
        fair: float | None = None
        if p_over is not None and p_under is not None:
            devigged = devig_proportional(p_over, p_under)
            if devigged is not None:
                fair = devigged[0]
        elif p_over is not None:
            fair = p_over / overround
        elif p_under is not None:
            fair = 1.0 - (p_under / overround)
        if fair is None:
            continue
        anchors.append(Anchor(threshold=point, survival=min(max(fair, 0.0), 1.0)))
    return anchors


def collect_anchors(per_bookmaker_odds: dict, market_key: str) -> list[Anchor]:
    """De-vig per book, combine books by median, enforce monotonicity (§2.1-§2.3).

    De-vigging happens per book *before* combining, because books carry
    different margins and blending raw prices bakes their vig into the result.
    The combine is a plain median -- that is the whole robustness story, no
    weights and no outlier rule (§2.2). Finally isotonic regression (PAV)
    flattens any dip a noisy line introduced, so the curve is a real CDF and
    differencing it can't produce negative mass.
    """
    by_threshold: dict[float, list[float]] = {}
    for book_markets in (per_bookmaker_odds or {}).values():
        for anchor in _book_anchors(book_markets or {}, market_key):
            by_threshold.setdefault(anchor.threshold, []).append(anchor.survival)

    if not by_threshold:
        return []

    thresholds = sorted(by_threshold)
    survivals = [median(by_threshold[t]) for t in thresholds]
    # Isotonic on the CDF (nondecreasing) == isotonic on survival (nonincreasing).
    cdf = _pav_isotonic([1.0 - s for s in survivals])
    return [Anchor(threshold=t, survival=1.0 - f) for t, f in zip(thresholds, cdf, strict=True)]


def _pchip_eval(xs: list[float], ys: list[float], x: float) -> float:
    """Evaluate the monotone cubic (PCHIP) interpolant of (xs, ys) at x."""
    n = len(xs)
    if n == 0:
        return 0.0
    if n == 1 or x <= xs[0]:
        return ys[0]
    if x >= xs[-1]:
        return ys[-1]
    i = 0
    for k in range(n - 1):
        if xs[k] <= x <= xs[k + 1]:
            i = k
            break
    x0, x1 = xs[i], xs[i + 1]
    y0, y1 = ys[i], ys[i + 1]
    h = (x1 - x0) or 1.0
    slopes = _pchip_slopes(xs, ys)
    m0, m1 = slopes[i], slopes[i + 1]
    t = (x - x0) / h
    t2 = t * t
    t3 = t2 * t
    return (
        (2 * t3 - 3 * t2 + 1) * y0
        + (t3 - 2 * t2 + t) * h * m0
        + (-2 * t3 + 3 * t2) * y1
        + (t3 - t2) * h * m1
    )


def _assumed_width_fit(x: float, cdf_at_x: float) -> tuple[float, float] | None:
    """Lognormal through one point, with its width assumed rather than fitted.

    Reached only where the anchors determine no width: a single posted
    threshold, or outermost anchors too close in probability to pin a slope.
    """
    if x <= 0:
        return None
    sigma = math.sqrt(math.log(1.0 + _ASSUMED_CV**2))
    z = NormalDist().inv_cdf(min(max(cdf_at_x, _EPS), 1.0 - _EPS))
    return math.log(x) - sigma * z, sigma


def _tail_fit(xs: list[float], cdf_ys: list[float], upper: bool) -> tuple[float, float] | None:
    """Fit the lognormal that continues the curve past the outermost anchor."""
    n = len(xs)
    end = n - 1 if upper else 0
    inward = range(n - 2, -1, -1) if upper else range(1, n)
    for j in inward:
        if abs(cdf_ys[j] - cdf_ys[end]) < _MIN_TAIL_F_GAP:
            continue
        fit = _fit_lognormal_from_two_points(
            max(xs[j], _EPS), cdf_ys[j], max(xs[end], _EPS), cdf_ys[end]
        )
        if fit and fit[1] > 0:
            return fit
    return _assumed_width_fit(xs[end], cdf_ys[end])


class ContinuousDistribution:
    """A yardage-type distribution: PCHIP between anchors, lognormal tails (§2.3).

    The tails are where the ceiling lives, so beyond the outermost anchors the
    curve continues as a lognormal fitted to the two anchors on that end --
    positive and right-skewed, which is the shape a yardage market has. The
    near-zero lower tail gets no special handling: if the market gives a bad
    game weight, it is already in the ladder.
    """

    def __init__(self, anchors: list[Anchor]):
        if len(anchors) < 2:
            raise ValueError("ContinuousDistribution needs at least two anchors")
        self.xs = [float(a.threshold) for a in anchors]
        self.cdf_ys = [min(max(1.0 - float(a.survival), 0.0), 1.0) for a in anchors]
        self._lower_fit = _tail_fit(self.xs, self.cdf_ys, upper=False)
        self._upper_fit = _tail_fit(self.xs, self.cdf_ys, upper=True)

    def quantile(self, u: float) -> float:
        u = min(max(u, _EPS), 1.0 - _EPS)
        if u < self.cdf_ys[0]:
            if self._lower_fit:
                mu, sigma = self._lower_fit
                return max(0.0, _lognormal_quantile(mu, sigma, u))
            # No usable fit: fall back to a straight line down to zero.
            span = self.cdf_ys[0] or 1.0
            return max(0.0, self.xs[0] * (u / span))
        if u > self.cdf_ys[-1]:
            if self._upper_fit:
                mu, sigma = self._upper_fit
                return max(self.xs[-1], _lognormal_quantile(mu, sigma, u))
            return self.xs[-1]
        return max(0.0, _pchip_inverse_cdf(self.xs, self.cdf_ys, u))

    def cdf(self, x: float) -> float:
        if x <= self.xs[0]:
            if self._lower_fit and x > 0:
                mu, sigma = self._lower_fit
                return min(max(_lognormal_cdf(mu, sigma, x), 0.0), self.cdf_ys[0])
            return 0.0 if x < self.xs[0] else self.cdf_ys[0]
        if x >= self.xs[-1]:
            if self._upper_fit:
                mu, sigma = self._upper_fit
                return min(max(_lognormal_cdf(mu, sigma, x), self.cdf_ys[-1]), 1.0)
            return self.cdf_ys[-1]
        return min(max(_pchip_eval(self.xs, self.cdf_ys, x), 0.0), 1.0)

    def sf(self, x: float) -> float:
        """P(stat >= x). Continuous, so the >= / > distinction doesn't bite."""
        return 1.0 - self.cdf(x)

    def support(self, buckets: int) -> tuple[list[float], list[float]]:
        """Equiprobable representation: `buckets` values, each with weight 1/n.

        Evaluating the quantile function at the midpoints of `buckets` equal
        probability slices is stratified sampling done once: it captures the
        tails at the resolution we can afford and makes drawing from this stat
        a constant-time pick afterwards.
        """
        n = max(2, int(buckets))
        values = [self.quantile((i + 0.5) / n) for i in range(n)]
        weight = 1.0 / n
        return values, [weight] * n

    def mean(self) -> float:
        values, weights = self.support(256)
        return sum(v * w for v, w in zip(values, weights, strict=True))


def _lognormal_cdf(mu: float, sigma: float, x: float) -> float:
    if x <= 0 or sigma <= 0:
        return 0.0
    z = (math.log(x) - mu) / sigma
    return 0.5 * (1.0 + math.erf(z / math.sqrt(2.0)))


def level_for_threshold(threshold: float) -> int:
    """The integer count a posted line is about: the k in P(count >= k).

    A book posts counts two ways. A half-point main line ("over 1.5 pass TDs")
    means two or more, so it rounds up. A ladder rung ("2+ TDs") is already
    written as the count itself, so an integer threshold is taken at face value
    -- which is exactly how the doc reads them: "2+ TD -> P(>=2)" (§4.1). A
    threshold of 0 (the anytime-TD market, which posts no point at all) is
    P(>=1).
    """
    if threshold <= 0:
        return 1
    if abs(threshold - round(threshold)) < 1e-9:
        return round(threshold)
    return math.ceil(threshold)


class CountDistribution:
    """A small-integer distribution read straight off the cumulative lines (§4).

    The posted lines *are* the survival curve, so exact-count probabilities
    come from differencing adjacent lines -- that subtraction is what removes
    the double count, since a 2-TD game is already inside the anytime number.
    The highest posted line becomes the top bucket, scored at its floor: those
    games have *at least* that many, and with no higher line posted we don't
    invent the mass above it.
    """

    def __init__(self, pmf: dict[int, float]):
        total = sum(pmf.values())
        if total <= 0:
            raise ValueError("CountDistribution needs positive probability mass")
        self.pmf = {int(k): float(v) / total for k, v in sorted(pmf.items()) if v > 0}
        self.counts = sorted(self.pmf)

    @classmethod
    def from_anchors(cls, anchors: list[Anchor]) -> CountDistribution | None:
        survival_by_level: dict[int, float] = {}
        for anchor in anchors:
            level = level_for_threshold(anchor.threshold)
            # Anchors arrive isotonic in threshold order; if two thresholds map
            # to the same level, the lower (more informative) one wins.
            survival_by_level.setdefault(level, min(max(anchor.survival, 0.0), 1.0))
        if not survival_by_level:
            return None

        levels = sorted(survival_by_level)
        # Survival must be non-increasing in level after the level collapse.
        survivals = [survival_by_level[level] for level in levels]
        for i in range(1, len(survivals)):
            survivals[i] = min(survivals[i], survivals[i - 1])

        if levels[0] > 1:
            # The ladder starts above 1 -- e.g. only a "2+" line is posted --
            # so differencing can't reach P(0) or P(1) and the distribution is
            # under-determined. The doc leaves the family open pending
            # calibration (§2.3); Poisson is the interim fill.
            return cls._from_sparse(levels, survivals)

        pmf: dict[int, float] = {0: 1.0 - survivals[0]}
        for i, level in enumerate(levels):
            if i + 1 < len(levels):
                # Mass between this line and the next. When the ladder skips a
                # rung (1 and 3 posted, no 2) the market never split that mass,
                # so it sits at the lower count rather than being invented into
                # the higher one.
                pmf[level] = survivals[i] - survivals[i + 1]
            else:
                pmf[level] = survivals[i]
        return cls(pmf)

    @classmethod
    def _from_sparse(cls, levels: list[int], survivals: list[float]) -> CountDistribution | None:
        points = [
            (level - 1, 1.0 - survival) for level, survival in zip(levels, survivals, strict=True)
        ]
        lam = _poisson_fit_lambda([(max(0, k), f) for k, f in points])
        if not lam or lam <= 0:
            return None
        pmf: dict[int, float] = {}
        term = math.exp(-lam)
        pmf[0] = term
        for k in range(1, _MAX_COUNT + 1):
            term *= lam / k
            pmf[k] = term
        return cls(pmf)

    def sf(self, count: float) -> float:
        """P(count >= `count`)."""
        return sum(p for k, p in self.pmf.items() if k >= count)

    def quantile(self, u: float) -> float:
        u = min(max(u, 0.0), 1.0)
        cumulative = 0.0
        last = 0
        for count in self.counts:
            cumulative += self.pmf[count]
            last = count
            if cumulative >= u - 1e-12:
                return float(count)
        return float(last)

    def support(self, buckets: int = 0) -> tuple[list[float], list[float]]:
        """Exact support: every count the market gives mass, with its probability."""
        return [float(k) for k in self.counts], [self.pmf[k] for k in self.counts]

    def mean(self) -> float:
        return sum(k * p for k, p in self.pmf.items())


def is_count_market(market_key: str) -> bool:
    key = (market_key or "").lower()
    if key in COUNT_MARKETS:
        return True
    return key.endswith(("_tds", "_interceptions")) or "receptions" in key


def is_continuous_market(market_key: str) -> bool:
    key = (market_key or "").lower()
    return key in CONTINUOUS_MARKETS or key.endswith("_yds")


def _single_anchor_distribution(anchor: Anchor) -> ContinuousDistribution | None:
    """Continuous distribution from one lonely anchor.

    Two points are the minimum a two-parameter lognormal needs, so a single
    posted threshold leaves the distribution under-determined. The doc presumes
    a ladder and is silent here, and this is genuinely the one place the engine
    assumes something the market didn't say -- flagged rather than hidden. It
    only fires when every book in the feed posts the same single threshold for
    a stat, and stops the moment a second distinct threshold appears anywhere.

    The assumption is the one this repo already made: skew the median off the
    threshold in proportion to how far the fair price sits from a coin flip,
    and when the price *is* a coin flip (which says nothing about width) fall
    back to the same quarter-of-the-line spread the older model used.
    """
    threshold = float(anchor.threshold)
    if threshold <= 0:
        return None
    survival = min(max(float(anchor.survival), _EPS), 1.0 - _EPS)
    median_estimate = threshold * (1.0 + (2.0 * survival - 1.0) * 0.5)
    if median_estimate <= 0 or abs(median_estimate - threshold) < 1e-6:
        # Coin-flip line: the median sits on the threshold and the width has to
        # be assumed outright.
        fit = _assumed_width_fit(threshold, 1.0 - survival)
        if fit is None:
            return None
        mu, sigma = fit
        lower = Anchor(threshold=_lognormal_quantile(mu, sigma, 0.25), survival=0.75)
        upper = Anchor(threshold=_lognormal_quantile(mu, sigma, 0.75), survival=0.25)
        return ContinuousDistribution([lower, upper])
    pair = sorted(
        [anchor, Anchor(threshold=median_estimate, survival=0.5)],
        key=lambda a: a.threshold,
    )
    if pair[0].threshold <= 0 or pair[0].survival <= pair[1].survival:
        return None
    return ContinuousDistribution(pair)


def build_distribution(
    per_bookmaker_odds: dict,
    market_key: str,
) -> ContinuousDistribution | CountDistribution | None:
    """Reconstruct one stat's distribution from every book's lines (steps 1-4)."""
    anchors = collect_anchors(per_bookmaker_odds, market_key)
    if not anchors:
        return None

    if is_count_market(market_key):
        return CountDistribution.from_anchors(anchors)

    if not is_continuous_market(market_key):
        return None

    if len({round(a.survival, 9) for a in anchors}) == 1:
        # Isotonic flattened every anchor to the same probability -- books
        # disagreeing about which way the line leans, which after pooling is
        # one point of information, not several. Treat it as one anchor rather
        # than fitting a shape to a flat segment.
        return _single_anchor_distribution(
            Anchor(threshold=median(a.threshold for a in anchors), survival=anchors[0].survival)
        )
    if len(anchors) >= 2:
        return ContinuousDistribution(anchors)
    return _single_anchor_distribution(anchors[0])
