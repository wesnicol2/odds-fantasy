# Odds Fantasy — implementation notes

This is the deep implementation document. `README.md` explains how to use the app; `CONTRIBUTING.md` owns process; the methodology spec owns the mathematical contract.

## Product boundary

The application is deliberately narrow:

1. Select a Sleeper league/team.
2. Show QB/RB/WR/TE Floor / Mid / Ceiling for one NFL week.
3. Open one player and inspect the exact sportsbook lines that created the stat distributions and fantasy-points curve.
4. Plot all projected roster players on one shared probability graph.

Lineup optimization, defense ranking, pre-draft boards, book-coverage dashboards, model-comparison tools, and debug-math UIs were removed. They created parallel products and duplicated the same data transformations. Git history preserves them if a future requirement is strong enough to justify reintroducing one deliberately.

## One projection engine

`oddsfantasy.projection.project_player` is the only player projection engine.

The old `range_model.py` adapter exposed several earlier single-anchor models alongside the methodology model. Keeping them selectable made every call site carry a `model` parameter and encouraged UI that compared obsolete models. The current product instead follows the methodology engine directly.

The canonical pipeline is:

`Sleeper roster → planner → Odds API → aggregator → market_math → scoring → projection`

`market_math.py` owns odds-to-distribution work. For each stat it:

- converts decimal prices to implied probabilities;
- de-vigs a book's two-way line before combining books;
- uses the median fair probability at a threshold as the consensus anchor;
- enforces a valid monotone survival curve;
- reconstructs continuous yardage or discrete count distributions.

`projection.py` samples each modeled stat, scores each draw with the league's actual Sleeper rules, sums the stat points, and sorts the resulting fantasy-point samples. Floor / Mid / Ceiling are the 10th / 50th / 90th percentiles of those samples. Sampling uses a fixed seed so unchanged odds do not make the UI jitter.

The model currently assumes marginal stat independence because the feed does not quote the joint distribution. That makes some right tails conservative, especially QB passing yards + passing TDs. Do not invent a correlation matrix without a market source for it.

## Curves are backend data, not UI math

`PlayerProjection.samples` is the source of truth for the fantasy-points curve. `projection.survival_curve()` downsamples those 4,000 sorted samples into a compact `P(FP >= x)` series for transport to the browser.

Both `/projections` and `/player/odds` use that helper. The UI only draws the returned points. It must not fit a Gaussian, reconvolve stat PMFs, or otherwise reconstruct a second projection model.

This replaced the old `ui/prob-curve.js`, which explicitly described itself as placeholder math. It also replaces the older visual that inferred a bell-shaped curve from Floor / Mid / Ceiling alone.

## Shared week context

Odds API calls are the expensive shared resource. `services._load_week_context()` is therefore the center of the application.

For a `(identity, week, region)` key it:

1. resolves the Sleeper roster and scoring rules;
2. fetches the NFL event list once;
3. gives that same event list to the planner (the planner does not fetch it again);
4. fetches each relevant game once, concurrently;
5. normalizes the event responses into per-player raw book lines;
6. caches the resulting Python context for `SERVICE_CACHE_TTL` seconds.

`compute_projections()` and `get_player_odds_details()` consume the same context. Clicking a player after loading the report therefore uses the same source lines and normally costs zero additional Odds API calls.

The browser's `Force fresh` setting applies when loading a report. Player detail requests intentionally reuse the just-loaded in-process context unless an explicit `fresh=1` is sent to the endpoint. This keeps a drill-down internally consistent with the row the user clicked.

## Raw lines and consensus anchors

`aggregator.py` does no prediction math. It only normalizes the raw feed into:

`player alias → bookmaker → market → over/under or alternate lines`

The old parallel `MarketSummary` aggregation was removed because the methodology engine never needed it. `market_math.collect_anchors()` already performs the correct per-book de-vig and across-book median directly from the raw lines.

The player detail endpoint exposes, per contributing stat:

- the stat's 10th / 50th / 90th percentile range;
- expected fantasy-point contribution;
- consensus anchors (`threshold`, fair `P(over)`);
- the exact main and alternate decimal prices from each book.

That is the audit trail from sportsbook lines to the player's probability curve.

## Missing coverage semantics

A player is projectable if `project_player()` produced at least one scored stat distribution and fantasy-point samples. That is represented as `has_projection`.

Missing an expected but unpriced market is not the same as having no projection. The previous backend set `incomplete=true` whenever *any* expected market was absent, while the UI treated `incomplete` as “hide all numbers.” That caused valid players to appear red with dashes even though their drill-down contained usable lines.

The UI no longer paints partial coverage red or suppresses valid numbers. Players with no usable priced/scorable markets show dashes and a muted `no priced markets` note.

## Scope of the report

The report is roster-scoped and includes QB/RB/WR/TE. K and DEF do not use the player-prop methodology and are intentionally excluded rather than displayed with meaningless null projections.

Rows are sorted by Mid descending. The all-player graph uses only players with real curves and keeps everyone on the same fantasy-point x-axis and probability y-axis.

## Identity

The browser stores selected `league_id` and `roster_id` in cookies. Those explicit identifiers are authoritative for projections. Username is used to discover leagues during setup and remains a legacy API fallback, not the preferred downstream identity.

## Season windows

`weekly_windows.resolve_week_windows()` must keep its schedule-aware fallback. During preseason the current calendar fantasy window can contain no games even though the next posted slate is valid. In that case the service should surface the next available scheduled window rather than silently returning an empty report.

## Documentation invariants

- If user-visible behavior or endpoints change, update `README.md` in the same change.
- If architecture or implementation reasoning changes, update this file.
- Do not silently change `CONTRIBUTING.md` or `docs/fantasy-projection-methodology.md`; those are process/spec contracts and require explicit approval.