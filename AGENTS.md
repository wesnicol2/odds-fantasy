# Odds Fantasy — implementation notes

`README.md` explains use, `CONTRIBUTING.md` owns process,
`docs/fantasy-projection-methodology.md` is the mathematical contract, and
`docs/design.md` is the UI/visualization contract.

## Product boundary

The application has three selectable weekly decision views:

1. **Players** — one linked analytical workstation: roster ranking, Floor / Mid / Ceiling, fantasy/stat probability visualizations, position/player comparison filters, Target FP and a persistent evidence inspector.
2. **Defenses** — all NFL defenses sorted by opponent implied team total, with Sleeper league ownership.
3. **Best lineup** — maximize Floor, Mid, or Ceiling across the league's actual modeled starter slots.

Player evidence is progressive disclosure inside the same workstation. There is no separate Graphs product surface and no alternate browser-side projection engine.

Pre-draft boards, model-comparison tools, book-coverage dashboards and alternate client-side projection engines remain removed.

## Frontend architecture

`frontend/` is the only authored frontend source for the analytical workstation specified in `docs/design.md`.

The stack is deliberately small:

- **React 19 + TypeScript** own components and interaction logic.
- **Vite 8** owns development and production bundling.
- **Apache ECharts 6** renders analytical visualizations.
- **Zustand** owns the small shared workstation state that coordinates ranking, chart, filters and inspector.
- **Biome** is the whole JavaScript/TypeScript/CSS formatting and linting story. Do not add ESLint or Prettier unless an explicit owner decision changes that contract.

React was chosen over Astro because the target UI is one coordinated interactive application rather than a mostly-static page with isolated interactive islands. Ranking selection, chart emphasis, metric/position filters, selected player and Target FP intentionally update one another continuously. Svelte was viable, but React was preferred for its mature ecosystem, predictable ECharts integration and broad agent familiarity.

State ownership is strict:

- Zustand owns canonical browser interaction state such as view, week, metric, selected player(s), position filters, Target threshold, data mode and lineup objective.
- React components consume that state and API data.
- ECharts receives data/options as a renderer and emits interaction events back to the application. It must not become the canonical owner of application state.
- The Python backend remains canonical for projections, probability distributions, scoring and sportsbook modeling. Browser code may derive display-only quantities from canonical payloads (for example `P(FP >= target)` from the supplied fantasy-point curve) but must not refit sportsbook evidence or create a second projection model.

Keep component boundaries recognizable: workspace/navigation, ranking pane, probability chart, Target control, inspector/evidence, league setup/settings, defense view and lineup view. Prefer focused components/state selectors over rebuilding a monolithic application component.

## Production frontend runtime

The Dockerfile is the production frontend build contract:

1. a Node 22 build stage runs `npm ci` and `npm run build` in `frontend/`;
2. the Python runtime copies the Vite `dist/` output into `/app/ui/`;
3. `oddsfantasy.api` serves `/app/ui/index.html` at `/` and compiled assets from the same directory.

The repository intentionally does **not** keep a second hand-written `ui/` implementation. Treat `/app/ui/` as generated runtime output. Do not add source files under repository `ui/` as a fallback or bypass the Vite build.

For local UI development, run the Python API on port 8000 and Vite on port 5173; `frontend/vite.config.ts` proxies application API routes to the Python service.

## League identity and operational data mode

`league_id` + `roster_id` browser cookies are authoritative after setup. Username is primarily league discovery and a legacy API fallback.

A fresh browser must be able to complete username → league → team setup entirely in React. Opening **Change league** for an existing identity must not delete the active selection until a replacement team is committed.

Odds data mode is operational state, not model state:

- `auto` reuses provider caches normally;
- `cache` forbids provider refreshes;
- `fresh` bypasses reusable odds caches for newly loaded data.

Client-side response caches must include identity and data mode in their keys so responses from one team or mode cannot silently satisfy another.

## One player projection engine

`oddsfantasy.projection.project_player` is the only player projection engine.

Pipeline:

`Sleeper roster → planner → Odds API → aggregator → market_math → scoring → projection`

`market_math.py` converts/de-vigs prices, takes consensus across books, enforces monotonic survival probabilities and reconstructs stat distributions. `projection.py` samples each modeled stat, scores each draw with Sleeper rules, sums fantasy points and reads 10th/50th/90th percentiles.

Cross-stat correlation is still assumed independent because the market feed does not provide a joint distribution.

## Visualizations are presentation-only canonical data

`PlayerProjection.samples` is the source of truth for the fantasy-points distribution. `survival_curve()` downsamples the same samples used for Floor/Mid/Ceiling into `P(FP >= x)` points. The browser converts that supplied curve into the existing one-point fantasy-score probability-mass display; Target FP continues to interpolate the canonical survival curve.

For individual stats, `oddsfantasy.graph_data.distribution_graph()` reads the already-fitted `StatProjection.distribution` and chooses one of three display projections without refitting anything:

- **continuous density** — yardage-like metrics are displayed as `x = value`, `y = P(x)` using a finite-width density derived from the fitted distribution's own survival function across its central range;
- **discrete PMF** — high-granularity count metrics such as receptions expose exact `P(X = x)` at integer values; the frontend may visually smooth the connecting line, but the displayed point values remain the backend PMF;
- **threshold gauge** — low-granularity count metrics such as passing TDs, anytime TDs and interceptions expose `P(X >= x)` for each useful integer threshold.

