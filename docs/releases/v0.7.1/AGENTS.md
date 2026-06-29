# v0.7.1 — Agent Task Assignment

**Release Theme**: Bridge Security Layer — Multi-Sig Validation, Validator Set Registry, Block Header Signatures

**Goal**: Add the security-critical multi-signature layer to the cross-chain bridge. Replace the current "accepts any valid secp256k1 signer" proof verification (`_verify_proposer_signature` in `cross_chain/bridge.py:477-523`) with proper M-of-N threshold signature validation against a per-chain validator set. Add block header signatures so proposers are cryptographically bound to the blocks they produce. Add CLI commands for security status and validator registration.

> **Rescope from original change.log**: The original v0.7.1 change.log bundled multi-sig + cross-chain sig verification + time-locks + audit trail into one release. This is too much for a single release cycle. Per the release-planning analysis, v0.7.1 is now scoped to **multi-sig core only**:
> - ✅ v0.7.1: Validator set registry, threshold sigs, block header signing, multi-sig lock/confirm, CLI, threat model
> - ➡️ v0.7.2: Time-locks (value-tiered), audit trail (cryptographic chaining), light client verification, Merkle proof verification, finality thresholds, oracle stub
>
> This rescoping aligns with the existing v0.7.2 change.log which already covers Merkle proof verification + block header verification + validator set tracking. Moving validator set tracking to v0.7.1 (where it's needed for multi-sig) and keeping Merkle proof verification in v0.7.2 (where it's needed for release path unfencing) gives a cleaner separation: v0.7.1 establishes the trust foundation (who are validators, how do they sign), v0.7.2 builds the verification layer on top.

> **No external security audit**: All development is in-house. The change.log's "External security audit required before merge" (line 15) and success criterion "External security audit passed" (line 252) are **dropped**. Internal code review + comprehensive test coverage replaces the external audit gate.

> **Scope constraint**: This release does NOT unfence the bridge release path. `BRIDGE_RELEASE_ENABLED=false` (config.py:285-290) remains in place. The confirm/release path stays gated until v0.7.2 completes Merkle proof verification. v0.7.1 adds multi-sig validation to the proof verification path, but the release fence is a separate safety layer that stays until cryptographic proof verification (not just signature verification) is complete.

> **Prerequisites**: [v0.7.0](../v0.7.0/change.log) — Bridge Basics. v0.7.0 Agent A (shared bridge SDK) is ✅ committed (`35b029852`). v0.7.0 Agent B (RPC endpoints, CLI, monitoring, tests) exists in the working tree but is **uncommitted** — Agent B must commit v0.7.0 work before starting v0.7.1. [v0.5.16](../v0.5.16/change.log) ✅ (bridge proof hardening + release fence).

> **Risk**: Medium-High. This release touches consensus-critical code (block header signing) and the bridge proof verification path. The `BRIDGE_RELEASE_ENABLED=false` fence prevents unauthorized fund release even if multi-sig has bugs. Block header signature changes are backward-compatible (new optional field, old blocks have empty signature).

---

## Status Baseline — Verified Code Targets (from subagent investigation, 2026-06-29)

