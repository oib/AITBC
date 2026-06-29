# Security Review: MultiValidatorPoA + PBFT Activation

**Status**: 🔴 BLOCKING — MultiValidatorPoA and PBFT cannot be activated (v0.7.4 B7) until the findings below are resolved.
**Review date**: 2026-06-29
**Reviewer**: Local code audit (Devin)
**Scope**: `apps/blockchain-node/src/aitbc_chain/consensus/multi_validator_poa.py` (294 lines), `apps/blockchain-node/src/aitbc_chain/consensus/pbft.py` (202 lines)
**Threat model reference**: [docs/architecture/bridge-threat-model.md](../../architecture/bridge-threat-model.md)

## Executive Summary

**Verdict: DO NOT ACTIVATE.** Both implementations are scaffolding, not production consensus. MultiValidatorPoA has no block signature verification, no slashing, and no validator rotation — the three requirements called out in the file's own threshold-state header. PBFT has no message signatures at all (`signature=""` on every message) and its network layer is a no-op (`_send_to_validator` is `pass`). Activating either would allow trivial block forgery and consensus takeover.

The header comment in both files states:
> Requires: validator rotation, slashing, multi-validator consensus audit

None of these three prerequisites are met. This review is the audit; the other two are unimplemented.

---

## Findings

### MultiValidatorPoA (`multi_validator_poa.py`)

#### CRITICAL — Block Forgery (no signature verification)

**Location**: `validate_block()` lines 98-112
**Severity**: Critical
**Description**: `validate_block()` checks only that the proposer address is in the validators dict and is active. It does **not** verify any cryptographic signature on the block. Any node that knows a valid proposer address can forge a block in that proposer's name.
**Impact**: Trivial block forgery → chain takeover by any network participant.
**Required fix**: Verify block signature against the proposer's public key before accepting. Use the existing ed25519 verification infrastructure from `aitbc/crypto/`.

#### CRITICAL — No Slashing (Byzantine validators face no penalty)

**Location**: `detect_byzantine_behavior()` lines 190-211, `record_prepare()` lines 171-188
**Severity**: Critical
**Description**: `detect_byzantine_behavior()` correctly identifies conflicting prepare messages (same round, different block hashes), but there is **no slashing or penalty mechanism**. A Byzantine validator can equivocate with zero consequences. Worse, `record_prepare()` line 184 explicitly returns `True` even when a conflicting message is detected — it records the conflict but takes no action.
**Impact**: Byzantine validators can disrupt consensus indefinitely with no cost.
**Required fix**: Implement slashing — when Byzantine behavior is detected, slash the validator's stake, set `is_active=False`, and broadcast a slashing event. The header comment requires this; it is not optional.

#### CRITICAL — No Validator Rotation

**Location**: `add_validator()` / `remove_validator()` lines 65-83
**Severity**: Critical
**Severity**: Critical
**Description**: Validators can be added and removed, but there is no rotation logic — no epoch advancement, no automatic proposer rotation based on stake/reputation, no mechanism to cycle validators. The header comment requires validator rotation; it is not implemented.
**Impact**: Stale validator sets, no recovery from compromised or inactive validators.
**Required fix**: Implement epoch-based validator rotation with on-chain epoch transitions.

#### HIGH — Fake Consensus (`attempt_consensus`)

**Location**: `attempt_consensus()` lines 152-169
**Severity**: High
**Description**: The method is a stub — it calls `asyncio.sleep(0.01)` then checks if a majority of validators are active. No messages are exchanged, no votes are collected, no quorum certificate is formed. This is not consensus; it is a majority check.
**Impact**: No actual agreement is reached; any active majority "consents" without participating.
**Required fix**: Replace with real consensus message exchange (prepare → commit → execute) or delegate to PBFT (which itself needs fixing — see below).

#### HIGH — Fake Transaction Validation

**Location**: `validate_transaction_async()` lines 141-150
**Severity**: High
**Description**: Calls `asyncio.sleep(0.001)` then checks `hasattr(transaction, "tx_id")`. No signature check, no balance check, no nonce check, no replay protection.
**Impact**: Invalid or forged transactions accepted into blocks.
**Required fix**: Delegate to the existing PoA transaction validation path (`poa.py` validate_transaction).

#### HIGH — Fake Block Creation

