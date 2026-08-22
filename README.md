# Fantasy Odds App

Pulls NFL betting lines (player props + team spreads/totals) from The Odds API,
converts them into de-vigged floor/mid/ceiling fantasy point projections for
your Sleeper roster, and serves them through a small JSON API and web UI.

Floor / mid / ceiling are the 10th / 50th / 90th percentiles of one simulated
fantasy-points curve per player — not three separate projections. The method is
specified in [docs/fantasy-projection-methodology.md](docs/fantasy-projection-methodology.md).

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

### What's deployed

Every page carries a footer with the commit the running instance was built
from, linked to it on GitHub, plus the image tag (`test` / `latest`) and build
time. Deployment is pull-based — Watchtower notices a new digest and recreates
the container on its own schedule — so this is the way to tell whether a change
has actually landed rather than inferring it from timestamps. `GET /health`
returns the same information as JSON.

Running from source shows the checkout's commit instead, marked `+local
changes` if the working tree is dirty. An image built without the commit build
arg reads `build unknown`.

### Configuration

| Variable              | Required | Default | Purpose                                             |
| --------------------- | -------- | ------- | --------------------------------------------------- |
| `API_KEY`             | yes      | —       | The Odds API key                                    |
| `ODDS_TTL`            | no       | `43200` | Seconds before a cached odds response expires (12h) |
| `SLEEPER_PLAYERS_TTL` | no       | `86400` | Seconds before the Sleeper player cache expires     |
| `TZ`                  | no       | UTC     | Container timezone                                  |

Sleeper's API needs no auth — just a username. Pass `fresh=1` to any endpoint
to bypass the cache for a single request.

### The two modes

The UI has exactly two screens, and the league's Sleeper status picks which one
opens:

- **Pre-Draft** — every draftable player on the slate, ranked, for breaking ties
  between players you already rate similarly. Alongside floor/mid/ceiling it
  shows **Upside** (ceiling − mid), which is the number to compare when two
  players project the same, and **Books** — how many bookmakers backed the
  projection, flagged when it's too few to tiebreak on.
- **In-Season** — your roster, week by week: optimal lineup, all players, and
  defenses.

There is deliberately no season-total projection. Books only post props for the
upcoming slate, so a season number could only be the per-game one multiplied by
a games constant — same ordering, no extra information, and it would read as a
market number when it isn't one.

### Choosing a projection model

Projections use the engine that implements the methodology doc: it reads every
threshold the books post, de-vigs each book, takes the median across books,
rebuilds each stat's distribution, and simulates the player's fantasy points
under your league's scoring. The earlier single-line models are still reachable
by hand for comparison — `?model=const|puelz|angelini|baseline` on any
projection endpoint — but they are no longer offered in the UI.

Scoring is read entirely from your league's Sleeper settings — point values,
PPR, and bonus thresholds alike — so a rules change needs no code change.

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
  `Dockerfile`'s `CMD`); `services.py` orchestrates. The projection math is
  `scoring.py` (league rules as configuration) + `market_math.py` (odds to a
  stat distribution) + `projection.py` (simulate and sum a player's stats),
  with `range_model.py` + `prob_models.py` holding the earlier models and the
  defense projection. `lineup.py` builds the optimal lineup; `odds_details.py`
  backs the per-player drill-down; `draft_prep.py` does the same league-wide
  for the draft board; `odds_client.py` + `ratelimit.py` handle caching and
  quota.
- `ui/` — static frontend, served by `api.py`.
- `tests/` — unit tests.
- `data/` — cached API responses (git-ignored; mount this).

## Known limitations

- A player's stats are simulated independently of each other, because the books
  price each stat on its own and this feed carries nothing that prices them
  jointly. Ceilings are therefore a little conservative for players whose stats
  move together — a QB's passing yards and passing touchdowns most of all.
- Fumbles lost and 2-point conversions are not modeled: there's no clean market
  to price them off, and guessing a rate would make the ranges less honest
  rather than more complete.
- Alternate-line ladders are requested for rushing yards, receiving yards and
  receptions only. Passing stats and touchdowns are rebuilt from whatever
  thresholds the books happen to differ on, which is a coarser curve. This is a
  quota decision — see [AGENTS.md](AGENTS.md).
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
- [docs/fantasy-projection-methodology.md](docs/fantasy-projection-methodology.md)
  — the projection method itself, argued from the market up and independent of
  any code. The spec the implementation is measured against.
