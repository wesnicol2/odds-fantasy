# Odds Fantasy — UI Design Contract

## Purpose

Odds Fantasy is a decision-support application for fantasy football.

The interface exists to help a user answer a small set of questions quickly:

1. What should I do with my lineup this week?
2. Which bench decisions are actually close?
3. Is there a defense I should use or acquire now for this week or next week?
4. What outcomes should I expect from a player?
5. What is the probability a player reaches a score or stat value I care about?
6. Why does the model believe what it believes, and what sportsbook evidence supports it?

The UI should feel like a **professional analytical workstation**, not a sportsbook, fantasy-news site, generic SaaS dashboard, or collection of unrelated cards.

This document defines product UI and visualization behavior independently of any frontend framework, component library, charting library, or rendering technology. Implementation choices belong in `AGENTS.md`.

---

## Core product rule: decision first, detail on demand

Simplicity is a workflow requirement, not merely a visual preference.

Every default surface should answer one dominant question with the minimum information needed to make the next decision. Additional explanation, evidence, controls, and raw data should appear only when the user deliberately drills down.

Use this test before adding permanent UI:

> **Does the user need this before making the next decision?**

If not, the information belongs one level deeper.

The default hierarchy is:

**decision → comparison/distribution → explanation → raw evidence**

Do not reverse that hierarchy merely because the underlying model is complicated.

Prefer **selection → reveal** over adding more permanent panels, cards, metrics, or controls. Avoid generic KPI tiles, decorative summaries, and charts that do not change a decision.

---

## Design principles

### 1. One dominant task per destination

The four primary destinations each have a clear job:

- **Dashboard** — What should I do?
- **Players** — Why do I believe this player projection, and how do players compare?
- **Defenses** — Which defense should I use or acquire?
- **Lineup** — What is my optimized roster for the selected objective?

A destination may contain sophisticated tools, but its default surface should not compete with itself for attention.

### 2. One linked analytical workspace for Players

Tables, charts, filters, and evidence are not separate products.

On desktop, the Players experience behaves as one coordinated workstation:

**ranking/list ↔ visualization ↔ inspector/evidence**

Selecting or inspecting information in one region updates or highlights related information in the others without modal navigation or losing context.

### 3. Dense, not cluttered

Odds Fantasy is a data application. High information density is desirable when the information is decision-relevant.

Prefer:

- compact tables and rows;
- aligned numbers;
- restrained spacing;
- clear grouping;
- small controlled typography;
- thin separators;
- progressive disclosure.

Avoid creating a card for every value simply to add visual separation. Whitespace should clarify hierarchy, not reduce useful information visible on screen.

### 4. Numbers are the interface

Numerical information must be easy to compare.

Numeric data should:

- use tabular numerals;
- align consistently;
- use consistent precision and units;
- distinguish missing values from zero;
- avoid visually exaggerated precision unsupported by the model.

Never display a missing projection as `0`. Use `—` or an explicit unavailable state.

### 5. Uncertainty is first-class

Odds Fantasy does not produce one definitive player value.

Floor / Mid / Ceiling, target probabilities, and probability distributions are core product concepts. Do not collapse them into one misleading "projection" when uncertainty matters to the decision.

### 6. Evidence is inspectable, not permanently noisy

Users should be able to move naturally from:

**projection → distribution → consensus market evidence → individual sportsbook lines**

The evidence should be available without permanently consuming the primary comparison area.

Visualizations are presentations of canonical backend model data. The frontend must not invent a second probability or lineup model.

### 7. Color communicates meaning

Use color primarily for:

- active selection;
- stable player/series identity;
- semantic status;
- warnings/errors;
- limited emphasis.

Do not use multiple unrelated accent colors merely to decorate sections. Do not rely on color alone to communicate meaning.

---

## Application structure

The app is one persistent application shell with four destinations, not separate copies of the application for each week.

### Primary destinations

1. **Dashboard**
2. **Players**
3. **Defenses**
4. **Lineup**

