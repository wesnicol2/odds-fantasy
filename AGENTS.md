# AGENTS.md — why this repo is shaped the way it is

The deep document. `README.md` covers how to use the app and `CONTRIBUTING.md`
covers process; this file holds the reasoning behind the code — the modelling
decisions, the constraints they answer to, and the things that were tried and
rejected. There is no length limit here. If you are about to write a paragraph
of rationale in a code comment or in the README, it probably belongs here.

## Which docs an agent may change

The four documents in this repo are not equally open to edit. An assistant
working here should treat them as two tiers.

**Keep current as you go — `README.md` and `AGENTS.md`.** If a change you make
contradicts something either file says, update it in the same commit. A change
that alters how someone runs or uses the app belongs in the README; a change
that alters why the code is shaped the way it is belongs here. This is not
optional tidying: a doc that describes an app that no longer exists is exactly
how this repo rotted the first time, and the next reader has no way to tell
that a stale sentence is stale. Do not leave it for a follow-up.

**Do not touch without explicit human approval — `CONTRIBUTING.md` and
`docs/fantasy-projection-methodology.md`.** These two are the contracts. One
defines how work moves through the repo, the other defines what the model is
supposed to compute; the rest of the repo is measured against them, so an
agent editing them unasked is an agent quietly moving the goalposts it is
being judged by. Ask first and get a clear yes, every time. This holds on a
`dev/` branch as much as anywhere else — being unmerged is not permission,
because review is precisely where an unrequested change to a contract is
easiest to wave through. If work seems to require changing one of them, say
so, propose the specific edit and wait.

The asymmetry is deliberate. Getting a stale README fixed is cheap and the
downside of not fixing it is real; changing a contract is cheap to do and
expensive to notice.

---

## The core idea

Sportsbooks price player props more carefully than any free fantasy projection
does, because they lose money when they're wrong. A line of "Josh Allen over
249.5 passing yards at -115" is a probability statement, and a full set of those
across every book is a distribution. This app's whole thesis is that converting
those lines into fantasy points beats consuming somebody else's projection
number, *and* that the honest output is a range rather than a single number.

Everything below follows from that.

## Turning odds into a range

### De-vigging comes first

