# Bridge / Cross-Chain

## 2. Bridge / Cross-Chain

### Operational security model

The bridge code includes multi-signature verification, Merkle-proof inclusion verification, and block-header/finality validation. In the **default** production configuration these checks are **not enforced on the release path** because:

- `bridge_release_enabled` defaults to `False`
- `bridge_multisig_enabled` defaults to `False`
- `bridge_require_merkle_proof` defaults to `False`

Therefore the live bridge currently operates as a **trusted-custodian bridge**: the node operator that runs the bridge service can release funds once a `confirm` request is accepted. To move to a trust-minimized bridge, an operator must:

1. Register a bridge validator set (`POST /bridge/validators/register`).
2. Store source-chain block headers (`POST /bridge/block-headers`).
3. Enable `bridge_multisig_enabled=True` and `bridge_require_merkle_proof=True`.
4. Only then set `bridge_release_enabled=True`.

The security-audit fixes for Bugs #3 and #4 (proposer-set membership and Merkle-proof enforcement) are implemented and regression-tested, but they are only active when the corresponding flags are enabled.

### Live activation and validation — 2026-08-24

The multi-signature, Merkle-proof, and block-header verification layers were activated on the live hub and shop nodes. Configuration: `bridge_release_enabled=true`, `bridge_multisig_enabled=true`, `bridge_require_merkle_proof=true`, `bridge_multisig_threshold=2`, and a 2-validator bridge validator set registered for `ait-hub.aitbc.bubuit.net`.

Live transfers of 1 compute-second were locked on `ait-hub.aitbc.bubuit.net`, anchored in real blocks with `bridge_state_root`, and confirmed on `ait-shop-island.aitbc.bubuit.net` using signed Merkle proofs. Negative cases (missing Merkle proof, insufficient signatures, invalid confirmer signature, invalid block-header admin signature) were rejected. After validation, `bridge_release_enabled` was returned to `false` to keep the live release path fenced off.

Two implementation defects were found and fixed during the live run:

1. `BlockHeaderRequest` omitted `bridge_state_root`, so ingested headers could not be used to verify Merkle proofs.
2. Re-registering an existing bridge validator did not refresh `registered_at`, causing the validator-set freshness check to reject re-registered sets as stale.

### Finality and Consensus Alignment

The bridge derives finality from `bridge_finality_blocks` confirmations. This must be configured to match the underlying consensus guarantee:

- **Single-validator PoA** (default): consensus provides no BFT finality, so use a higher confirmation count (default `bridge_finality_blocks=6`).
- **Multi-validator PoA + PBFT**: a block with a valid PBFT commit certificate (2f+1 commits) is final. `bridge_finality_blocks` should be set so confirmation-count finality is at least as strong as the PBFT guarantee, and bridge proofs should include or verify the PBFT certificate where available.

Do not set `bridge_finality_blocks` lower than the consensus finality the bridge is expected to trust.

### Bridge Operations

| Feature | Description | Documentation | Status | Release |
|---------|-------------|---------------|--------|---------|
| Bridge Lock | Lock funds for cross-chain transfer | [docs/releases/v0.7/v0.7.0_change.log](releases/v0.7/v0.7.0_change.log) | ✅ | v0.7.0 |
| Bridge Confirm | Confirm and release cross-chain transfer | [docs/releases/v0.7/v0.7.0_change.log](releases/v0.7/v0.7.0_change.log) | ✅ | v0.7.0 |
| Bridge Unlock | Refund a pending bridge transfer | [docs/releases/v0.7/v0.7.0_change.log](releases/v0.7/v0.7.0_change.log) | ✅ | v0.7.0 |
| Get Transfer | Get transfer status by ID | [docs/releases/v0.7/v0.7.0_change.log](releases/v0.7/v0.7.0_change.log) | ✅ | v0.7.0 |
| List Pending Transfers | List pending bridge transfers | [docs/releases/v0.7/v0.7.0_change.log](releases/v0.7/v0.7.0_change.log) | ✅ | v0.7.0 |
| Bridge Balance | Get bridge balance for a chain | [docs/releases/v0.7/v0.7.0_change.log](releases/v0.7/v0.7.0_change.log) | ✅ | v0.7.0 |
| Bridge Health | Bridge health check | [docs/releases/v0.7/v0.7.0_change.log](releases/v0.7/v0.7.0_change.log) | ✅ | v0.7.0 |
| Batch Lock/Confirm | Batch lock or confirm multiple transfers | [docs/releases/v0.7/v0.7.0_change.log](releases/v0.7/v0.7.0_change.log) | ✅ | v0.7.0 |

