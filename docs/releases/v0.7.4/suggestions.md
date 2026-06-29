## Preparation Phase
- Verify that all prerequisite releases are merged and tagged.
- Set up a test environment matching the target release's dependencies.
- Run existing test suite to ensure baseline passes before coding.
- Review the CHANGELOG and any linked design documents for ambiguities.
- Coordinate with relevant agents (A/B) to clarify file ownership and avoid conflicts.

# v0.7.4 Suggestions

## Status
**PLANNED 2026-06-29** — v0.7.4 created to track 7 deferred items from v0.7.0-v0.7.3 that were tagged "deferred to v0.8.x" but never assigned to a specific release. NOT on the critical path for v0.8.x or v0.9.0.

## Origin

During v0.8.0-v0.8.2 release planning, it was discovered that 7 items were deferred from v0.7.x to "v0.8.x" but none of the v0.8.x releases pick them up. These items are bridge/governance/consensus work, not trading work — they belong in the v0.7.x track.

## Deferred Items — Verified State (2026-06-29)

### 1. External Oracle Integration (from v0.7.2) — STUB ONLY
- `ExternalOracleClient` exists as stub (`aitbc/bridge/oracle.py:228-262`)
- All methods (`verify_proof`, `check_finality`, `mode`) raise `NotImplementedError`
- No `BRIDGE_ORACLE_ENDPOINTS` config exists (only in v0.7.2 change.log:111 as future comment)
- No `docs/architecture/oracle-roadmap.md` exists (referenced in v0.7.2 change.log:199)
- Exported in `aitbc/bridge/__init__.py:24,39,79`
- 13 references across v0.7.2 docs all say "deferred to v0.8.x or v0.9.x"

### 2. Oracle Fallback Policy (from v0.7.2) — NOT FOUND
- 0 matches for "oracle_fallback", "fallback_policy", "oracle_mode" in `aitbc/bridge/`
- `VerificationMode` enum has "in_process" and "oracle" modes (`aitbc/bridge/types.py`)
- No fallback logic between modes exists in `aitbc/bridge/proof.py`

### 3. Cross-Chain Governance (from v0.7.3) — NOT FOUND
- `aitbc/governance/onchain.py` — single-chain only (build_proposal_tx, build_vote_tx, build_execute_tx)
- `aitbc/governance/client.py` — single-chain only (create_proposal, cast_vote)
- 0 matches for "cross_chain_governance", "proposal_propagation", "vote_aggregation"
- `apps/governance/` — 991 lines, single-chain only

### 4. Parameter Automation (from v0.7.3) — PARTIALLY EXISTS
- `ParameterChangeSchema` exists (`aitbc/governance/types.py:119-136`) — dataclass only, no execute method
- Comment: "Parameter automation (actually applying the change to the target service) is deferred to v0.8.x"
- `build_parameter_change_params()` exists (`aitbc/governance/onchain.py:85-98`) — builds dict only
- Pool-hub has manual config API (`apps/pool-hub/src/poolhub/app/routers/services.py:54-127`) — NOT governance-driven
- Marketplace has no parameter change API

### 5. Emergency Proposals (from v0.7.3) — PARTIALLY EXISTS
- `EMERGENCY = "emergency"` in `ProposalType` enum (`aitbc/governance/types.py:41`)
- `emergency_quorum_threshold: 0.8` configured (`apps/governance/src/governance_service/main.py:221`)
- No special handling — emergency proposals treated same as regular (no accelerated timelock, no fast-track)
- 0 matches for "emergency_proposal" in `apps/governance/`

### 6. Coordinator-API Bridge Integration (from v0.7.0) — PARTIALLY EXISTS
- Coordinator-api has its own `CrossChainBridgeService` (`apps/coordinator-api/src/app/contexts/cross_chain/`)
- 0 matches for "BridgeClient" in coordinator-api — does NOT use `aitbc.bridge.BridgeClient`
- Two parallel bridge implementations exist (blockchain-node + coordinator-api)
- No integration between them

### 7. MultiValidatorPoA Activation (from v0.7.1) — STUB ONLY (dead code)
- Fully implemented (`apps/blockchain-node/src/aitbc_chain/consensus/multi_validator_poa.py`, 294 lines)
- Gated behind `MULTI_VALIDATOR_CONSENSUS_ENABLED=true` (line 45-49, raises `RuntimeError`)
- 0 production imports outside consensus/ and tests/
- PBFT also dead code, depends on MultiValidatorPoA
- v0.7.1 AGENTS.md: "Do NOT activate without security review"

## Recommendations

- **MultiValidatorPoA requires security review first**: This is consensus-critical. Bugs can chain-split. Do NOT activate without a thorough security audit. Consider activating on testnet first.
- **External oracle is optional**: In-process verification (v0.7.2) works. External oracle adds complexity + external dependency. Only implement if there's a concrete use case that in-process verification can't handle.
- **Cross-chain governance depends on v0.7.2 bridge**: Proposal propagation uses the bridge. Ensure v0.7.2 bridge verification is operational and tested before cross-chain governance.
- **Parameter automation is low-risk**: Adding governance-triggered parameter APIs to pool-hub/marketplace is additive. No consensus or bridge dependency.
- **Emergency proposals are low-risk**: Adding accelerated timelock + higher quorum enforcement is governance logic only. No consensus or bridge dependency.
- **Coordinator-API bridge integration is medium-risk**: Replacing CrossChainBridgeService with BridgeClient changes coordinator-api behavior. Needs careful migration.
- **NOT on critical path**: v0.8.x (trading) and v0.9.0 (atomic settlement) do not depend on v0.7.4. Can ship in parallel.
- **Consider splitting v0.7.4**: The 7 items have different risk levels. Low-risk items (parameter automation, emergency proposals) could ship first, while high-risk items (MultiValidatorPoA, external oracle) need more time.
