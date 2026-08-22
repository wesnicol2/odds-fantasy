# Fantasy Projection Methodology

**Purpose:** Define, from first principles and independent of any code, how we turn betting-market odds into a full fantasy-points probability distribution for each player. The method is ruleset-agnostic; this is the reference the implementation is measured against.

**Status:** v0.9 — living document. Market-translation-only and scoring-as-configuration principles established; method is ruleset-agnostic and PPR-ready; rushing/receiving/passing yards, receptions, touchdowns, and interceptions done; player aggregation and DEF / K next.

**Relationship to `AGENTS.md`.** This document is the *target*: what the model
should do, argued from the market up. `AGENTS.md` records what the code does
*today* and why, including where it falls short of this document. When the two
disagree, this one describes the destination and `AGENTS.md` describes the
current position — see its "As-built here, target in
`docs/fantasy-projection-methodology.md`" table for the live gap list.

**What the model produces.** A full fantasy-points *probability distribution* per player — the whole curve, not just a mean — because every downstream use (floor/ceiling, matchup leverage, lineup win-probability) needs the distribution. The method is **ruleset-agnostic**: scoring rules, PPR, bonuses, and league format are all configuration, and any specific league is just one instance (this project's is summarized in §2.4 and used in the worked examples).

**This project's goal (a usage lens, not part of the method).** The league this project runs in pays only for a top-3 finish — a tournament objective — so when *using* the curve (§5) we lean especially on the right tail (ceiling). This shapes how the distribution is read, not how it is built.

**Design principle — market translation only.** The model *only translates what the sportsbooks are telling us*. No exogenous inputs, no hand-tuned adjustments, no explicit knobs. The single cross-book operation is a **median aggregate** of the de-vigged prices. If a quantity isn't in the market (cross-stat correlation, fumbles, an injury adjustment), we don't invent it — we leave it out or flag it, never fudge it.

**Design principle — scoring is configuration (ruleset-agnostic).** No scoring constant is hardcoded. Every points value, per-yard rate, bonus threshold, and per-reception value is read from the league's scoring settings (e.g. Sleeper `scoring_settings`). The same engine serves any ruleset — PPR or non-PPR, any bonus set, any point values; a rules change is a config change, not a math change. **Every scorable stat is modeled and then scored by its configured value** — so a stat worth 0 in one league (receptions, in a non-PPR config) is still computed and simply contributes 0. Worked examples use this project's league as one instance (parameter table in §2.4).

**How this doc is organized:** §1 is the pipeline at a glance. §2 is the general method — every cross-cutting choice, with its status (Locked / Open). §3 and §4 are worked examples in pure numbers — a continuous stat (yards) and a discrete count (touchdowns) — pointing back to §2 for the "why," and each notes which other stats reuse it. §5 is how we use the resulting curve. §6–§7 are the open punch-list and roadmap; the changelog closes the doc.

---

## 1. Pipeline overview

Every stat follows the same path. Steps 1–6 produce one stat's fantasy-points curve; step 7 combines a player's stats into their overall curve.

1. **Odds → implied probability** — convert each posted price to a probability. *(worked in §3.2)*
2. **De-vig** — strip each book's margin at each two-way line → fair P(over). *(method §2.1; worked §3.3)*
3. **Combine books** — when several books post the same line, take the **median** of their fair probabilities. *(method §2.2)*
4. **Reconstruct the distribution** — interpolate between the market anchors, extrapolate the tails. This yields the survival curve S(k) = P(stat > k) and CDF F(k) = 1 − S(k). *(method §2.3; worked §3.4)*
5. **Apply league scoring** — transform the stat distribution into fantasy points, including threshold bonuses. All scoring values are config (§2.4). *(worked §3.5)*
6. **Sample** — draw from the distribution repeatedly to produce the full fantasy-points curve. *(worked §3.6)*
7. **Aggregate (player level)** — sum a player's stat contributions into their overall curve (cross-stat correlation is an open question). *(method §2.5)*

Discrete count stats (touchdowns, interceptions, receptions) are a special case: the cumulative market lines *are* the distribution, so steps 4–6 collapse into differencing the lines — see §4.

---

## 2. General method (stat-agnostic)

Each subsection states the current choice, the reasoning, candidate upgrades, and a **Status**: *Locked* (settled) or *Open* (to be decided, usually by calibration).

### 2.1 De-vig

Strip each book's margin so a two-way line's two sides sum to 1 → fair P(over). (Mechanics worked in §3.3.)

- **Current choice:** proportional (each side ÷ their sum). Transparent.
- **Candidate upgrade:** Shin or power de-vig — empirically more predictive and better on the asymmetric tail/longshot lines, which is the ceiling region we care about most. Player props carry high vig, so the method choice matters more here than for low-vig markets.
- **Caveat:** the feed is soft books only (no Pinnacle), so we de-vig a *consensus* of soft books rather than a true sharp line.
- **Status:** Open — proportional vs Shin vs power decided by calibration.

### 2.2 Combining multiple books

When several books post the same line, we have multiple estimates of one probability.

1. **De-vig each book first**, independently → each book's fair P(over).
2. **Combine across books by taking the median** of those fair probabilities.

That's the whole method — no weights, no knobs, no separate outlier mechanism. The median *is* the robustness: one stale book (didn't update for an injury/weather) can't move it. This keeps the combine step a pure market aggregate, per the design principle. (It supersedes the earlier manual-per-book-weight idea, which was an explicit knob.)