| Component | Location | Current State | v0.7.1 Target |
|-----------|----------|---------------|---------------|
| **Proposer signature verification** | `cross_chain/bridge.py:477-523` | ⚠️ PARTIAL — `_verify_proposer_signature` recovers signer address but accepts ANY valid secp256k1 key. No proposer-set membership check. Comment (line 485-489) says "deferred to v0.7.2". | Replace with M-of-N threshold verification against validator set. Multiple validator signatures required. |
| **Bridge proof structure** | `cross_chain/bridge.py:38-55`, `aitbc/bridge/types.py:33-48` | ✅ EXISTS — single `proposer_signature: str` field | Add `validator_signatures: list[str]` field (backward-compatible — old proofs with single proposer_signature still work) |
| **Processed proofs tracking** | `cross_chain/bridge.py:73` | ⚠️ IN-MEMORY — `self._processed_proofs: set[str] = set()` | No change in v0.7.1 (persistent audit trail deferred to v0.7.2) |
| **Block header model** | `base_models.py:25-76` | ⚠️ NO SIGNATURE — `proposer: str` field is address string only, no `signature` field | Add `signature: str = ""` field (optional, backward-compatible). PoA signs block headers on proposal. |
| **PoA consensus** | `consensus/poa.py:82-97` | ✅ EXISTS — single proposer from config (`PoAProposer`), tracks `_last_proposer_id` | Add block header signing on proposal + signature verification on validation |
| **Multi-validator PoA** | `consensus/multi_validator_poa.py` (293 lines) | ⚠️ DEAD CODE — gated behind `MULTI_VALIDATOR_CONSENSUS_ENABLED=true`, requires security review. Has `Validator` dataclass, `add_validator`, `remove_validator`, `select_proposer` (round-robin). | Do NOT activate. v0.7.1 builds a separate bridge validator set (not consensus validator set). MultiValidatorPoA activation is a separate future release. |
| **Validator set management** | — | ❌ NONE for bridge. Staking has `register_validator` (`economics/staking.py:180`) but for staking economics, not bridge. | Create bridge validator set registry: SQLModel table + in-memory cache + RPC endpoints |
| **Threshold signature utilities** | `aitbc/crypto/crypto.py` | ❌ NONE — only single-signer `recover_signer()`, `verify_signature()`. No threshold/BLS/aggregation. | Add secp256k1 M-of-N threshold verification (collect M sigs, verify each against validator set, check threshold). No BLS — keep it simple, no new dependencies. |
| **Time-locks** | — | ❌ NONE for bridge. Exist for guardian contracts (`test_guardian_contract.py`), escrow (`EscrowService.sol`), governance (`AgentDAO.sol`). | DEFERRED to v0.7.2 |
| **Audit trail** | — | ❌ NONE for bridge. `_processed_proofs` is in-memory only. Other audit logs exist: `AgentAuditLog` (coordinator-api), `PricingAuditLog` (trading), `AuditLogger` (CLI). | DEFERRED to v0.7.2 |
| **Light client** | — | ❌ NONE — only doc references in release plans | DEFERRED to v0.7.2 |
| **Threat model** | `docs/security/threat-model.md` (174 lines) | ⚠️ GENERAL — covers smart contracts, ZK, API, network, economic attacks. Does NOT cover bridge-specific threats (bridge mints, cross-chain replay, validator set attacks, proof forgery). | Create bridge-specific threat model addendum covering bridge attack surfaces |
| **CLI bridge commands** | `cli/aitbc_cli/commands/bridge.py` (186 lines) | ✅ 7 commands exist (lock, confirm, unlock, status, pending, balance, health) — from v0.7.0 Agent B | Add `security-status` and `register-validator` subcommands |
| **Bridge release fence** | `config.py:285-290`, `rpc/bridge.py:105-110` | ✅ EXISTS — `bridge_release_enabled: bool = False`, gates `/bridge/confirm` and `/bridge/batch/confirm` | No change — fence stays until v0.7.2 |
| **Bridge RPC endpoints** | `rpc/bridge.py` (405 lines) | ✅ 9 endpoints exist (lock, confirm, transfer, pending, unlock, balance, health, batch/lock, batch/confirm) — from v0.7.0 | Add `POST /bridge/validators/register` and `GET /bridge/validators/{chain_id}` endpoints |
| **Shared bridge SDK** | `aitbc/bridge/` (4 files) | ✅ EXISTS — BridgeClient, types, proof utilities (v0.7.0 Agent A, committed `35b029852`) | Extend types with ValidatorInfo, ValidatorSet, ThresholdProof. Add multisig.py module. |
| **Crypto utilities** | `aitbc/crypto/crypto.py` (226 lines) | ✅ EXISTS — `recover_signer()`, `verify_signature()`, `keccak256_hash()` | Reuse `recover_signer()` for threshold sig verification. No new crypto dependencies. |

### Already Fixed / Exists (verified — no work needed)

1. ✅ **Bridge core exists** — `CrossChainBridge` with lock/confirm/transfer/pending/unlock flow
2. ✅ **9 bridge RPC endpoints exist** — lock, confirm, transfer, pending, unlock, balance, health, batch/lock, batch/confirm (v0.7.0 Agent B)
3. ✅ **Bridge release fence active** — `BRIDGE_RELEASE_ENABLED=false` gates confirm/batch_confirm
4. ✅ **Shared bridge SDK exists** — `aitbc/bridge/` with BridgeClient, types, proof utilities (v0.7.0 Agent A)
5. ✅ **Single-signer secp256k1 utilities exist** — `recover_signer()`, `verify_signature()` in `aitbc/crypto/crypto.py`
6. ✅ **7 CLI bridge commands exist** — lock, confirm, unlock, status, pending, balance, health (v0.7.0 Agent B)
7. ✅ **General threat model exists** — `docs/security/threat-model.md` (174 lines, no bridge coverage)
8. ✅ **BridgeStatus enum includes REFUNDED** — already has the `refunded` status for unlock/refund flow

### Architecture: Bridge Security (v0.7.1)

