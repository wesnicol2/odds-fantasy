# Contributing / working agreement

This is a single-maintainer hobby project, not a public OSS project soliciting
outside contributions — this doc exists so future-you (or an AI assistant
picking the repo back up next season) doesn't have to re-derive "how do we do
things here" from scratch, and so the repo doesn't quietly rot into two
divergent implementations again (see: `main.py` vs `oddsfantasy/`, discovered
and removed August 2026).

## Branching model

Three kinds of branches, three purposes:

- **`main`** — always deployable. Every push to `main` triggers
  `.github/workflows/build.yml`, which builds and pushes the `:latest` image
  to GHCR — that image is what the Unraid container actually runs. Treat a
  push to `main` as a real deploy, not a checkpoint.
- **`feature/<name>`** — a body of related work with a season/initiative-sized
  scope (e.g. `feature/season-2026-readiness`). Branched from the current tip
  of `main` (so its diff against `main` is exactly "what this initiative
  changed," reviewable as a whole). Nothing is committed to a feature branch
  directly — it only ever receives merges from `dev/` branches. Once a
  feature branch has been tested (see below), it gets merged into `main` via
  PR.
- **`dev/<name>`** — one logical change, scoped to a single PR
  (e.g. `dev/draft-prep`, `dev/contributing-guidelines`). Branched from the
  feature branch it belongs to. **Dev branches never merge to `main`
  directly** — they always target the feature branch they were cut from.

```
main ──● feature/season-2026-readiness ──● ──● ──●  (tested here, then → main)
                       ▲          ▲       ▲
                dev/cleanup   dev/ci   dev/draft-prep
```

Naming: `feature/kebab-case-name`, `dev/kebab-case-name`. No other prefixes.

## Workflow

1. Cut a `dev/` branch from the relevant `feature/` branch (or from `main` if
   there's no active feature branch — small standalone fixes don't need a
   feature branch wrapper).
2. Make the change. Run `python -m pytest tests/` locally before opening a PR.
3. Open a PR: `dev/*` → the feature branch (or → `main` for standalone
   fixes). Even solo, use a PR rather than pushing directly — it keeps the
   diff reviewable and matches the rest of this repo's history.
4. Once a feature branch has everything it needs, actually run it
   (`python -m oddsfantasy.api`, or the Docker image) against live data for at
   least one real session before opening the `feature/*` → `main` PR. Unit
   tests catch regressions in the math; they don't catch "the lineup looks
   wrong" or "this endpoint times out against real odds data."
5. Merge `feature/*` → `main` via PR once it's been exercised for real.
   Deleting the feature/dev branches afterward is fine — the merge commits
   keep the history.

## Testing gate

`python -m pytest tests/` must pass before any merge. A `.github/workflows/test.yml`
CI check (added by hand — GitHub blocks API/automation tokens without an
explicit `workflow` scope from touching files under `.github/workflows/`,
so this one has to be added/edited by a human) runs this on every PR once in
place — treat a red check as a hard stop, not a "merge anyway and fix later."

## Keeping the repo from rotting again

The August 2026 cleanup found two full parallel implementations
(`main.py`+`predicted_stats.py`+`odds_api.py` vs. `oddsfantasy/`), a dead
Yahoo integration nobody removed after switching to Sleeper, a UI file
(`overrides.js`) not even linked from `index.html`, and a README describing
an app that hadn't been the real entrypoint in months. None of that was
malicious or even sloppy in the moment — it's just what happens by default
when a solo project doesn't have a rule against it. So:

- **If you replace an implementation, delete the old one in the same PR.**
  Don't leave it "just in case" — git history is the "just in case." A stale
  copy that still runs (or half-runs) is worse than no copy, because it looks
  current to the next person reading the repo.
- **The README's "Project Structure" section must name the real entrypoint.**
  If you change what the `Dockerfile` `CMD` points at, update the README in
  the same PR.
- **No scratch/debug files at the repo root.** `tmp_*`, one-off patch files,
  ad-hoc debug scripts — put them in a git-ignored `scratch/` directory
  (add it to `.gitignore` if it doesn't exist yet) or just don't commit them.
- **Don't commit `data/` or `.env`.** `.gitignore` already excludes `data/`;
  double check before `git add -A` on anything touching config or caching.
- **If a file isn't imported/linked from anywhere, it's dead — delete it,
  don't comment it out.** Verify with `grep` before deleting (that's how
  `overrides.js` and the legacy pipeline were confirmed safe to remove), then
  delete completely rather than leaving a `# removed` marker.

## Odds API quota awareness

The Odds API quota is a real, shared, metered resource — not just a rate
limit to retry past. `oddsfantasy/ratelimit.py` tracks remaining quota from
response headers; `oddsfantasy/odds_client.py` TTL-caches responses
(`ODDS_TTL`, default 12h) so routine use doesn't re-fetch every request.

Any new feature that fetches odds for **more than the caller's own roster**
(the way `oddsfantasy/draft_prep.py`'s draft board does — it has to look at
every relevant player on every team playing that week, not just yours) is a
meaningfully bigger quota cost than the weekly lineup flow. When adding
something like that:
- Default to a conservative market set (skip `_alternate` markets unless you
  have a specific reason — they multiply request size for a refinement the
  lognormal/Poisson fallback already covers reasonably well with a single
  line).
- Make it opt-in (a button/endpoint the user explicitly hits), not something
  that fires automatically on every page load or dashboard refresh.
- Respect `cache_mode`/`fresh` the same way every other endpoint does — don't
  bypass the TTL cache by default.

## Season-to-season maintenance

This app goes dormant for ~8 months a year (see the `odds-fantasy` container
sitting `Exited` in the Unraid Docker tab most of the year — that's expected,
not broken). At the start of each season, before trusting any projection:
- Confirm `data/sleeper_players.json` and the odds cache aren't stale from
  last season (`ODDS_TTL` should auto-expire odds; the Sleeper players cache
  has its own `SLEEPER_PLAYERS_TTL`, default 24h — force-refresh with
  `fresh=1` on first use of the season regardless).
- Re-read this file and the README's "Known limitations" section — they're
  meant to be updated in place as gaps get closed, not left stale.
