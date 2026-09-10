# Odds Fantasy

Odds Fantasy turns sportsbook markets into fantasy-football decision support for a selected Sleeper roster.

The app has four focused destinations:

- **Dashboard** — the default low-noise command center: this week's ideal Mid lineup, the bench players closest to cracking it, and the best available/owned defenses for this week and next week.
- **Players** — a linked analytical workstation with roster ranking, Floor / Mid / Ceiling, probability curves, position/player filters, Target FP analysis and sportsbook evidence.
- **Defenses** — every NFL defense ranked by its opponent's implied team total, with league ownership shown.
- **Lineup** — optimize your modeled starters for Floor, Mid, or Ceiling.

Dashboard intentionally summarizes conclusions rather than recreating projection logic. Its lineup and bench-pressure values come from the same backend optimizer used by Lineup, and its defense shortlists reuse the same ranked defense payload used by Defenses.

## What the player numbers mean

The projection engine reconstructs a distribution for each priced stat from bookmaker lines, applies the league's real Sleeper scoring rules, samples those stat distributions, and sums them into one fantasy-points distribution.

- **Floor** — 10th percentile fantasy points
- **Mid** — 50th percentile fantasy points
- **Ceiling** — 90th percentile fantasy points

The browser does not create a second projection model. The fantasy-points chart converts the dense backend-supplied survival curve into one-point probability-mass buckets, so the x-axis is the fantasy score and the y-axis is the chance of landing in the one-point bucket centered on that score. The chart focuses on the central 99% of each compared player's mass so extreme low-probability tails do not compress the useful shape. Setting **Target FP** still derives `P(FP ≥ target)` from the backend-supplied fantasy-points curve and ranks the visible players by that probability.

Individual-stat charts re-express the same backend-fitted sportsbook distributions according to the metric's support. Yardage uses a continuous probability-density view (`x = value`, `y = P(x)`) sampled densely from the canonical fitted distribution and kernel-smoothed for display so sparse sportsbook thresholds do not create artificial spikes or zero-probability holes. High-granularity integer stats such as receptions use exact probability mass at each integer (`P(X = x)`) with visible points and a smoothed connecting line. Low-granularity counts such as passing TDs, anytime TDs and interceptions use one vertical threshold gauge per value, with each player's marker showing `P(X ≥ x)`.

Compared player series stay at full color and opacity even when another player is selected or hovered. Selection is indicated with a modestly heavier stroke and higher draw order instead of dimming the other players, so every compared curve remains readable.

Continuous and high-granularity charts support axis-specific rescaling. On touch devices, pinch directly on the x-axis or y-axis to zoom only that axis while the chart updates continuously. Mouse-wheel or trackpad scrolling over an axis provides the same behavior on desktop; when an axis control is keyboard-focused, `+` and `-` zoom and `0` resets that axis.

Sportsbook evidence stays mathematically consistent with those views. Exact source-book thresholds can be marked on the x-axis of `P(x)` charts, while de-vigged consensus anchors remain inspectable in **Explain betting lines** because they are cumulative `P(X ≥ x)` quantities and therefore do not share the density/PMF y-axis. Low-granularity gauges already use the same cumulative threshold semantics directly.

A player with no usable priced markets stays visible with dashes and a `no priced markets` state. Missing one optional market does not hide an otherwise valid projection.

The header quota readout is refreshed independently of the odds cache. It uses The Odds API's zero-credit sports endpoint to obtain current remaining/used headers, throttled to one provider check per minute.

## Using the app

1. On a fresh browser, enter your Sleeper username, choose a league, then choose your team. The selection is saved in browser cookies.
2. Start on **Dashboard** for the current decision: ideal lineup, closest bench calls, and this/next-week defense targets. Select a player under **Distance from the ideal lineup** to compare that bench option directly with the optimizer-identified starter they would displace.
3. Use **Players**, **Defenses**, or **Lineup** when you want to drill down. Those destinations have their own **This week / Next week** context selector; Dashboard intentionally spans both defense weeks itself.
4. In **Players**, use position filters and graph checkboxes to choose comparisons. Select a player to keep its projection/evidence in the inspector. The fantasy-points inspector breaks the player's mean into exact per-stat expected-point contributions; select any contribution to open that stat's distribution and betting-line evidence. You can also choose a metric above the graph directly.
5. Enter or drag **Target FP** to compare each visible player's chance of reaching a specific fantasy score. Use **Explain betting lines** when you want the consensus anchors and source sportsbook prices.
6. In **Defenses**, lower opponent implied total ranks higher. The table marks a defense as Available, Yours, or Taken. Select any number — implied total, Floor, Mid, Ceiling or the book count — to open that team's detail panel showing exactly how the number was calculated: the per-sportsbook totals and spreads behind the implied total, or the points-allowed bracket and league scoring behind the range.
7. In **Lineup**, choose Floor, Mid, or Ceiling. The optimizer uses the league's Sleeper starter slots and only players/DEF on your roster.

