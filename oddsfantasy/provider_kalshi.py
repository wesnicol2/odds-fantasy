"""Kalshi public-market adapter for NFL player props."""

from __future__ import annotations

import datetime as dt
import os
import re
from urllib.parse import urlencode
from zoneinfo import ZoneInfo

import requests
from requests.adapters import HTTPAdapter

from .provider_cache import JsonProviderCache
from .provider_contract import (
    ProviderDiagnostic,
    ProviderRequest,
    ProviderResult,
    QuoteProvenance,
    QuoteSource,
    SidePrice,
    StatContractQuote,
    ThresholdPredicate,
)

PROVIDER_ID = "kalshi"
BASE_URL = os.getenv("KALSHI_BASE_URL", "https://external-api.kalshi.com/trade-api/v2")
REQ_TIMEOUT = (5, 20)
TTL = int(os.getenv("KALSHI_ODDS_TTL", "900"))

SERIES_BY_MARKET = {
    "player_pass_yds": "KXNFLPASSYDS",
    "player_pass_tds": "KXNFLPASSTDS",
    "player_rush_yds": "KXNFLRSHYDS",
    "player_receptions": "KXNFLREC",
    "player_reception_yds": "KXNFLRECYDS",
    "player_anytime_td": "KXNFLTD",
}

TEAM_CODE = {
    "Arizona Cardinals": "ARI",
    "Atlanta Falcons": "ATL",
    "Baltimore Ravens": "BAL",
    "Buffalo Bills": "BUF",
    "Carolina Panthers": "CAR",
    "Chicago Bears": "CHI",
    "Cincinnati Bengals": "CIN",
    "Cleveland Browns": "CLE",
    "Dallas Cowboys": "DAL",
    "Denver Broncos": "DEN",
    "Detroit Lions": "DET",
    "Green Bay Packers": "GB",
    "Houston Texans": "HOU",
    "Indianapolis Colts": "IND",
    "Jacksonville Jaguars": "JAC",
    "Kansas City Chiefs": "KC",
    "Las Vegas Raiders": "LV",
    "Los Angeles Chargers": "LAC",
    "Los Angeles Rams": "LAR",
    "Miami Dolphins": "MIA",
    "Minnesota Vikings": "MIN",
    "New England Patriots": "NE",
    "New Orleans Saints": "NO",
    "New York Giants": "NYG",
    "New York Jets": "NYJ",
    "Philadelphia Eagles": "PHI",
    "Pittsburgh Steelers": "PIT",
    "San Francisco 49ers": "SF",
    "Seattle Seahawks": "SEA",
    "Tampa Bay Buccaneers": "TB",
    "Tennessee Titans": "TEN",
    "Washington Commanders": "WAS",
}

_LABEL_RE = re.compile(
    r"^\s*(?P<name>.+?):\s*(?:Over\s+)?(?P<point>-?\d+(?:\.\d+)?)\+?\s*$",
    re.I,
)


class CacheMiss(RuntimeError):
    pass


def _norm_name(value: str) -> str:
    value = (value or "").lower().replace(chr(8217), "'")
    value = re.sub(r"[\.'`-]", " ", value)
    value = re.sub(r"[^a-z0-9 ]", "", value)
    tokens = [token for token in value.split() if token not in {"jr", "sr", "ii", "iii", "iv", "v"}]
    return " ".join(tokens)


def _parse_time(value: str | None) -> dt.datetime | None:
    if not value:
        return None
    try:
        parsed = dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo is not None else parsed.replace(tzinfo=dt.UTC)


def _game_date_code(value: str) -> str | None:
    parsed = _parse_time(value)
    if parsed is None:
        return None
    return parsed.astimezone(ZoneInfo("America/New_York")).strftime("%y%b%d").upper()


def _has_started(value: str) -> bool:
    parsed = _parse_time(value)
    return parsed is not None and parsed <= dt.datetime.now(dt.UTC)


def _market_label(market: dict) -> tuple[str, float] | None:
    for field in ("yes_sub_title", "subtitle", "title"):
        raw = str(market.get(field) or "").strip()
        match = _LABEL_RE.match(raw)
        if match:
            return match.group("name").strip(), float(match.group("point"))
    return None


def _probability(value: object) -> float | None:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    return parsed if 0.0 < parsed <= 1.0 else None


def _ask(market: dict, side: str) -> float | None:
    direct = _probability(market.get(f"{side}_ask_dollars"))
    if direct is not None:
        return direct
    opposite = "no" if side == "yes" else "yes"
    opposite_bid = _probability(market.get(f"{opposite}_bid_dollars"))
    if opposite_bid is None:
        return None
    derived = 1.0 - opposite_bid
    return derived if 0.0 < derived <= 1.0 else None


