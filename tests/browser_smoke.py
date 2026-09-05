"""Headless browser smoke test against the built production container.

The container serves the real React/Vite bundle. Application-data API calls are
intercepted with deterministic fixtures so the smoke test does not spend Odds
API quota or depend on Sleeper availability.
"""

from __future__ import annotations

import json
import os
from urllib.parse import parse_qs, urlparse

from playwright.sync_api import Route, sync_playwright

BASE_URL = os.getenv("SMOKE_BASE_URL", "http://127.0.0.1:18000")

CURVE_A = [
    {"x": 0, "survival": 1.0},
    {"x": 10, "survival": 0.85},
    {"x": 20, "survival": 0.50},
    {"x": 30, "survival": 0.10},
]
CURVE_B = [
    {"x": 0, "survival": 1.0},
    {"x": 8, "survival": 0.90},
    {"x": 18, "survival": 0.50},
    {"x": 28, "survival": 0.10},
]
RUSH_GRAPH = {
    "kind": "survival",
    "points": [
        {"x": 40, "probability": 0.90},
        {"x": 60, "probability": 0.74},
        {"x": 80, "probability": 0.47},
        {"x": 100, "probability": 0.21},
        {"x": 120, "probability": 0.06},
    ],
}


def fulfill_json(route: Route, payload: dict, status: int = 200) -> None:
    route.fulfill(status=status, content_type="application/json", body=json.dumps(payload))


def projection_player(
    name: str,
    pos: str,
    team: str,
    floor: float,
    mid: float,
    ceiling: float,
    curve: list[dict],
) -> dict:
    return {
        "name": name,
        "alias": name,
        "pos": pos,
        "team": team,
        "floor": floor,
        "mid": mid,
        "ceiling": ceiling,
        "mean": mid + 0.5,
        "curve": curve,
        "books_used": 2,
        "markets_used": 1,
        "has_projection": True,
    }


def api_fixture(route: Route) -> None:
    parsed = urlparse(route.request.url)
    query = parse_qs(parsed.query)

    if parsed.path == "/user/leagues":
        fulfill_json(
            route,
            {
                "username": query.get("username", ["smokeuser"])[0],
                "leagues": [{"league_id": "L1", "name": "Smoke League"}],
            },
        )
        return

    if parsed.path == "/league/resolve":
        fulfill_json(
            route,
            {
                "league_id": "L1",
                "name": "Smoke League",
                "teams": [
                    {
                        "roster_id": 7,
                        "owner_id": "owner-7",
                        "team_name": "Smoke Team",
                        "display_name": "Smoke Owner",
                    }
                ],
            },
        )
        return

    if parsed.path == "/projections":
        fulfill_json(
            route,
            {
                "week": query.get("week", ["this"])[0],
                "players": [
                    projection_player(
                        "Alpha Runner", "RB", "Buffalo Bills", 10, 17, 25, CURVE_A
                    ),
                    projection_player(
                        "Beta Receiver", "WR", "Miami Dolphins", 8, 15, 24, CURVE_B
                    ),
                ],
                "roster_positions": ["RB", "WR", "K"],
                "ratelimit": "Odds API · 499 remaining",
            },
        )
        return

    if parsed.path == "/player/odds":
        name = query.get("name", ["Alpha Runner"])[0]
        is_receiver = name == "Beta Receiver"
        pos = "WR" if is_receiver else "RB"
        team = "Miami Dolphins" if is_receiver else "Buffalo Bills"
        curve = CURVE_B if is_receiver else CURVE_A
        floor, mid, ceiling = ((8, 15, 24) if is_receiver else (10, 17, 25))
        fulfill_json(
            route,
            {
                "player": {"name": name, "pos": pos, "team": team},
                "projection": {
                    "floor": floor,
                    "mid": mid,
                    "ceiling": ceiling,
                    "mean": mid + 0.5,
                    "curve": curve,
                },
                "markets": {
                    "player_rush_yds": {
                        "stat_range": [45, 75, 115],
                        "expected_points": 7.5,
                        "graph": RUSH_GRAPH,
                        "anchors": [
                            {"threshold": 64.5, "survival": 0.68},
                            {"threshold": 84.5, "survival": 0.39},
                        ],
                        "lines": [
                            {
                                "book": "draftkings",
                                "source": "main",
                                "point": 64.5,
                                "over_odds": 1.91,
                                "under_odds": 1.91,
                            },
                            {
                                "book": "fanduel",
                                "source": "alternate",
                                "point": 84.5,
                                "over_odds": 2.10,
                                "under_odds": 1.72,
                            },
                        ],
                    }
                },
                "ratelimit": "Odds API · 499 remaining",
            },
        )
        return

    if parsed.path == "/defenses":
        fulfill_json(
            route,
            {
                "week": query.get("week", ["this"])[0],
                "defenses": [
                    {
                        "defense": "Los Angeles Chargers",
                        "abbr": "LAC",
                        "opponent": "Las Vegas Raiders",
                        "game_date": "2026-09-13T20:25:00Z",
                        "implied_total": 17.25,
                        "book_count": 6,
                        "taken": False,
                        "owner": None,
                        "owned_by_current": False,
                        "floor": 4.0,
                        "mid": 7.0,
                        "ceiling": 10.0,
                    },
                    {
                        "defense": "Jacksonville Jaguars",
                        "abbr": "JAX",
                        "opponent": "Tennessee Titans",
                        "game_date": "2026-09-13T17:00:00Z",
                        "implied_total": 19.5,
                        "book_count": 5,
                        "taken": True,
                        "owner": "Other Team",
                        "owned_by_current": False,
                        "floor": 3.0,
                        "mid": 6.0,
                        "ceiling": 9.0,
                    },
                ],
                "note": "DEF fantasy ranges use only the points-allowed component.",
                "ratelimit": "Odds API · 499 remaining",
            },
        )
        return

    if parsed.path == "/best-lineup":
        target = query.get("target", ["mid"])[0]
        values = {"floor": 10, "mid": 17, "ceiling": 25}
        fulfill_json(
            route,
            {
                "week": query.get("week", ["this"])[0],
                "target": target,
                "lineup": [
                    {
                        "slot": "RB",
                        "name": "Alpha Runner",
                        "pos": "RB",
                        "team": "Buffalo Bills",
                        "points": values[target],
                        "floor": 10,
                        "mid": 17,
                        "ceiling": 25,
                    }
                ],
                "total_points": values[target],
                "unmodeled_slots": ["K"],
                "unfilled_slots": [],
                "defense_note": "DEF ranges use only the points-allowed component.",
                "ratelimit": "Odds API · 499 remaining",
            },
        )
        return

    route.continue_()


