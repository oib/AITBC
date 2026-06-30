# v0.7.2 Bridge Verification — Agent A Tasks

**Last Updated**: 2026-06-30
**Version**: 1.0

**Agent**: Agent A (Shared Core)

**Scope**: Extend the bridge SDK with oracle client interface, verification types, and block header/finality validation utilities. These are dependency-free shared types that Agent B's blockchain node implementation consumes.

**Working directory**: `/opt/aitbc/aitbc/bridge/`

**Prerequisite**: v0.7.1 Agent A ✅ (committed `1fcf1e829`). v0.7.1 Agent B ✅ (committed `a4ea61295` — provides `BridgeValidator` table + block header `signature` field that the types mirror).

**Verification command**:
```bash
cd /opt/aitbc && ./venv/bin/python -m mypy --show-error-codes aitbc/bridge/ && ./venv/bin/python -m ruff check aitbc/bridge/ tests/unit/test_bridge_verification.py && ./venv/bin/python -m pytest tests/unit/test_bridge_verification.py tests/unit/test_bridge_security.py tests/unit/test_bridge_sdk.py -q -o addopts=""
```

---

## Tasks

| # | Task | Priority | Files | Status |
|---|------|----------|-------|--------|
| A1 | Extend bridge types — BridgeBlockHeader, FinalityConfig, ProofVerificationResult, VerificationMode enum | 🔴 P0 | `aitbc/bridge/types.py` (extend), `aitbc/bridge/__init__.py` (extend) | ✅ |
| A2 | Create `aitbc/bridge/oracle.py` — OracleClient ABC, InProcessVerifier, ExternalOracleClient stub | 🔴 P0 | `aitbc/bridge/oracle.py` (new), `aitbc/bridge/__init__.py` (extend) | ✅ |
| A3 | Create `aitbc/bridge/verification.py` — block header validation, finality check, verification message builder | 🔴 P0 | `aitbc/bridge/verification.py` (new), `aitbc/bridge/__init__.py` (extend) | ✅ |
| A4 | Extend BridgeClient with block header + oracle status RPC methods + unit tests for A1-A3 | High | `aitbc/bridge/client.py` (extend), `tests/unit/test_bridge_verification.py` (new) | ✅ |

---

## A1: Extend Bridge Types

Extend `aitbc/bridge/types.py` with verification-related types.

**New dataclasses**:

```python
class VerificationMode(StrEnum):
    """Bridge proof verification mode."""
    IN_PROCESS = "in_process"  # default — use local Merkle trie
    ORACLE = "oracle"          # future — external oracle (stub only in v0.7.2)


@dataclass
class BridgeBlockHeader:
    """A block header from a remote (source) chain.

    Used to anchor bridge proofs — the Merkle proof is verified against
    ``state_root``, and the block header's proposer signature is verified
    against the validator set (v0.7.1).
    """
    chain_id: str
    height: int
    hash: str
    parent_hash: str
    proposer: str               # proposer address
    state_root: str             # state root at this block
    signature: str = ""         # proposer signature (v0.7.1 field)
    timestamp: datetime | None = None
    finality_confirmed: bool = False  # set when finality threshold met
    confirmation_count: int = 0       # number of confirmations seen


@dataclass
class FinalityConfig:
    """Configuration for block finality tracking."""
    min_confirmations: int = 3          # minimum confirmations for any transfer
    finality_blocks: int = 6            # full finality threshold
    large_transfer_threshold: int = 10000  # transfers above this require full finality
    grace_period_seconds: int = 3600    # validator set transition grace period


@dataclass
class ProofVerificationResult:
    """Result of a bridge proof verification attempt."""
    valid: bool
    error: str = ""
    block_height: int = 0
    state_root: str = ""
    finality_confirmed: bool = False
    validator_epoch: int = 0
    verification_mode: VerificationMode = VerificationMode.IN_PROCESS
```

Update `aitbc/bridge/__init__.py` to re-export `BridgeBlockHeader`, `FinalityConfig`, `ProofVerificationResult`, `VerificationMode`.

---

## A2: Oracle Client Interface

Create `aitbc/bridge/oracle.py` — abstract oracle client interface with in-process default and external stub.

