# AITBC Bridge Threat Model (v0.9.0)

**Status**: Living document — updated through v0.9.0 (B4 HTLC contract integration).
**Scope**: Cross-chain bridge attack surfaces across v0.7.0–v0.9.0, including proof verification, validator set management, Merkle proofs, finality, HTLC settlement, and fund movement.
**Related**: [Bridge Security Audit](../releases/AUDIT.md) | [General Threat Model](../security/threat-model.md) | [Release Status](../releases/STATUS.md)

---

## 1. Bridge Components

| Component | Location | Attack Surface |
|-----------|----------|----------------|
| Bridge RPC endpoints | `rpc/bridge.py` | Unauthenticated HTTP (signature-verified per-request) |
| Proof verification path | `cross_chain/bridge.py:_validate_proof` | Accepts proofs from any caller; validates fields, signatures, Merkle proofs, finality |
| Validator set registry | `BridgeValidator` table + `ValidatorSetRegistry` | Validator registration, epoch rotation, grace period |
| Block header signatures | `BridgeBlockHeader.signature` + PoA signing | Block proposal, validation, canonical chain proof |
| Multi-sig aggregation | `aitbc/bridge/multisig.py` | Threshold signature collection + verification |
| Merkle proof verification | `state/merkle_patricia_trie.py:verify_proof` | Trie inclusion proof for lock events |
| Finality tracking | `BridgeBlockHeader.confirmation_count` + `_check_finality_for_transfer` | Confirmation counting, large-transfer finality gate |
| Release fence | `bridge_release_enabled` config | Gates confirm/release path (default: True) |
| HTLC settlement | `cross_chain/settlement.py` + `contracts/htlc_contract.py` | Fund locking, secret reveal, timelock enforcement, refund |
| Bridge enhanced (coordinator) | `coordinator-api/.../bridge_enhanced.py` | HTLC swap initiation, wallet adapter calls |

## 2. Security Layers (Defense in Depth)

```
Layer 1:  Signature verification (v0.7.0) — secp256k1 signature on every lock/unlock/confirm
Layer 2:  Block anchoring (v0.7.0) — proofs reference a specific block height + hash
Layer 3:  Multi-sig threshold (v0.7.1) — M-of-N validators must sign proofs
Layer 4:  Block header signatures (v0.7.1) — proposers sign block headers
Layer 5:  Validator set registry (v0.7.1) — only registered validators can sign
Layer 6:  Release fence (v0.5.16) — bridge_release_enabled gates the release path
Layer 7:  Merkle proof verification (v0.7.2) ✅ — proofs tied to verified on-chain state trie
Layer 8:  Finality checks (v0.7.2) ✅ — large transfers require full finality (6+ confirmations)
Layer 9:  Validator set freshness (v0.7.2) ✅ — epoch grace period prevents stale-set attacks
Layer 10: Proposer validator-set membership (v0.7.2 audit fix) ✅ — recovered signer checked against registered set
Layer 11: Merkle proof enforcement flag (v0.7.2 audit fix) ✅ — bridge_require_merkle_proof rejects proofs without inclusion evidence
Layer 12: HTLC contract (v0.9.0 B4) ✅ — Python-native contract moves funds with hashlock + timelock
Layer 13: Proof chain (v0.9.0 B3) ✅ — tamper-evident proof chain (lock → verify → execute → release → settle)
```

## 3. Attack Vectors

### 3.1 Forged Proof (No Actual Lock)

**Vector**: Attacker fabricates a lock proof with correct fields and a valid signature, without an actual lock transaction on the source chain.

**Mitigation (v0.7.1–v0.7.2)**: Multi-sig threshold (M-of-N) + Merkle proof verification. The proof must include a Merkle inclusion proof (`merkle_proof` + `lock_event`) verified against the block header's state root. When `bridge_require_merkle_proof=True`, proofs without inclusion evidence are rejected.

**Residual risk**: A colluding validator majority (≥M validators) who also control block production can still forge proofs with valid Merkle inclusion. Mitigation: multi-validator consensus (v0.7.5) distributes block production.

**Status**: ✅ Mitigated. Bug #3 (proposer signature not checked against validator set) fixed in audit. Bug #4 (Merkle proof silently skipped) fixed with enforcement flag.

