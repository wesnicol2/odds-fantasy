# AGENTS.md — why this repo is shaped the way it is

The deep document. `README.md` covers how to use the app and `CONTRIBUTING.md`
covers process; this file holds the reasoning behind the code — the modelling
decisions, the constraints they answer to, and the things that were tried and
rejected. There is no length limit here. If you are about to write a paragraph
of rationale in a code comment or in the README, it probably belongs here.

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
systematically overstates every event. `predicted_stats.implied_probability`
converts American odds to a probability, and `aggregator.py` de-vigs per book
when both sides of a market are present, normalising over/under to sum to 1.

De-vig **per book, then average across books** — not the other way around. Books
carry different margins, so averaging raw implied probabilities across books
blends their vig into the result in a way you can't back out afterwards. There
is a known wart here: `aggregator.py` averages the per-book de-vigged
probabilities, and an average of averages isn't strictly correct when books have
different numbers of markets. It's fine for a first pass and hasn't been worth
fixing.

### One line is not a distribution, so pick a shape

Usually there's a single (threshold, over-probability) pair per market, which
pins exactly one point on the CDF. Getting floor/mid/ceiling out of one point
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

### Alternate lines are deliberately not used by default

The Odds API sells `*_alternate` markets — the full ladder of thresholds, which
would give many CDF anchors instead of one and make the fits genuinely
data-driven rather than assumed. They are skipped by default anyway, because
they multiply request size for a refinement the lognormal/Poisson fallback
already approximates reasonably. This is a quota decision, not a modelling one.
See the quota section.

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

Three environments (E1/E2/E3), each pinned to its own GHCR tag, with Watchtower
on the home server polling and recreating containers. CI never reaches into the
server. The full model is in CONTRIBUTING.md; the reasoning for it is just that
a pull-based deploy needs no inbound access to a home network and no credentials
stored in GitHub beyond a registry token.

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
