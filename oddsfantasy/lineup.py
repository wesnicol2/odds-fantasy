"""Optimal-lineup construction.

Pure functions over the player/defense dicts that services.py produces --
no network, no config, no odds knowledge. Split out of services.py, where
they were the only self-contained block in a 1,800-line module.
"""

from __future__ import annotations


def build_lineup(
    players: list[dict], target: str = "mid", defenses: list[dict] | None = None
) -> dict:
    """Build lineup: QB1, WR2, RB2, FLEX1 (from WR/RB/TE), DEF1, then BENCH.

    Always include players with zero projection in BENCH.

    `defenses` is optional and should be rows shaped like `list_defenses()`
    output (i.e. dicts with `defense`/`floor`/`mid`/`ceiling`) for the
    caller's OWNED defenses only -- passing available (unowned) defenses
    would let the lineup builder "start" a team you don't roster.
    """
    print(f"[services] build_lineup target={target} defenses={len(defenses or [])}")
    buckets: dict[str, list[dict]] = {"QB": [], "RB": [], "WR": [], "TE": [], "DEF": []}
    for p in players:
        if p.get("pos") in buckets:
            buckets[p["pos"]].append(p)
    for d in defenses or []:
        buckets["DEF"].append(
            {
                "name": d.get("defense"),
                "pos": "DEF",
                "team": d.get("defense"),
                "floor": d.get("floor"),
                "mid": d.get("mid"),
                "ceiling": d.get("ceiling"),
            }
        )
    for pos in buckets:
        # Ensure None values do not break sort comparisons
        buckets[pos].sort(
            key=lambda x: float(x.get(target)) if isinstance(x.get(target), (int, float)) else 0.0,
            reverse=True,
        )

    used = set()

    def take(pos: str, n: int) -> list[dict]:
        out = []
        for item in buckets.get(pos, []):
            if item["name"] not in used:
                out.append(item)
                used.add(item["name"])
                if len(out) == n:
                    break
        return out

    starters = {
        "QB": take("QB", 1),
        "WR": take("WR", 2),
        "RB": take("RB", 2),
        "TE": take("TE", 1),
        "DEF": take("DEF", 1),
    }
    # FLEX best remaining WR/RB/TE
    flex_pool = [
        item
        for pos in ("WR", "RB", "TE")
        for item in buckets.get(pos, [])
        if item["name"] not in used
    ]
    flex_pool.sort(
        key=lambda x: float(x.get(target)) if isinstance(x.get(target), (int, float)) else 0.0,
        reverse=True,
    )
    flex = flex_pool[:1]
    for f in flex:
        used.add(f["name"])  # mark used for bench

    rows = []
    total = 0.0

    def add_slot(slot: str, p: dict):
        nonlocal total

        def _num(v):
            try:
                if v is None:
                    return 0.0
                return float(v)
            except Exception:
                return 0.0

        pts = _num(p.get(target, 0.0))
        total += pts
        rows.append(
            {
                "slot": slot,
                "name": p["name"],
                "pos": p["pos"],
                # keep team in payload for future, UI may ignore it
                "team": p.get("team"),
                "points": round(pts, 2),
                # include full trio for UI rendering
                "floor": round(_num(p.get("floor", 0.0)), 2),
                "mid": round(_num(p.get("mid", 0.0)), 2),
                "ceiling": round(_num(p.get("ceiling", 0.0)), 2),
                # so the UI can distinguish "actually projected for ~0" from
                # "no odds coverage, this number is meaningless" -- carried
                # through from compute_projections' players_out, not computed
                # freshly here (DEF rows built directly in build_lineup won't
                # have it, which is fine: they always come from real odds).
                "incomplete": bool(p.get("incomplete")),
            }
        )

    # Order: QB, WR, WR, RB, RB, TE, FLEX, DEF
    for p in starters["QB"]:
        add_slot("QB", p)
    if len(starters["WR"]) > 0:
        add_slot("WR", starters["WR"][0])
    if len(starters["WR"]) > 1:
        add_slot("WR", starters["WR"][1])
    if len(starters["RB"]) > 0:
        add_slot("RB", starters["RB"][0])
    if len(starters["RB"]) > 1:
        add_slot("RB", starters["RB"][1])
    for p in starters["TE"]:
        add_slot("TE", p)
    for p in flex:
        add_slot("FLEX", p)
    for p in starters["DEF"]:
        add_slot("DEF", p)

    # Bench: remaining players by target (include zeros)
    bench: list[dict] = [
        item
        for pos in ("QB", "WR", "RB", "TE", "DEF")
        for item in buckets.get(pos, [])
        if item["name"] not in used
    ]
    bench.sort(
        key=lambda x: float(x.get(target)) if isinstance(x.get(target), (int, float)) else 0.0,
        reverse=True,
    )

    def _num(v):
        try:
            if v is None:
                return 0.0
            return float(v)
        except Exception:
            return 0.0

    rows.extend(
        {
            "slot": "BENCH",
            "name": b["name"],
            "pos": b["pos"],
            "team": b.get("team"),
            "points": round(_num(b.get(target, 0.0)), 2),
            "floor": round(_num(b.get("floor", 0.0)), 2),
            "mid": round(_num(b.get("mid", 0.0)), 2),
            "ceiling": round(_num(b.get("ceiling", 0.0)), 2),
        }
        for b in bench
    )

    return {"target": target, "lineup": rows, "total_points": round(total, 2)}


def build_lineup_diffs(players: list[dict], defenses: list[dict] | None = None) -> dict:
    base = build_lineup(players, target="mid", defenses=defenses)
    floor = build_lineup(players, target="floor", defenses=defenses)
    ceil = build_lineup(players, target="ceiling", defenses=defenses)

    def diff(from_rows: list[dict], to_rows: list[dict]) -> list[dict]:
        by_slot_from = {r["slot"]: r for r in from_rows}
        by_slot_to = {r["slot"]: r for r in to_rows}
        return [
            {
                "slot": slot,
                "from": by_slot_from[slot]["name"],
                "to": by_slot_to[slot]["name"],
            }
            for slot in by_slot_from
            if by_slot_from[slot]["name"] != by_slot_to[slot]["name"]
        ]

    return {
        "from": base,
        "floor_changes": diff(base["lineup"], floor["lineup"]),
        "ceiling_changes": diff(base["lineup"], ceil["lineup"]),
    }