### 3.2 Signature Replay (Cross-Chain / Cross-Transfer)

**Vector**: Attacker reuses a valid proof on a different chain or for a different transfer.

**Mitigation**: `chain_id` is embedded in the proof and verified against the source chain. `_processed_proofs` set prevents replay of the same proof hash. Proof chain (`EscrowProofRecord`) persists proof hashes to DB, surviving node restarts.

**Residual risk**: `_processed_proofs` is in-memory for bridge transfers (not settlement). Settlement uses DB-persisted `EscrowProofRecord` with `previous_proof_hash` chaining.

**Status**: ✅ Mitigated for settlement. ⚠️ Bridge transfer replay protection is in-memory only.

### 3.3 Validator Key Compromise

**Vector**: Attacker steals a validator's private key.

**Mitigation**: M-of-N threshold — single key compromise is insufficient to forge a proof. Validator set rotation (epoch advancement) can remove compromised validators.

**Residual risk**: If ≥M validators are compromised simultaneously, the bridge is compromised. This is inherent to any M-of-N threshold system. Mitigation: keep M high enough (default 3-of-5) and rotate keys regularly.

**Status**: ✅ Mitigated. Risk is inherent to threshold systems.

### 3.4 Validator Set Rotation Attack

**Vector**: Attacker exploits the transition between validator set epochs — submitting a proof signed by the old set after the new set is active.

**Mitigation**: Epoch tracking in `ValidatorSetRegistry`. Old epoch sets are retained for a grace period (default 7200s) to allow in-flight transfers to complete. `_check_validator_set_freshness()` rejects proofs when the validator set is stale.

**Residual risk**: During the grace period, both old and new sets are valid. An attacker who compromised an old-set validator can still submit proofs during this window. Mitigation: keep grace period short.

**Status**: ✅ Mitigated.

### 3.5 Below-Threshold Attack

**Vector**: Attacker submits a proof with fewer than M signatures.

**Mitigation**: `check_threshold()` in `aitbc/bridge/multisig.py` verifies the signer count meets the threshold. Deduplication prevents counting the same signer twice.

**Status**: ✅ Fully mitigated.

### 3.6 Block Header Forgery

**Vector**: Attacker fabricates a block header (height + hash) to anchor a forged proof.

**Mitigation (v0.7.1–v0.7.2)**: Block header signatures verified via `_verify_block_header_signature()` using `validate_block_header()` from the shared SDK. The header's state root is checked against the proof's state root. Merkle proof verification ties the lock event to the state trie at that root.

**Residual risk**: A malicious proposer can sign a fabricated block, but the Merkle proof must be valid against the state root in that block. Without controlling the state trie, the attacker cannot produce a valid Merkle proof for a non-existent lock event.

**Status**: ✅ Mitigated. Block header signature + Merkle proof together prevent forgery.

### 3.7 Bridge RPC DoS

**Vector**: Attacker floods bridge RPC endpoints with requests.

**Mitigation**: Rate limiting (`@rate_limit` decorator on all bridge endpoints). Signature verification on lock/unlock/confirm prevents unauthenticated spam.

**Residual risk**: Rate limits can be bypassed with sufficient IP diversity. This is a general platform concern, not bridge-specific.

**Status**: ✅ Mitigated (standard DoS protections).

### 3.8 Validator Registration Attack

**Vector**: Attacker registers themselves as a validator to gain signing power.

**Mitigation**: `POST /bridge/validators/register` requires a signature proving ownership of the address being registered. In production, validator registration should be restricted to authorized operators (governance-controlled in v0.7.3).

**Residual risk**: No governance gate on validator registration in the current code. Any address with a valid signature can register. Mitigation: validator registration is an operational action performed by chain operators, not exposed to end users. The RPC endpoint should be firewalled to internal networks in production.

**Status**: ⚠️ Partially mitigated. Governance gate (v0.7.3) is implemented but validator registration RPC is not governance-gated at the code level.

### 3.9 HTLC Secret Reveal Front-Running

**Vector**: Attacker observes the secret being revealed on the destination chain and front-runs the source chain claim.

**Mitigation (v0.9.0 B4)**: The HTLC timelock ordering ensures `dest_timelock < source_timelock`, giving the buyer time to claim on the source chain after the seller reveals on the destination chain. The secret is revealed in the `complete_swap()` call which atomically releases funds.

