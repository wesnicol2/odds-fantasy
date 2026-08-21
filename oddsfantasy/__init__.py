"""Refactored fantasy odds pipeline.

Modules:
- api: WSGI entrypoint; serves the JSON API and the static UI
- services: orchestration layer behind every endpoint
- weekly_windows: compute Thursday->Monday windows
- planner: plan relevant games and markets per week window
- aggregator: aggregate per-player odds across bookmakers
- range_model: compute floor/mid/ceiling fantasy points
- prob_models: probability distributions behind the ranges
- draft_prep: league-wide draft board (no roster required)
- odds_client: Odds API client with a TTL disk cache
- ratelimit: Odds API quota tracking from response headers
"""
