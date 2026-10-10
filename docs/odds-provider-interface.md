# Odds provider interface

## Purpose

Odds Fantasy accepts market evidence from multiple external providers without allowing provider-specific transport formats or modeling choices to leak into projection math.

The stable boundary is:

`provider API -> provider adapter -> canonical market evidence -> source consensus -> distribution -> fantasy scoring`

The Odds API, Polymarket, and Kalshi are providers. A provider is not necessarily a consensus source: The Odds API can return many sportsbooks, while Polymarket and Kalshi normally each represent one source.

## Canonical contract

Every adapter implements `OddsProvider.fetch_quotes(ProviderRequest) -> ProviderResult` and returns `StatContractQuote` objects. A quote carries:

- application-owned game and player identity;
- a canonical market key such as `player_reception_yds`;
- an explicit settlement predicate (`>`, `>=`, `<`, `<=`) and threshold;
- raw executable YES/NO implied probabilities;
- independent source identity separately from provider identity;
- observation time, phase, and provider provenance.

Adapters may also return `BenchmarkQuote` objects for explicit fantasy-point markets. Benchmarks never feed the stat projection.

## Invariants

1. **Provider identity is not source identity.** Consensus gives one vote to each unique `source_id`.
2. **Canonical prices are probabilities.** Decimal/American/contract formats are transport details retained only as provenance/display metadata.
3. **Settlement semantics are preserved before normalization.** `75+` and `Over 74.5` can both normalize to the same integer-stat survival boundary without pretending the provider published identical text.
4. **Adapters do not de-vig or model.** They discover, match, parse, and normalize vendor evidence only.
5. **Core math owns de-vigging and consensus.** Every source is handled by the same downstream methodology.
6. **Main vs alternate is presentation metadata only.** Every threshold is evidence on the same source-level survival curve.
7. **Application identity is canonical.** Provider event/market/token IDs are provenance, never primary player/game identity.
8. **Partial provider failure is isolated.** One provider failing cannot suppress usable evidence from another.
9. **Duplicate sources count once.** If an aggregator and a direct adapter expose the same source, direct evidence wins only to choose the representation; it does not receive extra consensus weight.
10. **Fantasy-point markets are benchmarks.** They may compare against the model only when their scoring definition is known; they do not become model inputs.

## Predicate normalization

The projection engine represents survival evidence as `P(stat > threshold)`. NFL box-score stats used here are integer-valued, so adapters preserve the native predicate and the common compatibility layer maps it centrally:

| Provider predicate | Model boundary | YES maps to |
| --- | --- | --- |
| `stat > x` | `x` | over |
| `stat >= n` | `n - 0.5` | over |
| `stat < n` | `n - 0.5` | under |
| `stat <= n` | `n + 0.5` | under |

This prevents provider adapters from embedding subtly different threshold semantics.

## Compatibility boundary

The current projection engine still accepts the historical `player -> source -> market -> over/under` map. `quotes_to_players_odds()` is the single compatibility adapter from canonical evidence into that map. It emits a derived decimal-equivalent price only so the existing de-vig implementation remains behaviorally identical while migration occurs; `SidePrice.implied_probability` remains the canonical value.

`aggregate_by_week()` is the application integration seam. It delegates Odds API-only normalization to `aggregate_odds_api_by_week()`, asks `provider_service` for all enabled provider evidence, and returns the same mapping shape that the projection engine already consumes. The returned `ProviderOddsMap` also carries structured provider diagnostics, external benchmark quotes, and the provider IDs that participated as metadata; those fields do not enter projection math.

## Runtime composition

The default provider set is `odds_api,polymarket,kalshi`. Set `ODDS_PROVIDERS` to a comma-separated subset when an environment needs to disable a provider explicitly.

The Odds API remains the schedule/planning source. `PlannedGame` retains the request's region and operational data mode so the same plan can be presented to every provider adapter without a second scheduling model. Direct providers are fetched concurrently and independently; a failure becomes a diagnostic result and does not suppress evidence from the other providers.

Operational data modes retain their existing meaning across all providers:

- `auto` may reuse provider-owned cached evidence until its TTL expires;
- `cache` forbids network refreshes and reports cache misses diagnostically;
- `fresh` bypasses reusable provider cache entries.

Polymarket and Kalshi caches default to 15 minutes and may be configured with `POLYMARKET_ODDS_TTL` and `KALSHI_ODDS_TTL`. Each adapter owns its transport/cache implementation, but cache policy does not alter modeling weight.

## Provider responsibilities

A provider adapter owns authentication/networking, provider-specific discovery, provider IDs, parsing settlement rules, converting native executable prices to raw implied probabilities, caching/rate-limit behavior, and diagnostics.

It must not own de-vigging, source weighting, cross-source consensus, distribution reconstruction, fantasy scoring, or player projections.

## Diagnostics

Provider results carry structured diagnostics with provider, code, severity, and optional game/player/market/provider-market identity. The ingestion layer distinguishes transport failure, cache miss, game mapping failure, market not found, ambiguous settlement, unusable price, live/closed market rejection, and successful contribution counts.

These diagnostics exist to make coverage empirically testable rather than inferred from a low final book count.

## Fantasy-point benchmark boundary

`BenchmarkQuote` is intentionally implemented as a separate channel so a provider can eventually expose explicit fantasy-point probabilities without contaminating the stat-derived model. An adapter may populate that channel only when the provider market's scoring definition is known. A benchmark can then be compared with the application's projection under a compatible scoring profile; it is never inserted into the stat-source consensus.

## Acceptance criteria

The architecture is considered successful when:

- The Odds API can be expressed through the canonical contract without changing existing projections for the same evidence.
- Polymarket and Kalshi quotes enter the same per-source consensus as sportsbook evidence with no provider-specific weighting.
- A duplicate underlying source cannot receive two consensus votes.
- Unsupported, ambiguous, stale, or failed provider evidence is diagnosable and cannot corrupt other providers' results.
- Adding a future provider requires an adapter and contract tests, not projection-engine changes.