Raw implied probabilities from a two-sided market sum to more than 1 — that
excess is the book's margin (the "vig"). Using raw implied probability
systematically overstates every event. The feed quotes **decimal** odds (The
Odds API's default format, and no `oddsFormat` is passed), so the conversion is
just `1/odds` — `predicted_stats.implied_probability` and
`market_math.decimal_to_probability`. `aggregator.py` and `market_math.py` both
de-vig per book when both sides of a market are present, normalising over/under
to sum to 1. `market_math.american_to_probability` exists only so the
methodology doc's worked examples, which are quoted in American odds, can be
run through the real code as tests.

De-vig **per book, then combine across books** — not the other way around. Books
carry different margins, so combining raw implied probabilities across books
blends their vig into the result in a way you can't back out afterwards.

The combine step is a **median** of the per-book de-vigged probabilities
(`aggregator.py`), not a mean. The median is the robustness: a single stale book
that hasn't repriced for an injury or weather can't drag the consensus, and no
per-book weights or outlier rules are needed on top of it. Note the residual
naming debt — `MarketSummary` still calls the fields `avg_over_prob`,
`avg_under_prob` and `avg_threshold` from when this was a mean, and the values
they hold are medians.

### The methodology engine (`model=market`, the default)

`docs/fantasy-projection-methodology.md` is the spec: it argues, from the
market up and independent of any code, what the model should compute. Three
modules implement it, one per stage, and nothing else in the package needs to
know which stage it is talking to:

- **`scoring.py`** — the league's rules as configuration. Values, the
  per-reception value and bonus *(threshold, amount)* pairs all come from
  Sleeper's `scoring_settings`. The threshold is the part that used to be
  hardcoded: Sleeper only gives us a key like `bonus_rush_yd_100`, so the
  number is parsed out of the key name rather than paired with a literal `100`
  in the code. A league with `bonus_rush_yd_150` therefore works with no code
  change, which is what "ruleset-agnostic" has to mean to be worth claiming.
- **`market_math.py`** — odds to distribution. Per-book proportional de-vig,
  median across books, isotonic (PAV) to kill any dip, then either monotone
  cubic (PCHIP) between anchors with lognormal tails for yardage, or straight
  differencing of the cumulative lines for counts.
- **`projection.py`** — the player's curve. Draw from every stat, score each
  draw with the real configured scoring, sum, and read floor / mid / ceiling
  off the result as its 10th / 50th / 90th percentiles.

Four decisions inside that are worth not re-deriving:

**Counts are differenced, not fitted.** For touchdowns, receptions,
interceptions and passing touchdowns the posted cumulative lines *are* the
survival curve, so the distribution is read off directly: `P(0) = 1 - P(≥1)`,
`P(exactly 1) = P(≥1) - P(≥2)`, and so on. The highest posted line becomes the
top bucket scored at its floor — those games have *at least* that many, and
with no higher line we don't invent the mass above it. A Poisson fit survives
only for the genuinely under-determined case (the ladder starts above 1, so
differencing can't reach `P(0)`), which the doc leaves open pending
calibration.

**Bonuses stack.** A 210-yard rushing game collects both the 100- and the
200-yard bonus. The older code awarded only the highest (`elif`), which
contradicts the doc's expectation identity
`E = rate × E[stat] + Σ amount_i × P(≥ threshold_i)` — that only holds if each
threshold pays independently. Sleeper's own scoring stacks them too.

**Stats are summed independently, and that understates the right tail.** This
is the one place the market-translation-only principle bites: a player's stats
genuinely move together, but books quote marginals and this feed carries no
market that prices the joint. The alternatives were to assume independence or
to invent a correlation matrix; we took the first and say so. Ceilings are
therefore conservative for tightly coupled stats, a QB's passing yards and
passing touchdowns most of all.

**Sampling is seeded.** A fixed seed means the same odds produce the same
projection every time, so refreshing a page can't reshuffle a lineup. The seed
is shared across players, which makes the draws common random numbers: two
players compared on one screen were dealt the same luck.

Two smaller judgement calls, both places the doc stops short:

- A **one-sided ladder rung** ("125+" with no under posted) can't be de-vigged
  as a two-way market. It's corrected by that same book's *own* measured
  overround on that market — its margin, read off its two-way lines. That
  keeps it market-derived rather than picking a constant.
- A **continuous market with a single anchor** is under-determined: two points
  is the minimum a lognormal needs. It falls back to the shape described in the
  next section, and stops doing so the moment a second distinct threshold shows
  up anywhere in the feed — which multiple books usually supply on their own,
  since they rarely post the identical line.

The older models (`const`, `puelz`, `angelini`, `baseline`) are still
selectable via `?model=`, so the two approaches can be compared on the same
odds; the section below is what they do.

### One line is not a distribution, so pick a shape

The older models take a single (threshold, over-probability) pair per market,
which pins exactly one point on the CDF. Getting floor/mid/ceiling out of one point
requires assuming a shape, and the shape matters more than it looks:

- **Yardage markets** (`*_yds`) are right-skewed. A receiver with a 49.5-yard
  line has a fat upper tail — the 120-yard game exists, the negative-30-yard
  game does not. Modeled **lognormal**, fit from the threshold/probability pair
  plus the mean.
- **Count markets** (receptions, pass TDs, interceptions) are small non-negative
  integers. Modeled **Poisson**, with lambda fit to the observed CDF point.
- **Anytime TD** is binary. Modeled **Bernoulli** on {0, 1}. The mid uses the
  *mean* rather than the Bernoulli median on purpose: the median is 0 for any
  player under 50%, which would collapse to a step function and destroy the
  ordering between players when building a lineup.
- **Normal** is the fallback only when a shape-specific fit fails outright.

This was the main rejected alternative: a single symmetric Normal for
everything. It's simpler and it's wrong in a way that matters, because it
understates ceilings for exactly the boom/bust receivers where the ceiling is
the whole reason you'd start them.

Floor/mid/ceiling are the 15th/50th/85th percentiles, not min/expected/max.

### As-built here, target in `docs/fantasy-projection-methodology.md`

This section tracks **what the code does today** against the **target method**
in `docs/fantasy-projection-methodology.md` — derived from first principles,
independent of any code, and explicitly "the reference the implementation is
measured against." A reader hitting one without the other is the problem, so
the live position is worth naming. `model=market` is the default engine; the
older models are the row's second column.

| | Target (methodology doc) | `model=market` | Older models |
| --- | --- | --- | --- |
| CDF anchors | full ladder, PCHIP between anchors | every threshold any book posts, base and `*_alternate` alike | one (threshold, probability) pair |
| Count stats | difference the cumulative lines (`§4`) | differenced; Poisson only where the ladder starts above 1 | Poisson fit to the single CDF point |
| Floor / ceiling | 10th / 90th (`§5`) | 10th / 90th of the player's curve | 15th / 85th, per stat |
| Bonus thresholds | thresholds and amounts both configuration (`§2.4`) | both parsed from the league's scoring settings | thresholds hardcoded next to the amounts |
| Bonus scoring | kink priced per outcome (`§2.4`) | exact, applied per simulated draw | expected-value ramp, highest bonus only |
| Aggregation | player-level sum (`§2.5`) | Monte Carlo sum of the stat curves | per-stat only; no joint model |

What is still open, and why:

- **Cross-stat correlation** (`§2.5`) — assumed independent. Not closable from
  this feed; see the engine section above.
- **De-vig method** (`§2.1`) — proportional, as the doc's current choice. Shin
  and power de-vig are candidates the doc wants decided by calibration, and
  there is no calibration harness yet.
- **Sparse single-line counts** (`§2.3`) — Poisson, as an interim. Poisson vs
  negative-binomial is likewise a calibration question.
- **DEF and K** (`§7`) — untouched by the new engine; see the defense section
  below for why the market can't price them.
- **Fumbles and 2-point conversions** — no clean market, so omitted rather
  than estimated.

Closing any of these is a code change, not a doc change — the doc is the spec,
so update it first if the target itself should move.

### Alternate lines are requested for three markets, not all of them

The Odds API sells `*_alternate` markets — the full ladder of thresholds, which
is what turns a fit into a reconstruction. `planner._markets_for_positions`
asks for three of them: `player_rush_yds`, `player_reception_yds` and
`player_receptions`. Passing yards, passing touchdowns and the touchdown
ladders are not requested, so those stats reach the engine with whatever
thresholds the books happen to differ on.

That split is a quota decision, not a modelling one — each extra market
multiplies request size — and it is the main lever left if the yardage curves
look too coarse. The engine reads whatever ladder is present and invents
nothing where one isn't, so widening the set is a one-line change in
`planner.py` with a real cost attached. See the quota section.

### Defense scoring is a known partial model

D/ST floor/mid/ceiling models **only** the points-allowed scoring bracket,
derived from the opponent's implied total (game total and spread → implied
points for one side, `services._implied_total`). Sacks, interceptions, fumble
recoveries and defensive/return TDs aren't modeled at all.

That's not laziness: The Odds API doesn't sell team-level defensive props, so
there is nothing to price them off. Estimating them from historical rates would
mean mixing a fundamentally different data source into an odds-derived model and
silently making the ranges less honest. Left as a documented gap instead.

Kickers are fetched (`POSITION_STAT_CONFIG["K"]`) but never converted to points
or included in the lineup builder, for the same reason plus indifference.

## The Odds API quota

The quota is a metered, shared, monthly resource — not a rate limit you retry
past. Blowing it means the app is dead until the quota resets, which during the
season means dead when you actually need it.

Three mechanisms defend it:

1. **`odds_client.py` TTL-caches every response to disk** (`ODDS_TTL`, default
   12h) keyed by full URL, with an in-memory layer over it. Lines don't move
   enough within 12 hours to justify re-spending quota on a page refresh.
2. **`ratelimit.py` tracks remaining quota from response headers**, so the
   number in the UI is the book's count, not a local guess.
3. **`planner.py` computes the minimal market set per game** from the positions
   actually on your roster, rather than requesting every market for every game.

The rule for new features: anything that fetches odds for **more than the
caller's own roster** is a different cost class. `draft_prep.py`'s draft board
is the existing example — it has to look at every relevant player on every team
playing that week. That's why the draft board is a distinct opt-in endpoint you
click rather than something the dashboard loads automatically, and why
`_alternate` markets stay off by default.

## Identity: league + team, not username

The UI identifies "you" by Sleeper **league + team**, resolved by league ID —
but the *picking* starts from your username, because nobody has their league ID
memorised.

The flow: enter username → `GET /user/leagues` lists every league found →
pick one (its `league_id` is cookied) → pick which roster is yours (`roster_id`
cookied). Every endpoint accepts `league_id`+`roster_id` as an alternative to
`username`+`season`, and `league_id` wins when both are present
(`services._resolve_identity`).

The rejected simpler design was resolving everything from username alone. It
grabs "the first league this username is in," which silently picks the wrong
league for anyone in more than one — and picks it *silently*, producing a
plausible-looking lineup for a team that isn't yours. The username step is now
purely a lookup convenience, not the identity itself.

The chosen league's Sleeper `status` (`pre_draft`/`drafting` vs.
`in_season`/`complete`) decides whether the UI opens on the draft board or the
weekly lineup. That's read from Sleeper rather than inferred from the calendar,
because leagues draft on wildly different dates.

