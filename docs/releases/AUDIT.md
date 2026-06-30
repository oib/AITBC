# Bridge Security Audit Report

**Date:** 2026-06-18
**Scope:** Cross-chain bridge verification path in `apps/blockchain-node/src/aitbc_chain/cross_chain/bridge.py`
**Auditor:** Agent B (Bug fixes, infrastructure & apps)
**Status:** Fixes applied, regression tests passing

---

## Executive Summary

A security audit of the bridge's `_validate_proof` verification path identified two critical vulnerabilities and several lower-severity issues. Both critical bugs have been fixed with regression tests. The bridge's fund-release path (`confirm_transfer`) depends entirely on `_validate_proof` for security — any bypass allows unauthorized minting of bridge-released tokens.

---

## Findings

### BUG #3 — Proposer signature not checked against validator set

| Field | Value |
|-------|-------|
| **Severity** | Critical |
| **Status** | Fixed |
| **File** | `apps/blockchain-node/src/aitbc_chain/cross_chain/bridge.py` |
| **Function** | `_verify_proposer_signature` |
| **Lines** | 549–611 (post-fix) |

**Description:**
`_verify_proposer_signature` recovered the signer's Ethereum address from the proof's `proposer_signature` but explicitly accepted **any** valid signature without checking whether the recovered address belonged to the source chain's validator set. The code comment stated: *"we accept any valid signature — full proposer set verification is deferred to v0.7.2."*

This means any holder of any Ethereum private key could forge a valid-looking proof. Since `bridge_multisig_enabled` defaults to `False`, the single-signer path is the default verification mode. Combined with `bridge_release_enabled=True` (also default), this means the bridge's fund-release path was protected only by signature format validity, not signer authorization.

**Impact:**
Unauthorized fund release. An attacker with any Ethereum key could construct a proof with valid field values, sign it with their own key, and trigger `confirm_transfer` to release funds to any recipient.

**Fix:**
After recovering the signer address, check it against the validator set registered for the proof's source chain. If a validator set exists and the recovered address is not a member, reject the proof. If no validator set is registered (dev/isolated networks), preserve backward compatibility by accepting any valid signature.

**Regression tests:**
`tests/test_bridge_security_audit_fixes.py::TestBug3ProposerSignatureValidatorSetMembership`
- `test_non_member_signature_rejected_when_vset_registered` — non-member sig rejected
- `test_member_signature_accepted_when_vset_registered` — member sig accepted
- `test_any_valid_signature_accepted_without_vset` — dev mode backward compat

---

### BUG #4 — Merkle proof verification silently skipped

| Field | Value |
|-------|-------|
| **Severity** | High |
| **Status** | Fixed |
| **File** | `apps/blockchain-node/src/aitbc_chain/cross_chain/bridge.py` |
| **Function** | `_validate_proof` (Step 5c) |
| **Lines** | 523–543 (post-fix) |

**Description:**
When a proof omitted the `merkle_proof` field, `_validate_proof` silently skipped trie inclusion verification by logging a `DEBUG` message: *"No merkle_proof in proof — skipping trie verification (field+sig only)."* This meant a proof could pass validation without demonstrating that the lock event was actually included in the block's state trie.

The v0.7.2 change.log and the function docstring both claim "full cryptographic verification" including "Merkle proof verification," but the implementation silently bypassed it when the field was absent.

**Impact:**
A proof that passes field validation and signature verification but provides no Merkle inclusion proof would be accepted. This weakens the bridge's security guarantee from "cryptographic proof of lock event inclusion" to "field equality + signature validity." An attacker who can forge block headers or manipulate state roots (e.g., via a compromised node) could construct proofs without trie inclusion evidence.

**Fix:**
Added a new config flag `bridge_require_merkle_proof` (default `False` for backward compatibility). When set to `True`, proofs without `merkle_proof` are rejected. Even when `False`, the bypass now logs a `WARNING` (instead of `DEBUG`) so it is visible in production logs.

**Config:**
`bridge_require_merkle_proof: bool = False` in `config.py` (line 336). Set `BRIDGE_REQUIRE_MERKLE_PROOF=true` in production environments that move real value.

**Regression tests:**
`tests/test_bridge_security_audit_fixes.py::TestBug4MerkleProofEnforcement`
- `test_proof_without_merkle_rejected_when_required` — rejected when flag is True
- `test_proof_without_merkle_accepted_when_not_required` — accepted when flag is False
- `test_proof_with_valid_merkle_accepted_when_required` — valid proof accepted when flag is True

---

### INFO #1 — Dead config flag: `escrow_require_proof_verification`

| Field | Value |
|-------|-------|
| **Severity** | Low (informational) |
| **Status** | Documented (no code change needed) |
| **File** | `apps/blockchain-node/src/aitbc_chain/config.py` |

**Description:**
The config flag `escrow_require_proof_verification` is set to `True` but is never referenced anywhere in the `aitbc_chain/` codebase. It appears to be a dead flag from an earlier design phase.

**Recommendation:**
Either wire this flag into the settlement/escrow verification path or remove it to avoid confusion. The new `bridge_require_merkle_proof` flag serves a similar purpose for the bridge path.

---

### INFO #2 — HTLC contract integration complete