```
┌──────────────────────────────────────────────────────────────────────┐
│ Shared Core (aitbc/bridge/ — EXTEND + NEW MODULES)                   │
│                                                                      │
│  Bridge types (A1 — EXTEND types.py):                                │
│    ValidatorInfo, ValidatorSet, ThresholdProof                       │
│    BridgeProof gains validator_signatures: list[str]                 │
│                                                                      │
│  Multi-sig utilities (A2 — NEW multisig.py):                         │
│    verify_threshold_signatures(proof, validator_set, threshold)      │
│    recover_all_signers(message_data, signatures)                     │
│    check_threshold(signers, validator_set, threshold)                │
│                                                                      │
│  Validator set utilities (A3 — NEW validators.py):                   │
│    ValidatorSetRegistry — in-memory cache with epoch tracking        │
│    get_validator_set(chain_id, epoch)                                │
│    is_member(address, validator_set)                                 │
└──────────────────────────────────────────────────────────────────────┘
         ↑ consumed by                    ↑ consumed by
┌─────────────────────────┐    ┌──────────────────────────────────────┐
│ CLI (cli/aitbc_cli/)    │    │ Blockchain Node                      │
│                         │    │ (apps/blockchain-node/)              │
│  bridge security-status │    │                                      │
│  bridge register-       │    │  Block header signing (B3):          │
│    validator            │    │    Block.signature field (NEW)       │
│                         │    │    PoA signs on propose              │
│  Uses BridgeClient (A1) │    │    PoA verifies on validate          │
│  + new SDK methods      │    │                                      │
│                         │    │  Validator set table (B4):           │
│                         │    │    BridgeValidator SQLModel (NEW)    │
│                         │    │    fields: chain_id, address,        │
│                         │    │    pubkey, epoch, is_active          │
│                         │    │                                      │
│                         │    │  Validator RPC (B5):                 │
│                         │    │    POST /bridge/validators/register  │
│                         │    │    GET  /bridge/validators/{chain}   │
│                         │    │                                      │
│                         │    │  Multi-sig bridge (B6):              │
│                         │    │    _verify_proposer_signature →      │
│                         │    │    _verify_threshold_signatures      │
│                         │    │    Uses A2 + A3 + B4 validator set   │
│                         │    │                                      │
│                         │    │  Config (B2):                        │
│                         │    │    bridge_multisig_enabled           │
│                         │    │    bridge_multisig_threshold         │
│                         │    │    bridge_multisig_validators        │
│                         │    │                                      │
│                         │    │  Tests (B8):                         │
│                         │    │    multi-sig, validator set,         │
│                         │    │    block signing, CLI                │
└─────────────────────────┘    └──────────────────────────────────────┘

Phase 0 (prerequisite — either agent):
  docs/architecture/bridge-threat-model.md
```

---

## Task Split Overview

| Agent | Domain | Tasks | Files |
|-------|--------|-------|-------|
| **Agent A** | Shared core (`aitbc/`) | 4 items | `aitbc/bridge/types.py` (extend), `aitbc/bridge/multisig.py` (new), `aitbc/bridge/validators.py` (new), `aitbc/bridge/__init__.py` (extend), `aitbc/bridge/client.py` (extend), `tests/unit/` |
| **Agent B** | Apps & infrastructure | 8 items | `docs/architecture/bridge-threat-model.md` (new), `apps/blockchain-node/src/aitbc_chain/config.py`, `base_models.py`, `consensus/poa.py`, `cross_chain/bridge.py`, `rpc/bridge.py`, `rpc/router.py`, `cli/aitbc_cli/commands/bridge.py`, `aitbc/constants.py`, `apps/blockchain-node/tests/` |

**Conflict boundary**: Agent A owns `aitbc/bridge/` package (extends v0.7.0 work). Agent B owns all `apps/`, `cli/`, and `aitbc/constants.py`. Agent B consumes Agent A's `ValidatorSetRegistry`, `verify_threshold_signatures`, and extended types. No shared files are touched by both agents.

**Sequencing**: Agent A goes first (shared SDK). Agent B starts after Agent A completes A1-A3 (B6 multi-sig bridge depends on A2+A3). B1 (config), B2 (threat model), B3 (block header signing) can proceed in parallel with Agent A.

---

## Phase 0 — Threat Model (Prerequisite)

**Either agent can write this first. Recommended: Agent B (owns bridge implementation).**

Create `docs/architecture/bridge-threat-model.md` — bridge-specific threat model addendum to the existing `docs/security/threat-model.md` (which covers general platform threats but NOT bridge-specific ones).

Must cover:
- **Attack surfaces**: bridge RPC endpoints, proof verification path, validator set registry, block header signatures, multi-sig aggregation
- **Attack vectors**:
  - Forged proofs (attacker fabricates lock proof without actual lock) — mitigated by multi-sig + block anchoring
  - Signature replay (reuse valid proof on different chain/transfer) — mitigated by chain_id in proof + `_processed_proofs` tracking
  - Validator key compromise (attacker steals validator private key) — mitigated by M-of-N threshold (single key compromise insufficient)
  - Validator set rotation attack (exploit transition between validator sets) — mitigated by epoch tracking + grace period
  - Below-threshold attack (submit proof with insufficient signatures) — mitigated by threshold check
  - Block header forgery (fake block header to anchor proof) — mitigated by block header signatures (v0.7.1) + Merkle proof verification (v0.7.2)
- **Mitigations**: M-of-N threshold sigs, validator set registry, block header signing, release fence (until v0.7.2)
- **Residual risk** (after v0.7.1, before v0.7.2):
  - Proof verification is still signature-only (no Merkle proof) — a colluding validator majority can forge proofs
  - `_processed_proofs` is in-memory — replay possible after node restart (audit trail deferred to v0.7.2)
  - No time-locks — large transfers have no challenge period (deferred to v0.7.2)
  - Release fence (`BRIDGE_RELEASE_ENABLED=false`) is the primary protection until v0.7.2

---

## Agent A — Shared Core (`aitbc/`)

**Scope**: Extend the v0.7.0 bridge SDK with multi-sig types, threshold signature verification utilities, and validator set registry utilities. All consumed by Agent B's blockchain-node and CLI work.

**Working directory**: `/opt/aitbc/aitbc/bridge/`