**Residual risk**: If the gap between dest and source timelocks is too small and network latency is high, the buyer might not have enough time to claim on the source chain before the source timelock expires. Mitigation: `dest_timelock_margin_blocks` (default 20) provides adequate gap.

**Status**: ✅ Mitigated by timelock ordering.

### 3.10 HTLC Timelock Expiry Race

**Vector**: Attacker waits until just before the timelock expires, then tries to simultaneously claim and refund.

**Mitigation (v0.9.0 B4)**: The `HTLCContract.complete_swap()` and `refund_swap()` methods are called within a single DB session with atomic balance transfers. Only one can succeed — the first to commit wins. The status check (`SwapStatus.OPEN`) prevents double-spend.

**Residual risk**: In a distributed system with multiple nodes, concurrent calls to different nodes could race. Mitigation: DB-level transaction isolation prevents concurrent commits. For multi-node deployment, a distributed lock or consensus-level serialization may be needed.

**Status**: ✅ Mitigated for single-node. ⚠️ Multi-node race requires further testing (v0.9.0 chaos testing).

### 3.11 HTLC Contract Account Drain

**Vector**: Attacker attempts to withdraw funds from the HTLC contract escrow account (`HTLC_CONTRACT_ADDRESS`) without a valid swap.

**Mitigation (v0.9.0 B4)**: The `HTLC_CONTRACT_ADDRESS` is a reserved address. Funds can only leave it via `complete_swap()` (requires valid secret + open swap) or `refund_swap()` (requires expired timelock + open swap). Both methods verify swap state and transfer within a DB session.

**Residual risk**: If the contract address is used in other code paths (e.g., direct balance manipulation), funds could be drained. Mitigation: the address is a well-known constant, not user-configurable. No other code path transfers from this address.

**Status**: ✅ Mitigated.

### 3.12 Settlement Proof Chain Tampering

**Vector**: Attacker modifies or reorders proof records to make a fraudulent settlement appear legitimate.

**Mitigation (v0.9.0 B3)**: Each `EscrowProofRecord` includes a `previous_proof_hash` field creating a tamper-evident chain. Modifying any proof invalidates all subsequent proofs. The chain is: lock → verification → execution → release → settlement.

**Status**: ✅ Mitigated by hash chaining.

## 4. Configuration Summary

| Flag | Default | Production | Risk if misconfigured |
|------|---------|------------|----------------------|
| `bridge_release_enabled` | `True` | `True` (verification hardened) | Active by default — ensure all verification layers are configured |
| `bridge_multisig_enabled` | `False` | **`True`** | Off by default — single-signer path used, weaker security |
| `bridge_multisig_threshold` | `3` | `3` (minimum) | Lower = easier to forge proofs |
| `bridge_multisig_validators` | `5` | `5` (minimum) | Lower = easier to collude |
| `bridge_block_signature_required` | `True` | `True` | Disabling allows unsigned block headers |
| `bridge_require_merkle_proof` | `False` | **`True`** | Off by default — proofs without Merkle inclusion accepted |
| `bridge_verification_mode` | `in_process` | `in_process` | `oracle` mode is stub (NotImplementedError) |
| `bridge_min_confirmations` | `3` | `3` | Lower = less finality before release |
| `bridge_finality_blocks` | `6` | `6` | Lower = less finality for large transfers |
| `bridge_large_transfer_threshold` | `10000` | `10000` | Higher = more transfers bypass full finality |
| `bridge_validator_set_grace_period` | `7200` | `7200` | Higher = longer window for stale-set attacks |
| `escrow_enabled` | `False` | `True` (after audit) | Gates HTLC settlement |
| `escrow_htlc_enabled` | `True` | `True` | Disabling falls back to manual admin refund |
| `escrow_htlc_contract_address` | `""` | Set to deployed address | Empty = uses Python-native contract |
| `escrow_timeout_default` | `3600` | `3600` | Shorter = less time for secret reveal |
| `escrow_timeout_large` | `86400` | `86400` | Shorter = less time for large trade settlement |
| `multi_validator_consensus_enabled` | `False` | **`True`** (after soak) | Off = single-validator PoA, centralized block production |