One-sided alternate lines (e.g. "125+" with no under) can't be de-vigged as a two-way market, so they're handled in reconstruction (§2.3), not here.

- **Status:** Locked.

### 2.3 Distribution reconstruction

From the de-vigged anchors (points on the CDF), build the full distribution. (Worked in §3.4.)

- **Middle — interpolate.** Current: linear (transparent). Candidate/locked upgrade: monotone cubic (PCHIP), which is what the code's `angelini` model already does — **keep it, don't redesign.** First enforce monotonicity with isotonic regression (PAV) if a noisy line dips.
- **Tails — parametric.** Yards: lognormal (positive, right-skewed). This is shared by all yards-type stats — **rushing, receiving, and passing yards use identical reconstruction**, differing only in each player's fitted anchors (a higher or lower floor comes from the *odds ladder*, not from different math). The upper tail is where the ceiling lives, so validate the family per position. The near-zero lower tail (a player "laying an egg") gets **no special handling** — it's reconstructed from the odds like any other part of the curve; if the market gives that outcome weight, it's already in the ladder.
- **Count stats via cumulative lines (TDs, interceptions, receptions):** the anytime / 2+ / 3+ / over-under-count lines *are* the survival curve — read the distribution directly by **differencing** adjacent lines, no parametric fit. Use only the lines the book posts. Full worked model in §4. **Locked.**
- **Sparse single-line counts:** where a count has only one posted line *above* 0.5, differencing under-determines the distribution, so a discrete family would be fit — Poisson vs **negative-binomial** (NB likely; NFL counts are overdispersed). Open, decide by calibration. (A line at o/u 0.5 is just P(≥1) = a clean Bernoulli, no fit needed.)
- **Status:** Continuous reconstruction Locked (angelini); cumulative-line counts Locked (differencing, §4); sparse single-line count family Open.

### 2.4 Scoring & bonuses — all parameters are configuration

Scoring is a configurable function read from the league's scoring settings — **no scoring constant is hardcoded in the model**, and the same engine serves any ruleset. Worked examples use *this project's* league as one instance; the engine takes the values as inputs.

**Scoring config — this project's league (one instance; the engine is agnostic to these values):**

