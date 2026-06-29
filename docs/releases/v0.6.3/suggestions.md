## Preparation Phase
- Verify that all prerequisite releases are merged and tagged.
- Set up a test environment matching the target release's dependencies.
- Run existing test suite to ensure baseline passes before coding.
- Review the CHANGELOG and any linked design documents for ambiguities.
- Coordinate with relevant agents (A/B) to clarify file ownership and avoid conflicts.

# v0.6.3 Suggestions

## Status
**3 of 4 CLAIMS STILL OPEN** — Gap #4 partially resolved by v0.6.2. Specific file paths and line numbers added to change.log.

## Confirmed Gaps (verified in /opt/aitbc)

1. **SubscriptionClient single-hub/single-chain** — STILL OPEN
   `apps/blockchain-node/src/aitbc_chain/subscription_client.py` lines 23-26 — accepts only one `hub_url` and one `chain_id`.
   `apps/blockchain-node/src/aitbc_chain/main.py` lines 324-334 — creates ONE SubscriptionClient with `self._supported_chains()[0]` (only first chain).

2. **Island manager background tasks disabled** — STILL OPEN
   `apps/blockchain-node/src/aitbc_chain/main.py` lines 294-310 — island manager created but `start()` never called. Line 308 logs "background tasks disabled".
   Background tasks: `_bridge_request_monitor()` (island_manager.py:215, 60s interval, removes expired bridge requests >3600s) and `_island_health_check()` (island_manager.py:233, 30s interval, marks islands with 0 peers as INACTIVE after 600s).
   Both tasks self-heal on errors (try/except with 10s retry sleep).

3. **CHAIN_SYNC_SOURCES not implemented** — STILL OPEN
   No parsing code exists anywhere. Only in documentation. Config file `apps/blockchain-node/src/aitbc_chain/config.py` has no such field (only `bridge_islands` at line 199).
   Required: Add `chain_sync_sources` config field + `field_validator` for fail-fast parsing. Also add validators for `island_registry`, `gossip_backends`, and `bridge_islands`.

4. **Gossip topic not chain-specific** — PARTIALLY RESOLVED BY v0.6.2
   `apps/blockchain-node/src/aitbc_chain/main.py` lines 149-159 — v0.6.2 already subscribes to both `transactions.{chain_id}` (v2, chain-specific) and legacy `transactions` (v1, backward compat) when `gossip_backward_compat=true`.
   **Remaining for v0.6.3**: Add migration window config (`GOSSIP_MIGRATION_DAYS=30`, `GOSSIP_LOG_V1_WARNINGS=true`), add v1 warning logging in `process_txs()`, document the 30-day dual-subscribe → drop v1 timeline.

## Recommendations (incorporated into AGENTS.md)

1. **Verify v0.5.16 is merged and tagged before starting v0.6.3.** Reject any PR that fixes v0.5.16 bugs as part of v0.6.3. — ✅ v0.5.16 complete.

2. **Write an integration test with two hubs before coding** (Pre-Coding Integration Test).
   Follower with `supported_chains=ait-hub,ait-island1`, sync both chains, verify no cross-contamination in block hashes.
   — ✅ Added to AGENTS.md as "Pre-Coding Integration Test" section + `test_multi_island_design.py` spec.

3. **Enumerate and document each island manager background task** (name, failure recovery, restart behavior) before enabling them.
   — ✅ Added documentation table to AGENTS.md (B4 section) and change.log. Both tasks documented with purpose, failure recovery, restart behavior, and config.

4. **Define a 30-day gossip topic migration window**: subscribe to both `transactions` and `transactions.{chain_id}`, log warnings for v1 peers, then drop v1 support.
   — ✅ Added to AGENTS.md as "Gossip Topic Migration Window" section. Config: `GOSSIP_TX_TOPIC_V1`, `GOSSIP_TX_TOPIC_V2_TEMPLATE`, `GOSSIP_MIGRATION_DAYS=30`, `GOSSIP_LOG_V1_WARNINGS=true`. v0.6.2 already has dual-subscribe; v0.6.3 adds warning logging + migration timeline.

5. **Add error handling for `CHAIN_SYNC_SOURCES` and `ISLAND_REGISTRY` env var parsing.** Malformed values should fail fast with clear error messages, not crash silently.
   — ✅ Added `field_validator` methods to AGENTS.md B1 section for `chain_sync_sources`, `island_registry`, `gossip_backends`, and `bridge_islands`. All fail fast at startup.

## Additional Suggestions (incorporated)

6. **File ownership for multi-hub subscription client** — `subscription_client.py` rewrite touches shared infrastructure. Split: Agent A creates `SubscriptionManager` (generic multi-hub tracking in `aitbc/network/`), Agent B modifies `subscription_client.py` (WebSocket connection, lease/heartbeat). Interface contract (`SubscriptionClientProtocol`) must be agreed before implementation.
   — ✅ Added to AGENTS.md as A4 task + "Multi-Hub Subscription Client — Interface Contract" section.

7. **CLI commands — verify CLI group structure** — Confirmed: `chain sync-status` → `cli/aitbc_cli/commands/chain.py` (top-level `chain` group), `node island health` → `cli/aitbc_cli/commands/node/__init__.py` (island group at line 46-49), `node island list` → `cli/aitbc_cli/commands/node/island.py` (stub at line 161-174 with hardcoded UUID).
   — ✅ Updated AGENTS.md Status Baseline table and B6 instructions with correct paths.

8. **Quick wins for change.log**:
   - ✅ Added ISLAND_REGISTRY parsing validator (B1 config section)
   - ✅ Added GOSSIP_BACKENDS parsing validator (B1 config section)
   - ✅ Documented bridge_islands CSV format: UUID only, no spaces (B1 validator section)
   - ✅ Added success criterion: "Zero cross-chain block contamination in 24h multi-hub soak test"
