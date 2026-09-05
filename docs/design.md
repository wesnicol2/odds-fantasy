# Odds Fantasy — UI Design Contract

## Purpose

Odds Fantasy is a decision-support application for fantasy football.

The interface exists to help a user answer questions quickly:

1. What outcomes should I expect from my players?
2. Which players or defenses are preferable?
3. What lineup best matches the level of risk I want?
4. What is the probability a player reaches a score I care about?
5. Why does the model believe what it believes?
6. What sportsbook evidence supports the model?

The UI should feel like a **professional analytical workstation**, not a sportsbook, fantasy-news site, or generic SaaS dashboard.

This document defines the product's UI and visualization behavior independently of any frontend framework, component library, charting library, or rendering technology.

Implementation choices belong in `AGENTS.md`, not here.

---

## Design principles

### 1. Decision first

The most important information should require the least interaction.

A user should not need to open a detail panel to answer basic fantasy decisions.

For player projections, the primary decision data is:

- Player
- Position / team / opponent context
- Floor
- Mid
- Ceiling
- Probability of reaching a user-selected target when Target mode is active

Supporting evidence belongs progressively deeper in the interface.

The hierarchy is:

**Decision → distribution → explanation → raw evidence**

Do not reverse this hierarchy merely because the underlying data model is complicated.

### 2. One linked analytical workspace

Tables, charts, filters, and evidence are not separate products.

On desktop, the primary player-analysis experience should behave as one coordinated workspace. Selecting or inspecting information in one view should update or highlight the related information in the others without forcing the user through modal navigation.

The default mental model is:

**ranking/list ↔ visualization ↔ inspector/evidence**

The user should be able to move between comparison and explanation without losing context.

### 3. Dense, not cluttered

Odds Fantasy is a data application. High information density is desirable.

Prefer:

- compact tables;
- aligned numbers;
- restrained spacing;
- clear grouping;
- meaningful typography;
- progressive disclosure.

Avoid creating a card for every value simply to add visual separation.

Whitespace should clarify structure, not reduce the amount of useful information visible on screen.

### 4. Numbers are the interface

Numerical information must be especially easy to compare.

Numeric columns must:

- be right-aligned where appropriate;
- use tabular numerals;
- use consistent precision;
- preserve consistent units;
- visually distinguish missing values from zero.

Never display a missing projection as `0`.

`—`, an explicit unavailable state, or a short explanation is preferable.

### 5. Uncertainty is first-class

Odds Fantasy does not produce a single definitive player value.

Floor / Mid / Ceiling, target probabilities, and probability distributions are core product concepts and must never be visually reduced to a single "projection" without context.

The interface should make uncertainty understandable without making it intimidating.

### 6. Evidence should be inspectable

The product derives information from betting markets.

Users should be able to move naturally from:

**projection → curve → consensus market evidence → individual sportsbook lines**

without encountering a second, contradictory representation of the same model.

Visualizations are presentations of canonical backend model data. The frontend must not invent a separate probability model.

### 7. Color communicates meaning

Color must not exist merely to decorate the application.

Use color primarily for:

- active selection;
- stable player/series identity;
- semantic state;
- emphasis;
- warnings/errors.

Do not use multiple unrelated accent colors simply to make sections appear visually distinct.

Do not rely on color alone to communicate meaning.

---

## Desktop analytical workstation

The preferred desktop player-analysis layout is a coordinated three-region workspace:

1. **Ranking/list region** — player comparison, filters, Floor / Mid / Ceiling, compact uncertainty glyphs, and Target probability when active.
2. **Visualization region** — the dominant probability chart and metric controls.
3. **Inspector region** — the selected player's summary, relevant model details, and progressively disclosed sportsbook evidence.

These regions may resize or collapse based on viewport size, but they should behave as parts of one analytical surface rather than independent modal experiences.

The visualization should receive the largest share of available width after the ranking list remains comfortably scannable.

The inspector may collapse when nothing is selected, but selecting a player should not obscure or remove the primary ranking and graph context.

### Coordinated selection

A player selected in the ranking/list should become the active player in the inspector and be emphasized in the visualization.

A player emphasized through the visualization or legend should be identifiable in the ranking/list.

Where pointer hover exists, cross-highlighting should be immediate but temporary. Selection should remain explicit and persistent.