### Week is context, not a destination

Players, Defenses, and Lineup each accept a week context:

- **This week**
- **Next week**

Do not create separate top-level destinations such as “This Week Players” and “Next Week Players.”

Dashboard is intentionally different: it synthesizes the current lineup decision and a two-week defense-planning horizon, so it does **not** have a global week switch.

### Persistent shell

The application identity, league/team context, primary navigation, and operational settings should remain stable while the central destination changes.

Switching destinations should feel like changing modes inside one workstation rather than loading a disconnected page.

Meaningful navigation state should work with browser Back/Forward. Returning to Players should preserve relevant analytical state such as selected players, filters, metric, selected player, and target when practical rather than resetting the workstation.

Navigation itself must not trigger provider work unrelated to the destination being opened.

---

## Navigation

### Desktop

Use a compact horizontal primary navigation strip:

**Dashboard | Players | Defenses | Lineup**

Do not use a permanent left sidebar. The Players visualization benefits directly from horizontal width, and navigation should not compete with the graph for that space.

The current destination must be visually obvious but restrained.

For Players, Defenses, and Lineup, place the compact **This week / Next week** context control beneath or adjacent to the primary shell rather than mixing it with destination navigation.

### Mobile

Use the same four destinations in a persistent bottom navigation bar:

**Dashboard | Players | Defenses | Lineup**

This keeps destination switching reachable without shrinking the visualization horizontally.

The week selector remains page context near the content, not another bottom-navigation destination.

### Motion

The shell should remain stationary while destination content changes. A very short opacity transition may be used to soften the change, but navigation should feel fast because state is preserved and unnecessary reloads are avoided—not because of elaborate animation.

Honor `prefers-reduced-motion`.

---

## Dashboard

Dashboard is the default landing destination and the most opinionated surface in the product.

Its job is to answer in roughly ten seconds:

> **Who should I start, how close are the marginal lineup decisions, and is there a defense I should pick up?**

Dashboard is synthesis, not a second analysis engine.

### Default content

The initial Dashboard should contain only three decision areas:

1. **This week's ideal lineup**
2. **Bench pressure**
3. **Defense planning for this week and next week**

Do not add generic player rankings, sportsbook charts, quota configuration, broad league statistics, or decorative KPIs to the default Dashboard.

### This week's ideal lineup

Show the backend optimizer's **Mid** lineup for the current week.

Primary information:

- starter slot;
- player/defense;
- position/team context where useful;
- projected Mid value;
- total projected lineup value.

The Dashboard recommendation is intentionally concise. Floor/Ceiling alternatives and optimizer controls belong in Lineup.

A clear drill-down action should open Lineup in **This week / Mid** context.

### Bench pressure

Bench pressure should show only the closest marginal decisions, not the entire bench by default.

The authoritative measure is backend optimizer opportunity cost:

1. calculate the unconstrained ideal lineup;
2. force a bench player into an eligible starter slot;
3. re-optimize the remaining slots;
4. report the total projected value lost relative to the unconstrained ideal.

The displayed **FP back** value is that loss.

This is preferable to simply subtracting one player's raw projection from another because FLEX/SUPER_FLEX eligibility and global slot interactions can change the correct comparison.

When available, identify which current starter the bench player would displace. For example:

**Player B · 1.2 FP back · behind Player A**

The browser must not recreate optimizer eligibility logic to derive this value.

Selecting a bench-pressure row drills into Players for **This week** and opens a focused start/sit comparison between the bench player and the optimizer-identified starter they would displace. Preserve `FP back` as the optimizer's whole-lineup opportunity cost; do not relabel it as a raw difference between the two player projections.

The comparison inspector should show:

