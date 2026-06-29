# AITBC Bridge Threat Model (v0.7.1)

**Status**: Addendum to [docs/security/threat-model.md](../security/threat-model.md) (general platform threats).
**Scope**: Cross-chain bridge attack surfaces introduced in v0.7.0–v0.7.1 and residual risks before v0.7.2.

## 1. Bridge Components

| Component | Location | Attack Surface |
|-----------|----------|----------------|
| Bridge RPC endpoints | `rpc/bridge.py` | Unauthenticated HTTP (signature-verified per-request) |
| Proof verification path | `cross_chain/bridge.py:_validate_proof` | Accepts proofs from any caller; validates fields + signatures |
| Validator set registry | `BridgeValidator` table + `ValidatorSetRegistry` | Validator registration, epoch rotation |
| Block header signatures | `Block.signature` field + PoA signing | Block proposal, validation |
| Multi-sig aggregation | `aitbc/bridge/multisig.py` | Threshold signature collection + verification |
| Release fence | `BRIDGE_RELEASE_ENABLED` config | Gates confirm/release path |

## 2. Attack Vectors

### 2.1 Forged Proof (No Actual Lock)

**Vector**: Attacker fabricates a lock proof with correct fields and a valid signature, without an actual lock transaction on the source chain.

**Mitigation (v0.7.1)**: Multi-sig threshold — M-of-N validators must sign the proof. A single attacker cannot forge a proof without compromising M validators. Block anchoring (block_height + block_hash) ties the proof to a specific block.

**Residual risk (pre-v0.7.2)**: A colluding validator majority (≥M validators) can forge proofs with fabricated block anchors. Merkle proof verification (v0.7.2) will tie proofs to verifiable on-chain state, eliminating this risk.

### 2.2 Signature Replay (Cross-Chain / Cross-Transfer)

**Vector**: Attacker reuses a valid proof on a different chain or for a different transfer.

**Mitigation**: `chain_id` is embedded in the proof and verified against the source chain. `_processed_proofs` set prevents replay of the same proof hash.

**Residual risk (pre-v0.7.2)**: `_processed_proofs` is in-memory — a node restart loses replay protection. Persistent audit trail deferred to v0.7.2.

### 2.3 Validator Key Compromise

**Vector**: Attacker steals a validator's private key.

**Mitigation**: M-of-N threshold — single key compromise is insufficient to forge a proof (need M keys). Validator set rotation (epoch advancement) can remove compromised validators.

**Residual risk**: If ≥M validators are compromised simultaneously, the bridge is compromised. This is inherent to any M-of-N threshold system. Mitigation: keep M high enough (default 3-of-5) and rotate keys regularly.

### 2.4 Validator Set Rotation Attack

**Vector**: Attacker exploits the transition between validator set epochs — e.g., submitting a proof signed by the old set after the new set is active.

**Mitigation**: Epoch tracking in `ValidatorSetRegistry`. Old epoch sets are retained for a grace period (default 7200s) to allow in-flight transfers to complete, but new transfers must use the current epoch's set.

**Residual risk**: During the grace period, both old and new sets are valid. An attacker who compromised an old-set validator can still submit proofs during this window. Mitigation: keep grace period short.

### 2.5 Below-Threshold Attack

**Vector**: Attacker submits a proof with fewer than M signatures.

**Mitigation**: `check_threshold()` in `aitbc/bridge/multisig.py` verifies the signer count meets the threshold. Deduplication prevents counting the same signer twice.

**Residual risk**: None — this is fully mitigated by the threshold check.

### 2.6 Block Header Forgery

**Vector**: Attacker fabricates a block header (height + hash) to anchor a forged proof.

**Mitigation (v0.7.1)**: Block header signatures — PoA signs each block with the proposer's private key. The signature is verified during block validation when `bridge_block_signature_required=True`.

**Residual risk (pre-v0.7.2)**: Block header signatures prove the proposer signed the block, but do NOT prove the block is in the canonical chain. A malicious proposer can sign a fabricated block. Merkle proof verification (v0.7.2) will tie proofs to verified on-chain state.

### 2.7 Bridge RPC DoS

