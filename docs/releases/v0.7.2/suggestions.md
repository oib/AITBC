## Preparation Phase
- Verify that all prerequisite releases are merged and tagged.
- Set up a test environment matching the target release's dependencies.
- Run existing test suite to ensure baseline passes before coding.
- Review the CHANGELOG and any linked design documents for ambiguities.
- Coordinate with relevant agents (A/B) to clarify file ownership and avoid conflicts.

# v0.7.2 Suggestions

## Status
**RESCOPED** — The original plan assumed external oracle infrastructure (`oracle1.aitbc.bubuit.net`, `oracle2.aitbc.bubuit.net`) that does not exist. v0.7.2 has been rescoped to use in-process cryptographic verification with existing Merkle Patricia Trie infrastructure. See change.log for the updated plan.

**VERIFIED 2026-06-29** — All claims in this file confirmed against codebase. AGENTS.md created with grounded A/B task split.

## Resolved Issues
- ~~Oracle endpoints are listed in env examples but not confirmed as existing infrastructure.~~ → Confirmed: oracle endpoints do NOT exist. Rescoped to in-process verification.
- ~~Workflow requires integrating new external libraries (merkle verification, light client) before code is ready.~~ → No external libraries needed. Uses existing `merkle_patricia_trie.verify_proof` (verified at `state/merkle_patricia_trie.py:73`).

## Gaps
- ~~Bridge can't move forward safely without v0.7.1 auditor sign-off; this release may end up being theory-only if v0.7.1 slips.~~ → **CONFIRMED**: v0.7.1 Agent A is ✅ committed (`1fcf1e829`), but v0.7.1 Agent B is 🔴 NOT STARTED (v0.7.0 Agent B is still uncommitted). v0.7.2 implementation is HARD BLOCKED until v0.7.1 Agent B completes.
- ~~Validator set epoch tracking needs a persistence strategy (DB schema for validator set history).~~ → **CONFIRMED**: No `BridgeValidator` table exists. v0.7.1 Agent B creates it. v0.7.2 B6 extends with epoch tracking + grace period.
- ~~Block header finality tracking requires per-chain block header storage — current code may not store headers from other chains.~~ → **CONFIRMED**: No `BridgeBlockHeader` or equivalent table exists. `Block` table only stores local chain blocks. v0.7.2 B2 creates the remote block header table.
- ~~Threat model still missing — carried from v0.7.1.~~ → **CONFIRMED**: `docs/architecture/bridge-threat-model.md` does not exist. v0.7.1 B1 creates it. If v0.7.1 Agent B hasn't completed, this is missing.

## Additional Verified Findings (2026-06-29)
- `_validate_proof` at `cross_chain/bridge.py:399-475` does field equality + proposer sig format + block anchor + chain_id check, but NO Merkle proof verification.
- `_verify_proposer_signature` at `cross_chain/bridge.py:477-523` accepts ANY valid secp256k1 signer (comment lines 514-517 explicitly says "we accept any valid signature").
- `Block` model at `base_models.py:25-76` has `proposer: str` (line 38) and `state_root: str | None` (line 41), but NO `signature` field. v0.7.1 B3 adds it.
- `StateManager.compute_state_root()` at `state/merkle_patricia_trie.py:402` is complete and tested.
- `state_root_utils.py` has `compute_state_root_full()` and `compute_state_root_incremental()`.
- Bridge config in `config.py` has v0.7.0 fields (bridge_timeout, bridge_retry_limit, etc.) but NO v0.7.2 verification fields (bridge_verification_mode, bridge_min_confirmations, bridge_finality_blocks, bridge_large_transfer_threshold).
- `BRIDGE_RELEASE_ENABLED=false` at `config.py:290` — the fence is active and must remain until v0.7.2 B7 unfences it.

## Recommendations
- ~~Do not start coding before v0.7.1 is merged and tested.~~ → **STILL VALID**: v0.7.1 Agent B must complete first. AGENTS.md plan is ready for when it does.
- ~~Define the finality threshold per chain (default 6 blocks, configurable).~~ → Added to AGENTS.md B1: `bridge_finality_blocks: int = 6`, `bridge_min_confirmations: int = 3`.
- ~~Implement validator set cache with DB-backed persistence to survive node restarts.~~ → Added to AGENTS.md B6: DB-backed epoch tracking + grace period.
- ~~Add a `threat_model.md` to the bridge folder before coding starts (carried forward from v0.7.1).~~ → v0.7.1 B1 owns this. v0.7.2 extends it.
- Future oracle integration (v0.8.x+): pre-decide oracle fallback policy — when do we fall back to in-process verification (1 of N down? X seconds timeout?). → Added `ExternalOracleClient` stub to AGENTS.md A2. Fallback policy deferred to v0.8.x.