```python
"""Bridge oracle client interface (v0.7.2 §A2).

Abstract interface for bridge proof verification. The default
implementation (InProcessVerifier) uses local cryptographic verification
(Merkle proofs + block header signatures). A stub ExternalOracleClient
is included for future external oracle integration (deferred to v0.8.x+).

The InProcessVerifier delegates Merkle proof verification to a callable
provided by the blockchain node (which has access to the Merkle Patricia
Trie). This keeps the shared SDK dependency-free — the actual trie
verification happens in apps/blockchain-node/.
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from typing import Any, Callable, Protocol

from .types import (
    BridgeBlockHeader,
    FinalityConfig,
    ProofVerificationResult,
    VerificationMode,
)

logger = logging.getLogger(__name__)


class MerkleProofVerifier(Protocol):
    """Protocol for Merkle proof verification (implemented by blockchain node)."""

    def verify_merkle_proof(
        self,
        state_root: str,
        key: str,
        value: str,
        proof: list[bytes],
    ) -> bool:
        """Verify a Merkle proof against a state root."""
        ...


class OracleClient(ABC):
    """Abstract base class for bridge proof verification oracles."""

    @abstractmethod
    def verify_proof(
        self,
        proof: dict[str, Any],
        block_header: BridgeBlockHeader,
        finality_config: FinalityConfig,
    ) -> ProofVerificationResult:
        """Verify a bridge proof against a block header."""
        ...

    @abstractmethod
    def check_finality(
        self,
        block_header: BridgeBlockHeader,
        finality_config: FinalityConfig,
        transfer_amount: int,
    ) -> bool:
        """Check if a block header has sufficient finality for a transfer."""
        ...

    @property
    @abstractmethod
    def mode(self) -> VerificationMode:
        """The verification mode of this oracle."""
        ...


class InProcessVerifier(OracleClient):
    """Default in-process verification using local cryptographic primitives.

    Delegates Merkle proof verification to a MerkleProofVerifier callable
    provided by the blockchain node. Block header signature verification
    uses aitbc.bridge.multisig utilities.
    """

    def __init__(
        self,
        merkle_verifier: MerkleProofVerifier | None = None,
    ) -> None:
        self._merkle_verifier = merkle_verifier

    @property
    def mode(self) -> VerificationMode:
        return VerificationMode.IN_PROCESS

    def verify_proof(
        self,
        proof: dict[str, Any],
        block_header: BridgeBlockHeader,
        finality_config: FinalityConfig,
    ) -> ProofVerificationResult:
        """Verify a bridge proof in-process."""
        # 1. Verify block header state root matches proof
        # 2. Verify Merkle proof (if merkle_verifier is set)
        # 3. Check finality
        # 4. Return result
        ...

    def check_finality(
        self,
        block_header: BridgeBlockHeader,
        finality_config: FinalityConfig,
        transfer_amount: int,
    ) -> bool:
        """Check finality — large transfers require full finality."""
        threshold = (
            finality_config.finality_blocks
            if transfer_amount >= finality_config.large_transfer_threshold
            else finality_config.min_confirmations
        )
        return block_header.confirmation_count >= threshold


class ExternalOracleClient(OracleClient):
    """Stub for future external oracle integration.

    NOT IMPLEMENTED in v0.7.2. Raises NotImplementedError if used.
    External oracle integration is deferred to v0.8.x or v0.9.x when
    oracle infrastructure is actually deployed.
    """

    def __init__(self, endpoint: str = "") -> None:
        self._endpoint = endpoint
        logger.warning("ExternalOracleClient is a stub — not implemented in v0.7.2")

    @property
    def mode(self) -> VerificationMode:
        return VerificationMode.ORACLE

    def verify_proof(
        self,
        proof: dict[str, Any],
        block_header: BridgeBlockHeader,
        finality_config: FinalityConfig,
    ) -> ProofVerificationResult:
        raise NotImplementedError("External oracle integration deferred to v0.8.x+")

    def check_finality(
        self,
        block_header: BridgeBlockHeader,
        finality_config: FinalityConfig,
        transfer_amount: int,
    ) -> bool:
        raise NotImplementedError("External oracle integration deferred to v0.8.x+")
```

---

## A3: Verification Utilities

Create `aitbc/bridge/verification.py` — block header validation and finality checking utilities.

