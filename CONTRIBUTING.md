# Contributing / working agreement

Single-maintainer hobby project. This file is the process contract — environments,
branching, CI/CD, hygiene — so future-you (or an AI assistant picking the repo up
next season) doesn't re-derive it, and the repo doesn't quietly rot again.

## Environments

Two environments, each pinned to its own GHCR tag:

| Env        | Branch      | GHCR tag  | Container on home server |
| ---------- | ----------- | --------- | ------------------------ |
| Test       | `feature/*` | `:test`   | `odds-fantasy-test`      |
| Production | `main`      | `:latest` | `odds-fantasy`           |

Delivery is **pull-based**: CI never reaches into the home server. It pushes the
branch-appropriate tag to GHCR; Watchtower on the server polls each container's
tag and recreates it on a new digest. Promotion is a merge, never a manual image
copy.

> **`dev/*` branches deploy nowhere.** They still get full CI — lint and tests
> run on every push — but they derive no image tag, so nothing is published and
> no container moves. Verification against a running app happens on Test, after
> the `dev/*` → `feature/*` merge.

> **Test is last-merge-wins.** There is one `:test` tag, shared by every
> `feature/*` branch, so two feature branches in flight will overwrite each
> other's Test deploy and the container ends up running whichever merged last.
> Only one feature branch should expect to own Test at a time.

## Branching model

Strict promotion, always: `dev/*` → `feature/*` → `main`. There is no shortcut
for small changes — a one-line fix takes the same path as a season rewrite.

- **`dev/<kebab-case>`** — one logical change, cut from the `feature/` branch it
  belongs to. All code enters the repo here. Every push runs lint and tests;
  nothing is published and nothing deploys.
- **`feature/<kebab-case>`** — an initiative-sized body of work, cut from the tip
  of `main` so its diff against `main` is exactly what this initiative changed.
  Never committed to directly; it only receives merges from `dev/*` branches
  whose CI is green. Any merge publishes `:test` → Test.
- **`main`** — the default branch, always deployable. Merges require a review
  from the repo owner. A merge publishes `:latest` → Production, so treat it as
  a production deploy, not a checkpoint.

Naming: `feature/kebab-case-name`, `dev/kebab-case-name`. No other prefixes.

## Workflow

1. Cut a `feature/` branch from `main` for the initiative if one does not exist.
2. Cut a `dev/` branch from that feature branch for one logical change.
3. Make the change. Run `ruff check`, `ruff format --check`, and
   `python -m pytest tests/` locally before pushing.
4. Push. CI runs lint and tests; nothing deploys from a `dev/` branch. A red
   check here is a hard stop.
5. Open a PR `dev/*` → its feature branch. Merge only with green CI, then delete
   the `dev/` branch. The merge publishes `:test` and updates Test.
6. Exercise Test against live data for at least one real session. This is not
   optional for application changes.
7. Open a PR `feature/*` → `main` and get a review from the repo owner. Merging
   publishes `:latest` and updates Production. Delete the feature branch.

## Pull request descriptions

The first thing in every PR description is what the reviewer should test. Open
with a `## What to test` heading and a short bullet list.

- Five bullets at most.
- One line each: concrete action, then expected result.
- Say where to test it: URL, endpoint, command, or file.
- Lead with the thing most likely to be wrong.
- Explicitly flag anything that could not be verified before review.

Implementation detail, rationale, tests, and design notes come after that list.

## CI/CD pipeline

`ci.yml` is the only entrypoint. It runs on pushes to `dev/**`, `feature/**`, and
`main`, on pull requests, and via manual `workflow_dispatch`. It derives the
image tag from the branch and calls three reusable stages:

1. **`lint.yml`** — `ruff check`, `ruff format --check`, and a syntax compile
   check across tracked Python files.
2. **`test.yml`** — installs dependencies and runs `python -m pytest tests/`.
3. **`publish.yml`** — builds and pushes to `ghcr.io/<owner>/<repo>` using the
   built-in `GITHUB_TOKEN`. `feature/**` publishes `:test`; `main` publishes
   `:latest`; `dev/**` publishes nothing. Publishing is skipped for PR events.

The publish workflow preserves the build metadata used by `/health` and the UI
footer (`GIT_COMMIT`, `GIT_BRANCH`, `IMAGE_TAG`, `BUILT_AT`).

The repo must allow GitHub Actions **Read and write** permissions so
`GITHUB_TOKEN` can publish packages.

**A red check is a hard stop**, not a merge-anyway condition.

Editing workflow files is not human-only. Try the change with the available
GitHub credentials; only fall back to a human edit if GitHub actually rejects
the workflow write.

## Documentation

- **`README.md`** — concise external perspective: how to use and run the app.
  Update it in the same change when user-visible behavior or the real entrypoint
  changes.
- **`AGENTS.md`** — deep implementation reasoning, architecture, rejected
  approaches, and current behavior.
- **`CONTRIBUTING.md`** — process only.
- **`docs/*.md`** — durable long-form specifications. Every spec must be linked
  from `AGENTS.md`.

## Keeping the repo from rotting again

- If you replace an implementation, delete the old one in the same PR. Git
  history is the backup.
- The README's project-structure section must name the real entrypoint.
- No scratch/debug files at the repo root. Use a git-ignored `scratch/` area or
  do not commit them.
- Do not commit `data/` or `.env`.
- If a file is not imported or linked from anywhere, verify that it is dead and
  delete it rather than commenting it out.
- Delete every `dev/` and `feature/` branch as soon as its PR is merged.

## Odds API quota awareness

The quota is a metered, shared resource, not a rate limit to retry past.
`oddsfantasy/ratelimit.py` tracks it from response headers and
`oddsfantasy/odds_client.py` TTL-caches responses (`ODDS_TTL`, default 12h).
Features that fetch odds for more than the caller's own roster cost materially
more than the weekly lineup flow, so:

- Default to a conservative market set; skip `_alternate` markets without a
  specific reason.
- Make expensive fetches opt-in, not automatic on page load or refresh.
- Respect `cache_mode`/`fresh` consistently.

## Season-to-season maintenance

This app can sit dormant for much of the year. At the start of each season:

- Confirm `data/sleeper_players.json` and odds caches are not stale. Force a
  player refresh with `fresh=1` on first use of the season regardless of TTL.
- Re-read this file and README known limitations before trusting projections.