Filtering players or positions should update all coordinated views consistently.

Series identity should remain stable across compatible metrics whenever practical.

---

## Information architecture

The application has three primary decision sections plus the integrated analytical workspace.

### Player Report

The default section.

Its purpose is rapid comparison of the user's relevant players while keeping their probability distributions immediately available.

Primary row information:

- Player
- Position / matchup context
- Floor
- Mid
- Ceiling
- Compact uncertainty visualization
- Target probability when Target mode is active

`Mid` is the default numeric anchor but Floor and Ceiling must remain immediately comparable.

Rows with incomplete or unavailable projections remain visible but visually de-emphasized with an explicit reason.

Selecting a player updates the inspector and visualization without losing the user's place in the report.

### Inline uncertainty glyph

Player rows should include a compact visual representation of the Floor / Mid / Ceiling range when space permits.

The glyph should communicate:

- Floor as the low endpoint;
- Ceiling as the high endpoint;
- Mid as the central marker.

It supplements the actual numbers rather than replacing them.

Its purpose is rapid visual comparison of uncertainty width and upside/downside shape across many rows.

Do not use area, color saturation, or decorative effects that make the glyph harder to compare than a simple interval representation.

### Defenses

A ranking surface for defensive matchup quality.

Primary information:

- Defense
- Opponent
- Opponent implied team total
- Ownership state

Lower implied opponent total represents the better matchup.

Ownership states must be distinguishable as:

- Available
- Yours
- Taken

BYE teams remain visible and sort below playable defenses.

### Best Lineup

A recommendation surface rather than another general player table.

The user can optimize for:

- Floor
- Mid
- Ceiling

The selected objective must be obvious.

The result should emphasize:

1. starter slot;
2. chosen player or defense;
3. projected value for the selected objective;
4. total projected lineup value.

Unsupported or unfilled roster slots must be stated explicitly rather than silently filled with invented values.

When switching optimization objectives, the UI should make changed lineup slots easy to identify. Where useful, it may explain the tradeoff that caused a change, such as higher ceiling at the expense of floor.

Subtle transition is acceptable when it helps the user perceive changed slots. Animation must never delay comparison.

---

## Visualization workspace

Visualization is a first-class part of the primary analytical experience, not an optional secondary modal.

On sufficiently large screens, the user should be able to simultaneously see:

- the relevant player list or ranking;
- metric selection;
- player/position filtering;
- the active visualization;
- legend or direct labels;
- selected-player context;
- access to supporting sportsbook evidence.

Detailed evidence is progressively disclosed rather than permanently consuming the graph area.

The graph must not be constrained to an unnecessarily small viewport.

---

## Navigation and controls

Use a clear visual distinction between:

- navigation;
- filtering;
- analytical mode;
- actions.

Controls that switch between mutually exclusive states should use segmented controls, tabs, or equivalent single-selection patterns.

Examples:

- Player Report / Defenses / Best Lineup
- This Week / Next Week
- Floor / Mid / Ceiling
- metric selection

The currently selected state must always be visually obvious.

Operational controls such as cache behavior belong outside the primary analytical hierarchy.

---

## Visual language

### Overall character

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

Use a small semantic palette:

- page background;
- elevated surface;
- secondary surface;
- primary text;
- secondary text;
- subtle text;
- border;
- primary accent;
- positive;
- warning;
- destructive.

Exact implementation values belong in design tokens.

Surfaces should primarily be separated through hierarchy, spacing, and subtle borders rather than strong shadows.

### Typography

Use a highly legible UI sans-serif.

Typography hierarchy should remain small and controlled.

Do not create excessive heading sizes.

Data-heavy surfaces should prioritize usable screen space over editorial typography.

Numeric data should use tabular numerals.

### Borders and elevation

Prefer thin separators, subtle borders, and restrained background changes.

Use shadows primarily for genuinely floating surfaces such as:

- menus;
- temporary overlays;
- exceptional dialogs.

Normal analytical regions should not appear as stacks of floating cards.

### Corners

Use moderate corner radii consistently.

Avoid extremes such as either completely pill-shaped interfaces or excessive rounded-card styling.

Pills are appropriate for compact semantic statuses such as ownership.

---