**Location**: `create_block()` lines 234-242
**Severity**: High
**Description**: Uses `len(self.validators)` as block height (should come from chain state). Block hash is `sha256(str(time.time()))` — does not include parent hash, transactions, or state root. `add_transaction()` just checks `hasattr(transaction, "tx_id")`.
**Impact**: Blocks are not cryptographically linked to the chain; no immutability guarantee.
**Required fix**: Integrate with the real block creation path in `poa.py` / `block.py`.

#### MEDIUM — Global Mutable State (race condition)

**Location**: `consensus_instances` dict, lines 287-294
**Severity**: Medium
**Description**: `consensus_instances` is a module-level dict shared across all async tasks. `get_consensus()` creates instances lazily without a lock. Concurrent calls for the same `chain_id` could create duplicate instances.
**Impact**: Race condition in async context → inconsistent consensus state.
**Required fix**: Use `asyncio.Lock` or initialize all chain consensus instances at startup.

#### MEDIUM — No Persistence

**Location**: entire class — validators dict is in-memory
**Severity**: Medium
**Description**: Validator set, prepare messages, and consensus state are all in-memory. A node restart loses all state. `recover_state()` exists but is marked "for testing" and only restores validators, not prepare messages or consensus attempts.
**Impact**: Node restart = consensus reset; Byzantine detection history lost.
**Required fix**: Persist validator set and consensus state to the blockchain database.

#### LOW — `remove_validator` doesn't remove

**Location**: `remove_validator()` lines 75-83
**Severity**: Low
**Description**: Marks validator inactive and standby but does not remove from the dict. The validator still counts toward `len(self.validators)` in quorum calculations (line 162: `len(self.partitioned_validators) > len(self.validators) // 2`).
**Impact**: Quorum thresholds drift as validators are "removed" but still counted.
**Required fix**: Either actually remove from dict, or exclude inactive validators from quorum denominator.

#### LOW — Silent exception swallowing

**Location**: `recover_state()` lines 257-274
**Severity**: Low
**Description**: `except Exception: return False` swallows all errors with no logging.
**Impact**: State recovery failures are invisible.
**Required fix**: Log the exception before returning False.

---

### PBFT (`pbft.py`)

#### CRITICAL — No Message Signatures

**Location**: All PBFTMessage instances — `signature=""` with comment "Would be signed in real implementation"
**Severity**: Critical
**Description**: Every PBFT message (pre-prepare, prepare, commit) is created with an empty signature string. No message is ever signed or verified. PBFT without message authentication is completely insecure — any node can forge any message from any validator.
**Impact**: Complete consensus subversion — attacker can fabricate prepare/commit messages for any validator.
**Required fix**: Sign every message with the sender's ed25519 private key; verify signature on receipt. Reject messages with invalid/missing signatures.

#### CRITICAL — Network Layer is a No-Op

**Location**: `_send_to_validator()` line 181-184 (`pass`), `_broadcast_message()` lines 172-179
**Severity**: Critical
**Description**: `_send_to_validator` does nothing (`pass`). `_broadcast_message` iterates validators and calls `_send_to_validator`, which is a no-op. Messages are stored locally but never transmitted. This means PBFT only "works" in a single-process simulation — it cannot function across nodes.
**Impact**: PBFT cannot reach consensus in any real multi-node deployment.
**Required fix**: Implement actual network transport (reuse the existing gossip layer in `apps/blockchain-node/src/aitbc_chain/gossip/`).

#### HIGH — Static Fault Tolerance

**Location**: `__init__()` lines 69-70
**Severity**: High
**Description**: `fault_tolerance` and `required_messages` are calculated once at init from `len(consensus.get_consensus_participants())`. If validators are added or removed after init, these thresholds do not update.
**Impact**: Consensus thresholds become stale — either too lenient (validators removed) or too strict (validators added).
**Required fix**: Recalculate on each consensus round, or update when validator set changes.

#### HIGH — View Change Clears All State

**Location**: `handle_view_change()` lines 195-201
**Severity**: High
**Description**: `handle_view_change()` clears all prepared, committed, and pre-prepare messages. In real PBFT, view change preserves prepared certificates to ensure safety across view changes. Clearing everything can cause committed blocks to be re-proposed differently.
**Impact**: Safety violation — committed blocks may not be finalized across view changes.
**Required fix**: Implement proper view change protocol with prepared certificate preservation (see Castro-Liskov PBFT paper, section 4.4).

#### HIGH — No View Change Timer

