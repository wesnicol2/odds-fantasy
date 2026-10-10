"""Convert existing Odds API-normalized book lines into canonical provider evidence."""

from __future__ import annotations

import datetime as dt
from collections.abc import Iterable

from .aggregator import PLAYER_POSITION_META_KEY, aggregate_odds_api_by_week
from .provider_contract import (
    ProviderDiagnostic,
    ProviderResult,
    QuoteProvenance,
    QuoteSource,
    SidePrice,
    StatContractQuote,
    ThresholdPredicate,
)

PROVIDER_ID = "odds_api"


def _probability_from_decimal(value: object) -> float | None:
    try:
        decimal = float(value)
    except (TypeError, ValueError):
        return None
    if decimal <= 0:
        return None
    probability = 1.0 / decimal
    return probability if 0.0 < probability <= 1.0 else None


def _side(record: dict | None) -> SidePrice | None:
    if not record:
        return None
    probability = _probability_from_decimal(record.get("odds"))
    if probability is None:
        return None
    try:
        native = float(record.get("odds"))
    except (TypeError, ValueError):
        native = None
    return SidePrice(probability, native_price=native, native_format="decimal")


def _quote(
    *,
    game_id: str,
    player_id: str,
    source_id: str,
    market_key: str,
    point: float,
    over: dict | None,
    under: dict | None,
    is_primary: bool,
) -> StatContractQuote | None:
    over_side = _side(over)
    under_side = _side(under)
    if over_side is None and under_side is None:
        return None
    return StatContractQuote(
        source=QuoteSource(source_id, PROVIDER_ID, source_id),
        game_id=game_id,
        player_id=player_id,
        market_key=market_key,
        predicate=ThresholdPredicate("gt", point),
        yes=over_side,
        no=under_side,
        observed_at=None,
        phase="pregame",
        provenance=QuoteProvenance(
            provider_event_id=game_id,
            provider_market_id=f"{game_id}:{source_id}:{market_key}:{point}",
            raw_title=None,
            raw_rules=None,
        ),
        is_primary=is_primary,
    )


def _paired_alternates(entry: dict) -> Iterable[tuple[float, dict | None, dict | None]]:
    alts = entry.get("alts") if isinstance(entry, dict) else None
    if not isinstance(alts, dict):
        return []
    by_point: dict[float, dict[str, dict]] = {}
    for side in ("over", "under"):
        for record in alts.get(side) or []:
            try:
                point = float(record.get("point"))
            except (TypeError, ValueError):
                continue
            by_point.setdefault(point, {})[side] = record
    return [
        (point, sides.get("over"), sides.get("under")) for point, sides in sorted(by_point.items())
    ]


def normalize_fetched_odds(
    event_odds_by_game: dict[str, object], planned_games: dict[str, object]
) -> ProviderResult:
    """Preserve current Odds API matching while emitting the provider contract."""

    legacy = aggregate_odds_api_by_week(event_odds_by_game, planned_games)
    quotes: list[StatContractQuote] = []
    diagnostics: list[ProviderDiagnostic] = []
    game_by_player: dict[str, str] = {}
    for game_id, game in planned_games.items():
        for player in game.players:
            game_by_player[player["alias"]] = game_id

    for player_id, books in legacy.items():
        game_id = game_by_player.get(player_id)
        if game_id is None:
            continue
        for source_id, markets in books.items():
            for raw_key, entry in markets.items():
                if raw_key == PLAYER_POSITION_META_KEY or not isinstance(entry, dict):
                    continue
                alternate = raw_key.endswith("_alternate")
                market_key = raw_key[: -len("_alternate")] if alternate else raw_key
                if alternate:
                    for point, over, under in _paired_alternates(entry):
                        quote = _quote(
                            game_id=game_id,
                            player_id=player_id,
                            source_id=source_id,
                            market_key=market_key,
                            point=point,
                            over=over,
                            under=under,
                            is_primary=False,
                        )
                        if quote is not None:
                            quotes.append(quote)
                    continue

                over = entry.get("over") or None
                under = entry.get("under") or None
                point_value = (over or under or {}).get("point", 0)
                try:
                    point = float(point_value)
                except (TypeError, ValueError):
                    continue
                quote = _quote(
                    game_id=game_id,
                    player_id=player_id,
                    source_id=source_id,
                    market_key=market_key,
                    point=point,
                    over=over,
                    under=under,
                    is_primary=True,
                )
                if quote is not None:
                    quotes.append(quote)

    diagnostics.append(
        ProviderDiagnostic(
            provider_id=PROVIDER_ID,
            code="accepted_quotes",
            message=f"Normalized {len(quotes)} Odds API source quotes.",
        )
    )
    return ProviderResult(
        provider_id=PROVIDER_ID,
        quotes=tuple(quotes),
        diagnostics=tuple(diagnostics),
        fetched_at=dt.datetime.now(dt.UTC),
    )
