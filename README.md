# Fantasy Odds App

Pulls NFL betting lines (player props + team spreads/totals) from The Odds API,
converts them into de-vigged floor/mid/ceiling fantasy point projections for
your Sleeper roster, and serves them through a small JSON API and web UI.

## Run it

CI publishes the image to GHCR, so there's nothing to build:

```bash
docker run -d \
  --name odds-fantasy \
  -e API_KEY=<your-odds-api-key> \
  -p 8001:8000 \
  -v /mnt/user/appdata/odds-fantasy/data:/app/data \
  ghcr.io/wesnicol2/odds-fantasy:latest
```

Then open `http://<host>:8001/`. Or use the compose file, which mounts `./data`
and reads `.env`:

```bash
docker compose up -d
```

That brings up **two** services: `odds-fantasy` (production, `:latest`, port
8001) and `odds-fantasy-test` (test, `:test`, port 8003, its own `./data-test`
volume). For just the one, name it: `docker compose up -d odds-fantasy`. The
two environments are described in [CONTRIBUTING.md](CONTRIBUTING.md).

Mount `/app/data` somewhere persistent — the odds cache and Sleeper player
metadata live there, and losing it means re-spending API quota.

### Configuration

| Variable              | Required | Default | Purpose                                             |
| --------------------- | -------- | ------- | --------------------------------------------------- |
| `API_KEY`             | yes      | —       | The Odds API key                                    |
| `ODDS_TTL`            | no       | `43200` | Seconds before a cached odds response expires (12h) |
| `SLEEPER_PLAYERS_TTL` | no       | `86400` | Seconds before the Sleeper player cache expires     |
| `TZ`                  | no       | UTC     | Container timezone                                  |

Sleeper's API needs no auth — just a username. Pass `fresh=1` to any endpoint
to bypass the cache for a single request.

### First run

The UI asks for your Sleeper username, then has you pick a league and a team;
both are cookied. Every endpoint also accepts `league_id`+`roster_id` directly
as an alternative to `username`+`season`. If the league hasn't drafted yet, the
UI opens on the draft board rather than the weekly lineup.

## Run from source

```bash
pip install -r requirements.txt
python -m oddsfantasy.api --host 0.0.0.0 --port 8000
```

## Test it

```bash
pip install -e ".[dev]"
ruff check && ruff format --check
python -m pytest tests/
```

CI runs exactly these on every push, and a red check blocks the merge.

## Endpoints

`/health`, `/user/leagues`, `/league/resolve`, `/projections`, `/lineup`,
`/lineup/diffs`, `/defenses`, `/draft-board`, `/player/odds`, `/defense/odds`,
`/dashboard`. The UI is served from `/` and `/ui/*`.

## Project structure

- `oddsfantasy/` — the application. `api.py` is the entrypoint (the
  `Dockerfile`'s `CMD`); `services.py` orchestrates; `range_model.py` +
  `prob_models.py` turn betting-line probabilities into floor/mid/ceiling
  ranges; `lineup.py` builds the optimal lineup; `odds_details.py` backs the
  per-player drill-down; `draft_prep.py` does the same league-wide for the
  draft board; `odds_client.py` + `ratelimit.py` handle caching and quota.
- `ui/` — static frontend, served by `api.py`.
- `tests/` — unit tests.
- `data/` — cached API responses (git-ignored; mount this).

## Known limitations

- Kickers are fetched (see `POSITION_STAT_CONFIG["K"]`) but not converted into
  fantasy point projections or included in the lineup builder.
- Defense/Special-Teams floor/mid/ceiling models only the points-allowed
  scoring bracket, derived from the opponent's spread/total-implied score.
  Sacks, interceptions, fumble recoveries and defensive/return TDs aren't
  modeled — The Odds API doesn't sell team-level defensive props to price them
  off, so this is a known gap rather than an oversight.

## Docs

- [CONTRIBUTING.md](CONTRIBUTING.md) — environments, branching, CI/CD, hygiene.
- [AGENTS.md](AGENTS.md) — why the code is shaped this way: the modelling
  decisions, the quota rules, and what was tried and rejected.
