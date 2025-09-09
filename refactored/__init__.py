"""Refactored fantasy odds pipeline.

Modules:
- weekly_windows: compute Thursday→Monday windows
- planner: plan relevant games and markets per week window
- aggregator: aggregate per-player odds across bookmakers
- range_model: compute floor/mid/ceiling fantasy points
- runner: CLI entrypoint with step-by-step debug output
"""

