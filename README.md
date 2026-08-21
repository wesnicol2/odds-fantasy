# Fantasy Odds App

## Overview
This project pulls NFL betting lines (player props + team spreads/totals) from
The Odds API, converts them into de-vigged floor/mid/ceiling fantasy point
projections for your Sleeper roster, and serves them through a small JSON API
and web UI.

## Configuration
The application relies on the following environment variables (populate them
in your `.env` file or configure them directly in Docker/Unraid):
- `API_KEY` — The Odds API key

Sleeper's API requires no auth (only a username). Only supply values you are
comfortable sharing with the container. When running under Docker, pass them
as environment variables or mount a file via `env_file`.

## Docker Workflow
1. Copy your `.env` file into the project root (or ensure the required variables are defined elsewhere).
2. Build the container image:
   ```bash
   docker build -t odds-fantasy .
   ```
3. Run the container, mounting the `data` folder so cached responses survive restarts:
   ```bash
   docker run --rm \
     --name odds-fantasy \
     --env-file .env \
     -p 8000:8000 \
     -v $(pwd)/data:/app/data \
     odds-fantasy
   ```

### Docker Compose
You can use the provided `docker-compose.yml` to simplify local and Unraid deployments:
```bash
docker compose up --build
```
Override the command or environment variables in the compose file if you need to call different entry points.

### Deploying on Unraid
1. Copy the repo (or your packaged image) onto the server.
2. From the Unraid Docker tab, add a new container and point it at the built image (`odds-fantasy:latest`) or the repository if you publish it elsewhere.
3. Under the container configuration:
   - Map `/app/data` to a persistent host path (for example `/mnt/user/appdata/odds-fantasy/data`).
   - Map container port `8000` to a host port (e.g. `8001`).
   - Add the `API_KEY` environment variable.
4. Apply/Start the container, then open `http://<unraid-ip>:<mapped-port>/` for the UI.

## Contributing
See [CONTRIBUTING.md](CONTRIBUTING.md) for the branching model
(`feature/*` / `dev/*` / `main`) and repo-hygiene rules.

## League / team identity
The UI identifies "you" by Sleeper **league + team**, resolved by league ID
under the hood (not username) once picked -- but the picking itself starts
from your Sleeper username, since nobody has their league ID memorized. On
first load: enter your username (`GET /user/leagues?username=&season=` lists
every league it finds) -> pick which league (its league_id gets cookie'd) ->
pick which roster is yours in it (roster_id also cookie'd). This is more
precise than resolving everything from username alone, which just grabs "the
first league this username is in" and silently picks the wrong league for
anyone in more than one -- the username step here is purely a lookup
convenience, not the identity itself. The chosen league's own Sleeper
`status` (`pre_draft`/`drafting` vs. `in_season`/`complete`) decides whether
the UI defaults to the draft board or the weekly lineup view. Every endpoint
accepts `league_id`+`roster_id` as an alternative to `username`+`season`,
with `league_id` taking priority when both are present (see
`services._resolve_identity`). The header's username/season fields still
work as a fallback for anyone who hasn't set up a league.

## Project Structure
- `refactored/`: **This is the real application.** `refactored/api.py` is the
  entrypoint (`CMD` in the `Dockerfile`) — a stdlib WSGI server exposing
  `/health`, `/user/leagues`, `/league/resolve`, `/projections`, `/lineup`, `/lineup/diffs`,
  `/defenses`, `/draft-board`, `/player/odds`, `/defense/odds`, and
  `/dashboard`, and serving the UI under `/` and `/ui/*`. See
  `refactored/services.py` for the orchestration layer,
  `refactored/range_model.py` + `refactored/prob_models.py` for how
  betting-line probabilities become floor/mid/ceiling fantasy point ranges,
  `refactored/aggregator.py` + `refactored/planner.py` for how odds are
  fetched/grouped for your roster, `refactored/draft_prep.py` for the same
  thing but for every player league-wide (pre-draft, before you have a
  roster to scope to), and `refactored/odds_client.py` +
  `refactored/ratelimit.py` for caching and Odds-API rate-limit tracking.
- `config.py`: Loads environment configuration and defines shared constants
  (position→market mappings, Sleeper↔Odds-API name/team mappings, scoring
  key mappings).
- `predicted_stats.py`: Shared de-vig + mean-stat-estimate helpers used by
  `refactored/`.
- `sleeper_api.py`: Sleeper API client (roster, scoring rules, league/owner data).
- `ui/`: Static frontend served by `refactored/api.py`.
- `data/`: Cached API responses and Sleeper player metadata (persist this
  directory across runs). Odds cache entries auto-expire after `ODDS_TTL`
  seconds (default 12h); pass `fresh=1` to any endpoint to bypass the cache.
- `tests/`: Unit tests (`python -m pytest tests/`).

## Known limitations
- Kickers are fetched (see `POSITION_STAT_CONFIG["K"]`) but not yet converted
  into fantasy point projections or included in the lineup builder.
- Defense/Special-Teams floor/mid/ceiling only models the points-allowed
  scoring bracket (derived from the opponent's spread/total-implied score).
  Sacks, interceptions, fumble recoveries, and defensive/return TDs aren't
  modeled — The Odds API doesn't offer team-level defensive props to price
  them off of, so they're a known gap rather than an oversight.