- the optimizer's current recommendation and lineup-level `FP back` context;
- a weekly tie-breaker matrix with aligned Floor / Mid / Ceiling / Mean values for both players;
- this game's opponent, kickoff, spread, total and team implied total when the market supplies them;
- an aligned union of this week's modeled props with each stat's signed expected fantasy-point contribution;
- the same modeled props measured a second way, in raw stat value rather than league points, using each market's backend 10th / median / 90th percentiles;
- a visible edge marker on the better comparable value and a count of row wins;
- missing markets as `—`, distinct from a modeled zero-point contribution;
- a direct stat action that changes the shared chart to compare both fitted stat distributions;
- a direct return from the stat drill-down to the full matrix.

Fantasy points and stat value are two measurements of the same week, so both use the same visual language: the Floor / Mid / Ceiling thermometer already used by the ranking table. Every thermometer marks all three percentiles, and the two players in one row share a single zero-anchored scale so the glyphs read as magnitudes rather than as a zoomed-in gap. A thermometer is presentation only — it places backend percentiles on a scale and never derives a value the backend did not supply.

Fantasy-point and stat-value signals are counted as two separate tallies and must never be merged into one number: a stat and the points it produces are the same underlying market, so adding them would double-count it. Stat-value direction follows league scoring rather than assuming more is better — where the modeled contribution is negative (interceptions), the smaller weekly stat wins the row.

Every matrix input must apply directly to the selected week. Do not show ADP, draft rank, team season-win totals, rest-of-season projections, multi-week strength of schedule or any other draft/long-horizon statistic. Spread is context rather than a scored row because favorable game script is position-dependent. Tied or missing values award neither player a row win. Row-win counts are a transparent scan aid, not a confidence score and not a replacement for the backend optimizer.

This is a focused explanation mode inside the existing Players workstation, not a separate destination or browser-side start/sit model. Exiting comparison restores the normal selected-player inspector without discarding the narrowed two-player chart context.

### Defense planning

Show two short ranked groups:

- **This week**
- **Next week**

Each group should show only a few defenses that are either:

- available in the fantasy league; or
- already owned by the user.

Preserve the backend defense ranking order. Do not create a second browser-side defense-ranking formula.

Primary information:

- defense identity;
- opponent;
- opponent implied team total;
- status: **Yours** or **Available**.

Do not show defenses owned by another team in the Dashboard shortlist. They remain inspectable in the full Defenses destination.

Each group should provide a quiet drill-down to Defenses in the corresponding week context.

### Dashboard visual treatment

The Dashboard should read as a compact decision sheet, not a grid of dashboard cards.

Prefer:

- one clear heading;
- compact rows;
- simple separators;
- two-column desktop grouping when useful;
- one-column mobile flow;
- no charts by default;
- no decorative gauges or scorecards.

---

## Players

Players is the detailed projection-analysis workstation.

Its default mental model is:

**ranking/list ↔ probability visualization ↔ inspector/evidence**

### Desktop workstation

The preferred desktop layout is a coordinated three-region surface:

1. **Ranking/list region** — player comparison, filters, Floor / Mid / Ceiling, compact uncertainty cues, and Target probability when active.
2. **Visualization region** — the dominant probability chart and metric controls.
3. **Inspector region** — the selected player's summary, relevant model details, and progressively disclosed sportsbook evidence.

The visualization should receive the largest share of width after the ranking remains comfortably scannable.

Selecting a player must not obscure or destroy ranking/chart context.

### Coordinated selection

A player selected in the ranking becomes active in the inspector and is emphasized in the visualization.

A player emphasized through the visualization should remain identifiable in the ranking.

Pointer hover may cross-highlight temporarily; selection remains explicit and persistent.

Filtering players or positions updates coordinated views consistently.

Stable player identity should be retained across compatible metrics.

When one player is primary, secondary series should remain clearly visible rather than disappearing. Secondary lines should use approximately a **15% brightness reduction** relative to the primary series, not a large opacity reduction.

### Primary ranking information

Primary player-row information includes:

- Player
- Position / team / matchup context
- Floor
- Mid
- Ceiling
- Target probability when Target mode is active

Rows with unavailable projections remain visible but de-emphasized with an explicit reason.

