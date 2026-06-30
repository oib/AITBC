# v0.7.1 Bridge Security Layer — Agent A Tasks

**Last Updated**: 2026-06-30
**Version**: 1.0

**Agent**: Agent A (Shared Core)

**Scope**: Extend the v0.7.0 bridge SDK with multi-sig types, threshold signature verification utilities, and validator set registry utilities. All consumed by Agent B's blockchain-node and CLI work.

**Working directory**: `/opt/aitbc/aitbc/bridge/`

**Verification command**:
```bash
cd /opt/aitbc && ./venv/bin/python -m mypy --show-error-codes aitbc/bridge/ && ./venv/bin/python -m ruff check aitbc/bridge/ tests/unit/test_bridge_security.py && ./venv/bin/python -m pytest tests/unit/test_bridge_security.py tests/unit/test_bridge_sdk.py -q -o addopts=""
```

---

## Tasks

| # | Task | Priority | Files | Status |
|---|------|----------|-------|--------|
| A1 | Extend bridge types — add ValidatorInfo, ValidatorSet, ThresholdProof; add `validator_signatures` field to BridgeProof | 🔴 P0 | `aitbc/bridge/types.py` (extend), `aitbc/bridge/__init__.py` (extend) | ✅ |
| A2 | Create `aitbc/bridge/multisig.py` — threshold signature verification (M-of-N secp256k1) | 🔴 P0 | `aitbc/bridge/multisig.py` (new), `aitbc/bridge/__init__.py` (extend) | ✅ |
| A3 | Create `aitbc/bridge/validators.py` — ValidatorSetRegistry with epoch tracking | 🔴 P0 | `aitbc/bridge/validators.py` (new), `aitbc/bridge/__init__.py` (extend) | ✅ |
| A4 | Extend BridgeClient with validator RPC methods + unit tests for A1-A3 | High | `aitbc/bridge/client.py` (extend), `tests/unit/test_bridge_security.py` (new) | ✅ |

---

## A1: Extend Bridge Types

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

---

## A2: Multi-Sig Utilities

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

---

## A3: Validator Set Registry

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

---

## A4: BridgeClient Extensions + Unit Tests

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

## Related Topics

- [Overview](./overview.md) - Release overview and status baseline
- [Agent B Tasks](./agent-b.md) - Apps & infrastructure implementation details

---

**Documentation Version**: 1.0
**Last Updated**: 2026-06-30
**Release**: v0.7.1 — Bridge Security Layer
**Agent**: Agent A (Shared Core)
