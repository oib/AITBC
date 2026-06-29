## Preparation Phase
- Verify that all prerequisite releases are merged and tagged.
- Set up a test environment matching the target release's dependencies.
- Run existing test suite to ensure baseline passes before coding.
- Review the CHANGELOG and any linked design documents for ambiguities.
- Coordinate with relevant agents (A/B) to clarify file ownership and avoid conflicts.

# v0.6.4 Suggestions

## Status
**ALL 4 CLAIMS CONFIRMED** — Dead code verified, join_island caller inventory complete (8 call sites). All suggestions incorporated into change.log.

## Confirmed Gaps (verified in /opt/aitbc)

1. **MultiChainManager**: `apps/blockchain-node/src/aitbc_chain/network/multi_chain_manager.py` line 56 — defined but never imported in `main.py`. Confirmed dead code (0 imports in production code).
2. **MultiValidatorPoA**: `apps/blockchain-node/src/aitbc_chain/consensus/multi_validator_poa.py` line 33 — used only in tests/scripts, NOT in production code.
3. **PBFT**: `apps/blockchain-node/src/aitbc_chain/consensus/pbft.py` line 48 — used only in test scripts, NOT in production code.
4. **join_island() callers**: 8 call sites identified across 5 repos. All use old single-`chain_id` signature.
   - `apps/blockchain-node/src/aitbc_chain/rpc/islands.py:75`
   - `apps/blockchain-node/src/aitbc_chain/main.py:329`
   - `apps/blockchain-node/src/aitbc_chain/rpc/router.py:719`
   - `apps/edge/src/aitbc_edge/routers/islands.py:45`
   - `apps/edge/src/aitbc_edge/services/island_service.py:32`
   - `cli/aitbc_cli/commands/node/island.py:39`
   - `packages/py/aitbc-agent-sdk/src/aitbc_agent/edge_api_client.py:197`
   - `apps/coordinator-api/src/app/contexts/infrastructure/routers/islands_proxy.py:50`

## Recommendations (incorporated into change.log)

1. **Atomic join_island refactor** — Update all 8 call sites in single commit. Any mismatch crashes island join. Added backward compat adapter (`chain_id: str | list[str]`) to ease transition. Grep verification command documented.
   — ✅ Added to change.log "join_island() Caller Inventory" section.

2. **Startup sequencing with retry/backoff** — Sort chains by dependency (main chain first), start sequentially, fail fast if main chain fails. Secondary chains retry with exponential backoff. Config: `MULTI_CHAIN_START_MAX_RETRIES`, `MULTI_CHAIN_START_BASE_DELAY`, `MULTI_CHAIN_START_MAX_DELAY`, `MULTI_CHAIN_START_BACKOFF_MULTIPLIER`.
   — ✅ Added to change.log "Startup Sequencing with Retry/Backoff" section with full implementation spec.

3. **MultiValidatorPoA/PBFT threshold guard** — Leave in clearly commented THRESHOLD state. Added both comment guard (top of file) and runtime guard (`__init__` raises RuntimeError unless `MULTI_VALIDATOR_CONSENSUS_ENABLED=true`).
   — ✅ Added to change.log "Dead Code — MultiValidatorPoA and PBFT" section.

4. **No fallback behavior if dynamic chain start fails** — Added retry logic with exponential backoff (see Rec #2 above).

## Additional Suggestions (incorporated into change.log)

5. **Per-chain port allocation spec** — `CHAIN_PORT_OFFSETS` config with base port + offset per chain. Conflict detection on startup. Default: all chains share base ports (backward compat).
   — ✅ Added to change.log "Per-Chain Port Allocation" section.

6. **CLI command routing** — `aitbc chain start/stop` delegates to `node/chain.py` implementations. Single source of truth, no duplicate logic. `--island` flag added to `chain list`.
   — ✅ Added to change.log "CLI Command Routing" section with verified file paths.

7. **CHAIN_CONFIG_ parsing validator** — `field_validator` in config.py parses `CHAIN_CONFIG_*` env vars into typed `ChainConfig` objects. Fail fast on malformed entries.
   — ✅ Added to change.log config section with full validator spec.

8. **Island leave cleanup test** — Explicit test: leave island with 3 chains → verify all 3 databases closed, proposers stopped, gossip unsubscribed.
   — ✅ Added to change.log "Island Registry Testing" section.

9. **Backward compat test matrix** — 5-row matrix covering single-chain config, make_genesis --chain-id, join_island single string, IslandMembership.chain_id access, block_production_chains default.
   — ✅ Added to change.log "Backward Compatibility Testing" section.

## Quick Wins (incorporated into change.log)

- ✅ `MULTI_CHAIN_HEALTH_INTERVAL=60` config (Performance Targets + Breaking Changes)
- ✅ `CHAIN_SHUTDOWN_TIMEOUT=10` config (Performance Targets + Breaking Changes)
- ✅ `IslandMembership.chain_ids` serialization format documented (JSON array in RPC, Breaking Changes)
- ✅ Success criterion: "Zero port conflicts across 5+ chains on single island"
