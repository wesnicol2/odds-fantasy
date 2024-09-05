from abc import ABC, abstractmethod
from typing import List, Dict
import random

# --- Abstraction Layer ---

class OddsProvider(ABC):
    """
    Abstract base class for an odds provider.
    This will allow us to plug in different providers like Fanduel, DraftKings, etc.
    """
    @abstractmethod
    def get_odds(self) -> List[Dict]:
        """
        Fetch the odds data from the provider.
        This method should be implemented by each concrete provider.
        """
        pass


# --- Mock Implementation for Proof of Concept ---

class MockOddsProvider(OddsProvider):
    """
    A mock implementation of the OddsProvider to simulate fetching odds data.
    This will be useful during development before integrating real API data.
    """
    def get_odds(self) -> List[Dict]:
        # Simulating odds data for a few players
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


# --- Service Layer ---

class OddsService:
    """
    This service interacts with the odds provider.
    It abstracts away the underlying provider, allowing easy swapping in the future.
    """
    def __init__(self, provider: OddsProvider):
        self.provider = provider

    def fetch_odds(self) -> List[Dict]:
        """
        Fetch odds using the provided odds provider.
        """
        return self.provider.get_odds()


# --- Main Execution ---

if __name__ == "__main__":
    # Using the mock provider for now
    provider = MockOddsProvider()
    odds_service = OddsService(provider)
    
    # Fetch and display the odds data
    odds_data = odds_service.fetch_odds()

    print("Fetched Odds Data:")
    for odds in odds_data:
        print(odds)