```python
"""Bridge verification utilities (v0.7.2 §A3).

Block header signature validation and finality threshold checking.
These utilities are used by the InProcessVerifier and by the blockchain
node's bridge proof verification path.
"""

from __future__ import annotations

import logging
from typing import Any

from aitbc.crypto.crypto import recover_signer

from .types import BridgeBlockHeader, FinalityConfig, ValidatorSet

logger = logging.getLogger(__name__)


def build_verification_message(header: BridgeBlockHeader) -> dict[str, Any]:
    """Build the canonical message dict that a block header proposer signs.

    This is the block header without the signature field. Key ordering
    does not matter — recover_signer re-serializes with sort_keys=True.
    """
    return {
        "chain_id": header.chain_id,
        "height": header.height,
        "hash": header.hash,
        "parent_hash": header.parent_hash,
        "proposer": header.proposer,
        "state_root": header.state_root,
    }


def validate_block_header(
    header: BridgeBlockHeader,
    validator_set: ValidatorSet | None = None,
) -> tuple[bool, str, str | None]:
    """Validate a block header's proposer signature.

    Args:
        header: The block header to validate.
        validator_set: Optional validator set for membership check.
            If provided, the recovered signer must be a member.

    Returns:
        (valid, error_message, recovered_address)
    """
    if not header.signature:
        return False, "Block header has no signature", None

    message_data = build_verification_message(header)
    recovered = recover_signer(message_data, header.signature)
    if recovered is None:
        return False, "Invalid block header signature", None

    if validator_set is not None:
        if recovered not in validator_set.addresses:
            return False, f"Signer {recovered} not in validator set", recovered

    return True, "", recovered


def check_finality(
    header: BridgeBlockHeader,
    config: FinalityConfig,
    transfer_amount: int,
) -> tuple[bool, int]:
    """Check if a block header has sufficient finality for a transfer.

    Large transfers (>= config.large_transfer_threshold) require full
    finality (config.finality_blocks confirmations). Small transfers
    require only config.min_confirmations.

    Returns:
        (has_finality, required_confirmations)
    """
    required = (
        config.finality_blocks
        if transfer_amount >= config.large_transfer_threshold
        else config.min_confirmations
    )
    return header.confirmation_count >= required, required
```

---

## A4: BridgeClient Extensions + Unit Tests

Extend `aitbc/bridge/client.py` with block header and oracle status RPC methods:

```python
async def get_block_header(self, chain_id: str, height: int) -> dict[str, Any]:
    """Get a remote chain block header."""
    resp = await self._ensure_client().get(f"/bridge/block-headers/{chain_id}/{height}")
    resp.raise_for_status()
    return cast(dict[str, Any], resp.json())

async def oracle_status(self) -> dict[str, Any]:
    """Get bridge oracle/verification status."""
    resp = await self._ensure_client().get("/bridge/oracle/status")
    resp.raise_for_status()
    return cast(dict[str, Any], resp.json())
```

**`tests/unit/test_bridge_verification.py`** — unit tests for A1-A4:
- `test_bridge_block_header_dataclass` — all fields
- `test_bridge_block_header_defaults` — signature="", finality_confirmed=False
- `test_finality_config_defaults` — min_confirmations=3, finality_blocks=6, etc.
- `test_proof_verification_result_defaults` — valid=False, verification_mode=IN_PROCESS
- `test_verification_mode_enum` — IN_PROCESS, ORACLE values
- `test_in_process_verifier_mode` — returns IN_PROCESS
- `test_in_process_verifier_check_finality_small_transfer` — min_confirmations threshold
- `test_in_process_verifier_check_finality_large_transfer` — finality_blocks threshold
- `test_external_oracle_client_stub_raises` — NotImplementedError on verify_proof
- `test_external_oracle_client_mode` — returns ORACLE
- `test_oracle_client_is_abstract` — cannot instantiate OracleClient directly
- `test_build_verification_message` — correct fields, no signature
- `test_validate_block_header_valid` — valid sig, no validator set
- `test_validate_block_header_with_validator_set` — valid sig + member
- `test_validate_block_header_non_member` — valid sig but not in set
- `test_validate_block_header_no_signature` — empty signature rejected
- `test_validate_block_header_invalid_signature` — recover_signer returns None
- `test_check_finality_meets_threshold` — enough confirmations
- `test_check_finality_below_threshold` — insufficient confirmations
- `test_check_finality_large_transfer_requires_more` — large transfer needs finality_blocks
- `test_bridge_client_get_block_header` — mocked RPC
- `test_bridge_client_oracle_status` — mocked RPC
- `test_package_reexport_verification` — new names exported from aitbc.bridge

---

## Related Topics

- [Overview](./overview.md) - Release overview and status baseline
- [Agent B Tasks](./agent-b.md) - Apps & infrastructure implementation details

---

**Documentation Version**: 1.0
**Last Updated**: 2026-06-30
**Release**: v0.7.2 — Bridge Verification
**Agent**: Agent A (Shared Core)