| Stat | Engine | Config value(s) |
|------|--------|-----------------|
| Passing yards | continuous (§3) | 0.04 / yd; bonus +5 at 300, +5 at 400 |
| Rushing yards | continuous (§3) | 0.1 / yd; bonus +5 at 100, +5 at 200 |
| Receiving yards | continuous (§3) | 0.1 / yd; bonus +5 at 100, +5 at 200 |
| Receptions | count via differencing (§4) | 0 / reception here (PPR value — configurable) |
| Passing TDs | count via differencing (§4) | 4 / TD |
| Rushing + receiving TDs (pooled) | count via differencing (§4) | 6 / TD |
| Interceptions thrown | count via differencing (§4) | −1 / INT (negative) |
| Fumbles lost | — | −2 (no clean market → omitted, §2.5) |
| 2-pt conversions (pass/rush/rec) | — | +2 (no clean market → omitted) |

- **PPR is always enabled.** Receptions are modeled as a count regardless of ruleset and multiplied by the configured per-reception value. Here that value is 0 (non-PPR) so receptions contribute nothing; setting it to 0.5 or 1.0 turns on PPR with no math change. (When the value is 0 the reception computation may be skipped as an optimization, but the capability is standard.)
- **Bonuses are configurable (threshold, amount) pairs**, and are threshold *kinks*, so expected points must price the bonus probability in rather than scale the mean: `E = rate × E[stat] + Σ amount_i × P(≥ threshold_i)`.
- **Negative stats are just negative coefficients.** An interception (−1) shifts the curve left; the math is identical to a positive count, only the sign differs. Its "good" outcome is 0, so extra posted lines deepen the floor rather than raise the ceiling.
- Exact bonus handling comes free from sampling (§2.5): apply the real (configured) scoring to each simulated draw.
- **Status:** Locked. Scoring fully parameterized from config; K and DEF scoring are separate and pending (roadmap).

### 2.5 Aggregating a player's stats

A player's fantasy points = the sum of their stat contributions (rush yds + rec yds + TDs, etc.). Each stat's curve is dictated **entirely by its book odds** — no availability model, no injury/DNP handling, nothing layered on. Whatever the odds imply (including any chance a player barely plays) is already in each stat's distribution. The market-only principle does bite in one place, though: the books price each stat *marginally*, but the piece aggregation needs and the market doesn't quote is how a player's stats move *together*.

- **Cross-stat correlation — open tension.** A player's stats move together — a big game drives both yards and TDs; a QB's passing yards and passing TDs ride the same volume/efficiency; receptions and receiving yards climb together (relevant in PPR) — so independent sums understate the joint ceiling. But the books quote marginals, not the joint — the correlation isn't in the market. Under the market-only principle we won't invent a correlation matrix, so the options are: (i) assume independence (pure translation, but understates the tail we care about), or (ii) use correlation the market *does* imply (e.g. same-game-parlay pricing — not in our current feed). **Unresolved — to settle when we build aggregation.**
- **Fumbles.** No clean fumble market exists, so under the principle we don't invent a rate — fumbles are omitted unless a usable market appears.
- **Status:** Correlation Open. Aggregation spec pending (roadmap).

---

## 3. Worked example — a continuous stat (rushing yards)

Pure arithmetic; the "why" for each step lives in §2. (Single book here, so the combine step §2.2 is a no-op.) Scoring constants below are config values (§2.4), not hardcoded.

### 3.1 Inputs (raw odds from The Odds API)

A main line plus an alternate ("X+") ladder, American odds:

| Line | Over | Under |
|------|------|-------|
| 40+ | −450 | +330 |
| 60+ | −175 | +145 |
| 74.5 (main) | −115 | −105 |
| 90+ | +145 | −175 |
| 100+ | +210 | −270 |
| 125+ | +650 | −1100 |

### 3.2 Step 1 — Odds → implied probability

American odds: negative → `(−odds)/(−odds+100)`; positive → `100/(odds+100)`.

Main line 74.5: Over −115 → 115/215 = 0.535; Under −105 → 105/205 = 0.512. These sum to 1.047 — the excess **4.7% is the vig**.

### 3.3 Step 2 — De-vig

Each threshold is its own two-way market. Fair P(over) = over ÷ (over + under). Main line: 0.535 / 1.047 = 0.511. Across all thresholds → the survival curve S(k) and CDF F(k):

