from typing import List, Dict
from app.providers.base import OddsProvider

class OddsService:
    def __init__(self, provider: OddsProvider):
        self.provider = provider

    def fetch_odds(self) -> List[Dict]:
        return self.provider.get_odds()
