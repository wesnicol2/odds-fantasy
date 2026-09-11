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


def _starter_slot_specs(
    roster_positions: list[str] | None,
) -> tuple[list[tuple[int, str]], list[tuple[int, str]]]:
    """Return modeled/unmodeled starter slots with their submitted-starter index."""
    positions = list(roster_positions or DEFAULT_STARTERS)
    modeled: list[tuple[int, str]] = []
    unmodeled: list[tuple[int, str]] = []
    starter_index = 0
    for raw in positions:
        slot = str(raw or "").upper()
        if not slot or slot in IGNORED_SLOTS:
            continue
        spec = (starter_index, slot)
        starter_index += 1
        if slot in SLOT_ELIGIBILITY:
            modeled.append(spec)
        else:
            unmodeled.append(spec)
    return modeled, unmodeled


def build_best_lineup(
    players: list[dict],
    target: str = "mid",
    roster_positions: list[str] | None = None,
    defenses: list[dict] | None = None,
    locked_assignments: list[dict] | None = None,
    unavailable_player_ids: list[str] | set[str] | None = None,
) -> dict:
    """Maximize only starter slots that can still legally change.

    ``locked_assignments`` are the user's submitted starters whose NFL games
    have begun. They stay in their submitted slot and contribute actual fantasy
    points. ``unavailable_player_ids`` also removes already-started bench
    players, preventing hindsight recommendations after a Thursday/Saturday
    game has kicked off.
    """
    if target not in {"floor", "mid", "ceiling"}:
        raise ValueError("target must be floor, mid, or ceiling")

    player_count = len(players)
    candidates = [dict(player) for player in players]
    candidates.extend(
        {
            "player_id": defense.get("abbr") or defense.get("defense"),
            "name": defense.get("defense"),
            "pos": "DEF",
            "team": defense.get("defense"),
            "floor": defense.get("floor"),
            "mid": defense.get("mid"),
            "ceiling": defense.get("ceiling"),
        }
        for defense in defenses or []
    )

    modeled_specs, unmodeled_specs = _starter_slot_specs(roster_positions)
    locks = [dict(row) for row in (locked_assignments or [])]
    locked_by_index = {
        int(row["starter_index"]): row for row in locks if isinstance(row.get("starter_index"), int)
    }
    locked_ids = {str(row.get("player_id")) for row in locks if row.get("player_id") is not None}
    locked_names = {str(row.get("name")) for row in locks if row.get("name")}
    blocked_ids = {str(value) for value in (unavailable_player_ids or [])} | locked_ids

    def is_blocked(candidate: dict) -> bool:
        candidate_id = candidate.get("player_id")
        if candidate_id is not None and str(candidate_id) in blocked_ids:
            return True
        return bool(candidate.get("name") and str(candidate.get("name")) in locked_names)

    open_modeled_specs = [spec for spec in modeled_specs if spec[0] not in locked_by_index]
    open_unmodeled_specs = [spec for spec in unmodeled_specs if spec[0] not in locked_by_index]

    eligible_by_slot: list[list[int]] = []
    for _starter_index, slot in open_modeled_specs:
        eligible_positions = SLOT_ELIGIBILITY[slot]
        eligible_by_slot.append(
            [
                index
                for index, candidate in enumerate(candidates)
                if (
                    candidate.get("pos") in eligible_positions
                    and _score(candidate, target) is not None
                    and not is_blocked(candidate)
                )
            ]
        )

    def optimize(required_candidate: int | None = None) -> tuple[float, tuple[int | None, ...]]:
        required_bit = 1 << required_candidate if required_candidate is not None else 0

        @cache
        def solve(slot_index: int, used_mask: int) -> tuple[float, tuple[int | None, ...]]:
            if slot_index >= len(open_modeled_specs):
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
        for (starter_index, slot), choice in zip(open_modeled_specs, choices, strict=True):
            if choice is None:
                unfilled_slots.append(slot)
                continue
            candidate = candidates[choice]
            rows.append(
                {
                    "starter_index": starter_index,
                    "slot": slot,
                    "name": candidate.get("name"),
                    "pos": candidate.get("pos"),
                    "team": candidate.get("team"),
                    "points": round(float(_score(candidate, target) or 0.0), 2),
                    "floor": candidate.get("floor"),
                    "mid": candidate.get("mid"),
                    "ceiling": candidate.get("ceiling"),
                    "locked": False,
                    "game_status": "upcoming",
                    "actual_points": None,
                }
            )
        return rows, unfilled_slots

    remaining_total, choices = optimize()
    rows, unfilled_slots = lineup_rows(choices)
    baseline_remaining_total = remaining_total if remaining_total != float("-inf") else 0.0
    baseline_indices = {choice for choice in choices if choice is not None}
    baseline_slot_by_index = {
        choice: slot
        for (_starter_index, slot), choice in zip(open_modeled_specs, choices, strict=True)
        if choice is not None
    }

    locked_rows: list[dict] = []
    for starter_index, lock in sorted(locked_by_index.items()):
        actual = lock.get("actual_points")
        actual_points = float(actual) if isinstance(actual, (int, float)) else 0.0
        locked_rows.append(
            {
                "starter_index": starter_index,
                "slot": lock.get("slot"),
                "name": lock.get("name"),
                "pos": lock.get("pos"),
                "team": lock.get("team"),
                "points": round(actual_points, 2),
                "floor": None,
                "mid": None,
                "ceiling": None,
                "locked": True,
                "game_status": lock.get("game_status") or "final",
                "actual_points": round(actual_points, 2),
            }
        )

    bench_pressure: list[dict] = []
    modeled_player_positions = {
        position
        for _starter_index, slot in open_modeled_specs
        if slot != "DEF"
        for position in SLOT_ELIGIBILITY[slot]
        if position != "DEF"
    }
    for candidate_index, candidate in enumerate(candidates[:player_count]):
        if candidate_index in baseline_indices or is_blocked(candidate):
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
            choice
            for choice in choices
            if choice is not None and choice not in forced_indices and choice < len(candidates)
        ]
        displaced_index = displaced_indices[0] if displaced_indices else None
        forced_slot = next(
            (
                slot
                for (_starter_index, slot), choice in zip(
                    open_modeled_specs, forced_choices, strict=True
                )
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
                "delta_to_lineup": round(max(0.0, baseline_remaining_total - forced_total), 2),
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

    locked_points = sum(float(row["points"]) for row in locked_rows)
    all_rows = sorted(
        [*locked_rows, *rows],
        key=lambda row: int(row.get("starter_index", 10_000)),
    )
    starter_slot_count = len(modeled_specs) + len(unmodeled_specs)
    locked_bench_count = len(blocked_ids - locked_ids)

    return {
        "target": target,
        "lineup": all_rows,
        "total_points": round(locked_points + baseline_remaining_total, 2),
        "locked_points": round(locked_points, 2),
        "remaining_points": round(baseline_remaining_total, 2),
        "locked_count": len(locked_rows),
        "remaining_slots": max(0, starter_slot_count - len(locked_by_index)),
        "remaining_modeled_slots": len(open_modeled_specs),
        "locked_bench_count": locked_bench_count,
        "bench_pressure": bench_pressure,
        "unmodeled_slots": [slot for _index, slot in open_unmodeled_specs],
        "unfilled_slots": unfilled_slots,
    }
