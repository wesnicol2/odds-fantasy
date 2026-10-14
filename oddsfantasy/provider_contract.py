"""Provider-neutral contracts for external market evidence.

Provider adapters stop at this boundary. They discover vendor-specific markets,
parse settlement semantics, and express executable prices as raw implied
probabilities. The projection stack remains responsible for de-vigging,
source-level consensus, distribution reconstruction, and fantasy scoring.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field
from typing import Literal, Protocol

CacheMode = Literal["auto", "cache", "fresh"]
PredicateOperator = Literal["gt", "gte", "lt", "lte"]
MarketPhase = Literal["pregame", "live", "closed", "unknown"]
DiagnosticSeverity = Literal["info", "warning", "error"]


@dataclass(frozen=True)
class GameRef:
    game_id: str
    home_team: str
    away_team: str
    commence_time: str


@dataclass(frozen=True)
class PlayerRef:
    player_id: str
    full_name: str
    team: str
    position: str


@dataclass(frozen=True)
class GameRequest:
    game: GameRef
    players: tuple[PlayerRef, ...]
    markets: frozenset[str]


@dataclass(frozen=True)
class ProviderRequest:
    games: tuple[GameRequest, ...]
    cache_mode: CacheMode = "auto"
    region: str = "us"


@dataclass(frozen=True)
class QuoteSource:
    """The independent market source that receives one consensus vote."""

    source_id: str
    provider_id: str
    display_name: str


@dataclass(frozen=True)
class SidePrice:
    """Executable raw price for one side, expressed as implied probability."""

    implied_probability: float
    native_price: float | None = None
    native_format: str | None = None

    def __post_init__(self) -> None:
        if not 0.0 < self.implied_probability <= 1.0:
            raise ValueError("implied_probability must be in (0, 1]")


@dataclass(frozen=True)
class ThresholdPredicate:
    """The provider's exact settlement predicate before model normalization."""

    operator: PredicateOperator
    value: float


@dataclass(frozen=True)
class QuoteProvenance:
    provider_event_id: str | None
    provider_market_id: str
    raw_title: str | None = None
    raw_rules: str | None = None


@dataclass(frozen=True)
class StatContractQuote:
    source: QuoteSource
    game_id: str
    player_id: str
    market_key: str
    predicate: ThresholdPredicate
    yes: SidePrice | None
    no: SidePrice | None
    observed_at: dt.datetime | None = None
    phase: MarketPhase = "unknown"
    provenance: QuoteProvenance | None = None
    # Presentation metadata only. Projection math must not weight a primary line
    # differently from any other threshold in the same source's ladder.
    is_primary: bool = False


@dataclass(frozen=True)
class BenchmarkQuote:
    """External fantasy-point evidence that never feeds the stat projection."""

    source: QuoteSource
    game_id: str
    player_id: str
    benchmark_key: str
    predicate: ThresholdPredicate
    yes: SidePrice | None
    no: SidePrice | None
    scoring_profile: str | None
    provenance: QuoteProvenance | None = None
    observed_at: dt.datetime | None = None


@dataclass(frozen=True)
class ProviderDiagnostic:
    provider_id: str
    code: str
    message: str
    severity: DiagnosticSeverity = "info"
    game_id: str | None = None
    player_id: str | None = None
    market_key: str | None = None
    provider_market_id: str | None = None


@dataclass(frozen=True)
class ProviderResult:
    provider_id: str
    quotes: tuple[StatContractQuote, ...] = ()
    benchmarks: tuple[BenchmarkQuote, ...] = ()
    diagnostics: tuple[ProviderDiagnostic, ...] = ()
    fetched_at: dt.datetime = field(default_factory=lambda: dt.datetime.now(dt.UTC))


class OddsProvider(Protocol):
    provider_id: str

    def fetch_quotes(self, request: ProviderRequest) -> ProviderResult: ...