**Verification command**:
```bash
cd /opt/aitbc && ./venv/bin/python -m mypy --show-error-codes aitbc/bridge/ && ./venv/bin/python -m ruff check aitbc/bridge/ tests/unit/test_bridge_security.py && ./venv/bin/python -m pytest tests/unit/test_bridge_security.py tests/unit/test_bridge_sdk.py -q -o addopts=""
```

### Tasks

| # | Task | Priority | Files | Status |
|---|------|----------|-------|--------|
| A1 | Extend bridge types — add ValidatorInfo, ValidatorSet, ThresholdProof; add `validator_signatures` field to BridgeProof | 🔴 P0 | `aitbc/bridge/types.py` (extend), `aitbc/bridge/__init__.py` (extend) | ✅ |
| A2 | Create `aitbc/bridge/multisig.py` — threshold signature verification (M-of-N secp256k1) | 🔴 P0 | `aitbc/bridge/multisig.py` (new), `aitbc/bridge/__init__.py` (extend) | ✅ |
| A3 | Create `aitbc/bridge/validators.py` — ValidatorSetRegistry with epoch tracking | 🔴 P0 | `aitbc/bridge/validators.py` (new), `aitbc/bridge/__init__.py` (extend) | ✅ |
| A4 | Extend BridgeClient with validator RPC methods + unit tests for A1-A3 | High | `aitbc/bridge/client.py` (extend), `tests/unit/test_bridge_security.py` (new) | ✅ |

### Agent A — Detailed Instructions

#### A1: Extend Bridge Types

Extend `aitbc/bridge/types.py` with validator set types and multi-sig proof support.

**New dataclasses**:

```python
@dataclass
class ValidatorInfo:
    """A bridge validator for a specific chain."""
    address: str           # checksum address (0x...)
    public_key: str        # secp256k1 public key hex (0x...)
    chain_id: str          # chain this validator serves
    epoch: int             # validator set epoch number
    is_active: bool = True
    registered_at: datetime | None = None


@dataclass
class ValidatorSet:
    """The set of validators for a chain at a specific epoch."""
    chain_id: str
    epoch: int
    validators: list[ValidatorInfo] = field(default_factory=list)
    threshold: int = 3     # M-of-N: minimum signatures required
    total: int = 5         # N: total validators in set

    @property
    def addresses(self) -> list[str]:
        """List of active validator addresses."""
        return [v.address for v in self.validators if v.is_active]

    @property
    def active_count(self) -> int:
        """Number of active validators."""
        return sum(1 for v in self.validators if v.is_active)


@dataclass
class ThresholdProof:
    """A proof with multiple validator signatures (M-of-N threshold).

    Backward-compatible with single-signer BridgeProof: if
    validator_signatures is empty, falls back to proposer_signature.
    """
    source_chain: str
    lock_tx_hash: str
    amount: int
    sender: str
    recipient: str
    chain_id: str
    block_height: int
    block_hash: str
    proposer_signature: str           # original single sig (backward compat)
    validator_signatures: list[str] = field(default_factory=list)
```

**Extend BridgeProof** — add optional `validator_signatures` field:
```python
@dataclass
class BridgeProof:
    # ... existing fields ...
    proposer_signature: str
    validator_signatures: list[str] = field(default_factory=list)  # NEW
```

**Extend BridgeConfig** — add multi-sig config:
```python
@dataclass
class BridgeConfig:
    # ... existing fields ...
    multisig_enabled: bool = False        # NEW — require multi-sig for confirm
    multisig_threshold: int = 3           # NEW — M-of-N minimum
    multisig_validators: int = 5          # NEW — N total validators
```

Update `aitbc/bridge/__init__.py` to re-export `ValidatorInfo`, `ValidatorSet`, `ThresholdProof`.

#### A2: Multi-Sig Utilities

Create `aitbc/bridge/multisig.py` — threshold signature verification using existing `aitbc.crypto.crypto.recover_signer()`. No BLS, no new dependencies — just collect M individual secp256k1 signatures and verify each signer is in the validator set.