## Tables and ranking lists

Tables are a core UI primitive, not a fallback.

Use tables or table-like dense ranking lists whenever users benefit from scanning the same attributes across multiple players or teams.

Requirements:

- stable column positions;
- sortable-looking columns only when sorting actually exists;
- clear hover/focus/selected row states;
- readable row density;
- sticky headers where long datasets justify them;
- right-aligned numeric values;
- useful behavior at narrow widths.

Important numeric columns should not shift horizontally as data loads or changes.

Where horizontal scrolling is unavoidable on mobile, preserve player/team identity so the values being viewed remain understandable.

Selection state must remain visible even if the pointer moves away.

---

## Data visualization

Visualization is a core part of the product and should be treated as analytical software rather than decoration.

### General requirements

Every visualization must clearly communicate:

- what the x-axis represents;
- what the y-axis represents;
- units;
- which series correspond to which players;
- what special markers mean.

A user should not have to infer axis semantics from context.

Grid lines should aid estimation without dominating the graph.

Interactive charts should expose exact values through hover, focus, tap, keyboard interaction, or equivalent inspection.

Important information must remain accessible without requiring pointer hover.

### One probability grammar

Where possible, Odds Fantasy should use a consistent survival-probability grammar across metrics:

**P(metric ≥ x)**

This lets the user ask the same question across fantasy points and individual player statistics: "What is the chance this player reaches at least this value?"

For individual statistics this is the canonical stat-survival interpretation.

For fantasy points, the primary comparison visualization should likewise present:

**P(Fantasy Points ≥ x)**

using the canonical backend fantasy-point distribution/survival data. This is a presentation choice, not a replacement model.

### Fantasy-point survival comparison

Fantasy-point graphs compare players by the probability of reaching or exceeding each fantasy-score threshold.

Therefore:

- x-axis = fantasy-point threshold;
- y-axis = probability of scoring at least that many fantasy points.

The graph must make relative downside, median region, upside, and tail behavior easier to understand than Floor / Mid / Ceiling alone.

Multiple players may be compared simultaneously.

Series identity must remain stable while navigating between compatible metrics whenever practical.

Do not assign a different color to the same player merely because the selected graph changed.

Filtering players must update the graph without destroying the user's other relevant selections.

---

## Target mode

Target mode is a first-class player-comparison interaction.

It answers:

**"What is the probability this player scores at least X fantasy points?"**

The user chooses a fantasy-point threshold through direct manipulation of the fantasy-point survival graph, an accessible numeric control, or both.

The visualization should show the selected threshold as a clear vertical reference line or equivalent marker.

At the selected threshold, every currently compared player should expose:

**P(Fantasy Points ≥ target)**

That probability should also be available in the ranking/list so the user can rank or rapidly compare players at the chosen target without reading every curve manually.

Changing the target should update already-loaded results immediately and must not trigger sportsbook refetches merely because the display threshold moved.

The target value is an analytical lens over the canonical fantasy-point distribution. The frontend must not estimate a separate distribution to support it.

### Target interaction requirements

- Dragging the graph reference line should update target probabilities continuously or at an appropriately responsive cadence.
- Keyboard and touch users must have an equivalent way to change the target.
- The exact target value must always be readable.
- The exact probability for each selected player must be inspectable.
- Target selection must not erase player, position, week, or metric context.
- A user's manually chosen target should remain stable while comparing players until the user changes it or leaves the relevant analysis context.

Target mode is a player-analysis lens. It does **not** implicitly add a new Best Lineup optimization objective unless that is separately specified in the future.

---

## Stat survival curves

Individual-stat graphs represent:

**P(stat ≥ x)**

unless the underlying metric explicitly has different semantics.

Therefore:

- x-axis = stat threshold;
- y-axis = probability of reaching or exceeding that threshold.

The y-axis should use a consistent probability scale so graphs are comparable.

Count statistics should retain their discrete/step semantics instead of being visually smoothed into continuous measurements.

---

## Betting-market evidence

The visualization has three conceptually different elements.

### Fitted curve

The continuous or step line represents the modeled probability distribution.

It is the primary visual element.

### Consensus anchors

Consensus sportsbook thresholds are displayed as distinct point markers.

These represent de-vigged cross-book evidence constraining the fitted distribution.