Primary navigation preserves the analytical workspace in memory instead of rebuilding it as a set of disconnected pages. Browser Back/Forward restores the destination and week context. On desktop the primary navigation is a compact horizontal strip; on narrow screens it becomes a persistent bottom navigation bar so the Players visualization keeps its horizontal space.

Dashboard bench pressure is an optimizer-derived opportunity cost. For each bench player, the backend forces that player into the best valid lineup and reports how much total projected value is lost versus the unconstrained ideal lineup. A small `FP back` value therefore means the player is close to cracking the ideal lineup without the browser needing to recreate roster-slot eligibility rules. Selecting that row opens this week's tie-breaker matrix with the displaced starter: aligned projection ranges, game spread/total and team implied total, per-stat expected-point contributions, and one-click stat distribution drill-downs. The matrix measures the week twice — once in league fantasy points and once in raw stat value (each market's 10th percentile, median and 90th percentile) — and draws both with the same Floor / Mid / Ceiling thermometer used by the ranking table, on a scale shared by the two players in that row. The two measurements keep separate row-win tallies, because a stat and the points it produces are the same underlying market. Comparing a running back with a receiver or tight end shows rushing and receiving yards as one combined row, since those positions earn yardage in different markets; its range is sampled from both distributions rather than added percentile by percentile. Back-vs-back and receiver-vs-tight-end comparisons keep the separate markets. While the comparison is open, Players reorders around it: the matrix leads full width, the probability chart follows, and the ranking checkboxes move to the bottom. Exiting comparison restores the normal three-column workstation. The matrix deliberately excludes ADP, season-long rank, rest-of-season schedule and every other draft or multi-week input.

**Settings** contains operational odds-data controls: Auto (cached), Cache only, and Force fresh. Changing modes changes subsequent API requests and does not change projection mathematics.

Kickers are not currently projected from a trustworthy market model. If the league has a K slot, Lineup reports it as unmodeled rather than inventing a score.

Defense Floor/Mid/Ceiling used by Lineup is intentionally partial: it prices the points-allowed component from the opponent implied total. Sacks, turnovers and defensive touchdowns are not modeled.

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

After modifying Python, normalize it with the repo-owned pinned tool instead of hand-formatting:

```bash
./scripts/fix
```

Before every push, run the same Python verification gate CI runs:

```bash
./scripts/verify
cd frontend
npm ci --no-audit --no-fund
npm run check
npm run typecheck
npm run build
```

Feature/main CI additionally builds the exact Docker image and runs Chromium against the production-served React application with deterministic mocked application-data APIs. The deployed home-server Test container is optional and is reserved for deployment-specific verification.

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
- `oddsfantasy/graph_data.py` — display-only density, PMF and threshold-gauge data from canonical fitted stat distributions.
- `oddsfantasy/scoring.py` — Sleeper scoring-rule translation.
- `oddsfantasy/odds_details.py` — source-line player drill-down and stat graph payloads.
- `oddsfantasy/defense.py` — implied-team-total and points-allowed DEF math.
- `oddsfantasy/lineup.py` — pure starter-slot optimizer and optimizer-derived bench-pressure calculation.
- `scripts/` — repo-owned Python fix and verification commands used locally and by CI.
- `tests/` — unit/integration tests plus the production-container browser smoke script.

The repository does not keep a second hand-written production UI. Docker builds `frontend/` and copies the Vite output into the Python runtime's static directory.

## Deployment

See `CONTRIBUTING.md`. Changes move strictly `dev/*` → `feature/*` → `main`.