`graph_data` is display-only. It must never refit sportsbook lines or participate in projection sampling, fantasy scoring, percentiles, means or distribution fitting. The same rule applies to `StatProbabilityChart`: ECharts/CSS map backend values to pixels and interaction affordances; they do not create a probability model.

`/player/odds` includes graph points alongside de-vigged consensus anchors and exact source sportsbook lines. Their units matter:

- exact sportsbook line locations are x-axis evidence and may be marked on continuous-density or PMF charts;
- consensus anchors are cumulative `P(X >= x)` evidence, so they remain in the inspector when the active chart's y-axis is density or PMF rather than being plotted at incompatible y-values;
- low-granularity gauges already use cumulative threshold semantics, so their player marker height directly represents `P(X >= threshold)`.

`Explain betting lines` expands the same payload into consensus probabilities plus raw book/line/over/under prices. Evidence remains linked to the selected player without introducing a second representation of the fitted distribution.

Target FP is also display-only. The browser interpolates the supplied fantasy-point survival curve to show/rank `P(FP >= target)`; changing Target FP must not make a provider request or modify Floor / Mid / Ceiling.

## Shared player week context

`services._load_week_context()` caches the expensive roster/player-prop path for `(identity, week, region)`:

1. resolve Sleeper roster/scoring;
2. fetch the NFL event list once;
3. plan the roster's needed markets from that same event list;
4. fetch each relevant game concurrently once;
5. normalize raw book lines;
6. cache for `SERVICE_CACHE_TTL`.

The report and player-evidence requests consume that same context, so evidence loading normally adds no fresh Odds API calls and cannot silently use different lines from the ranking row. Stat metric comparison may request details for multiple selected players, but those HTTP requests reuse the shared backend week context.

## Missing coverage semantics

A player is valid when `project_player()` produces at least one scored stat. Missing an optional expected market does not invalidate the whole player.

No usable priced/scorable markets → `has_projection=false`, null report values and a muted `no priced markets` UI state. Never substitute fabricated zeroes.

## Defense comparison

Defense ranking is intentionally separate from the player-prop model.

`services.list_defenses()`:

- resolves the requested this/next-week window;
- fetches only `spreads,totals`, once per game and concurrently;
- derives each opponent's implied team total independently per book;
- takes the median implied total across books;
- returns all 32 defenses, with BYE teams at the bottom;
- joins Sleeper rosters to mark Available / Yours / Taken.

`defense.py` owns the pure math. Lower opponent implied total is the ranking signal.

Best Lineup also needs a DEF Floor/Mid/Ceiling value. That range uses only Sleeper's points-allowed scoring brackets, with a Normal team-score uncertainty around the market implied total. It does **not** estimate sacks, interceptions, fumble recoveries or defensive touchdowns. Keep that limitation explicit.

## Best lineup

`lineup.py` is pure and has no network knowledge. It accepts already-projected players, the selected roster's owned defenses, and Sleeper `roster_positions`.

A memoized assignment search maximizes the requested target across eligible starter slots. It supports QB/RB/WR/TE/DEF plus FLEX, WRRB_FLEX, REC_FLEX and SUPER_FLEX. Bench/IR/TAXI slots are ignored.

Unsupported starter slots (currently most importantly K) are returned as `unmodeled_slots`; the optimizer must not invent scores just to fill them. Starter positions with no priced candidate are returned as `unfilled_slots`.

## Odds API efficiency

Player props and defense matchup data have separate caches because they use different market sets, but both avoid duplicate calls inside their flow. Defense comparison is loaded only when the user selects Defenses or Best Lineup; it is not an automatic cost on Players.

Best Lineup calls `compute_projections()` and `list_defenses()`, which normally hit in-process caches if those flows are already loaded.

The selected player's `/player/odds` evidence may preload so the inspector is immediately useful. That request shares `_load_week_context()` with `/projections`, so it normally reuses normalized current-week odds rather than triggering a sportsbook fetch for that player. Target movement is always client-only.

## Automated runtime gate

Feature/main CI builds the exact Dockerfile, runs the image, verifies `/health` and `/`, then launches Chromium with Playwright against the production-served React bundle. Browser application-data requests are intercepted with deterministic fixtures, so the smoke test spends zero Odds API quota and does not depend on Sleeper availability.

The runtime smoke covers:

- fresh-browser username → league → team setup and cookie persistence;
- linked player ranking/chart/inspector behavior and Target FP;
- continuous yardage density, discrete exact-value PMF and low-granularity threshold-gauge rendering;
- stat metric evidence, consensus/source-line explanation and sportsbook rows;
- operational odds data mode reaching API requests;
- Change league preserving the active identity when canceled;
- defense comparison;
- Floor/Mid/Ceiling Best Lineup switching and unsupported slots.

This catches broken multi-stage Docker builds, compiled static assets, React wiring and primary interaction regressions. Watchtower/GHCR/Unraid-specific behavior remains an optional deployment smoke test when those systems themselves change.

## Weekly windows

`weekly_windows.resolve_week_windows()` keeps its schedule-aware fallback so a preseason calendar window with no games can still resolve the next posted NFL slate.

## Documentation invariants

- User-visible behavior/endpoints: update README in the same change.
- Architecture/reasoning: update this file.
- Process changes: update CONTRIBUTING explicitly.
- Durable model behavior belongs in `docs/fantasy-projection-methodology.md`.
- Durable UI and visualization behavior belongs in `docs/design.md`; implementation choices stay here.