```python
"""Bridge multi-signature threshold verification (v0.7.1 §A2).

M-of-N threshold signature verification using secp256k1. Each validator
signs the proof independently; the bridge verifies that at least M of the
N validators in the current validator set signed the proof.

No BLS aggregation — each signature is verified individually using
aitbc.crypto.crypto.recover_signer(). This keeps the dependency surface
minimal (no new crypto libraries) and is sufficient for the validator
set sizes in AITBC (5-21 validators per chain).
"""

from __future__ import annotations

import logging
from typing import Any

from aitbc.crypto.crypto import recover_signer

from .types import ThresholdProof, ValidatorSet

logger = logging.getLogger(__name__)


def recover_all_signers(message_data: dict[str, Any], signatures: list[str]) -> list[str]:
    """Recover signer addresses from multiple signatures over the same message.

    Returns list of recovered checksum addresses. Invalid signatures are
    skipped (not included in the result).
    """
    signers: list[str] = []
    for sig in signatures:
        if not sig:
            continue
        addr = recover_signer(message_data, sig)
        if addr:
            signers.append(addr)
    return signers


def check_threshold(
    signers: list[str],
    validator_set: ValidatorSet,
    threshold: int | None = None,
) -> tuple[bool, int, list[str]]:
    """Check if enough signers are in the validator set to meet threshold.

    Args:
        signers: Recovered signer addresses.
        validator_set: The validator set to check against.
        threshold: Override threshold (defaults to validator_set.threshold).

    Returns:
        (meets_threshold, valid_signer_count, valid_signer_addresses)
    """
    required = threshold if threshold is not None else validator_set.threshold
    valid_addresses = validator_set.addresses
    valid_signers = [s for s in signers if s in valid_addresses]
    # Deduplicate (one signer can't count twice)
    unique_signers = list(dict.fromkeys(valid_signers))
    return len(unique_signers) >= required, len(unique_signers), unique_signers


def verify_threshold_signatures(
    proof: ThresholdProof,
    validator_set: ValidatorSet,
    threshold: int | None = None,
) -> tuple[bool, int, list[str]]:
    """Verify that a proof has enough valid validator signatures to meet threshold.

    Builds the signed message from proof fields (excluding signatures),
    recovers all signers, checks threshold against validator set.

    Returns:
        (meets_threshold, valid_signer_count, valid_signer_addresses)
    """
    # Build the message that was signed (proof without signature fields)
    message_data: dict[str, Any] = {
        "source_chain": proof.source_chain,
        "lock_tx_hash": proof.lock_tx_hash,
        "amount": proof.amount,
        "sender": proof.sender,
        "recipient": proof.recipient,
        "chain_id": proof.chain_id,
        "block_height": proof.block_height,
        "block_hash": proof.block_hash,
    }

    # Collect all signatures (validator sigs + backward-compat proposer sig)
    all_sigs = list(proof.validator_signatures)
    if proof.proposer_signature and proof.proposer_signature not in all_sigs:
        all_sigs.append(proof.proposer_signature)

    signers = recover_all_signers(message_data, all_sigs)
    return check_threshold(signers, validator_set, threshold)
```

#### A3: Validator Set Registry

Create `aitbc/bridge/validators.py` — in-memory validator set registry with epoch tracking. This is the shared utility; Agent B creates the SQLModel table that persists it.

```python
"""Bridge validator set registry with epoch tracking (v0.7.1 §A3).

In-memory cache of validator sets per chain, keyed by epoch. Agent B
creates the persistent SQLModel table (BridgeValidator) that backs this
registry. This module provides the lookup/verification logic that the
bridge proof verification path uses.
"""

from __future__ import annotations

import logging

from .types import ValidatorInfo, ValidatorSet

logger = logging.getLogger(__name__)


class ValidatorSetRegistry:
    """In-memory registry of validator sets per chain per epoch."""

    def __init__(self) -> None:
        # chain_id -> epoch -> ValidatorSet
        self._sets: dict[str, dict[int, ValidatorSet]] = {}
        # chain_id -> current epoch number
        self._current_epoch: dict[str, int] = {}

    def register_validator(self, info: ValidatorInfo) -> None:
        """Add or update a validator in the registry."""
        chain_sets = self._sets.setdefault(info.chain_id, {})
        epoch_set = chain_sets.get(info.epoch)
        if epoch_set is None:
            epoch_set = ValidatorSet(chain_id=info.chain_id, epoch=info.epoch)
            chain_sets[info.epoch] = epoch_set
        # Replace if already exists
        epoch_set.validators = [v for v in epoch_set.validators if v.address != info.address]
        epoch_set.validators.append(info)
        epoch_set.total = len(epoch_set.validators)
        # Update current epoch if this is the latest
        if info.epoch >= self._current_epoch.get(info.chain_id, 0):
            self._current_epoch[info.chain_id] = info.epoch

    def get_validator_set(self, chain_id: str, epoch: int | None = None) -> ValidatorSet | None:
        """Get the validator set for a chain at a specific epoch.

        If epoch is None, returns the current (latest) epoch's set.
        """
        if epoch is None:
            epoch = self._current_epoch.get(chain_id, 0)
        chain_sets = self._sets.get(chain_id)
        if chain_sets is None:
            return None
        return chain_sets.get(epoch)

    def get_current_epoch(self, chain_id: str) -> int:
        """Get the current epoch number for a chain."""
        return self._current_epoch.get(chain_id, 0)

    def is_member(self, address: str, chain_id: str, epoch: int | None = None) -> bool:
        """Check if an address is a member of the validator set."""
        vset = self.get_validator_set(chain_id, epoch)
        if vset is None:
            return False
        return address in vset.addresses

    def advance_epoch(self, chain_id: str, new_set: ValidatorSet) -> int:
        """Advance to a new epoch for a chain.

        Returns the new epoch number. The old epoch's set is retained
        for in-flight transfer verification (grace period).
        """
        new_epoch = new_set.epoch
        self._sets.setdefault(chain_id, {})[new_epoch] = new_set
        self._current_epoch[chain_id] = new_epoch
        return new_epoch

    def remove_inactive(self, chain_id: str, epoch: int) -> int:
        """Remove inactive validators from a specific epoch's set.

        Returns the number removed.
        """
        vset = self.get_validator_set(chain_id, epoch)
        if vset is None:
            return 0
        before = len(vset.validators)
        vset.validators = [v for v in vset.validators if v.is_active]
        vset.total = len(vset.validators)
        return before - len(vset.validators)
```