### Bridge Security

| Feature | Description | Documentation | Status | Release |
|---------|-------------|---------------|--------|---------|
| Register Validator | Register a bridge validator | [docs/releases/v0.7/v0.7.1_change.log](releases/v0.7/v0.7.1_change.log) | ✅ | v0.7.1 |
| Get Validator Set | Get validator set for a chain | [docs/releases/v0.7/v0.7.1_change.log](releases/v0.7/v0.7.1_change.log) | ✅ | v0.7.1 |
| Multi-Sig Verification | Multi-signature verification for transfers (opt-in; `bridge_multisig_enabled` default `False`) | [docs/releases/v0.7/v0.7.1_change.log](releases/v0.7/v0.7.1_change.log) | ✅ | v0.7.1 |
| Time-Locks | Time-locked transfers with refund windows | [docs/releases/v0.7/v0.7.1_change.log](releases/v0.7/v0.7.1_change.log) | ✅ | v0.7.1 |
| Bridge Security Status | Bridge security status check | [docs/releases/v0.7/v0.7.1_change.log](releases/v0.7/v0.7.1_change.log) | ✅ | v0.7.1 |
| Bridge Threat Model | Threat modeling for bridge security | [docs/architecture/bridge-threat-model.md](../architecture/bridge-threat-model.md) | ✅ | v0.7.1 |

### Bridge Verification

| Feature | Description | Documentation | Status | Release |
|---------|-------------|---------------|--------|---------|
| Store Block Header | Store a remote chain block header | [docs/releases/v0.7/v0.7.2_change.log](releases/v0.7/v0.7.2_change.log) | ✅ | v0.7.2 |
| Get Block Header | Get a block header with finality status | [docs/releases/v0.7/v0.7.2_change.log](releases/v0.7/v0.7.2_change.log) | ✅ | v0.7.2 |
| Merkle Proof Verification | In-process Merkle proof verification (opt-in; `bridge_require_merkle_proof` default `False`) | [docs/releases/v0.7/v0.7.2_change.log](releases/v0.7/v0.7.2_change.log) | ✅ | v0.7.2 |
| Bridge Oracle Status | Bridge oracle/verification status | [docs/releases/v0.7/v0.7.2_change.log](releases/v0.7/v0.7.2_change.log) | ✅ | v0.7.2 |

### Atomic Settlement

| Feature | Description | Documentation | Status | Release |
|---------|-------------|---------------|--------|---------|
| Create Escrow | Create cross-chain escrow for atomic settlement | [docs/releases/v0.9/v0.9.0_change.log](releases/v0.9/v0.9.0_change.log) | ⚠️ | v0.9.0 |
| Lock Escrow Funds | Lock escrow funds | [docs/releases/v0.9/v0.9.0_change.log](releases/v0.9/v0.9.0_change.log) | ⚠️ | v0.9.0 |
| Verify Lock Proof | Verify lock proof | [docs/releases/v0.9/v0.9.0_change.log](releases/v0.9/v0.9.0_change.log) | ⚠️ | v0.9.0 |
| Execute Trade | Execute trade on destination chain | [docs/releases/v0.9/v0.9.0_change.log](releases/v0.9/v0.9.0_change.log) | ⚠️ | v0.9.0 |
| HTLC Contract | Hashed timelock contract integration | [docs/releases/v0.9/v0.9.0_change.log](releases/v0.9/v0.9.0_change.log) | ⚠️ | v0.9.0 |

### Cross-Chain Reputation

| Feature | Description | Documentation | Status | Release |
|---------|-------------|---------------|--------|---------|

---
