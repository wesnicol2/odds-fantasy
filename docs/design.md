# Odds Fantasy — UI Design Contract

## Purpose

Odds Fantasy is a decision-support application for fantasy football.

The interface exists to help a user answer questions quickly:

1. What outcomes should I expect from my players?
2. Which players or defenses are preferable?
3. What lineup best matches the level of risk I want?
4. Why does the model believe what it believes?
5. What sportsbook evidence supports the model?

The UI should feel like a **professional analytical tool**, not a sportsbook, fantasy-news site, or generic SaaS dashboard.

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

Supporting evidence belongs progressively deeper in the interface.

The hierarchy is:

**Decision → distribution → explanation → raw evidence**

Do not reverse this hierarchy merely because the underlying data model is complicated.

### 2. Dense, not cluttered

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

### 3. Numbers are the interface

Numerical information must be especially easy to compare.

Numeric columns must:

- be right-aligned where appropriate;
- use tabular numerals;
- use consistent precision;
- preserve consistent units;
- visually distinguish missing values from zero.

Never display a missing projection as `0`.

`—`, an explicit unavailable state, or a short explanation is preferable.

### 4. Uncertainty is first-class

Odds Fantasy does not produce a single definitive player value.

Floor / Mid / Ceiling and probability distributions are core product concepts and must never be visually reduced to a single "projection" without context.

The interface should make uncertainty understandable without making it intimidating.

### 5. Evidence should be inspectable

The product derives information from betting markets.

Users should be able to move naturally from:

**projection → curve → consensus market evidence → individual sportsbook lines**

without encountering a second, contradictory representation of the same model.

Visualizations are presentations of canonical backend model data. The frontend must not invent a separate probability model.

### 6. Color communicates meaning

Color must not exist merely to decorate the application.

Use color primarily for:

- active selection;
- series identity;
- semantic state;
- emphasis;
- warnings/errors.

Do not use multiple unrelated accent colors simply to make sections appear visually distinct.

Do not rely on color alone to communicate meaning.

---

## Information architecture

The application has four primary analytical surfaces.

### Player Report

The default surface.

Its purpose is rapid comparison of the user's relevant players.

Primary columns:

- Player
- Position / matchup context
- Floor
- Mid
- Ceiling

`Mid` is the default visual anchor but Floor and Ceiling must remain immediately comparable.

Rows with incomplete or unavailable projections remain visible but visually de-emphasized with an explicit reason.

Selecting a player opens deeper analysis without losing the user's place in the report.

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

### Graph Explorer

Graph Explorer is a first-class analytical workspace.

It should not feel like an incidental chart added to a report.

On sufficiently large screens it should have enough space to simultaneously display:

- metric selection;
- position/player filtering;
- visualization;
- legend;
- contextual explanation.

The visualization itself is the dominant element.

Detailed sportsbook evidence is progressively disclosed beneath or alongside it.

A framework implementation may use a route, full-screen workspace, sheet, or other presentation, but the graph must not be constrained to an unnecessarily small chart viewport.

---

## Navigation and controls

Use a clear visual distinction between:

- navigation;
- filtering;
- actions.

Controls that switch between mutually exclusive states should use segmented controls, tabs, or equivalent single-selection patterns.

Examples:

- Player Report / Defenses / Best Lineup
- This Week / Next Week
- Floor / Mid / Ceiling

Do not represent mutually exclusive choices as independent buttons when that obscures the relationship between them.

The currently selected state must always be visually obvious.

---

## Visual language

### Overall character

The application should feel:

- analytical;
- calm;
- compact;
- precise;
- modern;
- trustworthy.

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

Prefer subtle borders and background changes.

Use shadows primarily for genuinely floating surfaces such as:

- dialogs;
- menus;
- temporary overlays.

Normal report sections should not appear as stacks of floating cards.

### Corners

Use moderate corner radii consistently.

Avoid extremes such as either completely pill-shaped interfaces or excessive rounded-card styling.

Pills are appropriate for compact semantic statuses such as ownership.

---

## Tables

Tables are a core UI primitive, not a fallback.

Use tables whenever users benefit from scanning the same attributes across multiple players or teams.

Requirements:

- stable column positions;
- sortable-looking columns only when sorting actually exists;
- clear hover/focus row state;
- readable row density;
- sticky headers where long datasets justify them;
- right-aligned numeric values;
- useful behavior at narrow widths.

Important numeric columns should not shift horizontally as data loads or changes.

Where horizontal scrolling is unavoidable on mobile, preserve the identity column so the values being viewed remain understandable.

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

Interactive charts should expose exact values through hover, focus, tap, or equivalent inspection.

Important information must remain accessible without requiring pointer hover.

### Fantasy-point distributions

Fantasy-point graphs compare outcome distributions between players.

The graph must make relative probability and distribution shape easier to understand than the Floor / Mid / Ceiling table alone.