### Inline uncertainty cue

A compact Floor / Mid / Ceiling interval may supplement the numeric values when space permits:

- Floor = low endpoint
- Ceiling = high endpoint
- Mid = central marker

It supplements the numbers rather than replacing them.

---

## Defenses

Defenses is the complete defense-acquisition analysis.

Primary information:

- Defense
- Opponent
- Opponent implied team total
- Ownership state

Lower opponent implied total represents the better matchup under the current defense model.

Ownership states must distinguish:

- **Available**
- **Yours**
- **Taken**

BYE teams remain visible and sort below playable defenses.

Dashboard exposes only a small actionable subset. Defenses is where the user inspects the complete market.

---

## Lineup

Lineup is the detailed optimizer recommendation surface.

The user can optimize for:

- **Floor**
- **Mid**
- **Ceiling**

The selected objective must be obvious.

The result should emphasize:

1. starter slot;
2. chosen player or defense;
3. projected value for the selected objective;
4. total projected lineup value.

Unsupported or unfilled roster slots must be stated explicitly rather than silently filled with invented values.

When switching objectives, changed lineup slots should be easy to identify. Subtle transition is acceptable if it helps comparison but must never delay it.

Dashboard consumes the current-week Mid conclusion from this same optimizer rather than implementing separate browser-side lineup logic.

---

## Visual language

### Character

The application should feel:

- analytical;
- calm;
- compact;
- precise;
- modern;
- trustworthy;
- powerful without appearing complicated for its own sake.

It should not feel:

- promotional;
- playful;
- casino-like;
- excessively futuristic;
- gamified.

### Theme

The primary design is dark-first.

Use a small semantic palette for:

- page background;
- surfaces;
- primary/secondary/subtle text;
- borders;
- primary accent;
- positive/warning/destructive state.

Surfaces should be separated primarily through hierarchy, spacing, and subtle borders rather than strong shadows.

### Typography

Use a highly legible UI sans-serif with a restrained hierarchy.

Do not create oversized editorial headings in data-heavy surfaces.

Use tabular numerals for comparable values.

### Borders, elevation, and corners

Prefer thin separators, subtle borders, and restrained background changes.

Use shadows only for genuinely floating elements such as menus and dialogs.

Avoid stacks of floating analytical cards.

Use moderate radii consistently. Pill treatment is appropriate for compact semantic statuses, not for every control or container.

---

## Tables and ranking lists

Tables are a core UI primitive, not a fallback.

Use tables or dense table-like lists when users benefit from scanning repeated attributes across players or defenses.

Requirements:

- stable column positions;
- right-aligned numeric values where appropriate;
- tabular numerals;
- clear hover/focus/selected states;
- readable compact row density;
- sticky headers where long lists justify them;
- horizontal behavior designed intentionally for narrow screens.

Do not make a column look sortable unless sorting exists.

Important columns should not shift as data loads or changes.

---

## Probability visualization contract

Visualization is analytical software, not decoration.

Every chart must clearly communicate:

- x-axis meaning;
- y-axis meaning;
- units;
- series identity;
- special markers or thresholds.

A user should not need to infer axis semantics from surrounding prose.

Grid lines should aid estimation without dominating the graph.

Exact values should be inspectable through hover, focus, tap, keyboard interaction, direct labels, or an equivalent method. Important information must not require pointer hover alone.

### Canonical-data rule

All visualization forms are presentations of canonical backend model data.

The frontend may perform explicitly allowed display transformations, but it must not refit sportsbook evidence, sample a second probability model, or recreate backend business semantics.

---

## Fantasy-point distribution

The primary fantasy-points comparison chart shows score probability mass:

**P(Fantasy Points = x)**

In practice, `x` denotes a one-point fantasy-score bucket centered on the displayed value. Exact equality on a continuous Monte Carlo sample is not a stable visual quantity, so the one-point bucket is the user-facing equality meaning.

Requirements:

