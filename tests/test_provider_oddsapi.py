"""Regression tests for adapting Odds API evidence to the provider contract."""

import unittest

from oddsfantasy.provider_contract import quotes_to_players_odds
from oddsfantasy.provider_oddsapi import normalize_fetched_odds


class Game:
    def __init__(self):
        self.players = [{"alias": "AJ Brown", "primary_position": "WR"}]


def event_payload():
    return {
        "bookmakers": [
            {
                "key": "draftkings",
                "markets": [
                    {
                        "key": "player_reception_yds",
                        "outcomes": [
                            {
                                "name": "Over",
                                "description": "AJ Brown",
                                "price": 1.91,
                                "point": 74.5,
                            },
                            {
                                "name": "Under",
                                "description": "AJ Brown",
                                "price": 1.91,
                                "point": 74.5,
                            },
                        ],
                    },
                    {
                        "key": "player_reception_yds_alternate",
                        "outcomes": [
                            {
                                "name": "Over",
                                "description": "AJ Brown",
                                "price": 1.45,
                                "point": 59.5,
                            },
                            {
                                "name": "Under",
                                "description": "AJ Brown",
                                "price": 2.8,
                                "point": 59.5,
                            },
                        ],
                    },
                ],
            }
        ]
    }


class OddsApiAdapterTest(unittest.TestCase):
    def test_round_trip_preserves_existing_book_and_threshold_shapes(self):
        planned = {"game-1": Game()}
        result = normalize_fetched_odds({"game-1": event_payload()}, planned)
        self.assertEqual(result.provider_id, "odds_api")
        self.assertEqual(len(result.quotes), 2)
        players = quotes_to_players_odds([result], {"AJ Brown": "WR"})
        book = players["AJ Brown"]["draftkings"]
        self.assertAlmostEqual(book["player_reception_yds"]["over"]["odds"], 1.91)
        self.assertEqual(
            book["player_reception_yds_alternate"]["alts"]["over"][0]["point"], 59.5
        )
        self.assertEqual(book["__player_position__"]["value"], "WR")


if __name__ == "__main__":
    unittest.main()
