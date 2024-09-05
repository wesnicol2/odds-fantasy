import random
from app.providers.base import OddsProvider

class MockOddsProvider(OddsProvider):
    def get_odds(self):
        players = ['Player A', 'Player B', 'Player C']
        odds_data = []

        for player in players:
            odds = {
                'player_name': player,
                'team': f'Team {random.choice(["X", "Y", "Z"])}',
                'passing_yards': random.uniform(200.0, 400.0),
                'rushing_yards': random.uniform(50.0, 150.0),
                'receiving_yards': random.uniform(0.0, 100.0),
                'touchdowns': random.randint(0, 4),
            }
            odds_data.append(odds)

        return odds_data
