"""Best-lineup optimization over already-computed player ranges."""

from __future__ import annotations

from functools import cache

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

    player_count = len(players)
    candidates = [dict(player) for player in players]
    candidates.extend(
        {
            "name": defense.get("defense"),
            "pos": "DEF",
            "team": defense.get("defense"),
            "floor": defense.get("floor"),
            "mid": defense.get("mid"),
            "ceiling": defense.get("ceiling"),
        }
        for defense in defenses or []
    )

    modeled_slots, unmodeled_slots = _starter_slots(roster_positions)
    eligible_by_slot: list[list[int]] = []
    for slot in modeled_slots:
        eligible_positions = SLOT_ELIGIBILITY[slot]
        eligible_by_slot.append(
            [
                index
                for index, candidate in enumerate(candidates)
                if (
                    candidate.get("pos") in eligible_positions
                    and _score(candidate, target) is not None
                )
            ]
        )

    def optimize(required_candidate: int | None = None) -> tuple[float, tuple[int | None, ...]]:
        required_bit = 1 << required_candidate if required_candidate is not None else 0

        @cache
        def solve(slot_index: int, used_mask: int) -> tuple[float, tuple[int | None, ...]]:
            if slot_index >= len(modeled_slots):
                if required_candidate is not None and not used_mask & required_bit:
                    return float("-inf"), ()
                return 0.0, ()

            best_total = float("-inf")
            best_choices: tuple[int | None, ...] | None = None
            for candidate_index in eligible_by_slot[slot_index]:
                bit = 1 << candidate_index
                if used_mask & bit:
                    continue
                rest_total, rest_choices = solve(slot_index + 1, used_mask | bit)
                score = _score(candidates[candidate_index], target)
                if score is None or rest_total == float("-inf"):
                    continue
                total = score + rest_total
                if total > best_total:
                    best_total = total
                    best_choices = (candidate_index, *rest_choices)

            if best_choices is None:
                rest_total, rest_choices = solve(slot_index + 1, used_mask)
                return rest_total, (None, *rest_choices)
            return best_total, best_choices

        return solve(0, 0)

    def lineup_rows(choices: tuple[int | None, ...]) -> tuple[list[dict], list[str]]:
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
        return rows, unfilled_slots

    total, choices = optimize()
    rows, unfilled_slots = lineup_rows(choices)
    baseline_total = total if total != float("-inf") else 0.0
    baseline_indices = {choice for choice in choices if choice is not None}
    baseline_slot_by_index = {
        choice: slot
        for slot, choice in zip(modeled_slots, choices, strict=True)
        if choice is not None
    }

    bench_pressure: list[dict] = []
    modeled_player_positions = {
        position
        for slot in modeled_slots
        if slot != "DEF"
        for position in SLOT_ELIGIBILITY[slot]
        if position != "DEF"
    }
    for candidate_index, candidate in enumerate(candidates[:player_count]):
        if candidate_index in baseline_indices:
            continue
        if candidate.get("pos") not in modeled_player_positions:
            continue
        candidate_score = _score(candidate, target)
        if candidate_score is None:
            continue

        forced_total, forced_choices = optimize(required_candidate=candidate_index)
        if forced_total == float("-inf"):
            continue
        forced_indices = {choice for choice in forced_choices if choice is not None}
        displaced_indices = [
            index for index in baseline_indices if index not in forced_indices and index < len(candidates)
        ]
        displaced_index = displaced_indices[0] if displaced_indices else None
        forced_slot = next(
            (
                slot
                for slot, choice in zip(modeled_slots, forced_choices, strict=True)
                if choice == candidate_index
            ),
            None,
        )
        displaced = candidates[displaced_index] if displaced_index is not None else None
        bench_pressure.append(
            {
                "name": candidate.get("name"),
                "pos": candidate.get("pos"),
                "team": candidate.get("team"),
                "points": round(candidate_score, 2),
                "delta_to_lineup": round(max(0.0, baseline_total - forced_total), 2),
                "slot": forced_slot,
                "displaces": displaced.get("name") if displaced else None,
                "displaces_slot": (
                    baseline_slot_by_index.get(displaced_index)
                    if displaced_index is not None
                    else None
                ),
            }
        )

    bench_pressure.sort(
        key=lambda row: (
            row["delta_to_lineup"],
            -row["points"],
            str(row.get("name") or ""),
        )
    )

    return {
        "target": target,
        "lineup": rows,
        "total_points": round(baseline_total, 2),
        "bench_pressure": bench_pressure,
        "unmodeled_slots": unmodeled_slots,
        "unfilled_slots": unfilled_slots,
    }
