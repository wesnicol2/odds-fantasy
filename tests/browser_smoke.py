"""Headless browser smoke test against the built production container.

The container serves the real React/Vite bundle. Application-data API calls are
intercepted with deterministic fixtures so the smoke test does not spend Odds
API quota or depend on Sleeper availability.
"""

from __future__ import annotations

import json
import os
import re
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
    "kind": "continuous_density",
    "points": [
        {"x": 40, "probability": 0.003},
        {"x": 60, "probability": 0.009},
        {"x": 80, "probability": 0.013},
        {"x": 100, "probability": 0.008},
        {"x": 120, "probability": 0.002},
    ],
}
RECEIVING_GRAPH = {
    "kind": "continuous_density",
    "points": [
        {"x": 20, "probability": 0.004},
        {"x": 40, "probability": 0.011},
        {"x": 55, "probability": 0.014},
        {"x": 75, "probability": 0.007},
        {"x": 95, "probability": 0.002},
    ],
}
INTERCEPTIONS_GRAPH = {
    "kind": "threshold_gauge",
    "points": [
        {"x": 1, "probability": 0.55},
        {"x": 2, "probability": 0.22},
    ],
}
RECEPTIONS_GRAPH = {
    "kind": "discrete_pmf",
    "points": [
        {"x": 0, "probability": 0.02},
        {"x": 1, "probability": 0.08},
        {"x": 2, "probability": 0.16},
        {"x": 3, "probability": 0.24},
        {"x": 4, "probability": 0.23},
        {"x": 5, "probability": 0.16},
        {"x": 6, "probability": 0.08},
        {"x": 7, "probability": 0.03},
    ],
}
ANYTIME_TD_GRAPH = {
    "kind": "threshold_gauge",
    "points": [
        {"x": 1, "probability": 0.62},
        {"x": 2, "probability": 0.20},
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
        "markets_used": 3,
        "has_projection": True,
    }


def market_lines(point_a: float, point_b: float) -> list[dict]:
    return [
        {
            "book": "draftkings",
            "source": "main",
            "point": point_a,
            "over_odds": 1.91,
            "under_odds": 1.91,
        },
        {
            "book": "fanduel",
            "source": "alternate",
            "point": point_b,
            "over_odds": 2.10,
            "under_odds": 1.72,
        },
    ]


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
                    projection_player("Alpha Runner", "RB", "Buffalo Bills", 10, 17, 25, CURVE_A),
                    projection_player("Beta Receiver", "WR", "Miami Dolphins", 8, 15, 24, CURVE_B),
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
        floor, mid, ceiling = (8, 15, 24) if is_receiver else (10, 17, 25)
        mean = mid + 0.5
        fulfill_json(
            route,
            {
                "player": {"name": name, "pos": pos, "team": team},
                "projection": {
                    "floor": floor,
                    "mid": mid,
                    "ceiling": ceiling,
                    "mean": mean,
                    "curve": curve,
                },
                "matchup": {
                    "opponent": "New England Patriots" if is_receiver else "New York Jets",
                    "venue": "away" if is_receiver else "home",
                    "commence_time": "2026-09-13T17:00:00Z",
                    "game_total": 44 if is_receiver else 48,
                    "team_spread": 2 if is_receiver else -3,
                    "team_implied_total": 21 if is_receiver else 25.5,
                    "books_used": 6,
                },
                "markets": {
                    # The back is priced for rushing, the receiver is not: the
                    # exact mismatch the combined yardage row exists to fix.
                    **(
                        {}
                        if is_receiver
                        else {
                            "player_rush_yds": {
                                "stat_range": [45, 75, 115],
                                "stat_mean": 78.4,
                                "expected_points": 12.3,
                                "graph": RUSH_GRAPH,
                                "anchors": [
                                    {"threshold": 64.5, "survival": 0.68},
                                    {"threshold": 84.5, "survival": 0.39},
                                ],
                                "lines": market_lines(64.5, 84.5),
                            }
                        }
                    ),
                    "player_reception_yds": {
                        "stat_range": [30, 52, 85] if is_receiver else [5, 15, 30],
                        "stat_mean": 55.2 if is_receiver else 16.1,
                        "expected_points": 11.8 if is_receiver else 1.5,
                        "graph": RECEIVING_GRAPH,
                        "anchors": [
                            {"threshold": 44.5, "survival": 0.61},
                            {"threshold": 60.5, "survival": 0.34},
                        ],
                        "lines": market_lines(44.5, 60.5),
                    },
                    "player_receptions": {
                        "stat_range": [4, 7, 10] if is_receiver else [2, 4, 6],
                        "stat_mean": 6.8 if is_receiver else 4.1,
                        "expected_points": 0.0,
                        "graph": RECEPTIONS_GRAPH,
                        "anchors": [
                            {"threshold": 3.5, "survival": 0.58},
                            {"threshold": 4.5, "survival": 0.35},
                        ],
                        "lines": market_lines(3.5, 4.5),
                    },
                    # A negatively scored market, so the matrix must flag the
                    # player carrying more of it rather than the one with less.
                    "player_pass_interceptions": {
                        "stat_range": [0, 1, 2] if is_receiver else [0, 0, 1],
                        "stat_mean": 1.1 if is_receiver else 0.4,
                        "expected_points": -1.5 if is_receiver else -0.5,
                        "graph": INTERCEPTIONS_GRAPH,
                        "anchors": [
                            {"threshold": 0.5, "survival": 0.55},
                            {"threshold": 1.5, "survival": 0.22},
                        ],
                        "lines": market_lines(0.5, 1.5),
                    },
                    "player_anytime_td": {
                        "stat_range": [0, 1, 2],
                        "stat_mean": 0.9,
                        "expected_points": 3.7,
                        "graph": ANYTIME_TD_GRAPH,
                        "anchors": [
                            {"threshold": 0.0, "survival": 0.62},
                            {"threshold": 2.0, "survival": 0.20},
                        ],
                        "lines": market_lines(0.0, 2.0),
                    },
                },
                # Percentiles are not additive, so the backend samples the
                # combined yardage range instead of adding the components.
                "combined_markets": {
                    "rush_reception_yds": {
                        "markets": (
                            ["player_reception_yds"]
                            if is_receiver
                            else ["player_rush_yds", "player_reception_yds"]
                        ),
                        "stat_range": [30, 52, 85] if is_receiver else [58, 91, 130],
                        "stat_mean": 55.2 if is_receiver else 94.5,
                        "expected_points": 11.8 if is_receiver else 13.8,
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
                        "book_count": 2,
                        "taken": False,
                        "owner": None,
                        "owned_by_current": False,
                        "floor": 4.0,
                        "mid": 7.0,
                        "ceiling": 10.0,
                        # Every derived number ships with the inputs behind it.
                        "implied_books": [
                            {
                                "book": "draftkings",
                                "game_total": 42.5,
                                "opponent_spread": 8.0,
                                "implied_total": 17.25,
                            },
                            {
                                "book": "fanduel",
                                "game_total": 43.5,
                                "opponent_spread": 9.0,
                                "implied_total": 17.25,
                            },
                        ],
                        "range_breakdown": {
                            "opponent_mean": 17.25,
                            "sigma": 10.0,
                            "floor": {
                                "opponent_points": 30.06,
                                "percentile": 0.9,
                                "bracket": "pts_allow_28_34",
                                "bracket_label": "28-34",
                                "points": 4.0,
                            },
                            "ceiling": {
                                "opponent_points": 4.44,
                                "percentile": 0.1,
                                "bracket": "pts_allow_1_6",
                                "bracket_label": "1-6",
                                "points": 10.0,
                            },
                            "mid": {
                                "points": 7.0,
                                "brackets": [
                                    {
                                        "bracket": "pts_allow_1_6",
                                        "bracket_label": "1-6",
                                        "probability": 0.1,
                                        "points": 10.0,
                                        "contribution": 1.0,
                                    },
                                    {
                                        "bracket": "pts_allow_7_13",
                                        "bracket_label": "7-13",
                                        "probability": 0.3,
                                        "points": 4.0,
                                        "contribution": 1.2,
                                    },
                                    {
                                        "bracket": "pts_allow_14_20",
                                        "bracket_label": "14-20",
                                        "probability": 0.6,
                                        "points": 8.0,
                                        "contribution": 4.8,
                                    },
                                ],
                            },
                        },
                    },
                    {
                        "defense": "Jacksonville Jaguars",
                        "abbr": "JAX",
                        "opponent": "Tennessee Titans",
                        "game_date": "2026-09-13T17:00:00Z",
                        "implied_total": 19.5,
                        "book_count": 2,
                        "taken": True,
                        "owner": "Other Team",
                        "owned_by_current": False,
                        "floor": 3.0,
                        "mid": 6.0,
                        "ceiling": 9.0,
                        "implied_books": [
                            {
                                "book": "draftkings",
                                "game_total": 45.0,
                                "opponent_spread": 6.0,
                                "implied_total": 19.5,
                            },
                            {
                                "book": "fanduel",
                                "game_total": 46.0,
                                "opponent_spread": 7.0,
                                "implied_total": 19.5,
                            },
                        ],
                        "range_breakdown": None,
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
                "bench_pressure": [
                    {
                        "name": "Beta Receiver",
                        "pos": "WR",
                        "team": "Miami Dolphins",
                        "points": 15,
                        "delta_to_lineup": 2,
                        "slot": "WR",
                        "displaces": "Alpha Runner",
                        "displaces_slot": "RB",
                    }
                ],
                "unmodeled_slots": ["K"],
                "unfilled_slots": [],
                "defense_note": "DEF ranges use only the points-allowed component.",
                "ratelimit": "Odds API · 499 remaining",
            },
        )
        return

    route.continue_()


def alpha_of(style: str) -> float:
    """Alpha channel of an rgba() background declared in an inline style."""
    match = re.search(r"rgba\([^)]*,\s*([0-9.]+)\s*\)", style)
    return float(match.group(1)) if match else 0.0


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

        # Dashboard is the low-noise landing page: current lineup, bench pressure, two-week DEF plan.
        dashboard = page.get_by_role("main", name="Dashboard")
        dashboard.get_by_text("Lineup & pickups", exact=True).wait_for()
        dashboard.get_by_text("Alpha Runner", exact=True).wait_for()
        dashboard.get_by_text("Beta Receiver", exact=True).wait_for()
        dashboard.get_by_text("2.0", exact=True).wait_for()
        assert dashboard.get_by_text("LAC", exact=True).count() == 2

        # A close bench call opens the optimizer-paired, side-by-side start/sit explanation.
        dashboard.get_by_role(
            "button", name="Compare Beta Receiver with Alpha Runner", exact=True
        ).click()
        assert "view=players" in page.url
        assert "week=this" in page.url

        inspector = page.get_by_role("complementary", name="Player inspector")
        inspector.get_by_text("This week\u2019s tie-breaker matrix", exact=True).wait_for()

        def pane_order() -> list[str]:
            return page.locator(".workspace > *").evaluate_all(
                "nodes => nodes.map((node) => node.getAttribute('aria-label'))"
            )

        # Comparing leads with the decision: matrix, then chart, then the ranking checkboxes.
        assert pane_order() == ["Player inspector", "Probability analysis", "Player ranking"]
        inspector.get_by_text("Start Alpha Runner", exact=True).wait_for()
        inspector.get_by_text(
            "Beta Receiver is 2.0 lineup FP back after re-optimizing every eligible slot.",
            exact=True,
        ).wait_for()
        # Fantasy-point and stat-value signals are tallied separately, never merged.
        inspector.get_by_text(
            "Alpha Runner leads 8\u20130 across 10 comparable fantasy-point signals", exact=True
        ).wait_for()
        inspector.get_by_text(
            "Alpha Runner leads 2\u20131 across 4 comparable stat-value signals", exact=True
        ).wait_for()
        matrix = inspector.get_by_role("table", name="Weekly player comparison matrix")
        assert "Beta Receiver" in matrix.inner_text()
        assert "Alpha Runner" in matrix.inner_text()
        assert "Team implied total" in matrix.inner_text()
        assert "25.5 pts" in matrix.inner_text()

        # The matrix is numbers only: no glyphs, and no drawn edge chips.
        assert matrix.locator(".range-glyph").count() == 0
        # Floor / Median / Ceiling are their own rows, so no combined range row repeats them.
        assert "Fantasy point range" not in matrix.inner_text()
        # An unscored row is never shaded.
        kickoff_row = matrix.locator("tbody tr").filter(has_text="Kickoff")
        assert not any(
            "background-color"
            in (kickoff_row.locator("td").nth(index).get_attribute("style") or "")
            for index in (0, 1)
        )

        # A back and a pass catcher earn yardage in different markets, so RB vs WR
        # compares their summed yardage instead of two half-empty rows.
        assert "Rushing + receiving yards" in matrix.inner_text()
        assert "Rushing yards" not in matrix.inner_text()
        assert "Receiving yards" not in matrix.inner_text()
        combined_rows = matrix.locator("tbody tr").filter(has_text="Rushing + receiving yards")
        assert combined_rows.count() == 2
        # A summed row has no single fitted distribution, so it is not a drill-down.
        assert combined_rows.locator("button").count() == 0
        combined_points_row = matrix.locator("tbody tr").filter(has_text="+11.8 FP")
        assert "+13.8 FP" in combined_points_row.inner_text()

        # Stat value is measured on its own scale, with all three percentiles present.
        # Group headings render uppercase, so compare case-insensitively.
        assert "STAT VALUE \u00b7 WEEKLY MEAN" in matrix.inner_text().upper()
        # One number per stat, in the stat's own unit, not a three-part range.
        combined_value_row = matrix.locator("tbody tr").filter(has_text="94.5")
        assert "55.2" in combined_value_row.inner_text()
        assert "\u00b7" not in combined_value_row.locator("td").first.inner_text()

        def shade(row, index: int) -> str:
            return row.locator("td").nth(index).get_attribute("style") or ""

        # A rewarded stat tints the leader green; the gap here is wide, so it is strong.
        combined_shade = shade(combined_value_row, 1)
        assert "75, 200, 131" in combined_shade, combined_shade
        assert not shade(combined_value_row, 0)
        receptions_value_row = matrix.locator("tbody tr").filter(has_text="6.8")
        assert "75, 200, 131" in shade(receptions_value_row, 0)
        # A wider relative gap must read stronger than a narrow one.
        floor_row = matrix.locator("tbody tr").filter(has_text="8.0 FP")
        assert alpha_of(shade(combined_value_row, 1)) > alpha_of(shade(floor_row, 1))
        # Identical stat ranges award neither player a stat-value win, so neither is tinted.
        anytime_value_row = matrix.locator("tbody tr").filter(has_text="0.9")
        assert not shade(anytime_value_row, 0)
        assert not shade(anytime_value_row, 1)

        # A punished stat flags the player carrying more of it, in red, on both
        # the points row and the stat-value row.
        interception_rows = matrix.locator("tbody tr").filter(has_text="Interceptions")
        assert interception_rows.count() == 2
        for index in range(2):
            row = interception_rows.nth(index)
            assert "214, 92, 92" in shade(row, 0), shade(row, 0)
            assert not shade(row, 1)

        # Un-merged markets keep both drill-downs.
        matrix.get_by_role("button", name="Compare Receptions stat values", exact=True).click()
        receptions_comparison = inspector.get_by_role("region", name="Receptions comparison")
        receptions_comparison.get_by_text("Receptions comparison", exact=True).wait_for()
        # The drill-down keeps the percentile numbers and drops the glyph with them.
        assert "Stat value range" not in receptions_comparison.inner_text()
        assert receptions_comparison.locator(".range-glyph").count() == 0
        inspector.get_by_role("button", name="Full matrix", exact=True).click()
        matrix.get_by_role("button", name="Compare Receptions distributions", exact=True).click()
        receptions_comparison.get_by_text("Receptions comparison", exact=True).wait_for()
        inspector.get_by_role("button", name="Full matrix", exact=True).click()
        inspector.get_by_role("button", name="Exit comparison", exact=True).click()

        # Exiting restores the normal ranking/chart/inspector workstation order.
        assert pane_order() == ["Player ranking", "Probability analysis", "Player inspector"]

        primary_nav = page.get_by_role("navigation", name="Primary navigation")

        # Players remains one linked ranking/chart/inspector workspace.
        ranking = page.get_by_role("complementary", name="Player ranking")
        ranking.get_by_text("Alpha Runner", exact=True).wait_for()
        alpha_row = ranking.locator("tbody tr").filter(has_text="Alpha Runner").first
        assert "10.0" in alpha_row.inner_text()
        assert "17.0" in alpha_row.inner_text()
        assert "25.0" in alpha_row.inner_text()
        alpha_row.locator(".player-name-button").click()
        chart = page.locator(".probability-chart")
        chart.wait_for()
        assert chart.get_attribute("role") == "img"
        assert (chart.get_attribute("aria-label") or "").strip()

        target_input = page.get_by_label("Target FP")
        target_input.fill("20")
        inspector.get_by_text("Chance of ≥ 20.0 FP", exact=True).wait_for()
        inspector.get_by_text("50%", exact=True).wait_for()
        assert "≥ 20.0" in ranking.locator("thead").inner_text()

        # Mean fantasy points expose exact additive stat sources and drill into the chosen stat.
        inspector.get_by_text("Mean point sources", exact=True).wait_for()
        inspector.get_by_role("button", name="Analyze Rushing yards, +12.3 FP").click()

        # Continuous stat exploration uses probability density and keeps evidence inspectable.
        inspector.get_by_text("Rushing yards evidence", exact=True).wait_for()
        inspector.get_by_text("+12.3 FP", exact=True).wait_for()
        inspector.get_by_text("2 consensus thresholds", exact=True).wait_for()
        inspector.get_by_text("2 source lines", exact=True).wait_for()
        inspector.get_by_text("2 books", exact=True).wait_for()
        page.get_by_text(
            "Exact sportsbook thresholds are marked on the x-axis. Consensus P(≥x) anchors remain in the inspector because this chart shows P(x).",
            exact=True,
        ).wait_for()
        chart.wait_for()
        assert chart.get_attribute("data-chart-kind") == "continuous_density"
        inspector.get_by_text("Explain betting lines", exact=True).click()
        inspector.get_by_text("Consensus anchors", exact=True).wait_for()
        inspector.get_by_text("Exact sportsbook lines", exact=True).wait_for()
        inspector.get_by_text("draftkings", exact=True).wait_for()
        inspector.get_by_text("fanduel", exact=True).wait_for()
        inspector.get_by_role("button", name="All point sources").click()
        inspector.get_by_role("button", name="Analyze Receptions, 0.0 FP").click()

        # High-granularity discrete stats show exact P(X=x) with smoothed connecting lines.
        page.get_by_text(
            "Chance of each exact receptions value; the line is smoothed only between integer outcomes.",
            exact=True,
        ).wait_for()
        chart.wait_for()
        assert chart.get_attribute("data-chart-kind") == "discrete_pmf"

        # Low-granularity discrete stats use threshold thermometers with P(X>=x).
        page.get_by_role("button", name="Anytime TD").click()
        gauge_chart = page.locator(".threshold-gauge-chart")
        gauge_chart.wait_for()
        gauge_chart.get_by_text("1+", exact=True).wait_for()
        gauge_chart.get_by_text("2+", exact=True).wait_for()
        assert gauge_chart.get_attribute("data-chart-kind") == "threshold_gauge"
        assert gauge_chart.evaluate("element => element.tagName") == "FIELDSET"
        gauge_chart.get_by_role("button", name="Alpha Runner 1 or more: 62%", exact=True).wait_for()

        # Cache mode is operational state and must be sent to the API, not just styled locally.
        page.get_by_text("Settings", exact=True).click()
        with page.expect_request(
            lambda request: (
                urlparse(request.url).path == "/projections"
                and parse_qs(urlparse(request.url).query).get("mode") == ["cache"]
            )
        ):
            page.get_by_label("Odds data").select_option("cache")
        ranking.get_by_text("Alpha Runner", exact=True).wait_for()

        # Re-opening setup for an existing identity must not erase the active selection.
        page.get_by_role("button", name="Change league").click()
        assert page.locator("details.app-settings").get_attribute("open") is None
        setup.wait_for()
        setup.get_by_role("button", name="Close league setup").click()
        setup.wait_for(state="hidden")
        page.get_by_text("Smoke League · Smoke Team", exact=True).wait_for()

        # Defense comparison remains a dense, market-ranked drill-down.
        primary_nav.get_by_role("button", name="Defenses", exact=True).click()
        defense_view = page.get_by_role("main", name="Defense analysis")
        defense_view.get_by_text("LAC", exact=True).wait_for()
        first_defense = defense_view.locator("tbody tr").first
        assert "17.3" in first_defense.inner_text()
        assert "Available" in first_defense.inner_text()

        # Every ranked number opens the arithmetic that produced it.
        defense_view.get_by_role(
            "button", name="Explain Los Angeles Chargers opponent implied total 17.3", exact=True
        ).click()
        detail = page.get_by_role("complementary", name="Defense detail")
        detail.get_by_text("Los Angeles Chargers", exact=True).wait_for()
        implied_explain = detail.get_by_role("region", name="Opponent implied total derivation")
        implied_explain.get_by_text(
            "implied total = game total \u00f7 2 \u2212 opponent spread \u00f7 2", exact=True
        ).wait_for()
        book_table = implied_explain.get_by_role(
            "table", name="Opponent implied total by sportsbook"
        )
        # The book rows are the rows the median was actually taken over.
        assert book_table.locator("tbody tr").count() == 2
        draftkings_row = book_table.locator("tbody tr").filter(has_text="draftkings")
        assert "42.5" in draftkings_row.inner_text()
        assert "+8.0" in draftkings_row.inner_text()
        implied_explain.get_by_text("Median of 2 books = 17.3", exact=True).wait_for()

        # Mid is a probability-weighted sum, and the shown parts add to the shown total.
        detail.get_by_role("button", name="Mid").first.click()
        mid_explain = detail.get_by_role("region", name="Mid derivation")
        bracket_table = mid_explain.get_by_role("table", name="Mid by points-allowed bracket")
        assert bracket_table.locator("tbody tr").count() == 3
        assert "14-20" in bracket_table.inner_text()
        assert "60.0%" in bracket_table.inner_text()
        mid_explain.get_by_text("Sum of contributions = 7.0", exact=True).wait_for()

        # Floor reads a single bracket at the high opponent percentile.
        detail.get_by_role("button", name="Floor").first.click()
        floor_explain = detail.get_by_role("region", name="Floor derivation")
        floor_explain.get_by_text("Opponent points at the 90th percentile", exact=True).wait_for()
        floor_explain.get_by_text("30.1", exact=True).wait_for()
        floor_explain.get_by_text("Floor = 4.0", exact=True).wait_for()

        detail.get_by_role("button", name="Close", exact=True).click()
        assert page.get_by_role("complementary", name="Defense detail").count() == 0

        # Lineup remains the detailed optimizer and exposes unsupported slots explicitly.
        primary_nav.get_by_role("button", name="Lineup", exact=True).click()
        lineup_view = page.get_by_role("main", name="Best lineup")
        lineup_view.get_by_text("Alpha Runner", exact=True).wait_for()
        lineup_view.get_by_role("button", name="Ceiling").click()
        lineup_view.get_by_text("Projected Ceiling", exact=True).wait_for()
        assert "25.0" in lineup_view.inner_text()
        lineup_view.get_by_text("Not modeled: K.", exact=False).wait_for()

        # Browser history restores the previous section/week context without a reload.
        page.go_back()
        defense_view.get_by_text("LAC", exact=True).wait_for()

        browser.close()


if __name__ == "__main__":
    main()
