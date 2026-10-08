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

The multi-signature, Merkle-proof, and block-header verification layers were activated on the live hub and shop nodes. Configuration: `bridge_release_enabled=true`, `bridge_multisig_enabled=true`, `bridge_require_merkle_proof=true`, `bridge_multisig_threshold=2`, and a 2-validator bridge validator set registered for `ait-localnet`.

Live transfers of 1 compute-second were locked on `ait-localnet`, anchored in real blocks with `bridge_state_root`, and confirmed on `ait-shop-island.aitbc.bubuit.net` using signed Merkle proofs. Negative cases (missing Merkle proof, insufficient signatures, invalid confirmer signature, invalid block-header admin signature) were rejected. After validation, `bridge_release_enabled` was returned to `false` to keep the live release path fenced off.

Two implementation defects were found and fixed during the live run:

1. `BlockHeaderRequest` omitted `bridge_state_root`, so ingested headers could not be used to verify Merkle proofs.
2. Re-registering an existing bridge validator did not refresh `registered_at`, causing the validator-set freshness check to reject re-registered sets as stale.

### Finality and Consensus Alignment

The bridge derives finality from `bridge_finality_blocks` confirmations. This must be configured to match the underlying consensus guarantee:

- **Single-validator PoA** (default): consensus provides no BFT finality, so use a higher confirmation count (default `bridge_finality_blocks=6`).
- **Multi-validator PoA + PBFT**: a block with a valid PBFT commit certificate (2f+1 commits) is final. `bridge_finality_blocks` should be set so confirmation-count finality is at least as strong as the PBFT guarantee, and bridge proofs should include or verify the PBFT certificate where available.

Do not set `bridge_finality_blocks` lower than the consensus finality the bridge is expected to trust.

### Lock intake controls (operator runbook)

Two `aitbc-blockchain-rpc` env keys govern whether the node accepts *new* bridge locks. Both are read once into the cached `ChainSettings` at process start — a change only takes effect after an `aitbc-blockchain-rpc` restart.

| env key | default | meaning |
|---|---|---|
| `BRIDGE_LOCKS_PAUSED` | `false` | `true` fences off new locks on `POST /bridge/lock`, `POST /bridge/batch/lock`, `/swap`, `/cross-chain/bridge` and internal `initiate_transfer`. Refund, status-read and confirm paths stay available, so in-flight transfers can still settle. |
| `BRIDGE_MAX_LOCK_AMOUNT` | `0` (unlimited) | Per-lock maximum in compute units. `1 AIT = 36,000,000 units`; `36,000,000,000` = a 1,000 AIT per-lock cap — the value the live fleet runs. |

Normal state is **locks open** (`BRIDGE_LOCKS_PAUSED=false`) with a per-lock cap. The cap is **fail-closed in production**: when `BRIDGE_LOCKS_PAUSED` is false and `BRIDGE_MAX_LOCK_AMOUNT` is unset or `0`, `initiate_transfer` refuses locks with a logged reason instead of running uncapped. Development and test environments keep `0 = unlimited`. To pause intake again — e.g. while rotating the bridge validator set — edit `/etc/aitbc/blockchain.env` on the host:

```bash
sudo sed -i 's/^BRIDGE_LOCKS_PAUSED=.*/BRIDGE_LOCKS_PAUSED=true/' /etc/aitbc/blockchain.env
sudo systemctl restart aitbc-blockchain-rpc
```

Verify the running value in `/proc/<rpc pid>/environ` — the pause flag is not exposed on any read endpoint; `/rpc/bridge/health` does report `bridge_max_lock_amount`. A paused node answers lock requests with a "bridge locks paused" error. Reopen by setting the value back to `false` with another rpc restart. A host with an empty `bridge_validators` set can still accept locks it cannot yet release — releases fail closed below the multisig threshold — so the pause is the fence, not the validator set.

### Safety flag defaults vs the production fleet

Most bridge safety flags default off in code so isolated dev chains stay
simple; the fleet sets them explicitly in `/etc/aitbc/blockchain.env`. The
documented production intent for each flag:

| env key | code default | production fleet | notes |
|---|---|---|---|
| `BRIDGE_LOCKS_PAUSED` | `false` | `false` | intake fence; matches code default. |
| `BRIDGE_MAX_LOCK_AMOUNT` | `0` (unlimited) | `36000000000` | **fail-closed** in production when unset; fresh-node configs carry the fleet value. |
| `BRIDGE_RELEASE_ENABLED` | `false` | `true` | release fence; stays `false` until proofs/multisig are configured. |
| `BRIDGE_REQUIRE_MERKLE_PROOF` | `false` | `true` | rejects proof-less releases; set `true` wherever releases move real value. |
| `BRIDGE_MULTISIG_ENABLED` | `false` | `true` | M-of-N validator signatures for confirm. |
| `BRIDGE_MULTISIG_THRESHOLD` | `3` | `2` | M: signatures required per confirm. |
| `BRIDGE_MULTISIG_VALIDATORS` | `5` | `2` | N: registered validator count. |
| `BRIDGE_SUPPORTED_CHAINS` | `""` | fleet chain IDs | deployment-specific; set per island. |
| `BRIDGE_ADMIN_ADDRESSES` | `""` | per-node | deny-by-default when empty; already fail-closed. |

`setup.sh` writes `BRIDGE_MAX_LOCK_AMOUNT=36000000000` (plus the pause flag)
into a fresh minimal `blockchain.env`, and `examples/blockchain.env*` carry
the same values.

### Bridge Operations

