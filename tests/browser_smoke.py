"""Headless browser smoke test against the built container.

The container serves the real HTML/CSS/JS. Upstream-data API calls are intercepted
with deterministic fixtures so the test does not spend Odds API quota or depend
on Sleeper availability.
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
    route.fulfill(
        status=status,
        content_type="application/json",
        body=json.dumps(payload),
    )


def api_fixture(route: Route) -> None:
    parsed = urlparse(route.request.url)
    query = parse_qs(parsed.query)
    if parsed.path == "/league/resolve":
        fulfill_json(
            route,
            {
                "league_id": "L1",
                "name": "Smoke League",
                "teams": [{"roster_id": 7, "team_name": "Smoke Team"}],
            },
        )
        return
    if parsed.path == "/projections":
        fulfill_json(
            route,
            {
                "week": query.get("week", ["this"])[0],
                "players": [
                    {
                        "name": "Alpha Runner",
                        "pos": "RB",
                        "team": "Buffalo Bills",
                        "floor": 10,
                        "mid": 17,
                        "ceiling": 25,
                        "has_projection": True,
                        "curve": CURVE_A,
                    },
                    {
                        "name": "Beta Receiver",
                        "pos": "WR",
                        "team": "Miami Dolphins",
                        "floor": 8,
                        "mid": 15,
                        "ceiling": 24,
                        "has_projection": True,
                        "curve": CURVE_B,
                    },
                ],
            },
        )
        return
    if parsed.path == "/player/odds":
        name = query.get("name", ["Alpha Runner"])[0]
        pos = "WR" if name == "Beta Receiver" else "RB"
        team = "Miami Dolphins" if pos == "WR" else "Buffalo Bills"
        curve = CURVE_B if pos == "WR" else CURVE_A
        fulfill_json(
            route,
            {
                "player": {"name": name, "pos": pos, "team": team},
                "projection": {"floor": 10, "mid": 17, "ceiling": 25, "curve": curve},
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
                        "implied_total": 17.25,
                        "book_count": 6,
                        "taken": False,
                        "owner": None,
                        "owned_by_current": False,
                    },
                    {
                        "defense": "Jacksonville Jaguars",
                        "abbr": "JAX",
                        "opponent": "Tennessee Titans",
                        "implied_total": 19.5,
                        "book_count": 5,
                        "taken": True,
                        "owner": "Other Team",
                        "owned_by_current": False,
                    },
                ],
                "note": "DEF fantasy ranges use only the points-allowed component.",
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
            },
        )
        return
    route.continue_()


def main() -> None:
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        context = browser.new_context()
        context.add_cookies(
            [
                {"name": "league_id", "value": "L1", "url": BASE_URL},
                {"name": "roster_id", "value": "7", "url": BASE_URL},
            ]
        )
        page = context.new_page()
        page.route("**/*", api_fixture)
        page.goto(BASE_URL, wait_until="networkidle")

        page.locator("#playerReport").get_by_text("Alpha Runner", exact=True).wait_for()
        assert page.get_by_text("17.00", exact=True).count() >= 1

        page.get_by_role("button", name="Graphs").click()
        page.locator("#graphExplorer").wait_for()
        page.locator(".graph-filter-panel").wait_for()
        graph_area = page.locator("#graphChartArea")
        fantasy_subtitle = page.locator("#graphSubtitle").inner_text()
        assert "x = fantasy points" in fantasy_subtitle
        assert "y = probability within a 1-point scoring bucket" in fantasy_subtitle
        graph_area.get_by_text("full 4,000-sample fantasy-point projection", exact=False).wait_for()
        graph_area.get_by_text("Probability within 1 FP", exact=True).wait_for()
        assert graph_area.locator(".fp-probability-path").count() >= 2
        assert graph_area.locator(".fp-range-guide").count() >= 6
        assert graph_area.locator(".fp-range-marker").count() == 0
        assert "Floor 10.00" in graph_area.inner_text()
        assert "Mid 17.00" in graph_area.inner_text()
        assert "Ceiling 25.00" in graph_area.inner_text()

        page.locator('[data-graph-metric="player_rush_yds"]').wait_for()
        assert page.locator("#graphMetricList .graph-metric-btn").count() >= 2
        page.get_by_role("button", name="Next graph").click()
        assert page.locator("#graphTitle").inner_text() == "Rushing yards"
        subtitle = page.locator("#graphSubtitle").inner_text()
        assert "x = rushing yards threshold" in subtitle
        assert "y = probability at or above threshold" in subtitle
        graph_area.get_by_text("Probability at or above threshold", exact=True).wait_for()
        graph_area.get_by_text("consensus fair probability", exact=True).wait_for()
        assert graph_area.locator(".graph-consensus-marker").count() >= 2
        assert graph_area.locator(".graph-source-tick").count() >= 2
        graph_area.get_by_role("button", name="Explain betting lines").click()
        graph_area.get_by_text("Why this curve has this shape", exact=True).wait_for()
        graph_area.get_by_text("Consensus anchors", exact=True).wait_for()
        graph_area.get_by_text("Exact sportsbook lines", exact=True).wait_for()
        graph_area.get_by_text("draftkings", exact=True).wait_for()
        graph_area.get_by_text("fanduel", exact=True).wait_for()
        page.locator('[data-graph-position="WR"]').uncheck()
        assert "Beta Receiver" not in graph_area.inner_text()
        page.locator("#compareClose").click()

        page.get_by_role("button", name="Alpha Runner").click()
        details_body = page.locator("#detailsBody")
        details_body.get_by_text("Sportsbook lines used").wait_for()
        details_body.get_by_text("projection calculations are unchanged", exact=False).wait_for()
        details_body.get_by_text("draftkings", exact=True).wait_for()
        page.locator("#detailsClose").click()

        page.get_by_role("button", name="Defenses").click()
        page.get_by_text("LAC", exact=True).wait_for()
        first_defense = page.locator("#defenseReport tbody tr").first
        assert "17.25" in first_defense.inner_text()
        assert "Available" in first_defense.inner_text()

        page.get_by_role("button", name="Best lineup").click()
        page.locator("#lineupReport").get_by_text("Alpha Runner", exact=True).wait_for()
        page.get_by_role("button", name="Ceiling").click()
        page.get_by_text("Projected ceiling:", exact=False).wait_for()
        assert "25.00" in page.locator("#lineupReport").inner_text()
        assert "Not modeled: K." in page.locator("#lineupStatus").inner_text()

        browser.close()


if __name__ == "__main__":
    main()
