import json
import os
import sys
import unittest
from unittest.mock import patch

# Ensure project root is on sys.path so 'refactored' can be imported when tests
# are executed from the tests/ directory or other working dirs.
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from refactored.api import application


def wsgi_get(path: str):
    """Call the WSGI app with a simple GET request and return (status, headers, body_json)."""
    environ = {
        "REQUEST_METHOD": "GET",
        "PATH_INFO": path.split("?", 1)[0],
        "QUERY_STRING": (path.split("?", 1)[1] if "?" in path else ""),
        "wsgi.input": None,
        "wsgi.url_scheme": "http",
        "SERVER_NAME": "testserver",
        "SERVER_PORT": "80",
    }
    resp = {}

    def start_response(status, headers):
        resp["status"] = status
        resp["headers"] = headers

    body_chunks = application(environ, start_response)
    body = b"".join(body_chunks)
    try:
        payload = json.loads(body.decode("utf-8"))
    except Exception:
        payload = None
    return resp["status"], dict(resp["headers"]), payload


class ApiTestCase(unittest.TestCase):
    def test_health(self):
        status, headers, payload = wsgi_get("/health")
        self.assertTrue(status.startswith("200"))
        self.assertIn("application/json", headers.get("Content-Type", ""))
        self.assertEqual(payload.get("status"), "ok")

    @patch("refactored.api.compute_projections")
    def test_projections(self, mock_proj):
        mock_proj.return_value = {
            "week": "this",
            "players": [
                {
                    "name": "Test Player",
                    "pos": "WR",
                    "team": "X",
                    "floor": 1.1,
                    "mid": 2.2,
                    "ceiling": 3.3,
                    "books_used": 3,
                    "markets_used": 2,
                }
            ],
            "ratelimit": "remaining=100%",
        }
        status, headers, payload = wsgi_get("/projections?username=u&season=2025&week=this")
        self.assertTrue(status.startswith("200"))
        self.assertIsInstance(payload.get("players"), list)
        self.assertEqual(payload["players"][0]["name"], "Test Player")
        self.assertIn("ratelimit", payload)

    @patch("refactored.api.compute_book_coverage")
    def test_book_coverage(self, mock_cov):
        mock_cov.return_value = {
            "week": "this",
            "coverage": {
                "markets": ["player_anytime_td"],
                "rows": [
                    {
                        "name": "Test Player",
                        "pos": "WR",
                        "team": "BUF",
                        "alias": "test",
                        "markets": {"player_anytime_td": 3},
                        "total_books": 3,
                        "incomplete": False,
                    }
                ],
            },
            "ratelimit": "remaining=88%",
        }
        status, headers, payload = wsgi_get("/book-coverage?username=u&season=2025&week=this")
        self.assertTrue(status.startswith("200"))
        self.assertIn("coverage", payload)
        self.assertIsInstance(payload.get("coverage", {}).get("rows", []), list)

    @patch("refactored.api.list_defenses")
    @patch("refactored.api.build_lineup")
    @patch("refactored.api.compute_projections")
    def test_lineup(self, mock_proj, mock_build, mock_defs):
        mock_proj.return_value = {
            "players": [{"name": "QB A", "pos": "QB", "mid": 18.0}],
            "ratelimit": "remaining=90%",
        }
        mock_defs.return_value = {"defenses": []}
        mock_build.return_value = {
            "target": "mid",
            "lineup": [{"slot": "QB", "name": "QB A", "pos": "QB", "points": 18.0}],
            "total_points": 18.0,
        }
        status, headers, payload = wsgi_get("/lineup?username=u&season=2025&week=this&target=mid")
        self.assertTrue(status.startswith("200"))
        self.assertEqual(payload["target"], "mid")
        self.assertGreaterEqual(len(payload["lineup"]), 1)
        # Defenses are looked up scoped to the caller's own roster only
        self.assertEqual(mock_defs.call_args.kwargs.get("scope"), "owned")

    @patch("refactored.api.list_defenses")
    @patch("refactored.api.build_lineup_diffs")
    @patch("refactored.api.compute_projections")
    def test_lineup_diffs(self, mock_proj, mock_diffs, mock_defs):
        mock_proj.return_value = {"players": [], "ratelimit": "remaining=80%"}
        mock_defs.return_value = {"defenses": []}
        mock_diffs.return_value = {
            "from": {"lineup": []},
            "floor_changes": [{"slot": "FLEX", "from": "X", "to": "Y"}],
            "ceiling_changes": [],
        }
        status, headers, payload = wsgi_get("/lineup/diffs?username=u&season=2025&week=this")
        self.assertTrue(status.startswith("200"))
        self.assertIn("floor_changes", payload)

    @patch("refactored.api.list_defenses")
    def test_defenses(self, mock_defs):
        mock_defs.return_value = {
            "week": "this",
            "defenses": [
                {
                    "defense": "Buffalo Bills",
                    "opponent": "NY Jets",
                    "implied_total_median": 20.5,
                    "book_count": 5,
                    "source": "owned",
                }
            ],
            "ratelimit": "remaining=75%",
        }
        status, headers, payload = wsgi_get("/defenses?username=u&season=2025&week=this&scope=both")
        self.assertTrue(status.startswith("200"))
        self.assertIsInstance(payload.get("defenses"), list)

    @patch("refactored.api.compute_draft_board")
    def test_draft_board(self, mock_board):
        mock_board.return_value = {
            "week": "this",
            "players": [
                {
                    "name": "Josh Allen",
                    "pos": "QB",
                    "team": "Buffalo Bills",
                    "floor": 15.0,
                    "mid": 20.0,
                    "ceiling": 26.0,
                },
            ],
            "ratelimit": "remaining=95%",
        }
        status, headers, payload = wsgi_get(
            "/draft-board?username=u&season=2025&week=this&positions=QB,RB"
        )
        self.assertTrue(status.startswith("200"))
        self.assertIsInstance(payload.get("players"), list)
        self.assertEqual(payload["players"][0]["name"], "Josh Allen")
        # positions query param should be parsed into a list and passed through
        self.assertEqual(mock_board.call_args.kwargs.get("positions"), ["QB", "RB"])

    @patch("refactored.api.resolve_user_leagues")
    def test_user_leagues(self, mock_resolve):
        mock_resolve.return_value = {
            "username": "wesnicol",
            "user_id": "u1",
            "season": "2026",
            "leagues": [
                {"league_id": "123", "name": "My League", "status": "pre_draft", "season": "2026"}
            ],
        }
        status, headers, payload = wsgi_get("/user/leagues?username=wesnicol&season=2026")
        self.assertTrue(status.startswith("200"))
        self.assertEqual(len(payload["leagues"]), 1)

    def test_user_leagues_requires_username(self):
        status, headers, payload = wsgi_get("/user/leagues")
        self.assertTrue(status.startswith("400"))

    @patch("refactored.api.resolve_user_leagues")
    def test_user_leagues_not_found(self, mock_resolve):
        mock_resolve.return_value = {"error": "user_not_found", "username": "nobody"}
        status, headers, payload = wsgi_get("/user/leagues?username=nobody")
        self.assertTrue(status.startswith("404"))

    @patch("refactored.api.resolve_league")
    def test_league_resolve(self, mock_resolve):
        mock_resolve.return_value = {
            "league_id": "123",
            "name": "My League",
            "season": "2026",
            "status": "pre_draft",
            "teams": [
                {"roster_id": 1, "owner_id": "u1", "team_name": "Alice", "display_name": "Alice"}
            ],
        }
        status, headers, payload = wsgi_get("/league/resolve?league_id=123")
        self.assertTrue(status.startswith("200"))
        self.assertEqual(payload["status"], "pre_draft")
        self.assertEqual(len(payload["teams"]), 1)

    def test_league_resolve_requires_league_id(self):
        status, headers, payload = wsgi_get("/league/resolve")
        self.assertTrue(status.startswith("400"))

    @patch("refactored.api.resolve_league")
    def test_league_resolve_not_found(self, mock_resolve):
        mock_resolve.return_value = {"error": "league_not_found", "league_id": "bogus"}
        status, headers, payload = wsgi_get("/league/resolve?league_id=bogus")
        self.assertTrue(status.startswith("404"))

    @patch("refactored.api.list_defenses")
    @patch("refactored.api.build_lineup")
    @patch("refactored.api.compute_projections")
    def test_lineup_passes_league_id_and_roster_id_through(self, mock_proj, mock_build, mock_defs):
        mock_proj.return_value = {"players": [], "ratelimit": "remaining=90%"}
        mock_defs.return_value = {"defenses": []}
        mock_build.return_value = {"target": "mid", "lineup": [], "total_points": 0}
        wsgi_get("/lineup?league_id=LEAGUE123&roster_id=5&week=this&target=mid")
        self.assertEqual(mock_proj.call_args.kwargs.get("league_id"), "LEAGUE123")
        self.assertEqual(mock_proj.call_args.kwargs.get("roster_id"), 5)
        self.assertEqual(mock_defs.call_args.kwargs.get("league_id"), "LEAGUE123")
        self.assertEqual(mock_defs.call_args.kwargs.get("roster_id"), 5)

    def test_not_found(self):
        status, headers, payload = wsgi_get("/nope")
        self.assertTrue(status.startswith("404"))

    @patch("refactored.api.build_dashboard")
    def test_dashboard(self, mock_dash):
        mock_dash.return_value = {
            "lineups": {
                "this": {
                    "mid": {"target": "mid", "lineup": [], "total_points": 0},
                    "floor": {"target": "floor", "lineup": [], "total_points": 0},
                    "ceiling": {"target": "ceiling", "lineup": [], "total_points": 0},
                },
                "next": {
                    "mid": {"target": "mid", "lineup": [], "total_points": 0},
                    "floor": {"target": "floor", "lineup": [], "total_points": 0},
                    "ceiling": {"target": "ceiling", "lineup": [], "total_points": 0},
                },
            },
            "defenses": {"this": {"defenses": []}, "next": {"defenses": []}},
            "ratelimit": "remaining=?%",
        }
        status, headers, payload = wsgi_get("/dashboard?username=u&season=2025")
        self.assertTrue(status.startswith("200"))
        self.assertIn("lineups", payload)
        self.assertIn("defenses", payload)


if __name__ == "__main__":
    unittest.main()