They must be visually distinguishable from the curve itself.

### Exact sportsbook thresholds

Individual sportsbook line locations are displayed as lighter secondary markers along the relevant threshold axis.

They communicate where source evidence exists without visually overpowering the consensus or fitted model.

The graph must include a compact visual key explaining these encodings.

---

## Linked evidence inspection

Detailed evidence should be available through progressive disclosure in the inspector or adjacent evidence region.

The default visualization should remain readable without displaying a large raw sportsbook table.

When evidence is expanded, the user should be able to inspect:

- selected player;
- consensus threshold;
- fair consensus probability;
- sportsbook;
- main/alternate line type;
- exact line;
- over price;
- under price.

The graph and evidence should be linked where doing so reduces mental lookup work.

Examples of desirable coordinated behavior:

- selecting a consensus marker reveals or emphasizes the corresponding consensus evidence;
- inspecting an individual sportsbook line emphasizes its threshold location on the graph;
- changing the selected player updates evidence without destroying the graph's metric/filter context.

The interface should explain the relationship between raw prices, consensus anchors, and the displayed fitted curve in concise language.

Raw evidence should never visually compete with the primary graph until the user requests it.

---

## Persistent inspector

On desktop, player detail should normally appear in a persistent or collapsible inspector rather than a context-destroying full-screen/modal flow.

The inspector should prioritize:

1. player identity and matchup context;
2. Floor / Mid / Ceiling;
3. Target probability when active;
4. available modeled stats;
5. evidence summary;
6. progressively disclosed raw evidence.

Selecting another player should replace inspector content quickly while keeping the rest of the workspace stable.

A modal remains acceptable for exceptional flows where the user genuinely leaves the analytical context, but it should not be the default pattern for ordinary player inspection.

---

## Visualization interactions

Useful analytical interactions include:

- player selection;
- cross-highlighting between list, chart, legend, and inspector;
- position filtering;
- player search;
- metric selection;
- previous/next metric navigation;
- Target threshold manipulation;
- exact-value inspection;
- legend-driven identification;
- linked evidence inspection.

Interaction should answer analytical questions, not exist because a charting framework supports it.

Avoid unnecessary:

- 3D effects;
- animated entrances;
- particle effects;
- perspective transforms;
- decorative gradients;
- excessive transitions.

Pan, zoom, brushing, annotations, or additional linked views should only be introduced where they materially improve analysis.

---

## Loading states

Data loading must preserve context.

Prefer:

- skeleton structure;
- inline loading indicators;
- status text near the affected surface.

Avoid replacing the entire application with a global spinner when only one dataset is loading.

Existing data should generally remain visible while a refresh is in progress unless displaying it would be misleading.

Already-loaded client-side filtering, selection, Target movement, and metric presentation should not look like network operations.

---

## Empty and unavailable states

Empty states must explain why there is no data when the reason is known.

Examples:

- no priced markets;
- no selected players have this metric;
- BYE week;
- unsupported roster slot;
- source data unavailable.

Do not collapse different failure modes into a generic "No data."

---

## Errors

Errors should appear as close as practical to the operation that failed.

Error messages should communicate:

1. what failed;
2. whether existing information remains usable;
3. what action the user can take.

Technical stack traces and raw upstream errors do not belong in the primary UI.

---

## Settings and advanced controls

Settings that affect data retrieval but are not part of ordinary fantasy decisions should remain visually secondary.

Operational controls such as cache/fresh-data behavior should not compete with Player Report, Defenses, Best Lineup, Target analysis, or the visualization workspace.

---

## Responsive behavior

The desktop interface should optimize for analytical density and coordinated views.

The mobile interface should preserve the same decision hierarchy rather than reproducing the desktop three-region layout at a smaller scale.

A preferred narrow-screen order is:

1. ranking/player selection;
2. selected-player summary;
3. full-width visualization;
4. evidence/details.

On narrow screens:

- primary decisions remain visible first;
- controls may stack;
- secondary context may collapse;
- the inspector may become an inline section or sheet;
- detailed evidence may become a dedicated lower section;
- graphs must remain readable without requiring arbitrary fixed-width desktop canvases;
- Target mode must remain usable by touch and accessible numeric input.

