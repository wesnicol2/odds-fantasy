# Odds Fantasy

Odds Fantasy turns sportsbook markets into fantasy-football decision support for a selected Sleeper roster.

The app has three focused views:

- **Players** — a linked analytical workstation with roster ranking, Floor / Mid / Ceiling, probability curves, position/player filters, Target FP analysis and sportsbook evidence.
- **Defenses** — every NFL defense ranked by its opponent's implied team total, with league ownership shown.
- **Best lineup** — optimize your modeled starters for Floor, Mid, or Ceiling.

## What the player numbers mean

The projection engine reconstructs a distribution for each priced stat from bookmaker lines, applies the league's real Sleeper scoring rules, samples those stat distributions, and sums them into one fantasy-points distribution.

- **Floor** — 10th percentile fantasy points
- **Mid** — 50th percentile fantasy points
- **Ceiling** — 90th percentile fantasy points

The browser does not create a second projection model. Fantasy-points and individual-stat charts display survival probability: the x-axis is the threshold and the y-axis is the chance of reaching or exceeding it. Setting **Target FP** derives `P(FP ≥ target)` from the backend-supplied fantasy-points curve and ranks the visible players by that probability.

For stat metrics, consensus de-vigged sportsbook anchors are shown as diamonds on the fitted curve and exact source-book thresholds are marked along the x-axis. **Explain betting lines** expands the same evidence into consensus probabilities and raw book/line/over/under prices for the selected player.

A player with no usable priced markets stays visible with dashes and a `no priced markets` state. Missing one optional market does not hide an otherwise valid projection.

The header quota readout is refreshed independently of the odds cache. It uses The Odds API's zero-credit sports endpoint to obtain current remaining/used headers, throttled to one provider check per minute.

## Using the app

1. On a fresh browser, enter your Sleeper username, choose a league, then choose your team. The selection is saved in browser cookies.
2. Choose **This week** or **Next week**.
3. In **Players**, use position filters and graph checkboxes to choose comparisons. Select a player to keep its projection/evidence in the inspector. Choose a metric above the graph to move between fantasy points and priced stats.
4. Enter or drag **Target FP** to compare each visible player's chance of reaching a specific fantasy score.
5. For a stat metric, use **Explain betting lines** to inspect the consensus anchors and exact sportsbook prices behind the fitted curve.
6. In **Defenses**, lower opponent implied total ranks higher. The table marks a defense as Available, Yours, or Taken.
7. In **Best lineup**, choose Floor, Mid, or Ceiling. The optimizer uses the league's Sleeper starter slots and only players/DEF on your roster.

**Settings** contains operational odds-data controls: Auto (cached), Cache only, and Force fresh. Changing modes changes subsequent API requests and does not change projection mathematics.

Kickers are not currently projected from a trustworthy market model. If the league has a K slot, Best Lineup reports it as unmodeled rather than inventing a score.

Defense Floor/Mid/Ceiling used by Best Lineup is intentionally partial: it prices the points-allowed component from the opponent implied total. Sacks, turnovers and defensive touchdowns are not modeled.

## Running locally

For frontend development, run the API and Vite development server separately:

```bash
pip install -r requirements.txt
pip install -e ".[dev]"
python -m oddsfantasy.api --host 127.0.0.1 --port 8000
```

In another shell:

```bash
cd frontend
npm ci
npm run dev
```

Open `http://localhost:5173`. Vite proxies application API routes to port 8000.

For the production-shaped runtime, build and run Docker; the image builds the React app and the Python service serves the compiled assets from port 8000:

```bash
docker build -t odds-fantasy .
docker run --rm -p 8000:8000 odds-fantasy
```

Run checks before pushing:

```bash
ruff check .
ruff format --check .
python -m pytest tests/
cd frontend
npm ci
npm run check
npm run typecheck
npm run build
```

Feature/main CI additionally builds the exact Docker image and runs Chromium against the production-served React application with deterministic mocked application-data APIs.

## Endpoints

- `GET /health`
- `GET /quota`
- `GET /user/leagues?username=&season=`
- `GET /league/resolve?league_id=`
- `GET /projections?league_id=&roster_id=&week=this|next&mode=auto|cache|fresh`
- `GET /player/odds?league_id=&roster_id=&week=this|next&name=&mode=auto|cache|fresh`
- `GET /defenses?league_id=&roster_id=&week=this|next&mode=auto|cache|fresh`
- `GET /best-lineup?league_id=&roster_id=&week=this|next&target=floor|mid|ceiling&mode=auto|cache|fresh`

## Project structure

- `frontend/` — React + TypeScript analytical workstation; Vite builds the production assets.
- `oddsfantasy/api.py` — WSGI API and compiled-static-file server.
- `oddsfantasy/services.py` — cached application data flows.
- `oddsfantasy/planner.py` — maps roster players to games and needed prop markets.
- `oddsfantasy/aggregator.py` — normalizes raw per-book market data.
- `oddsfantasy/market_math.py` — de-vigging and stat-distribution reconstruction.
- `oddsfantasy/projection.py` — canonical fantasy-points sampling/curve.
- `oddsfantasy/graph_data.py` — display-only survival curves from canonical fitted stat distributions.
- `oddsfantasy/scoring.py` — Sleeper scoring-rule translation.
- `oddsfantasy/odds_details.py` — source-line player drill-down and stat graph payloads.
- `oddsfantasy/defense.py` — implied-team-total and points-allowed DEF math.
- `oddsfantasy/lineup.py` — pure starter-slot optimizer.
- `tests/` — unit/integration tests plus the production-container browser smoke script.

The repository does not keep a second hand-written production UI. Docker builds `frontend/` and copies the Vite output into the Python runtime's static directory.

## Deployment

See `CONTRIBUTING.md`. Changes move strictly `dev/*` → `feature/*` → `main`.
