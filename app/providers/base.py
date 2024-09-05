from abc import ABC, abstractmethod
from typing import List, Dict

class OddsProvider(ABC):
    @abstractmethod
    def get_odds(self) -> List[Dict]:
        pass
