# Contributing / working agreement

This file is the process contract for environments, branching, CI/CD and repository hygiene.

## Environments

| Env | Branch | GHCR tag | Home-server container |
| --- | --- | --- | --- |
| Test | `feature/*` | `:test` | `odds-fantasy-test` |
| Production | `main` | `:latest` | `odds-fantasy` |

Delivery is pull-based. CI pushes the tag; Watchtower may pull it on the home server.
CI never needs LAN access.

`dev/*` branches run validation but publish no image. Test is one shared `:test`
tag, so concurrent feature branches are last-write-wins.

## Branching model

Promotion is always `dev/*` → `feature/*` → `main`.

- `dev/<kebab-case>`: one logical change, cut from its feature branch.
- `feature/<kebab-case>`: initiative branch cut from `main`; only receives green
  `dev/*` merges.
- `main`: always deployable. A merge is a production deploy and requires owner review.

No direct commits to `feature/*` or `main`.

## Workflow

1. Create the feature branch from `main` if needed, then a `dev/*` branch from it.
2. Make the change and run `ruff check .`, `ruff format --check .`, and
   `python -m pytest tests/`.
3. Push the dev branch. Red CI is a hard stop.
4. PR `dev/*` → `feature/*`; merge only when green, then delete the dev branch.
5. Feature CI builds the real Docker image and runs the automated container/browser
   smoke test. This is the required pre-production runtime gate.
6. PR `feature/*` → `main` for owner review. Merge only when all CI is green, then
   delete the feature branch.

Testing the actual home-server Test container is **optional**, not a promotion
requirement. It is useful when a change specifically touches Watchtower, GHCR
permissions, Unraid networking/volumes, or another deployment-only behavior that
GitHub Actions cannot reproduce.

## Pull request descriptions

Every PR starts with `## What to test` and at most five one-line bullets. Each
bullet should name the action/location and expected result. Lead with the most
likely failure and explicitly flag anything that was not verified.

## CI/CD pipeline

`ci.yml` is the only entrypoint. It runs on pushes to `dev/**`, `feature/**`, and
`main`, on pull requests, and via `workflow_dispatch`.

1. `lint.yml`: Ruff lint, Ruff format check, Python syntax compile.
2. `test.yml`: deterministic unit/integration tests.
3. `smoke.yml`: for feature/main and PRs targeting main, build the actual
   Dockerfile, start the image, verify `/health` and `/`, then use Chromium via
   Playwright to exercise the player report, player drill-down, Compare Curves,
   defense comparison, and Best Lineup. Sleeper/Odds responses are intercepted
   with deterministic fixtures, so smoke CI spends no Odds API quota.
4. `publish.yml`: after all required gates pass, `feature/**` publishes `:test`
   and `main` publishes `:latest`. Pull requests never publish.

A green smoke test proves the built application boots and its primary browser
flows work. It intentionally does not claim to prove Watchtower or LAN routing.

## Documentation

- `README.md`: how to use/run the product.
- `AGENTS.md`: implementation reasoning and architecture.
- `CONTRIBUTING.md`: process only.
- `docs/*.md`: durable specifications; link every spec from `AGENTS.md`.

Update README with user-visible behavior changes and AGENTS with architecture changes.

## Repository hygiene

- Delete replaced implementations in the same PR; Git history is the backup.
- No scratch/debug files at repo root.
- Do not commit `data/` or `.env`.
- Remove dead unlinked/unimported files after verifying they are dead.
- Delete merged `dev/*` and `feature/*` branches promptly.

## Odds API quota awareness

The quota is a metered shared resource. `oddsfantasy/odds_client.py` caches API
responses and `oddsfantasy/ratelimit.py` records quota headers.

- Do not refetch data that can be shared from an existing context/cache.
- Keep broad or alternate-market fetches deliberate.
- `Defenses` is an explicit user-selected section; it fetches only game
  `spreads,totals`, once per game, and caches the result.
- Respect `cache_mode` / `fresh` consistently.
- Automated smoke tests must mock upstream responses and spend zero live quota.

## Season-to-season maintenance

At the start of a season, refresh Sleeper player metadata and inspect odds caches
before trusting projections. Re-read README limitations and the methodology spec
when league scoring or available sportsbook markets change.
