# Odds Fantasy

Odds Fantasy turns sportsbook player props into fantasy-football probability distributions for a Sleeper roster.

The app intentionally has one job: show **Floor / Mid / Ceiling** for every QB, RB, WR and TE on the selected roster, then let you inspect the sportsbook lines that created any player's curve.

## What the numbers mean

The projection engine reconstructs a distribution for each priced stat from bookmaker lines, applies the league's real Sleeper scoring rules, samples the stat distributions, and sums them into one fantasy-points distribution.

- **Floor** — 10th percentile fantasy points
- **Mid** — 50th percentile fantasy points
- **Ceiling** — 90th percentile fantasy points

The player detail view and the roster-wide **Compare curves** graph use the same backend samples as those three numbers. There is no second browser-side projection model.

## Using the app

1. Open the UI and select your Sleeper username, league and team.
2. Choose **This week** or **Next week**.
3. Read the roster report, sorted by Mid.
4. Click a player to inspect:
   - the same fantasy-points probability curve used by the report;
   - the consensus probability anchors reconstructed from the books;
   - every main and alternate sportsbook line that contributed to each modeled stat.
5. Click **Compare curves** to plot every roster player's probability curve on the same axes.

A player with no usable priced markets shows dashes instead of a fabricated zero. Missing one optional market does not hide an otherwise valid projection.

## Running locally

```bash
pip install -r requirements.txt
pip install -e ".[dev]"
python -m oddsfantasy.api --host 0.0.0.0 --port 8000
```

Then open `http://localhost:8000`.

Run checks before pushing:

```bash
ruff check .
ruff format --check .
python -m pytest tests/
```

## Endpoints

- `GET /health`
- `GET /user/leagues?username=&season=`
- `GET /league/resolve?league_id=`
- `GET /projections?league_id=&roster_id=&week=this|next&mode=auto|cache|fresh`
- `GET /player/odds?league_id=&roster_id=&week=this|next&name=`

The UI is served from `/` and `/ui/*`.

## Project structure

- `oddsfantasy/api.py` — small WSGI API and static-file server.
- `oddsfantasy/services.py` — shared cached week context and roster report.
- `oddsfantasy/planner.py` — maps roster players to games and required prop markets.
- `oddsfantasy/aggregator.py` — normalizes raw Odds API responses by player/book/market.
- `oddsfantasy/market_math.py` — de-vigging, consensus anchors, and stat-distribution reconstruction.
- `oddsfantasy/projection.py` — stat sampling and the canonical fantasy-points curve.
- `oddsfantasy/scoring.py` — Sleeper scoring-rule translation.
- `oddsfantasy/odds_details.py` — player drill-down built from the same cached source data.
- `ui/` — the single roster report, player detail view, and all-player curve comparison.
- `tests/` — unit and end-to-end projection tests.

## Deployment

See `CONTRIBUTING.md`. Changes move strictly `dev/*` → `feature/*` → `main`; feature branches publish `:test` and `main` publishes `:latest` to GHCR.