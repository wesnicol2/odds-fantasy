"""Polymarket Gamma/CLOB adapter for NFL player props."""

from __future__ import annotations

import datetime as dt
import json
import os
import re
from urllib.parse import urlencode
from zoneinfo import ZoneInfo

import requests
from requests.adapters import HTTPAdapter

from .provider_cache import JsonProviderCache
from .provider_contract import (
    PlayerRef,
    ProviderDiagnostic,
    ProviderRequest,
    ProviderResult,
    QuoteProvenance,
    QuoteSource,
    SidePrice,
    StatContractQuote,
    ThresholdPredicate,
)

PROVIDER_ID = "polymarket"
GAMMA_URL = os.getenv("POLYMARKET_GAMMA_URL", "https://gamma-api.polymarket.com")
CLOB_URL = os.getenv("POLYMARKET_CLOB_URL", "https://clob.polymarket.com")
REQ_TIMEOUT = (5, 20)
TTL = int(os.getenv("POLYMARKET_ODDS_TTL", "900"))

TEAM_CODE = {
    "Arizona Cardinals": "ari",
    "Atlanta Falcons": "atl",
    "Baltimore Ravens": "bal",
    "Buffalo Bills": "buf",
    "Carolina Panthers": "car",
    "Chicago Bears": "chi",
    "Cincinnati Bengals": "cin",
    "Cleveland Browns": "cle",
    "Dallas Cowboys": "dal",
    "Denver Broncos": "den",
    "Detroit Lions": "det",
    "Green Bay Packers": "gb",
    "Houston Texans": "hou",
    "Indianapolis Colts": "ind",
    "Jacksonville Jaguars": "jax",
    "Kansas City Chiefs": "kc",
    "Las Vegas Raiders": "lv",
    "Los Angeles Chargers": "lac",
    "Los Angeles Rams": "lar",
    "Miami Dolphins": "mia",
    "Minnesota Vikings": "min",
    "New England Patriots": "ne",
    "New Orleans Saints": "no",
    "New York Giants": "nyg",
    "New York Jets": "nyj",
    "Philadelphia Eagles": "phi",
    "Pittsburgh Steelers": "pit",
    "San Francisco 49ers": "sf",
    "Seattle Seahawks": "sea",
    "Tampa Bay Buccaneers": "tb",
    "Tennessee Titans": "ten",
    "Washington Commanders": "was",
}


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


def _has_started(value: str) -> bool:
    parsed = _parse_time(value)
    return parsed is not None and parsed <= dt.datetime.now(dt.UTC)


def _game_slug(away_team: str, home_team: str, commence_time: str) -> str | None:
    away = TEAM_CODE.get(away_team)
    home = TEAM_CODE.get(home_team)
    parsed = _parse_time(commence_time)
    if away is None or home is None or parsed is None:
        return None
    game_date = parsed.astimezone(ZoneInfo("America/New_York")).strftime("%Y-%m-%d")
    return f"nfl-{away}-{home}-{game_date}"


def _json_list(value: object) -> list[str]:
    if isinstance(value, list):
        return [str(item) for item in value]
    if not isinstance(value, str):
        return []
    try:
        parsed = json.loads(value)
    except ValueError:
        return []
    return [str(item) for item in parsed] if isinstance(parsed, list) else []


def _market_text(market: dict) -> str:
    return " ".join(
        str(market.get(field) or "")
        for field in ("question", "description", "groupItemTitle", "title", "slug")
    ).strip()


def _market_key(text: str) -> str | None:
    lowered = text.lower()
    if "receiving yards" in lowered:
        return "player_reception_yds"
    if "rushing yards" in lowered:
        return "player_rush_yds"
    if "passing yards" in lowered:
        return "player_pass_yds"
    if "passing touchdown" in lowered or "passing td" in lowered:
        return "player_pass_tds"
    if "interception" in lowered and ("throw" in lowered or "passing" in lowered):
        return "player_pass_interceptions"
    if "receptions" in lowered or "reception" in lowered:
        return "player_receptions"
    if "touchdown" in lowered and "team touchdown" not in lowered:
        return "player_anytime_td"
    return None


def _predicate(text: str, market_key: str) -> ThresholdPredicate | None:
    more_than = re.search(r"more than\s+(-?\d+(?:\.\d+)?)", text, re.I)
    if more_than:
        return ThresholdPredicate("gt", float(more_than.group(1)))
    explicit_over = re.search(r"\bover\s+(-?\d+(?:\.\d+)?)", text, re.I)
    if explicit_over:
        return ThresholdPredicate("gt", float(explicit_over.group(1)))
    plus = re.search(r"(-?\d+(?:\.\d+)?)\+", text)
    if plus:
        return ThresholdPredicate("gte", float(plus.group(1)))
    touchdown_pattern = r"score(?:s|d)?\s+(?:at least\s+)?(?:a|one|1)\s+touchdown"
    if market_key == "player_anytime_td" and re.search(touchdown_pattern, text, re.I):
        return ThresholdPredicate("gte", 1.0)
    return None


