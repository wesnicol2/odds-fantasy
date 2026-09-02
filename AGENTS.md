# Odds Fantasy — implementation notes

`README.md` explains use, `CONTRIBUTING.md` owns process, and
`docs/fantasy-projection-methodology.md` is the mathematical contract.

## Product boundary

The application has three selectable weekly sections plus player drill-down and graph exploration:

1. **Player report** — QB/RB/WR/TE Floor / Mid / Ceiling from sportsbook props.
2. **Defenses** — all NFL defenses sorted by opponent implied team total, with Sleeper league ownership.
3. **Best lineup** — maximize Floor, Mid, or Ceiling across the league's actual modeled starter slots.
4. Clicking a player exposes the exact source lines.
5. **Graphs** compares roster probability distributions for fantasy points and each available modeled stat, with graph/position/player filters, Previous/Next metric navigation, and sportsbook line provenance.

Pre-draft boards, model-comparison tools, book-coverage dashboards and alternate client-side projection engines remain removed.

## One player projection engine

`oddsfantasy.projection.project_player` is the only player projection engine.

Pipeline:

`Sleeper roster → planner → Odds API → aggregator → market_math → scoring → projection`

`market_math.py` converts/de-vigs prices, takes consensus across books, enforces monotonic survival probabilities and reconstructs stat distributions. `projection.py` samples each modeled stat, scores each draw with Sleeper rules, sums fantasy points and reads 10th/50th/90th percentiles.

Cross-stat correlation is still assumed independent because the market feed does not provide a joint distribution.

## Graphs are presentation-only canonical data

`PlayerProjection.samples` is the source of truth for the fantasy-points distribution. `survival_curve()` downsamples the same samples used for Floor/Mid/Ceiling into `P(FP >= x)` points. The browser derives fixed one-point fantasy-score buckets from that curve for display only.

For individual stat graphs, `oddsfantasy.graph_data.distribution_graph()` reads the already-fitted `StatProjection.distribution` and exposes its survival curve: x is a stat threshold and y is the fitted probability of clearing that threshold. Continuous yardage curves are sampled densely from the distribution's own survival function; count distributions expose their cumulative survival steps. This is display-only and must never refit sportsbook lines or participate in projection sampling/scoring.

`oddsfantasy.line_provenance.fair_line_points()` reuses the exact `_book_anchors()` de-vigging path from `market_math.py` to expose the per-book fair over probabilities immediately before median consensus. It is presentation metadata, not a second odds model. `/player/odds` returns these book points, the final consensus anchors, the fitted stat survival curve, and the unchanged raw source lines together.

The graph UI treats those layers distinctly:

- fitted distribution = solid player-colored curve;
- individual de-vigged book lines = small hollow points at their exact thresholds/probabilities;
- consensus anchors = larger filled points with faint vertical guides;
- collapsed graph-specific drill-down = book, main/alternate source, raw over/under prices and fair over probability.

The stat y-axis stays fixed at 0–100% so different curves remain interpretable as probabilities. The Graph explorer loads cached detail payloads and only filters/draws them. Do not add a second statistical model in JavaScript.

## Shared player week context

`services._load_week_context()` caches the expensive roster/player-prop path for `(identity, week, region)`:

1. resolve Sleeper roster/scoring;
2. fetch the NFL event list once;
3. plan the roster's needed markets from that same event list;
4. fetch each relevant game concurrently once;
5. normalize raw book lines;
6. cache for `SERVICE_CACHE_TTL`.

The report, player details and graph explorer consume that same context, so drill-down/graph loading normally adds no fresh Odds API calls and cannot silently use different lines from the row.

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

Player props and defense matchup data have separate caches because they use different market sets, but both avoid duplicate calls inside their flow. Defense comparison is loaded only when the user selects Defenses or Best Lineup; it is not an automatic cost on the Player Report.

Best Lineup calls `compute_projections()` and `list_defenses()`, which normally hit the in-process caches if those views were already loaded.

Graph explorer lazily requests `/player/odds` only after it is opened. Those requests share `_load_week_context()` with Player Report, so they reuse the current normalized odds context rather than triggering a new sportsbook fetch for each player.

## Automated runtime gate

The old process required a human/agent to exercise the LAN-only Test container. That is not a reliable automation contract.

Feature/main CI now builds the exact Dockerfile, runs the image, verifies `/health` and `/`, then launches Chromium with Playwright against the real served HTML/CSS/JS. Browser API requests for Sleeper/Odds-derived data are intercepted with deterministic fixtures. The smoke test covers:

- player report values;
- player details and sportsbook source lines;
- graph explorer left filter panel, multi-metric loading, metric cycling and position filtering;
- stat-graph sportsbook book points, consensus anchors, labeled survival axis and line-provenance drill-down;
- defense comparison;
- Floor/Mid/Ceiling Best Lineup switching.

This catches broken Docker entrypoints, static assets, JavaScript wiring and primary interaction regressions without consuming Odds API quota or depending on the home LAN. Watchtower/GHCR/Unraid-specific behavior remains an optional deployment smoke test when those systems themselves change.

## Identity and weekly windows

`league_id` + `roster_id` cookies are authoritative after setup. Username is primarily league discovery and a legacy fallback.

`weekly_windows.resolve_week_windows()` keeps its schedule-aware fallback so a preseason calendar window with no games can still resolve the next posted NFL slate.

## Documentation invariants

- User-visible behavior/endpoints: update README in the same change.
- Architecture/reasoning: update this file.
- Process changes: update CONTRIBUTING explicitly.
- Durable model behavior belongs in `docs/fantasy-projection-methodology.md`.
