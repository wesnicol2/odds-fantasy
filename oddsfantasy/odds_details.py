"""Player drill-down: the exact sportsbook lines behind the canonical curve."""

from __future__ import annotations

import re
from statistics import median

from . import odds_client, ratelimit
from .defense import implied_team_total
from .graph_data import distribution_graph
from .market_math import collect_anchors
from .projection import (
    COMBINED_YARDAGE_KEY,
    COMBINED_YARDAGE_MARKETS,
    combined_stat_range,
    project_player,
    survival_curve,
)
from .services import NO_GAMES_SCHEDULED_MESSAGE, _load_week_context


def _norm_name(value: str) -> str:
    value = (value or "").lower()
    value = re.sub(r"[\.'`-]", " ", value)
    value = re.sub(r"[^a-z0-9 ]", "", value)
    value = re.sub(r"\s+", " ", value).strip()
    tokens = [t for t in value.split() if t not in {"jr", "sr", "ii", "iii", "iv", "v"}]
    return " ".join(tokens)


def _line_rows(by_book: dict, market_key: str) -> list[dict]:
    """Flatten main and alternate lines without changing their prices."""
    rows: list[dict] = []
    for book_key, markets in (by_book or {}).items():
        main = (markets or {}).get(market_key)
        if isinstance(main, dict):
            over = main.get("over") or {}
            under = main.get("under") or {}
            if over or under:
                point = over.get("point") if over.get("point") is not None else under.get("point")
                rows.append(
                    {
                        "book": book_key,
                        "source": "main",
                        "point": point,
                        "over_odds": over.get("odds"),
                        "under_odds": under.get("odds"),
                    }
                )

        alternate = (markets or {}).get(f"{market_key}_alternate")
        alts = alternate.get("alts") if isinstance(alternate, dict) else None
        if isinstance(alts, dict):
            by_point: dict[float, dict] = {}
            for side in ("over", "under"):
                for item in alts.get(side) or []:
                    try:
                        point = float(item.get("point"))
                    except (TypeError, ValueError):
                        continue
                    row = by_point.setdefault(
                        point,
                        {
                            "book": book_key,
                            "source": "alternate",
                            "point": point,
                            "over_odds": None,
                            "under_odds": None,
                        },
                    )
                    row[f"{side}_odds"] = item.get("odds")
            rows.extend(by_point.values())
    rows.sort(key=lambda row: (float(row.get("point") or 0), str(row.get("book") or "")))
    return rows


def _game_line_context(event_odds: object, team: str) -> dict:
    """Return median same-week game lines without turning them into a player model."""
    events = (
        [event_odds]
        if isinstance(event_odds, dict)
        else [row for row in event_odds if isinstance(row, dict)]
        if isinstance(event_odds, list)
        else []
    )
    totals: list[float] = []
    spreads: list[float] = []
    implied_totals: list[float] = []
    books_used: set[str] = set()

    for event in events:
        for book in event.get("bookmakers", []) or []:
            game_total = None
            team_spread = None
            for market in book.get("markets", []) or []:
                if market.get("key") == "totals":
                    over = next(
                        (
                            outcome
                            for outcome in market.get("outcomes", []) or []
                            if outcome.get("name") == "Over"
                        ),
                        None,
                    )
                    game_total = over.get("point") if over else None
                elif market.get("key") == "spreads":
                    team_outcome = next(
                        (
                            outcome
                            for outcome in market.get("outcomes", []) or []
                            if outcome.get("name") == team
                        ),
                        None,
                    )
                    team_spread = team_outcome.get("point") if team_outcome else None

            try:
                parsed_total = float(game_total) if game_total is not None else None
                parsed_spread = float(team_spread) if team_spread is not None else None
            except (TypeError, ValueError):
                continue

            if parsed_total is not None:
                totals.append(parsed_total)
            if parsed_spread is not None:
                spreads.append(parsed_spread)
            if parsed_total is not None and parsed_spread is not None:
                implied_totals.append(implied_team_total(parsed_total, parsed_spread))
            if parsed_total is not None or parsed_spread is not None:
                books_used.add(str(book.get("key") or book.get("title") or "unknown"))

    return {
        "game_total": round(float(median(totals)), 2) if totals else None,
        "team_spread": round(float(median(spreads)), 2) if spreads else None,
        "team_implied_total": (round(float(median(implied_totals)), 2) if implied_totals else None),
        "books_used": len(books_used),
    }