## Week windows and the pre-season gap

A fantasy week is a Thursday 00:00 → Monday 23:59:59 UTC window.
`weekly_windows.compute_week_windows()` anchors "this week" to *today*: the
current Thu→Mon cycle stays "this" until Tuesday, when it flips to the next one.

That is correct in season and catastrophically wrong outside it, which produced
the most confusing bug this repo has had. During the pre-season gap — roughly
August until the opener — today's nearest Thu→Mon window contains zero games,
because The Odds API only lists regular-season games. Every endpoint that
anchored to it (`/projections`, `/lineup`, `/defenses`, the detail endpoints)
returned a bare empty list. It looked exactly like an expired API key, and was
diagnosed as one first; the health check, event count and rate-limit numbers
were all fine the whole time.

The fix is `weekly_windows.resolve_week_windows()`: if the calendar-anchored
window has no games in it, fall forward to the week of the earliest scheduled
game. It returns `None` only when there are no games at all, and callers surface
`NO_GAMES_SCHEDULED_MESSAGE` instead of an empty list.

**The lesson worth keeping** is not the bug, it's the shape of it: the same fix
had already been applied to the draft board (`draft_prep`, which anchors to the
schedule unconditionally, since a draft only ever happens pre-season) without
anyone checking whether the other callers of `compute_week_windows` had the same
problem. When you fix shared date logic, check every call site and add a
regression test per call site — that's what `tests/test_services_week_windows.py`
is for, separately from `tests/test_weekly_windows.py` which tests the fix
itself.