| Field | Value |
|-------|-------|
| **Severity** | Medium (design risk) |
| **Status** | ✅ Resolved (v0.9.0 B4 complete) |
| **Files** | `apps/blockchain-node/src/aitbc_chain/cross_chain/settlement.py`, `apps/coordinator-api/.../bridge_enhanced.py`, `apps/blockchain-node/src/aitbc_chain/contracts/htlc_contract.py` |

**Description:**
The `CrossChainSettlementService` now calls a Python-native `HTLCContract` (mirroring `CrossChainAtomicSwap.sol`) to move funds between accounts. The `lock_escrow`, `settle`, and `refund` methods perform real balance debits/credits through the contract escrow address. The `_create_htlc_contract` method in `bridge_enhanced.py` uses the configured `escrow_htlc_contract_address` and produces structured JSON calldata instead of SHA256-fabricated addresses.

**Remaining risk:**
`escrow_enabled` still defaults to `False` until the v0.9.0 chaos test + external security audit pass. Once enabled in production, ensure `bridge_require_merkle_proof=True`, `bridge_multisig_enabled=True`, and `multi_validator_consensus_enabled=True` are also set.

---

### INFO #3 — Multi-validator consensus not activated

| Field | Value |
|-------|-------|
| **Severity** | Medium (design risk) |
| **Status** | Known (v0.7.5 soak test pending) |
| **File** | `apps/blockchain-node/src/aitbc_chain/consensus/multi_validator_poa.py` |

**Description:**
`multi_validator_consensus_enabled` defaults to `False`. The PBFT consensus implementation in `consensus/pbft.py` exists but is not activated. Single-validator PoA remains active, meaning block production is centralized.

**Impact:**
With single-validator PoA, the bridge's block header signature verification (`_verify_block_header_signature`) checks signature validity but the validator set may contain only one validator. This concentrates trust in a single operator.

**Recommendation:**
Activate multi-validator consensus (v0.7.5) after the soak test. Ensure the validator set has sufficient diversity before enabling bridge operations with real value.

---

## Configuration Summary

| Flag | Default | Purpose | Risk if misconfigured |
|------|---------|---------|----------------------|
| `bridge_release_enabled` | `True` | Enables bridge fund release | Active by default — ensure verification is correct |
| `bridge_multisig_enabled` | `False` | Requires M-of-N validator sigs | Off by default — single-signer path used |
| `bridge_block_signature_required` | `True` | Requires block header signatures | Safe default |
| `bridge_require_merkle_proof` | `False` | **NEW** — rejects proofs without Merkle proof | Set to `True` for production |
| `escrow_enabled` | `False` | Enables HTLC settlement | Safe default until v0.9.0 audit passes |
| `multi_validator_consensus_enabled` | `False` | Activates PBFT consensus | Safe default (soak test pending) |
| `escrow_require_proof_verification` | — | **REMOVED** — dead flag, replaced by `bridge_require_merkle_proof` | N/A |

---

## Test Results

```
tests/test_bridge_security_audit_fixes.py: 6 passed
tests/test_v072_bridge_verification.py:    32 passed
tests/test_v071_bridge_security.py:        18 passed
Total: 56 passed, 0 failed
```

---

## Remediation Checklist

- [x] Bug #3: Proposer signature validator-set membership check
- [x] Bug #4: Merkle proof enforcement flag + loud warning on bypass
- [x] Regression tests for both bugs
- [x] Existing bridge test suite confirmed green
- [x] Removed dead `escrow_require_proof_verification` flag from config
- [x] Set `BRIDGE_REQUIRE_MERKLE_PROOF=true` in production env example (`examples/blockchain.env.example`)
- [x] Complete HTLC contract integration (v0.9.0 B4) — Python-native HTLCContract implemented, wired into settlement service
- [ ] Activate multi-validator consensus after soak test (v0.7.5) — operational, not a code change

---

## Files Changed

| File | Change |
|------|--------|
| `apps/blockchain-node/src/aitbc_chain/config.py` | Added `bridge_require_merkle_proof` flag; removed dead `escrow_require_proof_verification` flag |
| `apps/blockchain-node/src/aitbc_chain/cross_chain/bridge.py` | Bug #3 fix in `_verify_proposer_signature`; Bug #4 fix in `_validate_proof` Step 5c |
| `apps/blockchain-node/tests/test_bridge_security_audit_fixes.py` | New file: 6 regression tests |
| `examples/blockchain.env.example` | Added Bridge Security section with `BRIDGE_REQUIRE_MERKLE_PROOF=true` for production |
| `apps/blockchain-node/src/aitbc_chain/contracts/htlc_contract.py` | New file: Python-native HTLC contract (mirrors CrossChainAtomicSwap.sol) |
| `apps/blockchain-node/src/aitbc_chain/base_models.py` | Added `HTLCSwapState` SQLModel for persistent swap state |
| `apps/blockchain-node/src/aitbc_chain/cross_chain/settlement.py` | B4: wired HTLCContract into lock/settle/refund for real fund movement |
| `apps/coordinator-api/.../bridge_enhanced.py` | B4: replaced SHA256-fabricated addresses with real config + structured calldata |
| `apps/blockchain-node/tests/test_htlc_contract.py` | New file: 12 HTLC contract + settlement integration tests |
| `apps/blockchain-node/tests/test_settlement.py` | Updated MockSession for HTLC contract support (Account, HTLCSwapState, get, flush) |