#### A4: BridgeClient Extensions + Unit Tests

Extend `aitbc/bridge/client.py` with validator RPC methods:

```python
async def register_validator(
    self, chain_id: str, address: str, public_key: str, signature: str,
) -> dict[str, Any]:
    """Register a validator for bridge operations."""
    payload = {
        "chain_id": chain_id, "address": address,
        "public_key": public_key, "signature": signature,
    }
    resp = await self._ensure_client().post("/bridge/validators/register", json=payload)
    resp.raise_for_status()
    return cast(dict[str, Any], resp.json())

async def get_validator_set(self, chain_id: str, epoch: int | None = None) -> dict[str, Any]:
    """Get the validator set for a chain."""
    params = {}
    if epoch is not None:
        params["epoch"] = epoch
    resp = await self._ensure_client().get(f"/bridge/validators/{chain_id}", params=params)
    resp.raise_for_status()
    return cast(dict[str, Any], resp.json())

async def security_status(self) -> dict[str, Any]:
    """Get bridge security status (multi-sig config, validator count, etc.)."""
    resp = await self._ensure_client().get("/bridge/security/status")
    resp.raise_for_status()
    return cast(dict[str, Any], resp.json())
```

**`tests/unit/test_bridge_security.py`** — unit tests for A1-A4:
- `test_validator_info_dataclass` — all fields
- `test_validator_set_addresses_property` — active validators only
- `test_validator_set_active_count` — counts active
- `test_threshold_proof_defaults` — empty validator_signatures list
- `test_bridge_proof_with_validator_signatures` — extended BridgeProof
- `test_bridge_config_multisig_defaults` — multisig_enabled=False, threshold=3, validators=5
- `test_recover_all_signers_valid` — multiple valid sigs
- `test_recover_all_signers_skips_invalid` — invalid sigs skipped
- `test_recover_all_signers_skips_empty` — empty sigs skipped
- `test_check_threshold_meets` — enough signers
- `test_check_threshold_below` — insufficient signers
- `test_check_threshold_dedup` — duplicate signer doesn't count twice
- `test_check_threshold_override` — custom threshold
- `test_verify_threshold_signatures_valid` — full flow with valid sigs
- `test_verify_threshold_signatures_insufficient` — below threshold
- `test_verify_threshold_signatures_non_member` — signer not in validator set
- `test_verify_threshold_signatures_backward_compat` — single proposer_signature works
- `test_validator_registry_register_and_get` — register then lookup
- `test_validator_registry_get_current_epoch` — epoch tracking
- `test_validator_registry_is_member` — membership check
- `test_validator_registry_advance_epoch` — epoch rotation
- `test_validator_registry_remove_inactive` — inactive removal
- `test_validator_registry_unknown_chain` — returns None
- `test_bridge_client_register_validator` — mocked RPC
- `test_bridge_client_get_validator_set` — mocked RPC
- `test_bridge_client_security_status` — mocked RPC
- `test_package_reexport_security` — new names exported from aitbc.bridge

---

## Agent B — Apps & Infrastructure

**Scope**: Create threat model doc, add bridge security config, add block header signatures, create validator set SQLModel table + RPC, upgrade bridge proof verification to multi-sig, add CLI commands, write integration tests.

**Working directory**: `/opt/aitbc/apps/blockchain-node/` and `/opt/aitbc/cli/`

**Prerequisite**: Agent B must commit v0.7.0 work (currently uncommitted in working tree) before starting v0.7.1.

**Verification command**:
```bash
cd /opt/aitbc && ./venv/bin/python -m ruff check apps/blockchain-node/src/aitbc_chain/config.py apps/blockchain-node/src/aitbc_chain/base_models.py apps/blockchain-node/src/aitbc_chain/consensus/poa.py apps/blockchain-node/src/aitbc_chain/cross_chain/bridge.py apps/blockchain-node/src/aitbc_chain/rpc/bridge.py cli/aitbc_cli/commands/bridge.py aitbc/constants.py
cd /opt/aitbc && ./venv/bin/python -m pytest apps/blockchain-node/tests/test_bridge_suite.py apps/blockchain-node/tests/test_v071_bridge_security.py -q -o addopts="" --timeout=30
```

### Tasks

| # | Task | Priority | Files | Status |
|---|------|----------|-------|--------|
| B1 | Create bridge threat model doc (Phase 0 prerequisite) | 🔴 P0 | `docs/architecture/bridge-threat-model.md` (new) | ⬜ |
| B2 | Add bridge security config fields + constants | 🔴 P0 | `apps/blockchain-node/src/aitbc_chain/config.py`, `aitbc/constants.py` | ⬜ |
| B3 | Add block header signature field + PoA signing/verification | 🔴 P0 | `apps/blockchain-node/src/aitbc_chain/base_models.py`, `apps/blockchain-node/src/aitbc_chain/consensus/poa.py` | ⬜ |
| B4 | Create BridgeValidator SQLModel table + validator set cache | 🔴 P0 | `apps/blockchain-node/src/aitbc_chain/base_models.py` (or new models file), `apps/blockchain-node/src/aitbc_chain/cross_chain/bridge.py` | ⬜ |
| B5 | Add validator RPC endpoints — register, get set, security status | 🔴 P0 | `apps/blockchain-node/src/aitbc_chain/rpc/bridge.py`, `apps/blockchain-node/src/aitbc_chain/rpc/router.py` | ⬜ |
| B6 | Upgrade bridge proof verification to multi-sig threshold | 🔴 P0 | `apps/blockchain-node/src/aitbc_chain/cross_chain/bridge.py` | ⬜ |
| B7 | Add CLI commands — security-status, register-validator | High | `cli/aitbc_cli/commands/bridge.py` | ⬜ |
| B8 | Integration tests + verify mypy/ruff/pytest clean | High | `apps/blockchain-node/tests/test_v071_bridge_security.py` (new) | ⬜ |

