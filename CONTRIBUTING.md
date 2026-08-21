# Contributing / working agreement

Single-maintainer hobby project. This file is the process contract — environments,
branching, CI/CD, hygiene — so future-you (or an AI assistant picking the repo up
next season) doesn't re-derive it, and the repo doesn't quietly rot again.

## Environments

Three environments, each pinned to its own GHCR tag:

| Env | Purpose     | Branch      | GHCR tag  | Container on home server |
| --- | ----------- | ----------- | --------- | ------------------------ |
| E1  | Development | `dev/*`     | `:e1`     | `odds-fantasy-e1`        |
| E2  | Test        | `feature/*` | `:e2`     | `odds-fantasy-e2`        |
| E3  | Production  | `main`      | `:latest` | `odds-fantasy`           |

Delivery is **pull-based**: CI never reaches into the home server. It pushes the
branch-appropriate tag to GHCR; Watchtower on the server polls each container's
tag and recreates it on a new digest. Promotion is a merge, never a manual image
copy.

> **E1 is last-push-wins.** There is one `:e1` tag, shared by every `dev/*`
> branch, so two active dev branches will overwrite each other's E1 deploy and
> the container ends up running whichever pushed last. Only one dev branch
> should expect to own E1 at a time.

## Branching model

Strict promotion, always: `dev/*` → `feature/*` → `main`. There is no shortcut
for small changes — a one-line fix takes the same path as a season rewrite.

- **`dev/<kebab-case>`** — one logical change, cut from the `feature/` branch it
  belongs to. All code enters the repo here. Every commit publishes `:e1` → E1.
- **`feature/<kebab-case>`** — an initiative-sized body of work (e.g.
  `feature/season-2026-readiness`), cut from the tip of `main` so its diff
  against `main` is exactly "what this initiative changed." Never committed to
  directly; it only receives merges from `dev/*` branches already validated on
  E1. Any merge publishes `:e2` → E2.
- **`main`** — the default branch, always deployable. Merges require a review
  from the repo owner. A merge publishes `:latest` → E3, so treat it as a
  production deploy, not a checkpoint.

```
  dev/cleanup ──┐
  dev/ci ───────┼──► feature/season-2026-readiness ──► main
  dev/draft ────┘
      :e1                      :e2                     :latest
      E1 (dev)                 E2 (test)               E3 (prod)
```

Naming: `feature/kebab-case-name`, `dev/kebab-case-name`. No other prefixes.

## Workflow

1. Cut a `dev/` branch from the relevant `feature/` branch. If there isn't one
   for this work yet, cut the `feature/` branch from `main` first.
2. Make the change. Run `ruff check`, `ruff format --check`, and
   `python -m pytest tests/` locally before pushing.
3. Push. Every commit auto-deploys to **E1** — verify the change there.
4. Open a PR `dev/*` → its feature branch. Merging auto-deploys to **E2**.
5. Exercise E2 against live data for at least one real session. Unit tests catch
   regressions in the math; they don't catch "the lineup looks wrong" or "this
   endpoint times out against real odds data."
6. Open a PR `feature/*` → `main` and get a review from the repo owner. Merging
   auto-deploys to **E3**. Deleting the feature/dev branches afterward is fine —
   the merge commits keep the history.

## CI/CD pipeline

Modular, built from widely-used marketplace actions and composed with
`workflow_call` reusable workflows. `ci.yml` is the only entrypoint — `on: push`
for `dev/**`, `feature/**`, `main`, plus `on: pull_request` — and it derives the
image tag from `github.ref`, then calls three stages in sequence:

1. **`lint.yml`** — `actions/checkout@v4`, `astral-sh/ruff-action@v3`:
   `ruff check` and `ruff format --check`, plus a `python -m compileall` syntax
   check. Ruff is the whole linting story: no ESLint, no mypy.
2. **`test.yml`** — `actions/checkout@v4`, `actions/setup-python@v5` (with pip
   cache), then `python -m pytest tests/`.
