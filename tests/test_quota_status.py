import json
import unittest
from unittest.mock import Mock, patch

from oddsfantasy import odds_client, ratelimit
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
    return response["status"], json.loads(body.decode("utf-8"))


class QuotaStatusTestCase(unittest.TestCase):
    def setUp(self):
        self.old_last = dict(ratelimit._LAST)
        self.old_checked_at = odds_client._QUOTA_STATUS_CHECKED_AT
        ratelimit._LAST.update(
            {
                "remaining": None,
                "used": None,
                "source": None,
                "endpoint": None,
                "ts": None,
            }
        )
        odds_client._QUOTA_STATUS_CHECKED_AT = 0.0

    def tearDown(self):
        ratelimit._LAST.clear()
        ratelimit._LAST.update(self.old_last)
        odds_client._QUOTA_STATUS_CHECKED_AT = self.old_checked_at

    @patch("oddsfantasy.odds_client.API_KEY", "test-key")
    @patch("oddsfantasy.odds_client._SESSION.get")
    def test_refresh_quota_status_uses_zero_credit_sports_endpoint(self, mock_get):
        response = Mock()
        response.headers = {
            "x-requests-remaining": "4321",
            "x-requests-used": "679",
            "x-requests-last": "0",
        }
        response.raise_for_status.return_value = None
        mock_get.return_value = response

        details = odds_client.refresh_quota_status(force=True)

        mock_get.assert_called_once_with(
            "https://api.the-odds-api.com/v4/sports?apiKey=test-key",
            timeout=odds_client.REQ_TIMEOUT,
        )
        self.assertEqual(details["remaining"], 4321)
        self.assertEqual(details["used"], 679)
        self.assertEqual(details["total"], 5000)
        self.assertEqual(details["endpoint"], "quota_status")

    @patch("oddsfantasy.odds_client.API_KEY", "test-key")
    @patch("oddsfantasy.odds_client._SESSION.get")
    def test_recent_quota_snapshot_is_reused(self, mock_get):
        response = Mock()
        response.headers = {
            "x-requests-remaining": "4000",
            "x-requests-used": "1000",
        }
        response.raise_for_status.return_value = None
        mock_get.return_value = response

        first = odds_client.refresh_quota_status(force=True)
        second = odds_client.refresh_quota_status()

        self.assertEqual(mock_get.call_count, 1)
        self.assertEqual(first["remaining"], 4000)
        self.assertEqual(second["remaining"], 4000)

    @patch("oddsfantasy.api.ratelimit.format_status", return_value="remaining=80.0%")
    @patch(
        "oddsfantasy.api.ratelimit.get_details",
        return_value={
            "remaining": 4000,
            "used": 1000,
            "total": 5000,
            "pct": 80.0,
            "pct_str": "80.0%",
            "source": "network",
            "endpoint": "quota_status",
        },
    )
    @patch("oddsfantasy.api.compute_projections")
    @patch("oddsfantasy.api.odds_client.refresh_quota_status")
    def test_projection_response_overwrites_stale_cached_quota(
        self,
        mock_refresh,
        mock_projection,
        _mock_details,
        _mock_status,
    ):
        mock_projection.return_value = {
            "week": "this",
            "players": [],
            "ratelimit": "remaining=?%",
            "ratelimit_info": {"remaining": None, "used": None, "total": None},
        }

        status, payload = wsgi_get("/projections?league_id=L1&roster_id=7")

        self.assertTrue(status.startswith("200"))
        mock_refresh.assert_called_once_with()
        self.assertEqual(payload["ratelimit_info"]["remaining"], 4000)
        self.assertEqual(payload["ratelimit_info"]["total"], 5000)

    @patch("oddsfantasy.api.ratelimit.format_status", return_value="remaining=80.0%")
    @patch(
        "oddsfantasy.api.ratelimit.get_details",
        return_value={
            "remaining": 4000,
            "used": 1000,
            "total": 5000,
            "pct": 80.0,
            "pct_str": "80.0%",
            "source": "network",
            "endpoint": "quota_status",
        },
    )
    @patch("oddsfantasy.api.odds_client.refresh_quota_status")
    def test_quota_endpoint_returns_structured_status(
        self, mock_refresh, _mock_details, _mock_status
    ):
        status, payload = wsgi_get("/quota")

        self.assertTrue(status.startswith("200"))
        mock_refresh.assert_called_once_with()
        self.assertEqual(payload["ratelimit_info"]["remaining"], 4000)
        self.assertEqual(payload["ratelimit_info"]["used"], 1000)


if __name__ == "__main__":
    unittest.main()
