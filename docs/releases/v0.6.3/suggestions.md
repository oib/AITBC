## Preparation Phase
- Verify that all prerequisite releases are merged and tagged.
- Set up a test environment matching the target release's dependencies.
- Run existing test suite to ensure baseline passes before coding.
- Review the CHANGELOG and any linked design documents for ambiguities.
- Coordinate with relevant agents (A/B) to clarify file ownership and avoid conflicts.

# v0.6.3 Suggestions

## Status
**ALL 4 CLAIMS CONFIRMED** — Verified in codebase. Specific file paths and line numbers added to change.log.

## Confirmed Gaps (verified in /opt/aitbc)
1. **SubscriptionClient single-hub/single-chain**: `apps/blockchain-node/src/aitbc_chain/subscription_client.py` lines 23-26 — accepts only one `hub_url` and one `chain_id`.
2. **Island manager background tasks disabled**: `apps/blockchain-node/src/aitbc_chain/main.py` lines 283-288 — island manager created but `start()` never called. Line 286 logs "background tasks disabled".
3. **CHAIN_SYNC_SOURCES not implemented**: No parsing code exists anywhere. Only in documentation. Config file `config.py` has no such field.
4. **Gossip topic not chain-specific**: `main.py` line 146 — subscribes to `transactions` (not chain-specific). Line 174 — blocks use `blocks.{chain_id}` (chain-specific). Inconsistent.

## Recommendations
- Verify v0.5.16 is merged and tagged before starting v0.6.3. Reject any PR that fixes v0.5.16 bugs as part of v0.6.3.
- Write an integration test with two hubs before coding: follower with `supported_chains=ait-hub,ait-island1`, sync both chains, verify no cross-contamination in block hashes.
- Enumerate and document each island manager background task (name, failure recovery, restart behavior) before enabling them.
- Define a 30-day gossip topic migration window: subscribe to both `transactions` and `transactions.{chain_id}`, log warnings for v1 peers, then drop v1 support.
- Add error handling for `CHAIN_SYNC_SOURCES` and `ISLAND_REGISTRY` env var parsing. Malformed values should fail fast with clear error messages, not crash silently.