### Agent B — Detailed Instructions

#### B1: Threat Model Document

Create `docs/architecture/bridge-threat-model.md` — see Phase 0 section above for required content. This is a prerequisite for B6 (multi-sig implementation). Write it first, review it, then implement against it.

#### B2: Bridge Security Config + Constants

In `aitbc/constants.py`, add:
```python
# Bridge multi-sig defaults (v0.7.1)
BRIDGE_MULTISIG_DEFAULT_THRESHOLD = 3    # M-of-N: minimum signatures
BRIDGE_MULTISIG_DEFAULT_VALIDATORS = 5   # N: total validators
BRIDGE_MULTISIG_TIMEOUT = 3600           # seconds to collect signatures
BRIDGE_VALIDATOR_SET_GRACE_PERIOD = 7200 # seconds — old epoch valid during rotation
BRIDGE_BLOCK_SIGNATURE_REQUIRED = True   # require block header signatures
```

In `apps/blockchain-node/src/aitbc_chain/config.py`, add to `ChainSettings` (near existing `bridge_release_enabled` at line 285):
```python
    # Bridge multi-sig configuration (v0.7.1)
    bridge_multisig_enabled: bool = False          # require multi-sig for confirm
    bridge_multisig_threshold: int = 3             # M-of-N minimum signatures
    bridge_multisig_validators: int = 5            # N total validators
    bridge_multisig_timeout: int = 3600            # seconds to collect signatures
    bridge_validator_set_grace_period: int = 7200  # seconds — old epoch valid during rotation
    bridge_block_signature_required: bool = True   # require block header signatures
```

#### B3: Block Header Signatures

In `apps/blockchain-node/src/aitbc_chain/base_models.py`, add `signature` field to `Block` model (line 25-76):
```python
    # Block header signature (v0.7.1) — secp256k1 signature over the block hash
    # by the proposer. Empty for legacy blocks (pre-v0.7.1). Verified by PoA
    # consensus during block validation when bridge_block_signature_required=True.
    signature: str = ""
```

In `apps/blockchain-node/src/aitbc_chain/consensus/poa.py`:
- On block proposal: sign the block hash with the proposer's private key, set `block.signature`
- On block validation: when `bridge_block_signature_required=True`, verify `block.signature` recovers to `block.proposer` using `aitbc.crypto.crypto.recover_signer()`
- Backward compatibility: if `block.signature == ""`, skip verification (legacy block)

**Important**: The proposer's private key must be available to the PoA consensus. Check how the existing PoA gets its proposer identity — likely from config or env var. If the private key is not currently available to PoA, add a `proposer_private_key` config field (loaded from env var, never logged).

#### B4: BridgeValidator SQLModel Table

Create a `BridgeValidator` SQLModel table for persisting validator registrations:
```python
class BridgeValidator(SQLModel, table=True):
    """Bridge validator registration (v0.7.1)."""
    __tablename__ = "bridge_validators"

    id: int | None = Field(default=None, primary_key=True)
    chain_id: str = Field(index=True)           # chain this validator serves
    address: str = Field(index=True)            # checksum address
    public_key: str                             # secp256k1 public key hex
    epoch: int = Field(default=0, index=True)   # validator set epoch
    is_active: bool = Field(default=True)
    registered_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
```

Add a composite index on `(chain_id, epoch)` via `__table_args__` since the bridge queries by chain+epoch.

In `cross_chain/bridge.py`, add a `ValidatorSetCache` that loads from the `BridgeValidator` table into Agent A's `ValidatorSetRegistry` (from A3). The cache refreshes on epoch changes.

#### B5: Validator RPC Endpoints

In `rpc/bridge.py`, add three new endpoints:

1. **`POST /bridge/validators/register`** — Register a validator:
   - Request: `{chain_id, address, public_key, signature}` — signature proves ownership of the address
   - Verify signature recovers to `address`
   - Store in `BridgeValidator` table
   - Update `ValidatorSetCache`
   - Response: `{status: "registered", chain_id, address, epoch}`

2. **`GET /bridge/validators/{chain_id}`** — Get validator set:
   - Optional query param `epoch` (defaults to current)
   - Response: `{chain_id, epoch, threshold, total, validators: [{address, public_key, is_active}]}`

3. **`GET /bridge/security/status`** — Security status:
   - Response: `{multisig_enabled, threshold, validator_count, current_epoch, block_signature_required, release_enabled}`