def _player_matchup(
    context: dict,
    target_alias: str,
    team: str | None,
    region: str,
    cache_mode: str,
    fresh: bool,
) -> dict | None:
    game = next(
        (
            planned
            for planned in (context.get("planned") or {}).values()
            if any(player.get("alias") == target_alias for player in planned.players)
        ),
        None,
    )
    if game is None or not team:
        return None

    opponent = game.away_team if team == game.home_team else game.home_team
    venue = "home" if team == game.home_team else "away"
    line_context = {
        "game_total": None,
        "team_spread": None,
        "team_implied_total": None,
        "books_used": 0,
    }
    try:
        game_odds = odds_client.get_event_player_odds(
            event_id=game.game_id,
            markets="spreads,totals",
            regions=region,
            mode="fresh" if fresh else cache_mode,
        )
        line_context = _game_line_context(game_odds, team)
    except Exception as exc:
        print(f"[odds_details] game line fetch failed for {game.game_id}: {exc}")

    return {
        "opponent": opponent,
        "venue": venue,
        "commence_time": game.commence_time,
        **line_context,
    }


def get_player_odds_details(
    username: str,
    season: str,
    week: str = "this",
    region: str = "us",
    name: str = "",
    cache_mode: str = "auto",
    fresh: bool = False,
    league_id: str | None = None,
    roster_id: int | None = None,
) -> dict:
    """Return one player's projection plus only the lines that feed it."""
    context = _load_week_context(
        username=username,
        season=season,
        week=week,
        region=region,
        fresh=fresh,
        cache_mode=cache_mode,
        league_id=league_id,
        roster_id=roster_id,
    )
    if context.get("message"):
        return {
            "player": {"name": name},
            "projection": None,
            "markets": {},
            "combined_markets": {},
            "message": NO_GAMES_SCHEDULED_MESSAGE,
            "ratelimit": ratelimit.format_status(),
            "ratelimit_info": ratelimit.get_details(),
        }

    info_by_alias = context.get("info_by_alias") or {}
    target_alias = None
    wanted = _norm_name(name)
    for alias, info in info_by_alias.items():
        full_name = info.get("full_name", alias)
        if full_name == name or _norm_name(full_name) == wanted:
            target_alias = alias
            break

    if target_alias is None:
        return {
            "player": {"name": name},
            "projection": None,
            "markets": {},
            "combined_markets": {},
            "ratelimit": ratelimit.format_status(),
            "ratelimit_info": ratelimit.get_details(),
        }

    info = info_by_alias[target_alias]
    by_book = (context.get("players_odds") or {}).get(target_alias, {})
    projection = project_player(by_book, context.get("scoring_rules") or {})
    matchup = _player_matchup(
        context,
        target_alias,
        info.get("editorial_team_full_name"),
        region,
        cache_mode,
        fresh,
    )

    markets: dict[str, dict] = {}
    for market_key, stat in projection.stats.items():
        anchors = collect_anchors(by_book, market_key)
        markets[market_key] = {
            "stat_range": [round(value, 2) for value in stat.stat_range],
            "stat_mean": round(stat.mean, 2),
            "expected_points": round(stat.expected_points, 3),
            "graph": distribution_graph(stat.distribution, market_key),
            "anchors": [
                {
                    "threshold": round(anchor.threshold, 2),
                    "survival": round(anchor.survival, 4),
                }
                for anchor in anchors
            ],
            "lines": _line_rows(by_book, market_key),
        }

    # Rushing and receiving yardage summed into one comparable quantity. The
    # range is sampled by the projection engine because percentiles do not add.
    combined_markets: dict[str, dict] = {}
    combined_range = combined_stat_range(projection.stats)
    if combined_range is not None:
        sources = [key for key in COMBINED_YARDAGE_MARKETS if key in projection.stats]
        combined_markets[COMBINED_YARDAGE_KEY] = {
            "markets": sources,
            "stat_range": [round(value, 2) for value in combined_range],
            # Means add exactly, so this needs no sampling the way the range does.
            "stat_mean": round(sum(projection.stats[key].mean for key in sources), 2),
            "expected_points": round(
                sum(projection.stats[key].expected_points for key in sources), 3
            ),
        }

    has_projection = projection.has_projection
    return {
        "player": {
            "name": info.get("full_name", name),
            "pos": info.get("primary_position"),
            "team": info.get("editorial_team_full_name"),
        },
        "projection": (
            {
                "floor": round(projection.floor, 2),
                "mid": round(projection.mid, 2),
                "ceiling": round(projection.ceiling, 2),
                "mean": round(projection.mean, 2),
                "curve": survival_curve(projection.samples),
            }
            if has_projection
            else None
        ),
        "matchup": matchup,
        "markets": markets,
        "combined_markets": combined_markets,
        "ratelimit": ratelimit.format_status(),
        "ratelimit_info": ratelimit.get_details(),
    }