3. **`publish.yml`** — `docker/setup-buildx-action@v3`, `docker/login-action@v3`,
   `docker/metadata-action@v5`, `docker/build-push-action@v6`. Pushes to GHCR
   under the derived tag (`dev/**` → `:e1`, `feature/**` → `:e2`, `main` →
   `:latest`). Gated on lint and test passing, and skipped for pull requests —
   the merge is what deploys, not the PR.

**A red check is a hard stop**, not a "merge anyway and fix later."

> **Planned, not built.** Today the repo has `test.yml` (pytest on PRs and pushes
> to `main`) and `build.yml` (pushes `:latest` on `main`). The pipeline above is
> the target and lands as a separate change, because **files under
> `.github/workflows/` must be added and edited by a human** — GitHub rejects
> automation tokens without an explicit `workflow` scope.

## Documentation

Three files, three jobs — keeping them separate is what stops the README from
drifting into describing an app that stopped being the real entrypoint.

- **`README.md`** — concise, external perspective: how to use it, how to test it.
  Not inner workings. Updated in the same commit as any change that alters how
  someone uses or runs the app.
- **`AGENTS.md`** — the deep document: all reasoning and logic behind the repo's
  details. Why the model is shaped this way, why the quota rules exist, what was
  tried and rejected. No length limit. *(Written during the cleanup pass.)*
- **`CONTRIBUTING.md`** — this file. Process only. Rationale goes in `AGENTS.md`.

## Keeping the repo from rotting again

The August 2026 cleanup found two full parallel implementations (`main.py` +
`predicted_stats.py` + `odds_api.py` vs. `refactored/`), a dead Yahoo
integration, a UI file not linked from `index.html`, and a README describing an
app that hadn't been the real entrypoint in months — not sloppiness, just the
default outcome when a solo project has no rule against it. So:

- **If you replace an implementation, delete the old one in the same PR.** Git
  history is the "just in case." A stale copy that still half-runs looks current
  to the next reader, which is worse than no copy.
- **The README's "Project Structure" section must name the real entrypoint.** If
  you change what the `Dockerfile` `CMD` points at, update the README in the same
  PR.
- **No scratch/debug files at the repo root.** `tmp_*`, one-off patch files,
  ad-hoc debug scripts — use a git-ignored `scratch/` or don't commit them.
- **Don't commit `data/` or `.env`.** `.gitignore` already excludes `data/`;
  double check before `git add -A` on anything touching config or caching.
- **If a file isn't imported/linked from anywhere, it's dead — delete it, don't
  comment it out.** Verify with `grep` first, then delete completely.

## Odds API quota awareness

The quota is a metered, shared resource, not a rate limit to retry past.
`refactored/ratelimit.py` tracks it from response headers; `refactored/odds_client.py`
TTL-caches responses (`ODDS_TTL`, default 12h). Any feature fetching odds for
**more than the caller's own roster** (the way `refactored/draft_prep.py`'s draft
board does) costs meaningfully more than the weekly lineup flow, so:

- Default to a conservative market set; skip `_alternate` markets without a
  specific reason.
- Make it opt-in — a button or endpoint the user hits, not something firing on
  every page load or dashboard refresh.
- Respect `cache_mode`/`fresh` like every other endpoint.

*(Why these rules exist moves to `AGENTS.md` once it exists; keep the actionable
rules here.)*

## Season-to-season maintenance

This app goes dormant ~8 months a year — the `odds-fantasy` container sitting
`Exited` in the Unraid Docker tab most of the year is expected, not broken. At
the start of each season, before trusting any projection:

- Confirm `data/sleeper_players.json` and the odds cache aren't stale from last
  season. `ODDS_TTL` auto-expires odds; the Sleeper players cache has its own
  `SLEEPER_PLAYERS_TTL` (default 24h) — force-refresh with `fresh=1` on first use
  of the season regardless.
- Re-read this file and the README's "Known limitations" section — they're meant
  to be updated in place as gaps get closed, not left stale.
