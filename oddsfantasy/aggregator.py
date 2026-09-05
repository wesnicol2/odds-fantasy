"""Normalize Odds API event payloads into per-player, per-book market lines.

No projection math lives here. The methodology engine consumes the raw book
lines directly, de-vigs each book, and builds consensus anchors itself. Player
position is carried as non-market metadata so position-dependent league scoring
can interpret an anytime touchdown without changing the sportsbook evidence.
"""

from __future__ import annotations

import re

PLAYER_POSITION_META_KEY = "__player_position__"


def _norm_name(value: str) -> str:
    value = (value or "").lower()
    value = re.sub(r"[\.'`-]", " ", value)
    value = re.sub(r"[^a-z0-9 ]", "", value)
    value = re.sub(r"\s+", " ", value).strip()
    tokens = [t for t in value.split() if t not in {"jr", "sr", "ii", "iii", "iv", "v"}]
    return " ".join(tokens)


def _classify_side(name: str) -> str | None:
    name = (name or "").strip().lower()
    if name in {"over", "yes"}:
        return "over"
    if name in {"under", "no"}:
        return "under"
    return None


def aggregate_players_from_event(
    event_odds: object, target_player_aliases: set[str]
) -> dict[str, dict]:
    """Return ``alias -> bookmaker -> market -> raw sides`` for one event."""
    aliases = target_player_aliases or set()
    norm_alias_map = {_norm_name(alias): alias for alias in aliases}
    events = (
        [event_odds]
        if isinstance(event_odds, dict)
        else event_odds
        if isinstance(event_odds, list)
        else []
    )
    output: dict[str, dict] = {}

    for event in events:
        if not isinstance(event, dict):
            continue
        for book in event.get("bookmakers", []) or []:
            book_key = book.get("key")
            if not book_key:
                continue
            for market in book.get("markets", []) or []:
                market_key = market.get("key")
                if not market_key:
                    continue
                alternate = str(market_key).endswith("_alternate")
                gathered: dict[str, dict] = {}

                for outcome in market.get("outcomes", []) or []:
                    description = outcome.get("description")
                    if not description:
                        continue
                    alias = (
                        description
                        if description in aliases
                        else norm_alias_map.get(_norm_name(description))
                    )
                    if alias is None:
                        continue
                    side = _classify_side(outcome.get("name")) or "over"
                    record = {"odds": outcome.get("price"), "point": outcome.get("point", 0)}
                    if alternate:
                        bucket = gathered.setdefault(alias, {"over": [], "under": []})
                        bucket[side].append(record)
                    else:
                        bucket = gathered.setdefault(alias, {"over": None, "under": None})
                        bucket[side] = record

                for alias, sides in gathered.items():
                    market_out = output.setdefault(alias, {}).setdefault(book_key, {})
                    if alternate:
                        market_out[market_key] = {
                            "alts": {"over": list(sides["over"]), "under": list(sides["under"])}
                        }
                    else:
                        market_out[market_key] = {"over": sides["over"], "under": sides["under"]}

    return output


def aggregate_by_week(
    event_odds_by_game: dict[str, object], planned_games: dict[str, object]
) -> dict[str, dict]:
    """Merge normalized player odds across all planned games in a week.

    Position is copied from the already-resolved game plan into each book's
    market dictionary under :data:`PLAYER_POSITION_META_KEY`. It is metadata,
    not a market: the odds math ignores unknown keys, while the scoring layer
    can use it to distinguish receiving from rushing touchdown scoring.
    """
    output: dict[str, dict] = {}
    for game_id, event_odds in (event_odds_by_game or {}).items():
        game_plan = planned_games.get(game_id)
        if not game_plan:
            continue
        aliases = {player["alias"] for player in game_plan.players}
        position_by_alias = {
            player["alias"]: str(player.get("primary_position") or "").upper()
            for player in game_plan.players
        }
        event_players = aggregate_players_from_event(event_odds, aliases)
        for alias, books in event_players.items():
            player_out = output.setdefault(alias, {})
            for book_key, markets in books.items():
                book_out = player_out.setdefault(book_key, {})
                book_out.update(markets)
                position = position_by_alias.get(alias)
                if position:
                    book_out[PLAYER_POSITION_META_KEY] = {"value": position}
    return output
