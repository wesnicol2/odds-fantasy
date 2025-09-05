from __future__ import annotations

from typing import Dict, List, Tuple
from dataclasses import dataclass
import statistics

from predicted_stats import implied_probability


@dataclass
class MarketSummary:
    avg_over_prob: float
    avg_under_prob: float
    avg_threshold: float
    samples: int


def _classify_side(name: str) -> str | None:
    n = (name or "").strip().lower()
    if n in ("over", "yes"):
        return "over"
    if n in ("under", "no"):
        return "under"
    return None


def aggregate_players_from_event(
    event_odds: object,
    target_player_aliases: set[str],
) -> tuple[dict, dict]:
    """Aggregate per-bookmaker odds for target players from a single event response.

    Returns (per_player_odds, per_player_market_summaries).

    per_player_odds is compatible with predict_stats_for_player input shape:
      { player_alias: { bookmaker_key: { market_key: { 'over': {...}, 'under': {...} } } } }

    per_player_market_summaries:
      { player_alias: { market_key: MarketSummary(...) } }
    """
    out_per_player: dict = {}
    out_summaries: dict = {}

    # Normalize event structure: can be a list with one event, or a dict
    if isinstance(event_odds, dict):
        events_list = [event_odds]
    elif isinstance(event_odds, list):
        events_list = event_odds
    else:
        events_list = []

    for ev in events_list:
        for book in (ev.get("bookmakers", []) if isinstance(ev, dict) else []):
            bookmaker_key = book.get("key")
            if not bookmaker_key:
                continue
            for market in book.get("markets", []):
                market_key = market.get("key")
                # First gather outcomes by alias for this market so we can de‑vig per book
                alias_outcomes = {}
                for outcome in market.get("outcomes", []):
                    alias = outcome.get("description")
                    if not alias or alias not in target_player_aliases:
                        continue
                    side = _classify_side(outcome.get("name")) or "over"
                    alias_outcomes.setdefault(alias, {"over": None, "under": None})
                    alias_outcomes[alias][side] = {
                        "odds": outcome.get("price"),
                        "point": outcome.get("point", 0),
                    }

                for alias, sides in alias_outcomes.items():
                    over = sides.get("over")
                    under = sides.get("under")

                    # Persist raw per-book sides for downstream prediction
                    out_per_player.setdefault(alias, {})
                    out_per_player[alias].setdefault(bookmaker_key, {})
                    out_per_player[alias][bookmaker_key].setdefault(market_key, {"over": None, "under": None})
                    if over:
                        out_per_player[alias][bookmaker_key][market_key]["over"] = over
                    if under:
                        out_per_player[alias][bookmaker_key][market_key]["under"] = under

                    # Compute per-book de‑vig probabilities if we have both sides; otherwise use raw implied
                    p_over = 0.0
                    p_under = 0.0
                    if over and under and over.get("odds") and under.get("odds"):
                        try:
                            o_raw = implied_probability(over["odds"])  # 1/odds
                            u_raw = implied_probability(under["odds"])  # 1/odds
                            total = o_raw + u_raw
                            if total > 0:
                                p_over = o_raw / total
                                p_under = u_raw / total
                        except Exception:
                            p_over = implied_probability(over["odds"]) if over and over.get("odds") else 0.0
                            p_under = implied_probability(under["odds"]) if under and under.get("odds") else 0.0
                    else:
                        # one-sided: keep raw implied where present
                        if over and over.get("odds"):
                            p_over = implied_probability(over["odds"]) or 0.0
                        if under and under.get("odds"):
                            p_under = implied_probability(under["odds"]) or 0.0

                    # Summary accumulators (averaging already de‑vigged per-book p’s when available)
                    out_summaries.setdefault(alias, {})
                    acc = out_summaries[alias].setdefault(
                        market_key,
                        {"over_vals": [], "under_vals": [], "point_vals": []},
                    )
                    acc["over_vals"].append(p_over)
                    acc["under_vals"].append(p_under)
                    # threshold from over (preferred) or under
                    pt = None
                    if over and ("point" in over):
                        pt = over.get("point")
                    elif under and ("point" in under):
                        pt = under.get("point")
                    if pt is not None:
                        try:
                            acc["point_vals"].append(float(pt))
                        except Exception:
                            pass

    # Finalize summaries
    finalized: dict = {}
    for alias, mkts in out_summaries.items():
        finalized[alias] = {}
        for mkey, acc in mkts.items():
            over_vals = acc.get("over_vals", [])
            under_vals = acc.get("under_vals", [])
            point_vals = acc.get("point_vals", [])
            samples = max(len(over_vals), len(under_vals), len(point_vals))
            med_over = statistics.median(over_vals) if over_vals else 0.0
            med_under = statistics.median(under_vals) if under_vals else 0.0
            med_point = statistics.median(point_vals) if point_vals else 0.0
            finalized[alias][mkey] = MarketSummary(
                avg_over_prob=med_over,
                avg_under_prob=med_under,
                avg_threshold=med_point,
                samples=samples,
            )

    return out_per_player, finalized


def aggregate_by_week(
    event_odds_by_game: dict[str, list],
    planned_games: dict[str, object],  # PlannedGame-like with .players
) -> tuple[dict[str, dict], dict[str, dict]]:
    """Aggregate players across all games in a window.

    Returns (per_player_odds, per_player_market_summaries) where keys are player aliases.
    """
    per_player_odds: dict[str, dict] = {}
    per_player_summaries: dict[str, dict] = {}

    for gid, event_odds in event_odds_by_game.items():
        game_plan = planned_games.get(gid)
        if not game_plan:
            continue
        aliases = {p["alias"] for p in game_plan.players}
        p_odds, p_summ = aggregate_players_from_event(event_odds, aliases)

        # Merge per-player odds
        for alias, by_book in p_odds.items():
            per_player_odds.setdefault(alias, {})
            # merge bookmakers
            for book_key, mkts in by_book.items():
                per_player_odds[alias].setdefault(book_key, {})
                for mkey, sides in mkts.items():
                    per_player_odds[alias][book_key].setdefault(mkey, {"over": None, "under": None})
                    for side, payload in sides.items():
                        if payload:
                            per_player_odds[alias][book_key][mkey][side] = payload

        # Merge summaries (average of averages isn’t ideal, but fine for a first pass)
        for alias, mkts in p_summ.items():
            per_player_summaries.setdefault(alias, {})
            for mkey, summ in mkts.items():
                # If already exists, do a simple running average by sample size
                if mkey in per_player_summaries[alias]:
                    prev = per_player_summaries[alias][mkey]
                    total_n = prev.samples + summ.samples
                    if total_n == 0:
                        continue
                    w_prev = prev.samples / total_n
                    w_new = summ.samples / total_n
                    per_player_summaries[alias][mkey] = MarketSummary(
                        avg_over_prob=prev.avg_over_prob * w_prev + summ.avg_over_prob * w_new,
                        avg_under_prob=prev.avg_under_prob * w_prev + summ.avg_under_prob * w_new,
                        avg_threshold=prev.avg_threshold * w_prev + summ.avg_threshold * w_new,
                        samples=total_n,
                    )
                else:
                    per_player_summaries[alias][mkey] = summ

    return per_player_odds, per_player_summaries
