## Preparation Phase
- Verify that all prerequisite releases are merged and tagged.
- Set up a test environment matching the target release's dependencies.
- Run existing test suite to ensure baseline passes before coding.
- Review the CHANGELOG and any linked design documents for ambiguities.
- Coordinate with relevant agents (A/B) to clarify file ownership and avoid conflicts.

# v0.7.0 Suggestions

## Status
**CLAIMS CONFIRMED + FULLY INVESTIGATED** — Bridge code exists (887 lines across 3 files), RPC endpoints partially implemented (4 of 10), CLI broken (calls non-existent endpoints), monitoring missing. All findings verified by 3 subagent investigations on 2026-06-29.

## Confirmed Gaps (verified in /opt/aitbc)

1. **Bridge service boundary clarified**: No standalone `aitbc-bridge-service` exists. Bridge code is in:
   - `apps/blockchain-node/src/aitbc_chain/cross_chain/bridge.py` (401 lines) — core lock/confirm/refund logic
   - `apps/blockchain-node/src/aitbc_chain/rpc/bridge.py` (216 lines) — 4 RPC endpoints
   - `apps/blockchain-node/src/aitbc_chain/network/bridge_manager.py` (270 lines) — island-to-island connection management
   - `apps/bridge-monitor/` (574 lines) — **UNRELATED**: monitors Ethereum→AIT deposits, not AITBC cross-chain

2. **Missing RPC endpoints** (4 of 10 spec endpoints missing):
   - ❌ `POST /bridge/unlock` — refund/cancel pending transfer
   - ❌ `GET /bridge/balance/{chain_id}` — bridge balance per chain
   - ❌ `GET /bridge/health` — bridge health check
   - ❌ `POST /bridge/batch/lock` + `POST /bridge/batch/confirm` — batch operations
   - ⚠️ `GET /bridge/status/{transfer_id}` — exists as `/bridge/transfer/{transfer_id}`, needs alias

3. **CLI bridge commands broken**: `cli/aitbc_cli/commands/bridge.py` (78 lines) calls non-existent endpoints (`/rpc/bridge/start`, `/status`, `/stop`). Falls back to simulated data. Must be replaced with actual endpoints using `BridgeClient` from `aitbc/bridge/`.

4. **CLI node bridge commands are stubs**: `cli/aitbc_cli/commands/node/bridge.py` (52 lines) — `request`, `approve`, `reject`, `list-bridges` all return simulated data.

5. **Bridge config incomplete**: `config.py` has only `bridge_islands`, `bridge_request_monitor_interval`, `bridge_release_enabled`. Missing: timeout, retry, fee, supported_chains, batch_size, monitor_interval, stuck_transfer_timeout.

6. **No bridge constants** in `aitbc/constants.py`.

7. **No shared bridge SDK** — no `aitbc/bridge/` package. CLI and other services cannot reuse bridge types or client logic.

8. **Bridge monitoring missing**: `bridge_manager.py` has no health checks, stuck transfer detection, or metrics collection.

9. **Block headers NOT signed**: `Block` model (`base_models.py:25-76`) has `proposer` field (address string) but NO signature field. `_compute_block_hash()` in `poa.py:871-880` uses SHA-256 but does NOT sign with proposer key. This is a **v0.7.1 prerequisite** — v0.7.0 does not address it.

10. **Proposer-set tracking missing**: `_verify_proposer_signature()` in `cross_chain/bridge.py:322-368` accepts ANY valid secp256k1 signature. No proposer-set membership check. Deferred to v0.7.2.

11. **Merkle proof verification ready but unused**: `merkle_patricia_trie.py:73-121` has `verify_proof(key, value, proof)` — ready for v0.7.2 but NOT used in v0.7.0.

12. **Coordinator-api cross-chain is separate**: `apps/coordinator-api/src/app/contexts/cross_chain/` has its own bridge models (BridgeRequest, SupportedToken, ChainConfig, Validator) with NO integration to blockchain-node bridge RPC. Missing schemas (BridgeCreateRequest, BridgeConfirmRequest, etc. imported with `# type: ignore`). Deferred — v0.7.0 focuses on blockchain-node bridge only.

## Recommendations

- **v0.7.0 scope**: Bridge basics only — missing RPC endpoints, CLI fix, monitoring, shared SDK. Do NOT change proof validation logic.
- **Keep `BRIDGE_RELEASE_ENABLED=false`**: The confirm/release path stays gated until v0.7.2.
- **Create `aitbc/bridge/` package** (Agent A): BridgeClient, types, proof utilities — reusable by CLI and future coordinator-api integration.
- **Fix CLI as priority**: The broken CLI commands are the most visible gap. Use BridgeClient instead of raw HTTP.
- **v0.7.1 must add block signing**: The Block model needs a `block_signature` field. `PoAProposer._propose_block()` must sign blocks using `settings.proposer_key`. Without this, v0.7.2 cannot verify block headers.
- **v0.7.2 can then complete verification**: Replace partial `_verify_proposer_signature()` with full proposer-set + Merkle proof verification using existing `merkle_patricia_trie.verify_proof()`.
- **Coordinator-api integration deferred**: The coordinator-api cross-chain context has missing schemas and no blockchain-node integration. This should be a separate release or part of v0.8.0 (Inter-Chain Trading).