A related trap: an empty roster and an empty week window produce identical
symptoms. `planned_players=0` with a nonzero event count means "your roster is
empty" (normal before a draft), not "bad week window."

## Repo history worth not relearning

### Two parallel implementations

An August 2026 cleanup found the repo running two full pipelines: `main.py` +
`predicted_stats.py` + `odds_api.py` alongside `refactored/`. Only the latter
was reachable from the Dockerfile. There was also a dead Yahoo integration left
over from before the switch to Sleeper, and a README describing the wrong
entrypoint. All removed. The hygiene rules in CONTRIBUTING.md exist specifically
to stop that recurring.

### `refactored/` was a terrible name and is now `oddsfantasy/`

The package was called `refactored/` because it was, once, the refactored
version of something else. That something else has been gone for a long time,
but the name stuck around long enough that the README needed a sentence
explaining that the folder named "refactored" is the entire application. Renamed
to `oddsfantasy/`. If you find `python -m refactored.api` anywhere — an old shell
alias, an Unraid template, a bookmark — that's what it means.

`config.py`, `predicted_stats.py` and `sleeper_api.py` sat at the repo root for
the same historical reason and looked like leftovers, but were live code with 19
import sites. They're inside the package now.

### The overrides.js trap

The UI once carried runtime overrides: one inline in `details.js`, one in a
dynamically-loaded `/ui/overrides.js`. An earlier cleanup deleted `overrides.js`
after grepping `index.html` for `<script src>` tags and finding no reference —
but `details.js` injected the script tag *at runtime*, which a static grep can't
see. It broke the UI, and was only caught by a headless-browser console-error
check.

Two things follow. First, "unreferenced" for a JS file means unreferenced by
static markup *and* not injected at runtime — grep for the filename as a string,
not just as a tag. Second, `details.js` had accumulated three generations of the
same `renderMarketBlock` function, one of them with genuinely corrupted markup
(`class="market"summary-`, mojibake'd em-dashes) from some earlier edit, and only
the middle one was ever called. Dead UI code here is not inert; it is confusing
and occasionally load-bearing.

The incomplete-badge rendering that used to live in those overrides is now
directly in `script.js`'s `renderPlayers`/`renderLineup`.

## Deployment shape

Two environments -- Test (`:test`) and Production (`:latest`) -- each pinned to
its own GHCR tag, with Watchtower on the home server polling and recreating
containers. CI never reaches into the server. The full model is in
CONTRIBUTING.md; the reasoning for it is just that a pull-based deploy needs no
inbound access to a home network and no credentials stored in GitHub beyond a
registry token.

There was briefly a third tier, a per-`dev/*` environment on a shared `:e1` tag.
It was dropped before anything ran on it: one shared tag across every dev branch
means concurrent branches clobber each other's deploy, which makes the
environment untrustworthy exactly when more than one thing is in flight. Dev
branches still get full CI; they just don't deploy. Verification against a
running app happens on Test.

The app is dormant ~8 months a year. A container sitting `Exited` in the Unraid
Docker tab most of the year is the expected steady state, not a fault.

## Things deliberately not done

- **No database.** Everything is JSON files under `data/`. The dataset is one
  roster and one week of odds; anything more would be architecture for its own
  sake.
- **No async framework.** `api.py` is a stdlib WSGI server with a thread pool
  for concurrent odds fetches (`services._fetch_odds`). The workload is a
  handful of concurrent HTTP calls a few times a week.
- **No frontend build step.** Plain classic scripts, no bundler, no npm. The UI
  is served straight off disk by the same process.
- **No mypy, no ESLint.** Ruff only. See CONTRIBUTING.md.
- **Errors are swallowed at network and payload boundaries** on purpose, which
  is why `S110`/`BLE001` are disabled in the Ruff config. One malformed
  bookmaker payload should degrade one market, not take down a projection run.
  This is a real tradeoff — it does hide bugs — and the mitigation is that
  those paths log rather than pass silently.
