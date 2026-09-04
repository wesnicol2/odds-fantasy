# Odds Fantasy

Odds Fantasy turns sportsbook markets into fantasy-football decision support for a selected Sleeper roster.

The app has four focused views:

- **Player report** — Floor / Mid / Ceiling for every projected QB, RB, WR and TE.
- **Graphs** — compare roster probability distributions for fantasy points and the underlying modeled stats, with player/position filters.
- **Defenses** — every NFL defense ranked by its opponent's implied team total, with league ownership shown.
- **Best lineup** — optimize your modeled starters for Floor, Mid, or Ceiling.

Clicking a player also opens the exact sportsbook lines and consensus probability anchors that created that player's projection.

## What the player numbers mean

The projection engine reconstructs a distribution for each priced stat from bookmaker lines, applies the league's real Sleeper scoring rules, samples those stat distributions, and sums them into one fantasy-points distribution.

- **Floor** — 10th percentile fantasy points
- **Mid** — 50th percentile fantasy points
- **Ceiling** — 90th percentile fantasy points

Graphing is presentation-only. The fantasy-points graph shows the probability of finishing within a one-point bucket centered on each x-value (`x ± 0.5 FP`). Stat graphs instead show the fitted survival curve: the x-axis is the stat threshold and the y-axis is the probability of reaching or exceeding that threshold. Consensus de-vigged sportsbook anchors are drawn directly on that curve, and exact source-book thresholds are marked on the x-axis. **Explain betting lines** expands the raw source prices and consensus anchors for a selected player so the curve's shape can be traced back to the market evidence. None of these graph views changes Floor / Mid / Ceiling or creates a second projection model in the browser.

A player with no usable priced markets shows dashes. Missing one optional market does not hide an otherwise valid projection.

The header quota readout is refreshed independently of the odds cache. It uses The Odds API's zero-credit sports endpoint to obtain the current remaining/used headers, throttled to one provider check per minute, so a container restart or a cache-only report does not leave quota status unknown.

## Using the app

1. Select your Sleeper username, league and team.
2. Choose **This week** or **Next week**.
3. In **Player report**, click a player for source lines or open **Graphs**. The graph explorer has a left filter panel for graph type, position and player, plus Previous/Next controls to cycle through available metrics. Stat graphs show the fitted probability curve, consensus anchor diamonds and exact sportsbook line ticks; use **Explain betting lines** for the underlying prices.
4. In **Defenses**, lower opponent implied total ranks higher. The table marks a defense as Available, Yours, or Taken.
5. In **Best lineup**, choose Floor, Mid, or Ceiling. The optimizer uses the league's Sleeper starter slots and only players/DEF on your roster.

Kickers are not currently projected from a trustworthy market model. If the league has a K slot, Best Lineup reports it as unmodeled rather than inventing a score.

Defense Floor/Mid/Ceiling used by Best Lineup is intentionally partial: it prices the points-allowed component from the opponent implied total. Sacks, turnovers and defensive touchdowns are not modeled.

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

Feature/main CI additionally builds the Docker image and runs a Chromium smoke test against the real served UI with deterministic mocked upstream data.

## Endpoints

- `GET /health`
- `GET /quota`
- `GET /user/leagues?username=&season=`
- `GET /league/resolve?league_id=`
- `GET /projections?league_id=&roster_id=&week=this|next&mode=auto|cache|fresh`
- `GET /player/odds?league_id=&roster_id=&week=this|next&name=`
- `GET /defenses?league_id=&roster_id=&week=this|next`
- `GET /best-lineup?league_id=&roster_id=&week=this|next&target=floor|mid|ceiling`

## Project structure

- `oddsfantasy/api.py` — WSGI API and static-file server.
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
- `ui/` — report, graph explorer, player details, defenses and best-lineup views.
- `tests/` — unit/integration tests plus the browser smoke script.

## Deployment

See `CONTRIBUTING.md`. Changes move strictly `dev/*` → `feature/*` → `main`.