**Location**: no timeout mechanism anywhere in the class
**Severity**: High
**Description**: If the proposer fails, there is no timer to trigger a view change. The consensus can stall indefinitely waiting for a dead proposer.
**Impact**: Liveness failure — consensus halts if proposer crashes.
**Required fix**: Add a consensus timeout that triggers `handle_view_change` when no progress is made.

#### MEDIUM — No Sender Verification in Prepare/Commit

**Location**: `prepare_phase()` lines 101-128, `commit_phase()` lines 130-157
**Severity**: Medium
**Description**: Neither phase verifies that the `validator` argument actually corresponds to the message sender. Any caller can invoke `prepare_phase("some_other_validator", ...)` and record a prepare message on behalf of another validator.
**Impact**: Impersonation — one validator can fake prepare/commit messages for others.
**Required fix**: Verify the message signature matches the claimed sender (depends on CRITICAL signature fix above).

#### LOW — Execute Phase Does Nothing

**Location**: `execute_phase()` lines 159-170
**Severity**: Low
**Description**: Updates sequence number and cleans up messages, but does not execute the block or apply state transitions.
**Impact**: Blocks are "committed" but never applied.
**Required fix**: Call the actual block execution path after commit.

---

## Test Coverage Assessment

**Existing tests**: `apps/blockchain-node/tests/consensus/test_multi_validator_poa.py` (1 test class, basic CRUD tests). No PBFT tests found.

**Gaps**:
- No test for Byzantine detection → slashing (slashing doesn't exist)
- No test for block signature verification (verification doesn't exist)
- No test for view change safety (view change clears state unsafely)
- No test for consensus under network partition (partition handling is naive)
- No PBFT tests at all
- No multi-node integration test (network layer is a no-op)

---

## Gating Criteria for Activation (v0.7.4 B7)

The RuntimeError guard at `multi_validator_poa.py:45-49` and `pbft.py:60-64` must remain in place until **all** of the following are met:

### Must-Fix Before Activation (Critical + High)

- [ ] **C1**: Block signature verification in `validate_block()` (ed25519)
- [ ] **C2**: Slashing mechanism for Byzantine validators (stake slash + deactivate + broadcast)
- [ ] **C3**: Validator rotation (epoch-based, on-chain)
- [ ] **C4**: PBFT message signatures (sign + verify every message)
- [ ] **C5**: PBFT network transport (replace no-op `_send_to_validator` with gossip layer)
- [ ] **H1**: Real consensus in `attempt_consensus()` (message exchange, not majority check)
- [ ] **H2**: Real transaction validation (delegate to existing PoA path)
- [ ] **H3**: Real block creation (parent hash, tx root, state root — not `sha256(time)`)
- [ ] **H4**: Dynamic fault tolerance recalculation
- [ ] **H5**: Safe view change with prepared certificate preservation
- [ ] **H6**: View change timeout for liveness

### Must-Test Before Activation

- [ ] Byzantine validator detection + slashing test
- [ ] Block forgery rejection test (invalid signature)
- [ ] View change safety test (committed block preserved across view change)
- [ ] Network partition recovery test
- [ ] Multi-node PBFT integration test (≥3 nodes, 1 Byzantine)
- [ ] Proposer crash → view change → recovery test

### Operational Requirements

- [ ] Consensus state persistence (survive node restart)
- [ ] Consensus metrics (validator count, consensus rounds, view changes, byzantine detections)
- [ ] Rollback plan (document how to disable if issues found post-activation)
- [ ] Testnet deployment + soak test (≥48h) before mainnet

---

## Recommendation

**Do not activate in v0.7.4.** The implementation is scaffolding with placeholder logic in every security-critical path. Fixing the 6 Critical + 6 High findings is a substantial engineering effort — likely a dedicated release (v0.7.5 or a v0.7.4 phase 4 that slips to a later release).

**Suggested path forward**:
1. Keep the RuntimeError guard in place.
2. Split v0.7.4 B7 into a separate release (v0.7.5 "Consensus Activation") with the 12 must-fix items as its scope.
3. Ship v0.7.4 with the low-risk items only (parameter automation, emergency proposals, cross-chain governance, coordinator-api bridge, external oracle).
4. v0.7.5 ships only after all gating criteria are met + testnet soak test passes.

This unblocks v0.7.4 from being held hostage by consensus activation work that is nowhere near ready.
