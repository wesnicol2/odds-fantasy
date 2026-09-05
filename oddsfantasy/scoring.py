"""League scoring as configuration (methodology doc §2.4).

The methodology doc's second design principle is that *no scoring constant is
hardcoded*: every per-unit value, per-reception value and bonus (threshold,
amount) pair is read from the league's scoring settings, so the same engine
serves any ruleset and a rules change is a config change rather than a code
change.

The part that used to be hardcoded is the bonus *threshold*. Sleeper only hands
us keys like ``bonus_rush_yd_100``: the amount is the value, and the threshold
is encoded in the key name. Parsing the number out of the key (rather than
pairing a hardcoded ``100.0`` with it, as ``range_model``/``odds_details`` do)
is what makes thresholds configuration too -- a league with
``bonus_rush_yd_150`` is handled with no code change at all.

Bonuses **stack**: a 210-yard rushing game collects both the 100- and the
200-yard bonus. That follows the doc's expectation identity
``E = rate x E[stat] + sum_i amount_i * P(>= threshold_i)`` (§2.4), which only
holds if each threshold pays independently.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from .config import STAT_MARKET_MAPPING_SLEEPER
from .market_math import CONTINUOUS_MARKETS, COUNT_MARKETS

# The canonical player projection engine intentionally models only the market
# families whose reconstruction is specified and tested in market_math. Sleeper
# exposes scoring keys for DEF/K/fumbles/etc., but a scoring key alone is not a
# license to infer a probability distribution for an unsupported market.
_MODELED_PLAYER_MARKETS = CONTINUOUS_MARKETS | COUNT_MARKETS

# Sleeper spells yardage bonuses as bonus_<what>_yd_<threshold>. `what` maps to
# the market the bonus is measured against; the threshold is read from the key.
_BONUS_KEY_RE = re.compile(r"^bonus_(?P<what>[a-z_]+)_yd_(?P<threshold>\d+)$")

_BONUS_WHAT_TO_MARKET = {
    "pass": "player_pass_yds",
    "rush": "player_rush_yds",
    "rec": "player_reception_yds",
}

# The Odds API's anytime-TD market says only that the player scores a touchdown,
# not how. Position is the market-only metadata we already know about the player:
# WR/TE touchdowns use receiving-TD scoring; QB/RB use rushing-TD scoring. This
# matters only in leagues where those configured point values differ.
_RECEIVING_TD_POSITIONS = {"WR", "TE"}

# Markets whose scoring value is always negative regardless of how the league
# spells it. Sleeper stores pass_int as -1, but some settings dumps carry the
# magnitude only, and an interception that *adds* points would be silently wrong.
_ALWAYS_NEGATIVE_MARKETS = {"player_pass_interceptions"}


def _numeric_setting(settings: dict, key: str) -> float | None:
    if key not in settings:
        return None
    try:
        return float(settings.get(key) or 0.0)
    except (TypeError, ValueError):
        return None


@dataclass(frozen=True)
class StatScoring:
    """How one market's realized value converts to fantasy points."""

    market_key: str
    rule_key: str
    per_unit: float
    # (threshold, amount) pairs, ascending by threshold. Every crossed
    # threshold pays -- they are cumulative, not exclusive.
    bonuses: tuple[tuple[float, float], ...] = ()

    def points_for(self, value: float) -> float:
        """Fantasy points contributed by a single realized value of this stat."""
        total = self.per_unit * value
        for threshold, amount in self.bonuses:
            if value >= threshold:
                total += amount
        return total

    @property
    def is_scored(self) -> bool:
        """True if this stat can move fantasy points under the current config.

        A stat worth 0 with no bonus (receptions in a non-PPR league) is still
        *modeled* -- the doc is explicit that every scorable stat is computed
        and then scored by its configured value -- but callers may use this to
        skip work that provably cannot change the answer.
        """
        return self.per_unit != 0.0 or any(amount != 0.0 for _, amount in self.bonuses)


@dataclass(frozen=True)
class ScoringConfig:
    """A league's scoring rules, indexed by Odds API market key."""

    by_market: dict[str, StatScoring] = field(default_factory=dict)
    raw: dict[str, object] = field(default_factory=dict)

    @classmethod
    def from_settings(cls, scoring_settings: dict | None) -> ScoringConfig:
        settings = dict(scoring_settings or {})

        bonuses_by_market: dict[str, list[tuple[float, float]]] = {}
        for key, raw_amount in settings.items():
            match = _BONUS_KEY_RE.match(str(key))
            if not match:
                continue
            market = _BONUS_WHAT_TO_MARKET.get(match.group("what"))
            if not market:
                # e.g. a combined rush+rec yardage bonus: it isn't measured
                # against any single market we model, so we can't price it
                # without inventing a joint distribution. Left out, per the
                # market-translation-only principle.
                continue
            try:
                amount = float(raw_amount)
            except (TypeError, ValueError):
                continue
            bonuses_by_market.setdefault(market, []).append(
                (float(match.group("threshold")), amount)
            )

        by_market: dict[str, StatScoring] = {}
        for market_key, rule_key in STAT_MARKET_MAPPING_SLEEPER.items():
            if "_bonus_" in market_key:
                # Bonus pseudo-markets in the mapping table; handled above.
                continue
            if market_key not in _MODELED_PLAYER_MARKETS:
                # DEF/K/fumble/2pt mappings are real Sleeper scoring settings,
                # but this player engine has no canonical sportsbook model for
                # them. Leave them out instead of letting name-pattern matching
                # fabricate a distribution.
                continue
            per_unit = _numeric_setting(settings, rule_key)
            if per_unit is None:
                per_unit = 0.0
            if market_key in _ALWAYS_NEGATIVE_MARKETS:
                per_unit = -abs(per_unit)
            by_market[market_key] = StatScoring(
                market_key=market_key,
                rule_key=rule_key,
                per_unit=per_unit,
                bonuses=tuple(sorted(bonuses_by_market.get(market_key, []))),
            )

        return cls(by_market=by_market, raw=settings)

    def for_market(self, market_key: str, position: str | None = None) -> StatScoring | None:
        """Return configured scoring for a market, using position where required.

        ``player_anytime_td`` is the only ambiguous market: the sportsbook line
        does not identify rushing vs receiving touchdown type. For WR/TE, use
        the league's configured ``rec_td`` value when present; otherwise fall
        back to the existing ``rush_td`` mapping. QB/RB and callers without
        position retain the rushing-TD mapping.
        """
        base = self.by_market.get(market_key)
        if market_key != "player_anytime_td" or base is None:
            return base

        if str(position or "").upper() in _RECEIVING_TD_POSITIONS:
            receiving_value = _numeric_setting(self.raw, "rec_td")
            if receiving_value is not None:
                return StatScoring(
                    market_key=market_key,
                    rule_key="rec_td",
                    per_unit=receiving_value,
                )
        return base

    def score(self, stat_line: dict[str, float], position: str | None = None) -> float:
        """Fantasy points for one realized stat line (one simulated game).

        This is the exact scoring function applied per Monte Carlo draw, which
        is how bonus kinks are priced correctly (§2.4): a draw either cleared
        the threshold or it didn't.
        """
        total = 0.0
        for market_key, value in stat_line.items():
            stat_scoring = self.for_market(market_key, position=position)
            if stat_scoring is None or value is None:
                continue
            total += stat_scoring.points_for(float(value))
        return total