## 5. Residual Risk Summary (After v0.9.0 B4)

| Risk | Severity | Mitigation | Timeline |
|------|----------|------------|----------|
| Colluding validator majority can forge proofs | High | Multi-validator consensus (v0.7.5) | Soak test pending |
| Multi-node HTLC timelock race | Medium | Chaos testing (v0.9.0) | Testnet + chaos tests |
| Bridge transfer replay protection is in-memory | Medium | Migrate to DB-persisted proof tracking | Future hardening |
| No governance gate on validator registration RPC | Medium | Governance-controlled registration (v0.7.3) | Implemented but not enforced at RPC level |
| External oracle is a stub | Low | In-process verification is active | v0.7.4 oracle deferred |
| Single-validator PoA centralized block production | Medium | v0.7.5 consensus activation | Soak test pending |
| No external security audit for HTLC settlement | High | External audit firm | v0.9.0 audit pending |

## 6. Audit History

| Audit | Date | Findings | Status |
|-------|------|----------|--------|
| Bridge security audit | 2026-06-18 | Bug #3 (Critical): Proposer sig not checked vs validator set. Bug #4 (High): Merkle proof silently skipped. | ✅ Fixed, regression tests passing |
| HTLC contract review | 2026-06-30 | B4 integration: Python-native HTLCContract mirrors CrossChainAtomicSwap.sol. Fund movement via Account balance transfers. | ✅ Implemented, 12 tests passing |
| Consensus security review | 2026-06-29 | 6 Critical + 6 High findings in MultiValidatorPoA + PBFT | ⚠️ Code complete, NOT activated (soak test pending) |

## 7. Testing Coverage

### Bridge Verification (v0.7.0–v0.7.2)
- `tests/test_bridge_security_audit_fixes.py` — 6 tests (Bug #3 + Bug #4 regression)
- `tests/test_v072_bridge_verification.py` — 32 tests (Merkle proofs, block headers, finality, validator sets)
- `tests/test_v071_bridge_security.py` — 18 tests (multi-sig, validator registration, threshold)

### HTLC Settlement (v0.9.0)
- `tests/test_htlc_contract.py` — 12 tests (initiate/complete/refund + settlement integration)
- `tests/test_settlement.py` — 20+ tests (full escrow lifecycle, proof chain, timeout, refund)

### Pending Test Coverage
- **Chaos testing**: Network partitions, timeout races, Byzantine validators on both chains
- **Multi-node integration**: 3+ node testnet with HTLC settlement across nodes
- **External audit**: Bridge security firm review of HTLC + proof verification

## 8. Critical Path to Production

```
Current state (v0.9.0 B4 complete):
  ✅ Bridge proof verification (Merkle + signatures + finality)
  ✅ HTLC contract integration (fund movement + timelock + secret reveal)
  ✅ Proof chain (tamper-evident settlement audit trail)
  ✅ 102 tests passing (bridge + settlement)

Remaining:
  1. v0.7.5 consensus activation — 3+ node testnet, 48h soak, 1 Byzantine
  2. v0.9.0 chaos testing — partition/timeout/Byzantine scenarios
  3. External security audit — bridge + HTLC settlement review
  4. Production config hardening — set all "Production" column values
  5. v1.0.0 production readiness — monitoring, alerting, incident response
```

## 9. References

- [Bridge Security Audit](../releases/AUDIT.md) — Bug #3, #4 findings and fixes
- [Release Status](../releases/STATUS.md) — All releases, config defaults, audit summary
- [v0.9.0 Change Log](../releases/v0.9.0/change.log) — Atomic settlement release
- [v0.7.2 Change Log](../releases/v0.7.2/change.log) — Bridge verification (Merkle proofs)
- [v0.7.1 Change Log](../releases/v0.7.1/change.log) — Bridge security (multi-sig)
- [General Threat Model](../security/threat-model.md) — Platform-wide threats
- `apps/blockchain-node/src/aitbc_chain/cross_chain/bridge.py` — Bridge implementation
- `apps/blockchain-node/src/aitbc_chain/contracts/htlc_contract.py` — HTLC contract
- `apps/blockchain-node/src/aitbc_chain/cross_chain/settlement.py` — Settlement service