**Vector**: Attacker floods bridge RPC endpoints with requests.

**Mitigation**: Rate limiting (`@rate_limit` decorator on all bridge endpoints). Signature verification on lock/unlock/confirm prevents unauthenticated spam.

**Residual risk**: Rate limits can be bypassed with sufficient IP diversity. This is a general platform concern, not bridge-specific.

### 2.8 Validator Registration Attack

**Vector**: Attacker registers themselves as a validator to gain signing power.

**Mitigation**: `POST /bridge/validators/register` requires a signature proving ownership of the address being registered. In production, validator registration should be restricted to authorized operators (governance-controlled in v0.7.3).

**Residual risk (pre-v0.7.3)**: No governance gate on validator registration. Any address with a valid signature can register. Mitigation: validator registration is an operational action performed by chain operators, not exposed to end users. The RPC endpoint should be firewalled to internal networks in production.

## 3. Security Layers (Defense in Depth)

```
Layer 1: Signature verification (v0.7.0) — every lock/unlock/confirm requires a valid secp256k1 signature
Layer 2: Block anchoring (v0.7.0) — proofs reference a specific block height + hash
Layer 3: Multi-sig threshold (v0.7.1) — M-of-N validators must sign proofs
Layer 4: Block header signatures (v0.7.1) — proposers sign block headers
Layer 5: Validator set registry (v0.7.1) — only registered validators can sign
Layer 6: Release fence (v0.5.16) — BRIDGE_RELEASE_ENABLED=false gates the release path
Layer 7: Merkle proof verification (v0.7.2 — FUTURE) — proofs tied to verified on-chain state
Layer 8: Time-locks (v0.7.2 — FUTURE) — large transfers have a challenge period
Layer 9: Audit trail (v0.7.2 — FUTURE) — persistent proof tracking prevents replay after restart
```

## 4. Residual Risk Summary (After v0.7.1, Before v0.7.2)

| Risk | Severity | Mitigation Timeline |
|------|----------|---------------------|
| Colluding validator majority can forge proofs | High | v0.7.2 (Merkle proof verification) |
| In-memory `_processed_proofs` lost on restart | Medium | v0.7.2 (persistent audit trail) |
| No time-locks on large transfers | Medium | v0.7.2 (value-tiered time-locks) |
| No governance gate on validator registration | Medium | v0.7.3 (governance release) |
| Block header signatures don't prove canonical chain | Medium | v0.7.2 (Merkle proof + finality) |

**Key invariant**: The `BRIDGE_RELEASE_ENABLED=false` fence prevents ALL fund release until v0.7.2 ships. Even if multi-sig has bugs, no funds can be minted/released without explicitly enabling the fence on a production network.

## 5. Configuration Recommendations

| Setting | Dev/Test | Production |
|---------|----------|------------|
| `bridge_release_enabled` | `true` (for testing) | `false` (until v0.7.2) |
| `bridge_multisig_enabled` | `true` | `true` |
| `bridge_multisig_threshold` | `2` (fast testing) | `3` (minimum) or higher |
| `bridge_multisig_validators` | `3` | `5` (minimum) or higher |
| `bridge_block_signature_required` | `true` | `true` |
| `bridge_validator_set_grace_period` | `3600` | `7200` |

## 6. Testing Coverage

- **Unit tests** (`tests/unit/test_bridge_security.py`): Validator set types, threshold verification, registry operations
- **Integration tests** (`apps/blockchain-node/tests/test_v071_bridge_security.py`): Block header signing, validator registration RPC, multi-sig confirm flow, CLI commands
- **Existing bridge suite** (`apps/blockchain-node/tests/test_bridge_suite.py`): Proof verification, lock/confirm endpoints, lifecycle, cross-chain contamination

## 7. References

- [v0.7.1 AGENTS.md](../releases/v0.7.1/AGENTS.md) — task assignment and implementation details
- [v0.7.0 change.log](../releases/v0.7.0/change.log) — bridge basics (lock/unlock/balance/health/batch)
- [v0.5.16 change.log](../releases/v0.5.16/change.log) — bridge proof hardening + release fence
- [General threat model](../security/threat-model.md) — platform-wide threats
