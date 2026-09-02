"""Odds Fantasy package.

Core flow:
- sleeper_api: league/roster/scoring identity
- planner: relevant games and prop markets
- odds_client: Odds API access and cache
- aggregator: raw per-player bookmaker lines
- market_math: de-vigged stat distributions
- scoring: Sleeper scoring configuration
- projection: canonical fantasy-points curve
- services / odds_details / api: application layer
"""