class KalshiProvider:
    provider_id = PROVIDER_ID

    def __init__(
        self,
        session: requests.Session | None = None,
        cache: JsonProviderCache | None = None,
    ):
        self.session = session or requests.Session()
        self.session.headers.update({"Accept": "application/json"})
        self.session.mount("https://", HTTPAdapter(pool_connections=8, pool_maxsize=16))
        self.cache = cache or JsonProviderCache(PROVIDER_ID, TTL)

    def _get_json(self, path: str, params: dict[str, object], mode: str) -> dict:
        url = f"{BASE_URL}{path}"
        query = urlencode(sorted((str(k), str(v)) for k, v in params.items()))
        key = f"GET {url}?{query}"
        cached = self.cache.get(key, mode)
        if cached is not None:
            return cached
        if mode == "cache":
            raise CacheMiss(key)
        response = self.session.get(url, params=params, timeout=REQ_TIMEOUT)
        response.raise_for_status()
        data = response.json()
        self.cache.put(key, data)
        return data

    def fetch_quotes(self, request: ProviderRequest) -> ProviderResult:
        quotes: list[StatContractQuote] = []
        diagnostics: list[ProviderDiagnostic] = []
        source = QuoteSource(PROVIDER_ID, PROVIDER_ID, "Kalshi")

        for game_request in request.games:
            game = game_request.game
            if _has_started(game.commence_time):
                diagnostics.append(
                    ProviderDiagnostic(
                        PROVIDER_ID,
                        "live_market",
                        "Skipped Kalshi player props after scheduled kickoff.",
                        game_id=game.game_id,
                    )
                )
                continue

            date_code = _game_date_code(game.commence_time)
            away = TEAM_CODE.get(game.away_team)
            home = TEAM_CODE.get(game.home_team)
            if not date_code or not away or not home:
                diagnostics.append(
                    ProviderDiagnostic(
                        PROVIDER_ID,
                        "game_not_mappable",
                        "Could not map game date/team identity to a Kalshi event ticker.",
                        "warning",
                        game_id=game.game_id,
                    )
                )
                continue

            players = {}
            for player in game_request.players:
                players[_norm_name(player.full_name)] = player
                players[_norm_name(player.player_id)] = player

            found: set[tuple[str, str]] = set()
            requested = {
                (player.player_id, market_key)
                for player in game_request.players
                for market_key in game_request.markets
                if market_key in SERIES_BY_MARKET
            }

            for market_key in sorted(game_request.markets):
                series = SERIES_BY_MARKET.get(market_key)
                if series is None:
                    continue
                event_ticker = f"{series}-{date_code}{away}{home}"
                try:
                    payload = self._get_json(
                        "/markets",
                        {
                            "event_ticker": event_ticker,
                            "status": "open",
                            "limit": 1000,
                        },
                        request.cache_mode,
                    )
                except CacheMiss:
                    diagnostics.append(
                        ProviderDiagnostic(
                            PROVIDER_ID,
                            "cache_miss",
                            f"No cached Kalshi payload for {event_ticker}.",
                            game_id=game.game_id,
                            market_key=market_key,
                        )
                    )
                    continue
                except Exception as exc:
                    diagnostics.append(
                        ProviderDiagnostic(
                            PROVIDER_ID,
                            "transport_error",
                            f"Kalshi request failed for {event_ticker}: {exc}",
                            "warning",
                            game_id=game.game_id,
                            market_key=market_key,
                        )
                    )
                    continue

                for market in payload.get("markets") or []:
                    if not isinstance(market, dict):
                        continue
                    parsed_label = _market_label(market)
                    if parsed_label is None:
                        continue
                    raw_name, threshold = parsed_label
                    player = players.get(_norm_name(raw_name))
                    if player is None:
                        continue
                    yes_probability = _ask(market, "yes")
                    no_probability = _ask(market, "no")
                    if yes_probability is None and no_probability is None:
                        diagnostics.append(
                            ProviderDiagnostic(
                                PROVIDER_ID,
                                "unusable_price",
                                "Kalshi market has no executable YES or NO ask.",
                                game_id=game.game_id,
                                player_id=player.player_id,
                                market_key=market_key,
                                provider_market_id=str(market.get("ticker") or ""),
                            )
                        )
                        continue

                    yes = (
                        SidePrice(yes_probability, yes_probability, "contract_ask")
                        if yes_probability is not None
                        else None
                    )
                    no = (
                        SidePrice(no_probability, no_probability, "contract_ask")
                        if no_probability is not None
                        else None
                    )
                    rules = "\n".join(
                        str(market.get(field) or "").strip()
                        for field in ("rules_primary", "rules_secondary")
                        if market.get(field)
                    )
                    quotes.append(
                        StatContractQuote(
                            source=source,
                            game_id=game.game_id,
                            player_id=player.player_id,
                            market_key=market_key,
                            predicate=ThresholdPredicate("gte", threshold),
                            yes=yes,
                            no=no,
                            observed_at=_parse_time(market.get("updated_time")),
                            phase="pregame",
                            provenance=QuoteProvenance(
                                provider_event_id=str(market.get("event_ticker") or event_ticker),
                                provider_market_id=str(market.get("ticker") or ""),
                                raw_title=str(
                                    market.get("yes_sub_title")
                                    or market.get("subtitle")
                                    or market.get("title")
                                    or ""
                                ),
                                raw_rules=rules or None,
                            ),
                        )
                    )
                    found.add((player.player_id, market_key))

            for player_id, market_key in sorted(requested - found):
                diagnostics.append(
                    ProviderDiagnostic(
                        PROVIDER_ID,
                        "market_not_found",
                        "No matching open Kalshi player market was found.",
                        game_id=game.game_id,
                        player_id=player_id,
                        market_key=market_key,
                    )
                )

        diagnostics.append(
            ProviderDiagnostic(
                PROVIDER_ID,
                "accepted_quotes",
                f"Accepted {len(quotes)} Kalshi quotes.",
            )
        )
        return ProviderResult(
            provider_id=PROVIDER_ID,
            quotes=tuple(quotes),
            diagnostics=tuple(diagnostics),
            fetched_at=dt.datetime.now(dt.UTC),
        )