Register these endpoints in `rpc/router.py`.

#### B6: Upgrade Bridge Proof Verification to Multi-Sig

This is the core security change. In `cross_chain/bridge.py`:

1. **Replace `_verify_proposer_signature`** (lines 477-523) with `_verify_threshold_signatures`:
   - When `bridge_multisig_enabled=True`: use Agent A's `verify_threshold_signatures()` from `aitbc.bridge.multisig`
   - When `bridge_multisig_enabled=False`: fall back to existing single-sig verification (backward compat)
   - The proof dict gains an optional `validator_signatures: list[str]` field

2. **Update `_validate_proof`** (lines 440-475) to call `_verify_threshold_signatures` instead of `_verify_proposer_signature`

3. **Update `confirm_transfer`** to check validator set exists for the source chain before proceeding. If no validator set is registered and `multisig_enabled=True`, reject with error.

4. **The `BRIDGE_RELEASE_ENABLED=false` fence stays** — multi-sig is an additional layer, not a replacement for the fence.

#### B7: CLI Commands

In `cli/aitbc_cli/commands/bridge.py`, add two new subcommands:

1. **`bridge security-status`** — calls `BridgeClient.security_status()`, displays:
   - Multi-sig enabled/disabled
   - Threshold (M-of-N)
   - Validator count
   - Current epoch per chain
   - Block signature requirement
   - Release fence status

2. **`bridge register-validator`** — calls `BridgeClient.register_validator()`:
   - Args: `--chain-id`, `--address`, `--public-key`, `--private-key` (for signing)
   - Signs the registration request with the private key
   - Submits to `/bridge/validators/register`

#### B8: Integration Tests

Create `apps/blockchain-node/tests/test_v071_bridge_security.py`:

- `test_block_header_signature_on_propose` — PoA signs block, signature field populated
- `test_block_header_signature_verification` — valid signature accepted
- `test_block_header_signature_invalid_rejected` — wrong signer rejected
- `test_block_header_signature_empty_legacy` — empty signature accepted (backward compat)
- `test_validator_registration` — register via RPC, verify in DB
- `test_validator_registration_invalid_signature` — bad signature rejected
- `test_get_validator_set` — get set by chain_id and epoch
- `test_validator_set_epoch_rotation` — advance epoch, old set retained for grace period
- `test_bridge_confirm_multisig_valid` — M-of-N valid sigs, confirm succeeds (if fence enabled)
- `test_bridge_confirm_multisig_insufficient` — below threshold, confirm rejected
- `test_bridge_confirm_multisig_non_member` — signer not in validator set, rejected
- `test_bridge_confirm_multisig_disabled_fallback` — multisig disabled, single sig works
- `test_bridge_confirm_release_fence` — confirm returns 503 when fence active
- `test_security_status_endpoint` — GET /bridge/security/status returns config
- `test_cli_security_status` — CLI command output
- `test_cli_register_validator` — CLI command submits registration

---

## Coordination

### Sequencing

1. **Phase 0** (B1): Threat model doc — Agent B writes first, either agent reviews
2. **Agent A** (A1-A4): Shared SDK extensions — can start immediately (extends v0.7.0 committed work)
3. **Agent B** (B2-B3): Config + block header signing — can start in parallel with Agent A
4. **Agent B** (B4-B5): Validator table + RPC — can start in parallel with Agent A
5. **Agent B** (B6): Multi-sig bridge upgrade — **WAITS for Agent A A2+A3** (needs `verify_threshold_signatures` + `ValidatorSetRegistry`)
6. **Agent B** (B7-B8): CLI + tests — waits for B5+B6

### v0.7.0 Agent B Commit

Agent B's v0.7.0 work (B1-B7) is currently uncommitted in the working tree:
- `aitbc/constants.py` (bridge constants)
- `apps/blockchain-node/src/aitbc_chain/config.py` (bridge config fields)
- `apps/blockchain-node/src/aitbc_chain/cross_chain/bridge.py` (refund_transfer method)
- `apps/blockchain-node/src/aitbc_chain/network/bridge_manager.py` (monitoring)
- `apps/blockchain-node/src/aitbc_chain/rpc/bridge.py` (5 new endpoints)
- `apps/blockchain-node/src/aitbc_chain/rpc/router.py` (endpoint registration)
- `cli/aitbc_cli/commands/bridge.py` (7 CLI commands)
- `cli/aitbc_cli/commands/node/bridge.py` (node bridge wiring)
- `apps/blockchain-node/tests/test_v070_bridge_basics.py` (new test file)

**Agent B must commit v0.7.0 work before starting v0.7.1.** The v0.7.0 AGENTS.md status column also needs updating (currently shows ⬜ for all B tasks, but code inspection confirms B1-B4, B6 are done).

### Shared Files

No shared files are touched by both agents in v0.7.1. Agent A owns `aitbc/bridge/` exclusively. Agent B owns `apps/`, `cli/`, and `aitbc/constants.py` exclusively. The only cross-dependency is Agent B importing from Agent A's `aitbc.bridge` package (B6 imports `verify_threshold_signatures`, `ValidatorSetRegistry`).
