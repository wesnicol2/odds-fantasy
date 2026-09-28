"""Orchestrate provider-neutral player-prop evidence for one planned week."""

from __future__ import annotations

import datetime as dt
import os
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import asdict, dataclass

from .provider_contract import (
    BenchmarkQuote,
    GameRef,
    GameRequest,
    OddsProvider,
    PlayerRef,
    ProviderDiagnostic,
    ProviderRequest,
    ProviderResult,
    quotes_to_players_odds,
)
from .provider_kalshi import KalshiProvider
from .provider_oddsapi import normalize_fetched_odds
from .provider_polymarket import PolymarketProvider

DEFAULT_PROVIDERS = ("odds_api", "polymarket", "kalshi")
_DIRECT_PROVIDER_FACTORIES = {
    "polymarket": PolymarketProvider,
    "kalshi": KalshiProvider,
}


@dataclass(frozen=True)
class EvidenceBundle:
    players_odds: dict[str, dict]
    diagnostics: tuple[dict, ...]
    benchmarks: tuple[dict, ...]
    providers_used: tuple[str, ...]


def enabled_provider_ids() -> tuple[str, ...]:
    raw = os.getenv("ODDS_PROVIDERS", ",".join(DEFAULT_PROVIDERS))
    requested = [item.strip().lower() for item in raw.split(",") if item.strip()]
    return tuple(dict.fromkeys(requested))


def _base_market_key(market_key: str) -> str:
    suffix = "_alternate"
    return market_key[: -len(suffix)] if market_key.endswith(suffix) else market_key


def _provider_request(
    planned_games: dict[str, object],
    cache_mode: str,
    region: str,
) -> tuple[ProviderRequest, dict[str, str]]:
    games: list[GameRequest] = []
    position_by_player: dict[str, str] = {}
    for game_id, planned in planned_games.items():
        players: list[PlayerRef] = []
        for row in planned.players:
            player_id = str(row.get("alias") or row.get("full_name") or "").strip()
            full_name = str(row.get("full_name") or player_id).strip()
            position = str(row.get("primary_position") or "").upper()
            team = str(row.get("editorial_team_full_name") or "").strip()
            if not player_id or not full_name or not position or not team:
                continue
            players.append(
                PlayerRef(
                    player_id=player_id,
                    full_name=full_name,
                    team=team,
                    position=position,
                )
            )
            position_by_player[player_id] = position
        markets = frozenset(_base_market_key(str(key)) for key in planned.markets if key)
        games.append(
            GameRequest(
                game=GameRef(
                    game_id=game_id,
                    home_team=planned.home_team,
                    away_team=planned.away_team,
                    commence_time=planned.commence_time,
                ),
                players=tuple(players),
                markets=markets,
            )
        )
    return (
        ProviderRequest(games=tuple(games), cache_mode=cache_mode, region=region),
        position_by_player,
    )


def _serialize_diagnostic(diagnostic: ProviderDiagnostic) -> dict:
    return asdict(diagnostic)


def _serialize_benchmark(benchmark: BenchmarkQuote) -> dict:
    payload = asdict(benchmark)
    observed_at = benchmark.observed_at
    payload["observed_at"] = observed_at.isoformat() if observed_at is not None else None
    return payload


def _failed_result(provider_id: str, exc: Exception) -> ProviderResult:
    return ProviderResult(
        provider_id=provider_id,
        diagnostics=(
            ProviderDiagnostic(
                provider_id=provider_id,
                code="transport_error",
                message=f"Provider fetch failed: {exc}",
                severity="warning",
            ),
        ),
        fetched_at=dt.datetime.now(dt.UTC),
    )


def collect_provider_evidence(
    event_odds_by_game: dict[str, object],
    planned_games: dict[str, object],
    cache_mode: str,
    region: str = "us",
    *,
    providers: dict[str, OddsProvider] | None = None,
    enabled_ids: tuple[str, ...] | None = None,
) -> EvidenceBundle:
    """Collect all enabled sources and adapt them to the existing model input."""

    enabled = enabled_ids if enabled_ids is not None else enabled_provider_ids()
    request, position_by_player = _provider_request(planned_games, cache_mode, region)
    results: list[ProviderResult] = []
    diagnostics: list[ProviderDiagnostic] = []

    if "odds_api" in enabled:
        try:
            results.append(normalize_fetched_odds(event_odds_by_game, planned_games))
        except Exception as exc:
            results.append(_failed_result("odds_api", exc))

    direct = providers or {
        provider_id: factory()
        for provider_id, factory in _DIRECT_PROVIDER_FACTORIES.items()
        if provider_id in enabled
    }
    tasks = {
        provider_id: provider
        for provider_id, provider in direct.items()
        if provider_id in enabled and provider_id != "odds_api"
    }
    if request.games and tasks:
        with ThreadPoolExecutor(max_workers=min(len(tasks), 4)) as executor:
            futures = {
                executor.submit(provider.fetch_quotes, request): provider_id
                for provider_id, provider in tasks.items()
            }
            for future in as_completed(futures):
                provider_id = futures[future]
                try:
                    results.append(future.result())
                except Exception as exc:
                    results.append(_failed_result(provider_id, exc))

    known = {"odds_api", *_DIRECT_PROVIDER_FACTORIES}
    diagnostics.extend(
        [
            ProviderDiagnostic(
                provider_id=provider_id,
                code="unknown_provider",
                message=f"Unknown odds provider configured: {provider_id}",
                severity="warning",
            )
            for provider_id in enabled
            if provider_id not in known
        ]
    )

    for result in results:
        diagnostics.extend(result.diagnostics)

    players_odds = quotes_to_players_odds(results, position_by_player)
    benchmarks = tuple(
        _serialize_benchmark(benchmark)
        for result in results
        for benchmark in result.benchmarks
    )
    providers_used = tuple(sorted({result.provider_id for result in results}))
    return EvidenceBundle(
        players_odds=players_odds,
        diagnostics=tuple(_serialize_diagnostic(item) for item in diagnostics),
        benchmarks=benchmarks,
        providers_used=providers_used,
    )