def _player_for_market(text: str, players: tuple[PlayerRef, ...]) -> PlayerRef | None:
    normalized = _norm_name(text)
    matches: list[tuple[int, PlayerRef]] = []
    for player in players:
        for candidate in (player.full_name, player.player_id):
            name = _norm_name(candidate)
            if name and name in normalized:
                matches.append((len(name), player))
    return max(matches, key=lambda item: item[0])[1] if matches else None


def _tokens(market: dict) -> tuple[str, str] | None:
    outcomes = _json_list(market.get("outcomes"))
    token_ids = _json_list(market.get("clobTokenIds"))
    if len(outcomes) != len(token_ids) or len(outcomes) != 2:
        return None
    positive = negative = None
    for outcome, token_id in zip(outcomes, token_ids, strict=True):
        label = outcome.strip().lower()
        if label in {"yes", "over"}:
            positive = token_id
        elif label in {"no", "under"}:
            negative = token_id
    if positive is None or negative is None:
        return None
    return positive, negative


def _probability(value: object) -> float | None:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    return parsed if 0.0 < parsed <= 1.0 else None


class PolymarketProvider:
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

    def _get_json(
        self,
        base: str,
        path: str,
        params: dict[str, object],
        mode: str,
    ) -> object:
        url = f"{base}{path}"
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

    def _post_json(self, path: str, body: list[dict[str, str]], mode: str) -> dict:
        url = f"{CLOB_URL}{path}"
        encoded = json.dumps(body, sort_keys=True, separators=(",", ":"))
        key = f"POST {url} {encoded}"
        cached = self.cache.get(key, mode)
        if cached is not None:
            return cached
        if mode == "cache":
            raise CacheMiss(key)
        response = self.session.post(url, json=body, timeout=REQ_TIMEOUT)
        response.raise_for_status()
        data = response.json()
        self.cache.put(key, data)
        return data

    def _events_for_game(self, slug: str, mode: str) -> list[dict]:
        main = self._get_json(GAMMA_URL, f"/events/slug/{slug}", {}, mode)
        if not isinstance(main, dict):
            return []
        game_id = main.get("gameId")
        sports = main.get("sports")
        if game_id is None and isinstance(sports, dict):
            game_id = sports.get("game_id") or sports.get("gameId")
        events = [main]
        if game_id is not None:
            related = self._get_json(
                GAMMA_URL,
                "/events/keyset",
                {"game_id": game_id, "closed": "false", "limit": 100},
                mode,
            )
            if isinstance(related, dict):
                events.extend(event for event in related.get("events") or [] if isinstance(event, dict))
        unique = {}
        for event in events:
            key = str(event.get("id") or event.get("slug") or id(event))
            unique[key] = event
        return list(unique.values())

    def _prices(self, token_ids: set[str], mode: str) -> dict[str, float]:
        output: dict[str, float] = {}
        ordered = sorted(token_ids)
        for start in range(0, len(ordered), 500):
            chunk = ordered[start : start + 500]
            body = [{"token_id": token_id, "side": "BUY"} for token_id in chunk]
            payload = self._post_json("/prices", body, mode)
            if not isinstance(payload, dict):
                continue
            for token_id in chunk:
                row = payload.get(token_id)
                if not isinstance(row, dict):
                    continue
                probability = _probability(row.get("BUY"))
                if probability is not None:
                    output[token_id] = probability
        return output

    def fetch_quotes(self, request: ProviderRequest) -> ProviderResult:
        quotes: list[StatContractQuote] = []
        diagnostics: list[ProviderDiagnostic] = []
        source = QuoteSource(PROVIDER_ID, PROVIDER_ID, "Polymarket")

        for game_request in request.games:
            game = game_request.game
            if _has_started(game.commence_time):
                diagnostics.append(
                    ProviderDiagnostic(
                        PROVIDER_ID,
                        "live_market",
                        "Skipped Polymarket player props after scheduled kickoff.",
                        game_id=game.game_id,
                    )
                )
                continue
            slug = _game_slug(game.away_team, game.home_team, game.commence_time)
            if slug is None:
                diagnostics.append(
                    ProviderDiagnostic(
                        PROVIDER_ID,
                        "game_not_mappable",
                        "Could not map game date/team identity to a Polymarket NFL slug.",
                        "warning",
                        game_id=game.game_id,
                    )
                )
                continue
            try:
                events = self._events_for_game(slug, request.cache_mode)
            except CacheMiss:
                diagnostics.append(
                    ProviderDiagnostic(
                        PROVIDER_ID,
                        "cache_miss",
                        f"No cached Polymarket event payload for {slug}.",
                        game_id=game.game_id,
                    )
                )
                continue
            except Exception as exc:
                diagnostics.append(
                    ProviderDiagnostic(
                        PROVIDER_ID,
                        "transport_error",
                        f"Polymarket event discovery failed for {slug}: {exc}",
                        "warning",
                        game_id=game.game_id,
                    )
                )
                continue

            candidates = []
            token_ids: set[str] = set()
            found: set[tuple[str, str]] = set()
            requested = {
                (player.player_id, market_key)
                for player in game_request.players
                for market_key in game_request.markets
            }
            for event in events:
                if event.get("closed") is True:
                    continue
                for market in event.get("markets") or []:
                    if not isinstance(market, dict) or market.get("closed") is True:
                        continue
                    text = _market_text(market)
                    market_key = _market_key(text)
                    if market_key is None or market_key not in game_request.markets:
                        continue
                    player = _player_for_market(text, game_request.players)
                    if player is None:
                        continue
                    predicate = _predicate(text, market_key)
                    token_pair = _tokens(market)
                    if predicate is None or token_pair is None:
                        diagnostics.append(
                            ProviderDiagnostic(
                                PROVIDER_ID,
                                "ambiguous_settlement",
                                (
                                    "Matched Polymarket player market but could not "
                                    "parse its predicate/outcomes."
                                ),
                                game_id=game.game_id,
                                player_id=player.player_id,
                                market_key=market_key,
                                provider_market_id=str(market.get("id") or ""),
                            )
                        )
                        continue
                    positive_token, negative_token = token_pair
                    token_ids.update((positive_token, negative_token))
                    candidates.append(
                        {
                            "event": event,
                            "market": market,
                            "player": player,
                            "market_key": market_key,
                            "predicate": predicate,
                            "positive_token": positive_token,
                            "negative_token": negative_token,
                        }
                    )

            try:
                prices = self._prices(token_ids, request.cache_mode) if token_ids else {}
            except CacheMiss:
                diagnostics.append(
                    ProviderDiagnostic(
                        PROVIDER_ID,
                        "cache_miss",
                        f"No cached Polymarket CLOB prices for {slug}.",
                        game_id=game.game_id,
                    )
                )
                prices = {}
            except Exception as exc:
                diagnostics.append(
                    ProviderDiagnostic(
                        PROVIDER_ID,
                        "transport_error",
                        f"Polymarket price lookup failed for {slug}: {exc}",
                        "warning",
                        game_id=game.game_id,
                    )
                )
                prices = {}

            for candidate in candidates:
                yes_probability = prices.get(candidate["positive_token"])
                no_probability = prices.get(candidate["negative_token"])
                player = candidate["player"]
                market_key = candidate["market_key"]
                market = candidate["market"]
                event = candidate["event"]
                if yes_probability is None and no_probability is None:
                    diagnostics.append(
                        ProviderDiagnostic(
                            PROVIDER_ID,
                            "unusable_price",
                            "Polymarket market has no executable BUY price on either side.",
                            game_id=game.game_id,
                            player_id=player.player_id,
                            market_key=market_key,
                            provider_market_id=str(market.get("id") or ""),
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
                quotes.append(
                    StatContractQuote(
                        source=source,
                        game_id=game.game_id,
                        player_id=player.player_id,
                        market_key=market_key,
                        predicate=candidate["predicate"],
                        yes=yes,
                        no=no,
                        observed_at=_parse_time(
                            market.get("updatedAt") or market.get("updated_at")
                        ),
                        phase="pregame",
                        provenance=QuoteProvenance(
                            provider_event_id=str(event.get("id") or event.get("gameId") or slug),
                            provider_market_id=str(
                                market.get("id") or market.get("conditionId") or ""
                            ),
                            raw_title=str(market.get("question") or market.get("groupItemTitle") or ""),
                            raw_rules=str(market.get("description") or "") or None,
                        ),
                    )
                )
                found.add((player.player_id, market_key))

            for player_id, market_key in sorted(requested - found):
                diagnostics.append(
                    ProviderDiagnostic(
                        PROVIDER_ID,
                        "market_not_found",
                        "No matching open Polymarket player market was found.",
                        game_id=game.game_id,
                        player_id=player_id,
                        market_key=market_key,
                    )
                )

        diagnostics.append(
            ProviderDiagnostic(
                PROVIDER_ID,
                "accepted_quotes",
                f"Accepted {len(quotes)} Polymarket quotes.",
            )
        )
        return ProviderResult(
            provider_id=PROVIDER_ID,
            quotes=tuple(quotes),
            diagnostics=tuple(diagnostics),
            fetched_at=dt.datetime.now(dt.UTC),
        )