- x-axis = fantasy-score bucket center;
- y-axis = probability of landing in that one-point bucket;
- y-axis begins at zero and scales to visible mass;
- default x-axis focuses on the central probability mass rather than extreme near-zero tails;
- a manually chosen Target FP outside the focused domain expands the view enough to keep the target visible.

The displayed distribution may be bell-like, skewed, discretized, or multi-peaked. Do not force a mathematically false normal curve merely for appearance.

---

## Target FP

Target FP asks:

> **What is the probability this player scores at least X fantasy points?**

It uses:

**P(Fantasy Points ≥ target)**

The user may choose the threshold through direct chart manipulation and/or an accessible numeric control.

The chart should show a clear target reference. Ranking/list context should also expose the resulting target probability so players can be compared without manually reading every curve.

Changing Target FP must update already-loaded data immediately and must not trigger a sportsbook refetch.

Target probability remains derived from the backend-supplied fantasy survival curve; the probability-mass chart does not redefine Target semantics.

Target selection should not erase player, position, week, or metric context.

---

## Individual-stat chart taxonomy

Individual stat metrics use one of three visualization classes according to the support of the modeled variable.

### 1. Continuous density

Use for yardage metrics.

- x-axis = stat value;
- y-axis = `P(x)` probability density;
- player series are smooth curves;
- y-axis begins at zero and scales to visible density.

The backend supplies a dense display series derived from the canonical fitted distribution. Sparse sportsbook line availability must not create artificial zero-probability holes or narrow spikes in the displayed curve.

A continuous density is not cumulative probability. Do not plot cumulative consensus `P(X ≥ x)` anchors at their probability heights on this y-axis.

Far-right numerical tails with negligible mass must not force hundreds of pixels of empty graph space. The default display domain should focus on meaningful probability mass while preserving the underlying data.

### 2. Discrete high granularity

Use for integer-count metrics with enough support to compare shape, including receptions and supported rush-attempt/touch metrics.

- x-axis = integer value;
- y-axis = exact `P(X = x)`;
- every integer outcome retains an explicit point marker;
- a visually smoothed connecting line may aid multi-player comparison;
- smoothing is presentation-only and must not imply probability mass at non-integer outcomes.

The y-axis begins at zero and scales to visible mass.

### 3. Discrete low granularity

Use for sparse count metrics such as passing TDs, anytime TDs, and interceptions.

The primary visual form is a compact group of narrow vertical threshold gauges resembling thermometers.

- each gauge represents one useful threshold such as `1+`, `2+`, `3+`;
- each gauge uses a fixed 0%–100% vertical scale;
- every compared player has a horizontal marker at `P(X ≥ threshold)`;
- exact probability and player identity are directly inspectable and labeled where space permits;
- gauges should be packed closely together as one comparison unit rather than spread across unused horizontal space;
- stop adding thresholds once they are no longer decision-useful.

These are analytical comparison scales, not decorative speedometers.

---

## Axis scaling interactions

Continuous-density and high-granularity line charts support responsive axis-specific rescaling.

### Touch

- Pinching directly on the x-axis changes only the x scale.
- Pinching directly on the y-axis changes only the y scale.
- Scaling updates continuously with the gesture.
- Touch behavior elsewhere should remain available for normal page/chart interactions.

### Mouse / trackpad

Wheel or trackpad zoom over an axis should rescale that axis around the pointer position.

### Keyboard

When the corresponding axis control is focused:

- `+` zooms in;
- `-` zooms out;
- `0` or an equivalent reset command restores the default domain.

Axis zoom is a viewing operation only. It must not alter the canonical distribution or trigger new provider data.

Low-granularity threshold gauges keep their meaningful fixed 0%–100% probability scale and do not need the same free-axis zoom interaction.

---

## Betting-market evidence

The visualization and inspector expose conceptually different quantities that must remain mathematically consistent.

### Fitted distribution presentation

The active density, PMF, or threshold-gauge view is the primary presentation of the canonical fitted distribution.

### Consensus anchors