Multiple players may be compared simultaneously.

Series identity must remain stable while navigating between compatible metrics whenever practical.

Do not assign a different color to the same player merely because the selected graph changed.

Filtering players must update the graph without destroying the user's other relevant selections.

### Stat survival curves

Individual-stat graphs represent:

**P(stat ≥ x)**

unless the underlying metric explicitly has different semantics.

Therefore:

- x-axis = stat threshold;
- y-axis = probability of reaching or exceeding that threshold.

The y-axis should use a consistent probability scale so graphs are comparable.

Count statistics should retain their discrete/step semantics instead of being visually smoothed into continuous measurements.

### Betting-market evidence

The visualization has three conceptually different elements.

#### Fitted curve

The continuous or step line represents the modeled probability distribution.

It is the primary visual element.

#### Consensus anchors

Consensus sportsbook thresholds are displayed as distinct point markers.

These represent de-vigged cross-book evidence constraining the fitted distribution.

They must be visually distinguishable from the curve itself.

#### Exact sportsbook thresholds

Individual sportsbook line locations are displayed as lighter secondary markers along the relevant threshold axis.

They communicate where source evidence exists without visually overpowering the consensus or fitted model.

The graph must include a compact visual key explaining these encodings.

---

## Evidence inspection

Detailed evidence should be available through progressive disclosure.

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

The interface should explain the relationship between these values and the displayed fitted curve in concise language.

Raw evidence should never visually compete with the primary graph until the user requests it.

---

## Visualization interactions

Useful analytical interactions include:

- player selection;
- position filtering;
- player search;
- metric selection;
- previous/next metric navigation;
- exact-value inspection;
- legend-driven identification.

Interaction should answer analytical questions, not exist because a charting framework supports it.

Avoid unnecessary:

- 3D effects;
- animated entrances;
- particle effects;
- perspective transforms;
- decorative gradients;
- excessive transitions.

Pan, zoom, brushing, annotations, or cross-highlighting should only be introduced where they materially improve analysis.

---

## Loading states

Data loading must preserve context.

Prefer:

- skeleton structure;
- inline loading indicators;
- status text near the affected surface.

Avoid replacing the entire application with a global spinner when only one dataset is loading.

Existing data should generally remain visible while a refresh is in progress unless displaying it would be misleading.

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

Operational controls such as cache/fresh-data behavior should not compete with Player Report, Defenses, Best Lineup, or Graph Explorer.

---

## Responsive behavior

The desktop interface should optimize for analytical density.

The mobile interface should optimize for preserving the same decision hierarchy rather than reproducing the desktop layout at a smaller scale.

On narrow screens:

- primary decisions remain visible first;
- controls may stack;
- secondary context may collapse;
- detailed evidence may become a dedicated lower section or sheet;
- graphs must remain readable without requiring arbitrary fixed-width desktop canvases.

Do not convert every table row into a large card unless that demonstrably improves readability.

---

## Accessibility

The application should target WCAG 2.2 AA behavior.

At minimum:

- all controls are keyboard accessible;
- focus states are clearly visible;
- semantic HTML is preferred;
- controls have accessible names;
- dialogs properly manage focus;
- text and essential graphics have adequate contrast;
- color is never the only indicator of state;
- charts expose meaningful textual values or equivalent accessible inspection;
- touch targets are large enough for mobile interaction.

Reduced-motion preferences must be respected.

---

## Motion

Motion should communicate state change, not personality.

Appropriate uses include:

- short disclosure transitions;
- loading indicators;
- subtle state transitions.

Large animated chart transitions should not make comparisons harder.

The user should never have to wait for an animation to finish before reading current data.

---

## Performance

The interface should feel immediate once the underlying data exists.

Frontend architecture should avoid shipping substantial client-side code for static or noninteractive presentation merely because a framework makes it convenient.

Large visualization dependencies must justify their cost through functionality used by the product.

Filtering or switching an already-loaded visualization should ordinarily feel instantaneous.

---

## Content style

Use concise, literal language.

Prefer:

- `No priced markets`
- `Optimize for Ceiling`
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
- hidden information that is essential to basic comparison.

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

### States

Are loading, empty, unavailable, selected, disabled, error, and success states understandable?

### Responsive behavior

Does the interface remain useful at desktop and mobile widths?

### Accessibility

Can core workflows be completed with keyboard and touch, and are states perceivable without depending entirely on color?

### Visualization semantics

Do chart axes, probability meaning, markers, series identities, and evidence still represent the canonical backend data correctly?

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
- removing Floor/Mid/Ceiling from direct comparison;
- changing graph probability semantics;
- changing the meaning of consensus/source markers;
- materially changing how evidence is exposed;
- changing the application's design character.

Agents must not modify this contract merely to make an implementation easier.

If implementation and this document disagree, surface the disagreement rather than silently changing the specification.
