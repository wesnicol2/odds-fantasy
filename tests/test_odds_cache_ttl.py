"""Cache freshness differs for schedules and player-prop payloads."""

import unittest
from unittest.mock import patch

from oddsfantasy import odds_client


class OddsCacheTtlTest(unittest.TestCase):
    @patch("oddsfantasy.odds_client.time.time", return_value=10_000)
    @patch("oddsfantasy.odds_client._load_meta", return_value={"url": 9_000})
    def test_player_props_expire_before_event_list(self, _meta, _time):
        self.assertTrue(odds_client._is_fresh_enough("url", odds_client.ODDS_TTL))
        self.assertFalse(odds_client._is_fresh_enough("url", odds_client.PLAYER_ODDS_TTL))

    def test_player_prop_default_ttl_is_shorter_than_event_ttl(self):
        self.assertLess(odds_client.PLAYER_ODDS_TTL, odds_client.ODDS_TTL)


if __name__ == "__main__":
    unittest.main()