Consensus sportsbook anchors are cumulative survival probabilities:

**P(X ≥ threshold)**

They belong in explanation/evidence surfaces when the active graph y-axis is density or exact PMF because the units are different.

Do not overlay a survival probability at its percentage height on a `P(x)` or `P(X=x)` chart.

### Exact source-book thresholds

Exact sportsbook line locations may be shown as restrained x-axis evidence markers on compatible density/PMF charts.

Source-book thresholds should not determine curve shape or introduce holes in continuous plots.

### Explain betting lines

Detailed evidence should be progressively disclosed and may include:

- consensus thresholds and probabilities;
- book identity;
- source type;
- line point;
- over/under prices.

Evidence should remain linked to the currently selected player without becoming a second graphing system.

---

## Inspector behavior

The inspector exists for explanation, not duplication.

It should answer, as needed:

- Which player is selected?
- What are Floor / Mid / Ceiling?
- What is the Target probability?
- Which stats contribute to the mean fantasy-point total, and by exactly how many expected points?
- What sportsbook evidence supports the fit?

When fantasy points is the active metric, show the selected player's additive per-stat expected-point contributions in the inspector. Order them by absolute impact so the primary sources are immediately obvious, retain signed values so penalties are explicit, and keep zero-point modeled stats visible. Selecting a contribution opens that stat's probability visualization and evidence; the stat drill-down retains its expected-point contribution and provides a direct return to the complete breakdown.

Label this as a breakdown of the **mean**. Expected values add across stats; per-stat quantiles do not generally add to the player's Floor, Mid or Ceiling. The interface must not present a mathematically false quantile decomposition.

Do not permanently expand raw sportsbook rows when the user only needs the projection.

The inspector should preserve current ranking/chart context rather than opening a modal that replaces it on desktop.

---

## Filters and analytical controls

Keep distinctions clear between:

- **navigation** — Dashboard / Players / Defenses / Lineup;
- **page context** — This week / Next week;
- **filters/comparison state** — positions and selected players;
- **analytical lens** — metric and Target FP;
- **optimizer objective** — Floor / Mid / Ceiling;
- **operations/settings** — data refresh/cache mode and league selection.

Do not style all of these as equally prominent controls.

Operational controls belong outside the primary decision hierarchy.

---

## Loading, empty, and error states

A data application must remain understandable when data is incomplete.

### Loading

Loading states should preserve layout where practical to avoid large shifts.

Use concise status language. Avoid blocking overlays when part of the application can remain useful.

### Missing market coverage

A player with no usable priced markets remains visible with missing values and an explicit state such as `no priced markets` rather than being silently removed or shown as zero.

### Dashboard partial data

If one Dashboard area cannot load, do not invent replacement values. Preserve other successfully loaded decision areas when possible and show a compact local explanation.

### Errors

Error text should explain what failed in user-relevant terms without flooding the normal interface with technical details.

---

## Responsive behavior

Responsive design is intentional, not a shrunken desktop layout.

### Dashboard

Desktop may place lineup/bench pressure beside defense planning. Narrow screens should flow them vertically in decision order.

### Players

Desktop keeps the ranking → visualization → inspector workstation.

On smaller screens, preserve the logical order and allow focused inspection without attempting to squeeze all three desktop regions side by side.

The chart must retain enough height and width to be useful. Controls should wrap or become horizontally scrollable where appropriate rather than crushing the visualization.

### Navigation

Desktop uses compact horizontal navigation. Mobile uses persistent bottom navigation.

Ensure fixed mobile navigation does not cover the end of page content.

---

## Accessibility

All primary functionality must be available without relying exclusively on pointer hover, color, or fine motor precision.

Requirements include:

- semantic landmarks and headings;
- meaningful button labels;
- visible keyboard focus;
- keyboard-operable navigation and controls;
- accessible alternatives for chart interactions;
- explicit selected states;
- sufficient contrast;
- `aria-current` or equivalent for the active destination where appropriate;
- semantic fieldsets/legends for grouped controls such as week or metric selectors;
- reduced-motion support.

