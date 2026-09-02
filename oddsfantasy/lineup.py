"""Best-lineup optimization over already-computed player ranges."""

from __future__ import annotations

from functools import lru_cache

DEFAULT_STARTERS = ["QB", "RB", "RB", "WR", "WR", "TE", "FLEX", "DEF"]
SLOT_ELIGIBILITY: dict[str, set[str]] = {
    "QB": {"QB"},
    "RB": {"RB"},
    "WR": {"WR"},
    "TE": {"TE"},
    "FLEX": {"RB", "WR", "TE"},
    "WRRB_FLEX": {"WR", "RB"},
    "REC_FLEX": {"WR", "TE"},
    "SUPER_FLEX": {"QB", "RB", "WR", "TE"},
    "DEF": {"DEF"},
}
IGNORED_SLOTS = {"BN", "IR", "TAXI"}


def _score(candidate: dict, target: str) -> float | None:
    value = candidate.get(target)
    if isinstance(value, (int, float)):
        return float(value)
    return None


def _starter_slots(roster_positions: list[str] | None) -> tuple[list[str], list[str]]:
    positions = list(roster_positions or DEFAULT_STARTERS)
    modeled: list[str] = []
    unmodeled: list[str] = []
    for raw in positions:
        slot = str(raw or "").upper()
        if not slot or slot in IGNORED_SLOTS:
            continue
        if slot in SLOT_ELIGIBILITY:
            modeled.append(slot)
        else:
            unmodeled.append(slot)
    return modeled, unmodeled


def build_best_lineup(
    players: list[dict],
    target: str = "mid",
    roster_positions: list[str] | None = None,
    defenses: list[dict] | None = None,
) -> dict:
    """Maximize the selected range across the league's modeled starter slots."""
    if target not in {"floor", "mid", "ceiling"}:
        raise ValueError("target must be floor, mid, or ceiling")

    candidates = [dict(player) for player in players]
    for defense in defenses or []:
        candidates.append(
            {
                "name": defense.get("defense"),
                "pos": "DEF",
                "team": defense.get("defense"),
                "floor": defense.get("floor"),
                "mid": defense.get("mid"),
                "ceiling": defense.get("ceiling"),
            }
        )

    modeled_slots, unmodeled_slots = _starter_slots(roster_positions)
    eligible_by_slot: list[list[int]] = []
    for slot in modeled_slots:
        eligible_positions = SLOT_ELIGIBILITY[slot]
        eligible_by_slot.append(
            [
                index
                for index, candidate in enumerate(candidates)
                if candidate.get("pos") in eligible_positions and _score(candidate, target) is not None
            ]
        )

    @lru_cache(maxsize=None)
    def solve(slot_index: int, used_mask: int) -> tuple[float, tuple[int | None, ...]]:
        if slot_index >= len(modeled_slots):
            return 0.0, ()

        best_total = float("-inf")
        best_choices: tuple[int | None, ...] | None = None
        for candidate_index in eligible_by_slot[slot_index]:
            bit = 1 << candidate_index
            if used_mask & bit:
                continue
            rest_total, rest_choices = solve(slot_index + 1, used_mask | bit)
            score = _score(candidates[candidate_index], target)
            if score is None:
                continue
            total = score + rest_total
            if total > best_total:
                best_total = total
                best_choices = (candidate_index, *rest_choices)

        if best_choices is None:
            rest_total, rest_choices = solve(slot_index + 1, used_mask)
            return rest_total, (None, *rest_choices)
        return best_total, best_choices

    total, choices = solve(0, 0)
    rows: list[dict] = []
    unfilled_slots: list[str] = []
    for slot, choice in zip(modeled_slots, choices, strict=True):
        if choice is None:
            unfilled_slots.append(slot)
            continue
        candidate = candidates[choice]
        rows.append(
            {
                "slot": slot,
                "name": candidate.get("name"),
                "pos": candidate.get("pos"),
                "team": candidate.get("team"),
                "points": round(float(_score(candidate, target) or 0.0), 2),
                "floor": candidate.get("floor"),
                "mid": candidate.get("mid"),
                "ceiling": candidate.get("ceiling"),
            }
        )

    return {
        "target": target,
        "lineup": rows,
        "total_points": round(total if total != float("-inf") else 0.0, 2),
        "unmodeled_slots": unmodeled_slots,
        "unfilled_slots": unfilled_slots,
    }
