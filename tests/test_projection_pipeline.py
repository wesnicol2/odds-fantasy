"""End-to-end: roster + book odds -> projections, through the default model.

The unit tests check each step against the methodology doc's numbers. This one
checks that the steps are actually wired to each other -- planner, aggregator,
market_math, scoring and projection -- and that /projections defaults to the
engine that implements the doc.
"""

import datetime as dt
import unittest
from unittest.mock import patch

from oddsfantasy import services


def _next_sunday() -> dt.datetime:
    """A fantasy week is Thursday 00:00 -> Monday 23:59 UTC, so a fixture game
    has to land on a real slate day or every window lookup misses it."""
    now = dt.datetime.utcnow().replace(hour=17, minute=0, second=0, microsecond=0)
    return now + dt.timedelta(days=(6 - now.weekday()) % 7 or 7)


FUTURE_GAME = _next_sunday()

EVENT = {
    "id": "evt1",
    "home_team": "Buffalo Bills",
    "away_team": "Miami Dolphins",
    "commence_time": FUTURE_GAME.strftime("%Y-%m-%dT%H:%M:%SZ"),
}

ROSTER = {
    "scoring_rules": {
        "rush_yd": 0.1,
        "rush_td": 6,
        "rec": 0.5,
        "rec_yd": 0.1,
        "bonus_rush_yd_100": 5,
        "bonus_rec_yd_100": 5,
    },
    "players": {
        "1": {
            "name": {"full": "James Cook"},
            "primary_position": "RB",
            "editorial_team_full_name": "Buffalo Bills",
        }
    },
}


def outcome(name, price, point=None, description="James Cook"):
    row = {"name": name, "price": price, "description": description}
    if point is not None:
        row["point"] = point
    return row


EVENT_ODDS = [
    {
        "id": "evt1",
        "bookmakers": [
            {
                "key": "draftkings",
                "markets": [
                    {
                        "key": "player_rush_yds",
                        "outcomes": [
                            outcome("Over", 1.87, 74.5),
                            outcome("Under", 1.95, 74.5),
                        ],
                    },
                    {
                        "key": "player_rush_yds_alternate",
                        "outcomes": [
                            outcome("Over", 1.22, 40),
                            outcome("Under", 4.3, 40),
                            outcome("Over", 2.45, 100),
                            outcome("Under", 1.57, 100),
                        ],
                    },
                    {
                        "key": "player_receptions",
                        "outcomes": [
                            outcome("Over", 1.83, 3.5),
                            outcome("Under", 1.98, 3.5),
                        ],
                    },
                    {
                        "key": "player_anytime_td",
                        "outcomes": [outcome("Yes", 2.2), outcome("No", 1.7)],
                    },
                ],
            },
            {
                "key": "fanduel",
                "markets": [
                    {
                        "key": "player_rush_yds",
                        "outcomes": [
                            outcome("Over", 1.91, 77.5),
                            outcome("Under", 1.91, 77.5),
                        ],
                    }
                ],
            },
        ],
    }
]


class ProjectionPipelineTest(unittest.TestCase):
    def _run(self, **kwargs):
        with (
            patch("oddsfantasy.services.odds_client.get_nfl_events", return_value=[EVENT]),
            patch("oddsfantasy.services._resolve_identity", return_value=ROSTER),
            patch(
                "oddsfantasy.planner.odds_client.get_nfl_events",
                return_value=[EVENT],
            ),
            patch(
                "oddsfantasy.services._fetch_odds",
                return_value={"this": {"evt1": EVENT_ODDS}},
            ),
        ):
            return services.compute_projections(
                username="wesnicol", season="2026", week="this", fresh=True, **kwargs
            )

    def test_projects_the_rostered_player(self):
        result = self._run()
        players = result["players"]
        self.assertEqual([p["name"] for p in players], ["James Cook"])

    def test_floor_mid_ceiling_are_ordered_and_non_trivial(self):
        player = self._run()["players"][0]
        self.assertLess(player["floor"], player["mid"])
        self.assertLess(player["mid"], player["ceiling"])
        self.assertGreater(player["floor"], 0.0)

    def test_default_model_is_the_methodology_engine(self):
        default = self._run()["players"][0]
        explicit = self._run(model="market")["players"][0]
        self.assertEqual(
            (default["floor"], default["mid"], default["ceiling"]),
            (explicit["floor"], explicit["mid"], explicit["ceiling"]),
        )

    def test_ppr_value_flows_through_from_league_config(self):
        ppr = self._run()["players"][0]
        with patch.dict(ROSTER["scoring_rules"], {"rec": 0.0}):
            non_ppr = self._run()["players"][0]
        self.assertGreater(ppr["mid"], non_ppr["mid"])

    def test_older_models_still_run_through_the_same_pipeline(self):
        for model in ("baseline", "const", "puelz", "angelini"):
            player = self._run(model=model)["players"][0]
            self.assertLessEqual(player["floor"], player["ceiling"], msg=model)


if __name__ == "__main__":
    unittest.main()