def normalize_predicate(predicate: ThresholdPredicate) -> tuple[float, bool]:
    """Return the existing model's ``P(stat > threshold)`` boundary.

    NFL box-score stats modeled here are integer-valued even when sportsbooks
    express half-point O/U lines. ``yes_is_over`` tells the compatibility layer
    whether the provider's YES side is the over side at the normalized boundary.
    """

    value = float(predicate.value)
    if predicate.operator == "gt":
        return value, True
    if predicate.operator == "gte":
        return value - 0.5, True
    if predicate.operator == "lt":
        return value - 0.5, False
    if predicate.operator == "lte":
        return value + 0.5, False
    raise ValueError(f"unsupported predicate operator: {predicate.operator}")


def _decimal_compatibility_price(side: SidePrice | None) -> dict | None:
    if side is None:
        return None
    probability = side.implied_probability
    return {
        # ``probability`` is canonical. ``odds`` is a temporary compatibility
        # representation for the existing market-math boundary.
        "probability": probability,
        "odds": 1.0 / probability,
        "native_price": side.native_price,
        "native_format": side.native_format,
    }


def _quote_priority(quote: StatContractQuote) -> tuple[int, float]:
    """Prefer direct evidence when two providers expose the same source."""

    direct = int(quote.source.provider_id == quote.source.source_id)
    observed = quote.observed_at.timestamp() if quote.observed_at is not None else 0.0
    return direct, observed


def quotes_to_players_odds(
    results: tuple[ProviderResult, ...] | list[ProviderResult],
    position_by_player: dict[str, str],
) -> dict[str, dict]:
    """Adapt canonical evidence to the projection engine's current source map.

    Consensus identity is ``source_id``, not provider identity. A source can
    therefore contribute at most once at one player/market/threshold boundary,
    even if an aggregator and a direct provider both expose it.
    """

    from .aggregator import PLAYER_POSITION_META_KEY

    selected: dict[tuple[str, str, str, float], StatContractQuote] = {}
    normalized: dict[int, tuple[float, bool]] = {}
    for result in results:
        for quote in result.quotes:
            threshold, yes_is_over = normalize_predicate(quote.predicate)
            key = (quote.source.source_id, quote.player_id, quote.market_key, threshold)
            current = selected.get(key)
            if current is None or _quote_priority(quote) > _quote_priority(current):
                selected[key] = quote
                normalized[id(quote)] = (threshold, yes_is_over)

    output: dict[str, dict] = {}
    for quote in selected.values():
        threshold, yes_is_over = normalized.get(id(quote), normalize_predicate(quote.predicate))
        yes_record = _decimal_compatibility_price(quote.yes)
        no_record = _decimal_compatibility_price(quote.no)
        over = yes_record if yes_is_over else no_record
        under = no_record if yes_is_over else yes_record
        for record in (over, under):
            if record is not None:
                record["point"] = threshold
                record["provider"] = quote.source.provider_id
                record["source_id"] = quote.source.source_id
                if quote.provenance is not None:
                    record["provider_market_id"] = quote.provenance.provider_market_id
                    record["raw_title"] = quote.provenance.raw_title
                    record["raw_rules"] = quote.provenance.raw_rules

        player_out = output.setdefault(quote.player_id, {})
        source_out = player_out.setdefault(quote.source.source_id, {})
        position = position_by_player.get(quote.player_id)
        if position:
            source_out[PLAYER_POSITION_META_KEY] = {"value": position}

        if quote.is_primary and quote.market_key not in source_out:
            source_out[quote.market_key] = {"over": over, "under": under}
            continue

        alternate_key = f"{quote.market_key}_alternate"
        alternate = source_out.setdefault(alternate_key, {"alts": {"over": [], "under": []}})
        if over is not None:
            alternate["alts"]["over"].append(over)
        if under is not None:
            alternate["alts"]["under"].append(under)

    for books in output.values():
        for markets in books.values():
            for market in markets.values():
                alts = market.get("alts") if isinstance(market, dict) else None
                if not isinstance(alts, dict):
                    continue
                alts["over"].sort(key=lambda row: float(row["point"]))
                alts["under"].sort(key=lambda row: float(row["point"]))
    return output
