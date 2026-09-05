# Odds Fantasy — implementation notes

`README.md` explains use, `CONTRIBUTING.md` owns process,
`docs/fantasy-projection-methodology.md` is the mathematical contract, and
`docs/design.md` is the UI/visualization contract.

## Product boundary

The application has three selectable weekly sections plus player drill-down and graph exploration:

1. **Player report** — QB/RB/WR/TE Floor / Mid / Ceiling from sportsbook props.
2. **Defenses** — all NFL defenses sorted by opponent implied team total, with Sleeper league ownership.
3. **Best lineup** — maximize Floor, Mid, or Ceiling across the league's actual modeled starter slots.
4. Clicking a player exposes the exact source lines.
5. **Graphs** compares roster probability distributions for fantasy points and each available modeled stat, with graph/position/player filters and Previous/Next metric navigation.

Pre-draft boards, model-comparison tools, book-coverage dashboards and alternate client-side projection engines remain removed.

## One player projection engine

`oddsfantasy.projection.project_player` is the only player projection engine.

Pipeline:

`Sleeper roster → planner → Odds API → aggregator → market_math → scoring → projection`

`market_math.py` converts/de-vigs prices, takes consensus across books, enforces monotonic survival probabilities and reconstructs stat distributions. `projection.py` samples each modeled stat, scores each draw with Sleeper rules, sums fantasy points and reads 10th/50th/90th percentiles.

Cross-stat correlation is still assumed independent because the market feed does not provide a joint distribution.

## Graphs are presentation-only canonical data

`PlayerProjection.samples` is the source of truth for the fantasy-points distribution. `survival_curve()` downsamples the same samples used for Floor/Mid/Ceiling into `P(FP >= x)` points. The browser derives fixed one-point fantasy-score buckets from that curve for display only.

For individual stat graphs, `oddsfantasy.graph_data.distribution_graph()` reads the already-fitted `StatProjection.distribution` and emits a display-only survival curve. Continuous stats evaluate the fitted distribution's own survival function across its central range, including fitted anchor x-values. Count stats expose cumulative `P(count >= x)` values as a step curve. This graph helper must never refit sportsbook lines or participate in projection sampling/scoring.

`/player/odds` already includes the stat graph points alongside the stat's consensus anchors and exact source sportsbook lines. The Graph explorer places those three pieces on one explainability surface:

- solid player-colored line = fitted survival curve;
- diamond = de-vigged cross-book consensus anchor at its sportsbook threshold;
- short x-axis tick = an exact source-book line location.

The stat graph y-axis is fixed to probability and the x-axis is the stat threshold, so anchors and the fitted curve share the same semantics. `Explain betting lines` expands the same cached payload into a per-player table of consensus probabilities plus raw book/line/over/under prices. The browser only maps existing backend evidence to pixels; it does not calculate a replacement probability model.

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
- stat graph fitted curve, consensus markers, exact sportsbook threshold markers and betting-line explanation panel;
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
- Durable UI and visualization behavior belongs in `docs/design.md`; implementation choices stay here.
