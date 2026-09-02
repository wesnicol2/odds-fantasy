"""Player drill-down: the exact sportsbook lines behind the canonical curve."""

from __future__ import annotations

import re

from . import ratelimit
from .graph_data import distribution_graph
from .line_provenance import fair_line_points, fair_probability_lookup
from .market_math import collect_anchors
from .projection import project_player, survival_curve
from .services import NO_GAMES_SCHEDULED_MESSAGE, _load_week_context


def _norm_name(value: str) -> str:
    value = (value or "").lower()
    value = re.sub(r"[\.'`-]", " ", value)
    value = re.sub(r"[^a-z0-9 ]", "", value)
    value = re.sub(r"\s+", " ", value).strip()
    tokens = [t for t in value.split() if t not in {"jr", "sr", "ii", "iii", "iv", "v"}]
    return " ".join(tokens)


def _line_rows(by_book: dict, market_key: str) -> list[dict]:
    """Flatten raw lines and attach the exact per-book fair over probability."""
    fair_lookup = fair_probability_lookup(by_book, market_key)
    rows: list[dict] = []
    for book_key, markets in (by_book or {}).items():
        main = (markets or {}).get(market_key)
        if isinstance(main, dict):
            over = main.get("over") or {}
            under = main.get("under") or {}
            if over or under:
                point = over.get("point") if over.get("point") is not None else under.get("point")
                try:
                    point_key = float(point)
                except (TypeError, ValueError):
                    point_key = None
                rows.append(
                    {
                        "book": book_key,
                        "source": "main",
                        "point": point,
                        "over_odds": over.get("odds"),
                        "under_odds": under.get("odds"),
                        "fair_over": (
                            fair_lookup.get((str(book_key), point_key))
                            if point_key is not None
                            else None
                        ),
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
                            "fair_over": fair_lookup.get((str(book_key), point)),
                        },
                    )
                    row[f"{side}_odds"] = item.get("odds")
            rows.extend(by_point.values())
    rows.sort(key=lambda row: (float(row.get("point") or 0), str(row.get("book") or "")))
    return rows


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
            "ratelimit": ratelimit.format_status(),
            "ratelimit_info": ratelimit.get_details(),
        }

    info = info_by_alias[target_alias]
    by_book = (context.get("players_odds") or {}).get(target_alias, {})
    projection = project_player(by_book, context.get("scoring_rules") or {})

    markets: dict[str, dict] = {}
    for market_key, stat in projection.stats.items():
        anchors = collect_anchors(by_book, market_key)
        markets[market_key] = {
            "stat_range": [round(value, 2) for value in stat.stat_range],
            "expected_points": round(stat.expected_points, 3),
            "graph": distribution_graph(stat.distribution, market_key),
            "line_points": fair_line_points(by_book, market_key),
            "anchors": [
                {
                    "threshold": round(anchor.threshold, 2),
                    "survival": round(anchor.survival, 4),
                }
                for anchor in anchors
            ],
            "lines": _line_rows(by_book, market_key),
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
        "markets": markets,
        "ratelimit": ratelimit.format_status(),
        "ratelimit_info": ratelimit.get_details(),
    }
