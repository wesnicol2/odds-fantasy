import json
import unittest
from unittest.mock import patch

from oddsfantasy.api import application


def wsgi_get(path: str):
    environ = {
        "REQUEST_METHOD": "GET",
        "PATH_INFO": path.split("?", 1)[0],
        "QUERY_STRING": path.split("?", 1)[1] if "?" in path else "",
        "wsgi.input": None,
        "wsgi.url_scheme": "http",
        "SERVER_NAME": "testserver",
        "SERVER_PORT": "80",
    }
    response = {}

    def start_response(status, headers):
        response["status"] = status
        response["headers"] = headers

    body = b"".join(application(environ, start_response))
    try:
        payload = json.loads(body.decode("utf-8"))
    except Exception:
        payload = None
    return response["status"], dict(response["headers"]), payload


class ApiTestCase(unittest.TestCase):
    def test_health(self):
        status, headers, payload = wsgi_get("/health")
        self.assertTrue(status.startswith("200"))
        self.assertIn("application/json", headers.get("Content-Type", ""))
        self.assertEqual(payload["status"], "ok")

    @patch("oddsfantasy.api.compute_projections")
    def test_projections_passes_explicit_identity(self, mock_projection):
        mock_projection.return_value = {
            "week": "this",
            "players": [{"name": "Test Player", "floor": 10, "mid": 15, "ceiling": 20}],
            "ratelimit": "ok",
        }
        status, _, payload = wsgi_get("/projections?league_id=L1&roster_id=7&week=this")
        self.assertTrue(status.startswith("200"))
        self.assertEqual(payload["players"][0]["name"], "Test Player")
        self.assertEqual(mock_projection.call_args.kwargs["league_id"], "L1")
        self.assertEqual(mock_projection.call_args.kwargs["roster_id"], 7)

    @patch("oddsfantasy.api.list_defenses")
    def test_defenses_endpoint(self, mock_defenses):
        mock_defenses.return_value = {
            "week": "next",
            "defenses": [{"defense": "Buffalo Bills", "implied_total": 17.5}],
        }
        status, _, payload = wsgi_get("/defenses?league_id=L1&roster_id=7&week=next")
        self.assertTrue(status.startswith("200"))
        self.assertEqual(payload["defenses"][0]["implied_total"], 17.5)
        self.assertEqual(mock_defenses.call_args.kwargs["week"], "next")

    @patch("oddsfantasy.api.compute_best_lineup")
    def test_best_lineup_endpoint(self, mock_lineup):
        mock_lineup.return_value = {
            "target": "ceiling",
            "lineup": [{"slot": "QB", "name": "Test QB", "points": 25}],
            "total_points": 25,
        }
        status, _, payload = wsgi_get(
            "/best-lineup?league_id=L1&roster_id=7&week=this&target=ceiling"
        )
        self.assertTrue(status.startswith("200"))
        self.assertEqual(payload["target"], "ceiling")
        self.assertEqual(mock_lineup.call_args.kwargs["target"], "ceiling")

    def test_best_lineup_rejects_unknown_target(self):
        status, _, payload = wsgi_get("/best-lineup?target=average")
        self.assertTrue(status.startswith("400"))
        self.assertEqual(payload["error"], "target_must_be_floor_mid_or_ceiling")

    @patch("oddsfantasy.api.odds_details.get_player_odds_details")
    def test_player_details(self, mock_details):
        mock_details.return_value = {
            "player": {"name": "Test Player"},
            "projection": {"floor": 10, "mid": 15, "ceiling": 20, "curve": []},
            "markets": {},
        }
        status, _, payload = wsgi_get("/player/odds?league_id=L1&roster_id=7&name=Test+Player")
        self.assertTrue(status.startswith("200"))
        self.assertEqual(payload["projection"]["mid"], 15)
        self.assertEqual(mock_details.call_args.kwargs["league_id"], "L1")
        self.assertEqual(mock_details.call_args.kwargs["roster_id"], 7)

    @patch("oddsfantasy.api.resolve_user_leagues")
    def test_user_leagues(self, mock_resolve):
        mock_resolve.return_value = {
            "username": "wesnicol",
            "leagues": [{"league_id": "123", "name": "League"}],
        }
        status, _, payload = wsgi_get("/user/leagues?username=wesnicol&season=2026")
        self.assertTrue(status.startswith("200"))
        self.assertEqual(payload["leagues"][0]["league_id"], "123")

    def test_user_leagues_requires_username(self):
        status, _, _ = wsgi_get("/user/leagues")
        self.assertTrue(status.startswith("400"))

    @patch("oddsfantasy.api.resolve_league")
    def test_league_resolve(self, mock_resolve):
        mock_resolve.return_value = {
            "league_id": "123",
            "name": "League",
            "teams": [{"roster_id": 1, "team_name": "Mine"}],
        }
        status, _, payload = wsgi_get("/league/resolve?league_id=123")
        self.assertTrue(status.startswith("200"))
        self.assertEqual(payload["teams"][0]["roster_id"], 1)

    def test_removed_legacy_endpoint_is_not_found(self):
        for path in ("/lineup", "/draft-board", "/dashboard", "/book-coverage"):
            status, _, _ = wsgi_get(path)
            self.assertTrue(status.startswith("404"), path)

    def test_not_found(self):
        status, _, payload = wsgi_get("/nope")
        self.assertTrue(status.startswith("404"))
        self.assertEqual(payload["error"], "not_found")


if __name__ == "__main__":
    unittest.main()