| Line k | S(k) = P(yds > k) | F(k) = P(yds ≤ k) |
|--------|-------------------|-------------------|
| 40 | 0.779 | 0.221 |
| 60 | 0.609 | 0.391 |
| 74.5 | 0.511 | 0.489 |
| 90 | 0.391 | 0.609 |
| 100 | 0.307 | 0.693 |
| 125 | 0.127 | 0.873 |

F(k) is monotone increasing here (if a noisy line dipped, isotonic regression would flatten it — see §2.3). That F(k) column *is* the rushing-yards distribution.

### 3.4 Step 4 — Reconstruct the full distribution

We know F(k) at six points; we need it everywhere.

**Between anchors — interpolate.** Median (F = 0.50) sits between 74.5 (0.489) and 90 (0.609):
`yds = 74.5 + (0.50 − 0.489)/(0.609 − 0.489) × (90 − 74.5) = 75.9`.
25th percentile ≈ 43 yds by the same method.

**Beyond the last anchor — parametric tail.** For the 90th percentile, F = 0.90 exceeds the top anchor (125 → 0.873), so extend with a lognormal. Fitting to the two upper anchors gives μ = 4.43, σ = 0.35:
`q90 = e^(4.43 + 0.35 × 1.28) = ≈131 yds`.

Range: floor (10th) ≈ 18, median ≈ 76, ceiling (90th) ≈ 131 yds.

### 3.5 Step 5 — Yards → fantasy points

Scoring for rushing yards in this instance (config §2.4): **0.1 pt/yd, +5 at 100 yds, +5 more at 200 yds.**

| Percentile | Yards | Points |
|-----------|-------|--------|
| Floor (10th) | 18 | 1.8 |
| Median | 76 | 7.6 |
| 75th | 108 | 10.8 + 5 = 15.8 |
| Ceiling (90th) | 131 | 13.1 + 5 = 18.1 |

The bonus is a **kink**: crossing 100 yds jumps points from 10.0 to 15.0. So expected points must price the bonus probability in:

```
E[points] = 0.1 × E[yds] + 5 × P(≥100) + 5 × P(≥200)
          = 0.1 × 76 + 5 × 0.307 + 5 × 0.007
          = 7.6 + 1.54 + 0.03 ≈ 9.2 pts
```

~1.5 of the ~9.2 expected points come purely from the 100-yard bonus probability, and the bonus roughly doubles the median→ceiling gap. This is the ceiling premium the configured bonus creates.

### 3.6 Step 6 — The full curve (sampling)

Draw u ~ Uniform(0,1), invert F to get yards, score it. Examples:

- u = 0.08 → ~15 yds → 1.5 pts
- u = 0.42 → 64 yds → 6.4 pts
- u = 0.70 → 101 yds → 10.1 + 5 = 15.1 pts (just cleared the bonus)
- u = 0.93 → 141 yds → 14.1 + 5 = 19.1 pts

10,000 draws → the histogram is the rushing-yards fantasy-points curve: a hump near 7–8 pts with a distinct bump in the right tail where the 100-yard bonus lives.

### 3.7 Reused by: receiving yards, passing yards

- **Receiving yards** — identical engine, config §2.4. (Receptions are a separate stat, modeled as a count in §4.5 and scored by the configured per-reception value.)
- **Passing yards** — identical engine, config §2.4 (**0.04/yd, bonus at 300/400**). One nuance (not a math change): a volume passer's median yards is often near 300, so that bonus fires near *even money* — right around the median, not out in the tail like the 100-yard rushing bonus. Same kink, different location; the market ladder places it per-player. A starting QB is also almost never near zero, so the lower tail is a non-issue.

---

## 4. Worked example — a discrete count (touchdowns)