def main() -> None:
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        context = browser.new_context()
        page = context.new_page()
        page.route("**/*", api_fixture)
        page.goto(BASE_URL, wait_until="networkidle")

        # Fresh-browser setup is part of the production runtime, not a legacy fallback.
        setup = page.get_by_role("dialog", name="Set up your league")
        setup.wait_for()
        setup.get_by_label("Sleeper username").fill("smokeuser")
        setup.get_by_role("button", name="Continue").click()
        league_select = setup.get_by_label("League for smokeuser")
        league_select.wait_for()
        league_select.select_option("L1")
        setup.get_by_role("button", name="Continue").click()
        team_select = setup.get_by_label("Team in Smoke League")
        team_select.wait_for()
        team_select.select_option("7")
        setup.get_by_role("button", name="Use this team").click()
        setup.wait_for(state="hidden")

        page.get_by_text("Smoke League · Smoke Team", exact=True).wait_for()
        cookies = {row["name"]: row["value"] for row in context.cookies()}
        assert cookies["league_id"] == "L1"
        assert cookies["roster_id"] == "7"

        # The default player view is one linked ranking/chart/inspector workspace.
        ranking = page.get_by_role("complementary", name="Player ranking")
        ranking.get_by_text("Alpha Runner", exact=True).wait_for()
        alpha_row = ranking.locator("tbody tr").filter(has_text="Alpha Runner").first
        assert "10.0" in alpha_row.inner_text()
        assert "17.0" in alpha_row.inner_text()
        assert "25.0" in alpha_row.inner_text()
        page.get_by_role("img", name="Fantasy points survival probability comparison", exact=False).wait_for()

        target_input = page.get_by_label("Target FP")
        target_input.fill("20")
        inspector = page.get_by_role("complementary", name="Player inspector")
        inspector.get_by_text("Chance of ≥ 20.0 FP", exact=True).wait_for()
        inspector.get_by_text("50%", exact=True).wait_for()
        assert "≥ 20.0" in ranking.locator("thead").inner_text()

        # Stat exploration reuses the same workspace and exposes inspectable evidence.
        page.get_by_role("button", name="Rushing yards").wait_for()
        page.get_by_role("button", name="Rushing yards").click()
        inspector.get_by_text("Rushing yards evidence", exact=True).wait_for()
        inspector.get_by_text("2 consensus thresholds", exact=True).wait_for()
        inspector.get_by_text("2 source lines", exact=True).wait_for()
        inspector.get_by_text("2 books", exact=True).wait_for()
        page.get_by_text(
            "Diamonds show consensus market anchors; x-axis ticks show exact sportsbook thresholds for the selected player.",
            exact=True,
        ).wait_for()
        inspector.get_by_text("Explain betting lines", exact=True).click()
        inspector.get_by_text("Consensus anchors", exact=True).wait_for()
        inspector.get_by_text("Exact sportsbook lines", exact=True).wait_for()
        inspector.get_by_text("draftkings", exact=True).wait_for()
        inspector.get_by_text("fanduel", exact=True).wait_for()

        # Cache mode is operational state and must be sent to the API, not just styled locally.
        page.get_by_text("Settings", exact=True).click()
        with page.expect_request(
            lambda request: urlparse(request.url).path == "/projections"
            and parse_qs(urlparse(request.url).query).get("mode") == ["cache"]
        ):
            page.get_by_label("Odds data").select_option("cache")
        ranking.get_by_text("Alpha Runner", exact=True).wait_for()

        # Re-opening setup for an existing identity must not erase the active selection.
        page.get_by_role("button", name="Change league").click()
        setup.wait_for()
        setup.get_by_role("button", name="Close league setup").click()
        setup.wait_for(state="hidden")
        page.get_by_text("Smoke League · Smoke Team", exact=True).wait_for()

        # Defense comparison remains a dense, market-ranked decision table.
        page.get_by_role("button", name="Defenses").click()
        defense_view = page.get_by_role("main", name="Defense analysis")
        defense_view.get_by_text("LAC", exact=True).wait_for()
        first_defense = defense_view.locator("tbody tr").first
        assert "17.3" in first_defense.inner_text()
        assert "Available" in first_defense.inner_text()

        # Best Lineup keeps the canonical optimizer and exposes unsupported slots explicitly.
        page.get_by_role("button", name="Best lineup").click()
        lineup_view = page.get_by_role("main", name="Best lineup")
        lineup_view.get_by_text("Alpha Runner", exact=True).wait_for()
        lineup_view.get_by_role("button", name="Ceiling").click()
        lineup_view.get_by_text("Projected Ceiling", exact=True).wait_for()
        lineup_view.get_by_text("25.0", exact=True).wait_for()
        lineup_view.get_by_text("Not modeled: K.", exact=False).wait_for()

        browser.close()


if __name__ == "__main__":
    main()