Charts should expose a meaningful accessible label that describes their semantics, not autogenerated implementation noise.

---

## Performance and data-use behavior

The interface should feel immediate because it preserves useful state and reuses already-loaded canonical data.

Do not refetch sportsbook/provider data merely because the user:

- changes Target FP;
- changes chart scale;
- selects/hover a player;
- navigates away and back to a previously loaded compatible view.

Dashboard legitimately spans more data than an individual detailed destination, but it should reuse backend/frontend caches where possible rather than creating duplicate provider calls.

Smooth navigation means primarily:

- no unnecessary remount/reset;
- no unnecessary provider work;
- no flicker from preventable full-page loading;
- state restoration on return.

---

## Content style

Use concise language oriented toward decisions.

Prefer:

- `1.2 FP back`
- `Available`
- `Yours`
- `Opponent implied`
- `Chance of ≥ 20 FP`

over lengthy explanatory prose in the default interface.

Detailed mathematical explanation belongs in drill-down/evidence surfaces and documentation.

Avoid hype, gambling language, or claims of certainty unsupported by the model.

---

## Anti-patterns

Do not introduce the following without an explicit product decision:

- a permanent left navigation sidebar that reduces graph width;
- separate top-level pages for every week/destination combination;
- a generic card-heavy dashboard;
- decorative charts or KPI tiles on Dashboard;
- raw sportsbook evidence on every default row;
- browser-side lineup eligibility or defense-ranking formulas;
- a second client-side projection model;
- cumulative survival anchors plotted at incompatible heights on density/PMF charts;
- continuous curves whose shape is determined by gaps between sportsbook thresholds;
- low-granularity threshold gauges spread across excessive empty width;
- secondary comparison lines faded so aggressively that they cannot be compared;
- animation that delays decisions;
- hidden missing data represented as zero.

---

## Design QA checklist

Before considering a user-facing UI change complete, verify:

### Application structure

- Does the change preserve the four-destination mental model?
- Is week treated as context rather than duplicate navigation where appropriate?
- Does browser Back/Forward preserve meaningful navigation context?
- Does returning to Players retain useful analytical state?

### Simplicity

- Is the default surface showing only information required for the next decision?
- Could any new permanent control, metric, card, or chart move one level deeper?
- Is there one obvious dominant task on the destination?

### Dashboard

- Is the current Mid ideal lineup immediately readable?
- Is bench pressure optimizer-derived rather than a raw projection subtraction?
- Are only a few actionable Available/Yours defenses shown for both weeks?
- Do drill-downs open the corresponding detailed destination/context?

### Players

- Do ranking, chart, filters, and inspector remain linked?
- Are secondary series still clearly visible when one player is primary?
- Do existing Target FP and sportsbook-evidence behaviors remain intact?

### Visualization semantics

- Does each chart's y-axis match the metric taxonomy?
- Are continuous curves dense/smooth without sportsbook-gap artifacts?
- Are PMF integer points preserved?
- Are threshold gauges using `P(X ≥ x)` and packed compactly?
- Are incompatible cumulative anchors kept out of density/PMF y-axes?
- Does axis zoom alter only the intended viewing scale?

### Responsive/accessibility

- Does mobile navigation remain reachable without covering content?
- Does Players retain useful visualization space?
- Are controls keyboard/touch accessible?
- Are focus, selection, and semantic states understandable without color alone?

### Data integrity

- Is missing data distinct from zero?
- Is the backend still authoritative for projections, lineup eligibility, defense ranking, and probability semantics?
- Does a display interaction avoid unnecessary provider requests?

---

## Change control

This file is the durable UI contract for Odds Fantasy.

When a user-visible workflow or visualization rule changes materially, update this document in the same feature so future implementation work does not regress the product model.

Implementation-specific framework, component, state, cache, and deployment choices belong in `AGENTS.md`.