Counts use the same survival-curve idea as yards, but because the value is a small integer, the market lines give the distribution **directly** — no interpolation, no tail-fitting. For the worked example we use touchdowns: rushing and receiving TDs are pooled into one **total-TD count** (they score equally, and the "anytime TD scorer" market is itself combined rush-or-receive; if a ruleset scored rush and receiving TDs differently, they'd be modeled as separate counts). Passing TDs are their own count (§4.5).

### 4.1 Inputs — the count lines *are* a survival curve

De-vigged and median-combined across books, the markets give cumulative probabilities. **Use only the lines the book actually posts:**

- Anytime TD → P(≥1)
- 2+ TD → P(≥2)  *(only if posted)*
- 3+ TD → P(≥3)  *(only if posted)*

Enforce monotonicity first — P(≥1) ≥ P(≥2) ≥ P(≥3) (isotonic, as in §2.3) — so differencing can't produce a negative bucket.

### 4.2 Difference into exact counts (the no-double-count step)

The lines are cumulative, so a 2-TD game is already inside the anytime number. Recover exact-count probabilities by differencing adjacent lines:

- P(0) = 1 − P(≥1)
- P(exactly 1) = P(≥1) − P(≥2)
- P(exactly 2) = P(≥2) − P(≥3)
- P(top bucket) = P(≥ highest posted line)

Subtracting the next line out is exactly what removes the double count. The top (highest-posted) bucket is scored at its floor: those games have *at least* that many, but with no higher line we don't invent the mass above it.

### 4.3 Points and the distribution

Points = (config value, §2.4) × count = 6 × count for TDs. Worked example — anytime = 0.55, 2+ = 0.18 (no 3+ posted):

| TDs | Probability | Points |
|-----|------------|--------|
| 0 | 1 − 0.55 = 0.45 | 0 |
| 1 | 0.55 − 0.18 = 0.37 | 6 |
| 2+ | 0.18 (scored as 2) | 12 |

Expected TD points = 6(0.37) + 12(0.18) = **4.38**. Sanity check via the survival identity (E[count] = Σ P(≥k)): (0.55 + 0.18) × 6 = 4.38. ✓

### 4.4 Which lines the book posts drives the ceiling

- **Anytime only** → the model collapses to a Bernoulli (0 or 1): E = value × P(≥1), hard ceiling of one unit. We do **not** invent multi-count mass.
- **+ 2+ line** → adds the two-unit outcome (here an 18% shot at two TDs, 12 pts). That ceiling mass is where a multi-TD game's value lives — exactly the upside a tournament objective rewards (§5).
- **+ 3+ line** → splits the top bucket further: P(exactly 2) = P(≥2) − P(≥3), plus a three-unit bucket.

Keep exactly the lines the book posts — nothing more, nothing invented.

### 4.5 Reused by: passing TDs, interceptions, receptions

- **Passing TDs** — same differencing engine on the `player_pass_tds` cumulative lines, × **4** pts (config §2.4). QBs live higher up the count (2–3–4-TD games are common), so there are simply more buckets — identical math.
- **Interceptions thrown** — same differencing engine, × **−1** pt (negative, §2.4). Usually only an over/under 0.5 is posted = P(≥1) → a clean **Bernoulli**; like anytime-only TDs, we don't invent the 2-INT downside unless a line for it is posted. Being negative, its good outcome is 0, so more lines would deepen the floor, not raise the ceiling.
- **Receptions** — same differencing engine on the `player_receptions` cumulative lines (o/u + 3+/5+/7+…), × the configured **per-reception** value (§2.4). Non-PPR (value 0) → receptions contribute nothing and may be skipped; PPR (0.5 or 1.0) → receptions become a major, high-floor contributor. Always modeled; only the coefficient changes. Receptions correlate strongly with receiving yards, which matters for aggregation (§2.5) in PPR.

---

## 5. Using the curve — floor / mid / ceiling and matchup leverage

Floor / mid / ceiling are **three percentiles of the one curve**, not separate projections:
- Floor ≈ 10th percentile (bad game)
- Mid ≈ median (typical game)
- Ceiling ≈ 90th percentile (things break right)

Head-to-head pays for **beating your opponent**, not for points, so the target is P(your total > their total). That dictates how to weight variance:

- **Underdog (facing a stronger projected team):** your median loses, so you *want* variance — start ceiling plays to buy a shot at the right tail.
- **Favorite (facing a weaker projected team):** your median already wins, so variance is the enemy — start floor plays to lock it in.

Refinements:
- A **tiebreaker between similar-mean options**, not license to torch expected points.
- A **dial, not a switch** — lean harder the bigger the projected gap.
- It's the **projected matchup** that sets underdog/favorite, not reputation or record.

The rigorous version: simulate the full lineup vs the opponent's and pick the lineup maximizing P(win); this automatically leans ceiling when behind and floor when ahead. Floor/mid/ceiling are the human-readable readout of that.

---

## 6. Open questions / to validate

Each points to the section that owns it:

- De-vig method — proportional vs Shin vs power (§2.1). Arbiter: calibration (PIT / coverage / CRPS).
- Sparse single-line counts — one posted line above 0.5: fit Poisson/NB vs bucket coarsely (§2.3). (o/u 0.5 is a clean Bernoulli.)
- Cross-stat correlation at aggregation — assume independence (pure translation) vs. use market-implied correlation; can't invent it under the market-only principle. Tightest for QB pass yds ↔ pass TDs, and receptions ↔ receiving yards in PPR (§2.5).
- Which count lines the feed actually returns (anytime only, or also 2+/3+; receptions ladder depth) — determines how much tail we can capture (§4).
- Fumbles — currently omitted (no clean market); revisit only if a usable one appears (§2.5).
- Soft-book-only consensus — how much bias vs a true sharp line? (§2.1)

---

## 7. Roadmap for this document

- [x] Continuous-stat engine (worked: rushing yards) — reused by receiving and passing yards
- [x] Receptions — count engine, scored by the configured per-reception value (0 in non-PPR; PPR-ready)
- [x] Discrete-count engine (worked: touchdowns) — reused by passing TDs and interceptions
- [x] Negative stats (interceptions) via a negative coefficient
- [ ] Assemble full players (RB / WR / QB) into one curve each — needs aggregation + the correlation call
- [ ] **DEF** (points-allowed bracket from opponent implied total) and **K** (distance-bucket market caveat)
- [ ] Cross-stat correlation at aggregation — independence vs. market-implied (open tension, §2.5)
- [ ] Monte Carlo aggregation + exact-bonus scoring spec
- [ ] Calibration/backtest harness

---

## Changelog

- **v0.9** — Made the doc ruleset-agnostic: separated the (objective) method from this project's specific config and goal — the top matter now frames the method as producing a full distribution for *any* ruleset, with the top-3 goal recast as a usage lens (§5) and worked-example headings generalized ("a continuous stat", "a discrete count"). Enabled receptions / PPR: receptions are always modeled as a count (§4.5) and scored by the configured per-reception value — 0 here (non-PPR) so no impact, but enabling PPR is a pure config change. Updated §2.3/§2.4/§2.5/§3.7 accordingly.
- **v0.8** — Added QB passing stats, all reusing existing engines via config: passing yards (§3.7), passing TDs and interceptions (§4.5, the first negative stat). Established **scoring is configuration** with the §2.4 parameter table.
- **v0.7** — Added the Touchdowns worked example (§4): cumulative scorer lines differenced into a pooled rush+rec TD count, ×6 for points, using only the lines the book posts.
- **v0.6** — Removed all availability/early-exit framing. The graph is dictated purely by book odds.
- **v0.5** — Established the **market-translation-only** design principle (median aggregate across books; superseded manual per-book weights; correlation and fumbles reframed as open tensions).
- **v0.4** — Receiving yards folded in as identical math to rushing.
- **v0.3** — Reorganized: split general method (§2) from the worked example (§3); status tags; one open-items list.
- **v0.2** — Added combining multiple books (later superseded in v0.5).
- **v0.1** — Initial doc. Pipeline overview + rushing yards fully worked + floor/mid/ceiling and matchup-leverage usage.