| Feature | Description | Documentation | Status | Release |
|---------|-------------|---------------|--------|---------|
| Bridge Lock (`BRIDGE_LOCK`) | Lock funds for cross-chain transfer | [docs/releases/v0.7/v0.7.0_change.log](../releases/v0.7/v0.7.0_change.log) | ✅ | v0.7.0 |
| Bridge Confirm (`BRIDGE_CONFIRM`) | Confirm and release cross-chain transfer | [docs/releases/v0.7/v0.7.0_change.log](../releases/v0.7/v0.7.0_change.log) | ✅ | v0.7.0 |
| Bridge Unlock — CLI `unlock`, on-chain `BRIDGE_REFUND` (`refund_transfer`) | Refund a pending bridge transfer | [docs/releases/v0.7/v0.7.0_change.log](../releases/v0.7/v0.7.0_change.log) | ✅ | v0.7.0 |
| Get Transfer (`get_transfer`) | Get transfer status by ID | [docs/releases/v0.7/v0.7.0_change.log](../releases/v0.7/v0.7.0_change.log) | ✅ | v0.7.0 |
| List Pending Transfers (`list_pending_transfers`) | List pending bridge transfers | [docs/releases/v0.7/v0.7.0_change.log](../releases/v0.7/v0.7.0_change.log) | ✅ | v0.7.0 |
| Bridge Balance (`get_bridge_balance`) | Get bridge balance for a chain | [docs/releases/v0.7/v0.7.0_change.log](../releases/v0.7/v0.7.0_change.log) | ✅ | v0.7.0 |
| Bridge Health (`bridge_health`) | Bridge health check | [docs/releases/v0.7/v0.7.0_change.log](../releases/v0.7/v0.7.0_change.log) | ✅ | v0.7.0 |
| Batch Lock/Confirm (`batch_lock`, `batch_confirm`) | Batch lock or confirm multiple transfers | [docs/releases/v0.7/v0.7.0_change.log](../releases/v0.7/v0.7.0_change.log) | ✅ | v0.7.0 |

### Bridge Security

| Feature | Description | Documentation | Status | Release |
|---------|-------------|---------------|--------|---------|
| Register Validator (`register_validator`) | Register a bridge validator | [docs/releases/v0.7/v0.7.1_change.log](../releases/v0.7/v0.7.1_change.log) | ✅ | v0.7.1 |
| Get Validator Set (`get_validator_set`) | Get validator set for a chain | [docs/releases/v0.7/v0.7.1_change.log](../releases/v0.7/v0.7.1_change.log) | ✅ | v0.7.1 |
| Multi-Sig Verification (`bridge_multisig_enabled`) | Multi-signature verification for transfers (opt-in; `bridge_multisig_enabled` default `False`) | [docs/releases/v0.7/v0.7.1_change.log](../releases/v0.7/v0.7.1_change.log) | ✅ | v0.7.1 |
| Time-Locks (`timelock`) | Time-locked transfers with refund windows | [docs/releases/v0.7/v0.7.1_change.log](../releases/v0.7/v0.7.1_change.log) | ✅ | v0.7.1 |
| Bridge Security Status (`bridge_security_status`) | Bridge security status check | [docs/releases/v0.7/v0.7.1_change.log](../releases/v0.7/v0.7.1_change.log) | ✅ | v0.7.1 |
| Bridge Threat Model | Threat modeling for bridge security | [docs/architecture/bridge-threat-model.md](../architecture/bridge-threat-model.md) | 📄 doc | — |

### Bridge Verification

| Feature | Description | Documentation | Status | Release |
|---------|-------------|---------------|--------|---------|
| Store Block Header (`store_block_header`) | Store a remote chain block header | [docs/releases/v0.7/v0.7.2_change.log](../releases/v0.7/v0.7.2_change.log) | ✅ | v0.7.2 |
| Get Block Header (`get_block_header`) | Get a block header with finality status | [docs/releases/v0.7/v0.7.2_change.log](../releases/v0.7/v0.7.2_change.log) | ✅ | v0.7.2 |
| Merkle Proof Verification (`verify_merkle_proof`, `bridge_require_merkle_proof`) | In-process Merkle proof verification (opt-in; `bridge_require_merkle_proof` default `False`) | [docs/releases/v0.7/v0.7.2_change.log](../releases/v0.7/v0.7.2_change.log) | ✅ | v0.7.2 |
| Bridge Oracle Status (`oracle_status`) | Bridge oracle/verification status | [docs/releases/v0.7/v0.7.2_change.log](../releases/v0.7/v0.7.2_change.log) | ✅ | v0.7.2 |

### Atomic Settlement

| Feature | Description | Documentation | Status | Release |
|---------|-------------|---------------|--------|---------|
| Create Escrow | Create cross-chain escrow for atomic settlement | [docs/releases/v0.9/v0.9.0_change.log](../releases/v0.9/v0.9.0_change.log) | ⚠️ | v0.9.0 |
| Lock Escrow Funds | Lock escrow funds | [docs/releases/v0.9/v0.9.0_change.log](../releases/v0.9/v0.9.0_change.log) | ⚠️ | v0.9.0 |
| Verify Lock Proof | Verify lock proof | [docs/releases/v0.9/v0.9.0_change.log](../releases/v0.9/v0.9.0_change.log) | ⚠️ | v0.9.0 |
| Execute Trade | Execute trade on destination chain | [docs/releases/v0.9/v0.9.0_change.log](../releases/v0.9/v0.9.0_change.log) | ⚠️ | v0.9.0 |
| HTLC Contract | Hashed timelock contract integration | [docs/releases/v0.9/v0.9.0_change.log](../releases/v0.9/v0.9.0_change.log) | ⚠️ | v0.9.0 |

### Cross-Chain Reputation

| Feature | Description | Documentation | Status | Release |
|---------|-------------|---------------|--------|---------|

---
