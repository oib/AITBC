## Preparation Phase
- Verify that all prerequisite releases are merged and tagged.
- Set up a test environment matching the target release's dependencies.
- Run existing test suite to ensure baseline passes before coding.
- Review the CHANGELOG and any linked design documents for ambiguities.
- Coordinate with relevant agents (A/B) to clarify file ownership and avoid conflicts.

# v0.8.1 Suggestions

## Status
**CLAIMS CONFIRMED** — IslandManager has no offer sync. Distributed search index not identified. Staleness threshold too aggressive.

## Confirmed Gaps (verified in /opt/aitbc)
1. **IslandManager is a membership registry only**: `apps/blockchain-node/src/aitbc_chain/network/island_manager.py` (264 lines) — 14 methods, none related to offer sync.
2. **No distributed search index**: No library identified for cross-chain offer search.
3. **Staleness threshold**: 5 minutes may be too aggressive for slow-block networks.

## Recommendations
- Start with polling-based sync using `If-Modified-Since`. Subscription-based sync can be Phase 2.
- Define the offer cache invalidation strategy before implementing — stale offers lead to failed trades.
- Make staleness threshold configurable per chain (5 min fast chains, 30 min slow chains).
- Consider whether cross-chain offer sync is needed at v0.8.1 or can be deferred to v0.9.0 alongside settlement.