Do not convert every table row into a large card unless that demonstrably improves readability.

---

## Accessibility

The application should target WCAG 2.2 AA behavior.

At minimum:

- all controls are keyboard accessible;
- focus states are clearly visible;
- semantic HTML is preferred;
- controls have accessible names;
- dialogs properly manage focus when dialogs are used;
- text and essential graphics have adequate contrast;
- color is never the only indicator of state;
- charts expose meaningful textual values or equivalent accessible inspection;
- Target threshold manipulation has a keyboard-operable equivalent;
- touch targets are large enough for mobile interaction.

Reduced-motion preferences must be respected.

---

## Motion

Motion should communicate state change, not personality.

Appropriate uses include:

- short disclosure transitions;
- loading indicators;
- subtle cross-highlighting;
- restrained transitions that make changed Best Lineup slots easier to perceive.

Large animated chart transitions should not make comparisons harder.

The user should never have to wait for an animation to finish before reading current data.

---

## Performance

The interface should feel immediate once the underlying data exists.

Frontend architecture should avoid shipping substantial client-side code for static or noninteractive presentation merely because a framework makes it convenient.

Large visualization dependencies must justify their cost through functionality used by the product.

Filtering, selecting players, cross-highlighting, switching an already-loaded visualization, and moving the Target threshold should ordinarily feel instantaneous.

The visualization implementation should support the expected number of simultaneously rendered player series without interaction latency becoming distracting.

---

## Content style

Use concise, literal language.

Prefer:

- `No priced markets`
- `Optimize for Ceiling`
- `Chance of scoring at least 24.5`
- `Opponent implied total`
- `Explain betting lines`

Avoid:

- marketing copy;
- unexplained jargon;
- clever error messages;
- unnecessary fantasy-football slang.

When specialized statistical concepts are necessary, explain them near the point of use.

---

## Design anti-patterns

Do not introduce the following without a specific product reason:

- dashboard cards for every metric;
- oversized KPI tiles;
- gradients used primarily for decoration;
- glassmorphism;
- 3D charts;
- pie charts for probability distributions;
- gauges or speedometers;
- traffic-light coloring of every value;
- excessive badges;
- animation for visual spectacle;
- horizontal carousels of analytical data;
- hidden information that is essential to basic comparison;
- separate modal workflows for information that should remain coordinated with the primary analysis surface.

Do not mimic sportsbook visual design.

Odds Fantasy consumes sportsbook information; it is not a betting interface.

---

## Design QA

A UI change is not complete merely because it renders.

Review should verify:

### Hierarchy

Can the user identify the most important decision information immediately?

### Comparison

Can values that are intended to be compared actually be scanned quickly?

### Coordination

Do list selection, graph emphasis, inspector state, filters, and evidence stay logically synchronized?

Does ordinary inspection preserve analytical context rather than forcing unnecessary navigation?

### Target mode

Can a user choose a fantasy-point target and immediately understand each selected player's probability of reaching it?

Does Target mode use the canonical fantasy-point distribution and avoid unnecessary data refetches?

### States

Are loading, empty, unavailable, selected, disabled, error, and success states understandable?

### Responsive behavior

Does the interface remain useful at desktop and mobile widths?

### Accessibility

Can core workflows be completed with keyboard and touch, and are states perceivable without depending entirely on color?

### Visualization semantics

Do chart axes, survival-probability meaning, markers, series identities, Target probabilities, and evidence still represent the canonical backend data correctly?

### Regression

Has an apparently cosmetic redesign accidentally changed model meaning or hidden important limitations?

---

## Change control

This file is a product contract.

Implementation must conform to it.

Changes to frontend framework, charting library, CSS architecture, component system, or rendering technology do **not** by themselves require this document to change.

Changes to the intended user experience or visualization semantics do.

Examples requiring an intentional design-contract change:

- changing the primary information hierarchy;
- abandoning the coordinated analytical-workstation model;
- removing Floor/Mid/Ceiling from direct comparison;
- removing or materially changing Target mode;
- changing graph probability semantics;
- changing the meaning of consensus/source markers;
- materially changing how evidence is exposed;
- changing the application's design character.

Agents must not modify this contract merely to make an implementation easier.

If implementation and this document disagree, surface the disagreement rather than silently changing the specification.
