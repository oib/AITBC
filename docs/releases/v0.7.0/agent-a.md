# v0.7.0 Cross-Chain Bridge Basics — Agent A Tasks

**Last Updated**: 2026-06-30
**Version**: 1.0

**Agent**: Agent A (Shared Core)

**Scope**: Create (1) a shared bridge client SDK with types, (2) proof generation/validation utilities. Both are consumed by Agent B's CLI and blockchain-node work.

**Working directory**: `/opt/aitbc/aitbc/bridge/`

**Verification command**:
```bash
cd /opt/aitbc && ./venv/bin/python -m mypy --show-error-codes aitbc/bridge/ && ./venv/bin/python -m ruff check aitbc/bridge/ tests/unit/test_bridge_sdk.py && ./venv/bin/python -m pytest tests/unit/test_bridge_sdk.py -q -o addopts=""
```

---

## Tasks

| # | Task | Priority | Files | Status |
|---|------|----------|-------|--------|
| A1 | Create `aitbc/bridge/` package — BridgeClient (HTTP client), bridge types (BridgeStatus, BridgeTransfer, BridgeProof, BridgeConfig) | 🔴 P0 | `aitbc/bridge/__init__.py` (new), `aitbc/bridge/types.py` (new), `aitbc/bridge/client.py` (new) | ✅ |
| A2 | Create `aitbc/bridge/proof.py` — proof generation + basic validation utilities using `aitbc/crypto/crypto.py` | 🔴 P0 | `aitbc/bridge/proof.py` (new) | ✅ |
| A3 | Unit tests for A1-A2 + verify mypy/ruff/pytest clean | High | `tests/unit/test_bridge_sdk.py` (new) | ✅ |

---

## A1: BridgeClient + Bridge Types

Create `aitbc/bridge/__init__.py`, `aitbc/bridge/types.py`, and `aitbc/bridge/client.py`.

**`aitbc/bridge/types.py`** — Shared bridge dataclasses (mirror the existing types in `cross_chain/bridge.py` but as standalone shared types):

```python
"""Shared bridge types for cross-chain transfers (v0.7.0 §A1)."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum


class BridgeStatus(str, Enum):
    """Status of a cross-chain bridge transfer."""
    PENDING = "pending"
    LOCKED = "locked"
    CONFIRMED = "confirmed"
    COMPLETED = "completed"
    FAILED = "failed"
    REFUNDED = "refunded"


@dataclass
class BridgeTransfer:
    """A cross-chain bridge transfer record."""
    transfer_id: str
    source_chain: str
    target_chain: str
    sender: str
    recipient: str
    amount: int  # in compute-seconds (1 AIT = 3600)
    asset: str = "native"
    status: BridgeStatus = BridgeStatus.PENDING
    source_tx_hash: str | None = None
    target_tx_hash: str | None = None
    lock_time: datetime | None = None
    confirm_time: datetime | None = None
    fee: int = 0


@dataclass
class BridgeProof:
    """Proof that a lock occurred on the source chain.

    Required fields for basic validation (v0.7.0):
    - source_chain, lock_tx_hash, amount, sender, recipient, chain_id
    - block_height, block_hash, proposer_signature

    Full Merkle proof verification deferred to v0.7.2.
    """
    source_chain: str
    lock_tx_hash: str
    amount: int
    sender: str
    recipient: str
    chain_id: str
    block_height: int
    block_hash: str
    proposer_signature: str


@dataclass
class BridgeConfig:
    """Configuration for bridge operations."""
    rpc_url: str = "http://localhost:8202"
    chain_id: str = "ait-hub"
    timeout: int = 30
    retry_limit: int = 3
    fee_basis_points: int = 10  # 0.1%
    batch_size: int = 10
```

**`aitbc/bridge/client.py`** — HTTP client for bridge RPC endpoints:

```python
"""Bridge RPC client for cross-chain operations (v0.7.0 §A1).

HTTP client that wraps the blockchain-node bridge RPC endpoints.
Used by the CLI and other services to interact with the bridge.
"""

from __future__ import annotations

import logging
from typing import Any

import httpx

from .types import BridgeConfig, BridgeStatus, BridgeTransfer

logger = logging.getLogger(__name__)


class BridgeClient:
    """HTTP client for blockchain-node bridge RPC endpoints.

    Wraps the following endpoints:
    - POST /bridge/lock — lock funds for cross-chain transfer
    - POST /bridge/confirm — confirm and release bridged funds
    - POST /bridge/unlock — refund/cancel a pending transfer
    - GET /bridge/transfer/{transfer_id} — get transfer status
    - GET /bridge/pending — list pending transfers
    - GET /bridge/balance/{chain_id} — get bridge balance per chain
    - GET /bridge/health — bridge health check
    - POST /bridge/batch/lock — batch lock
    - POST /bridge/batch/confirm — batch confirm
    """

    def __init__(self, config: BridgeConfig | None = None) -> None:
        self._config = config or BridgeConfig()
        self._client: httpx.AsyncClient | None = None

    async def __aenter__(self) -> BridgeClient:
        self._client = httpx.AsyncClient(
            base_url=self._config.rpc_url,
            timeout=self._config.timeout,
        )
        return self

    async def __aexit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        if self._client:
            await self._client.aclose()
            self._client = None

    def _ensure_client(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(
                base_url=self._config.rpc_url,
                timeout=self._config.timeout,
            )
        return self._client

    async def lock(
        self, target_chain: str, sender: str, recipient: str,
        amount: int, asset: str = "native", signature: str = "",
        source_chain: str | None = None,
    ) -> dict[str, Any]:
        """Lock funds for a cross-chain transfer."""
        payload: dict[str, Any] = {
            "target_chain": target_chain,
            "sender": sender,
            "recipient": recipient,
            "amount": amount,
            "asset": asset,
            "signature": signature,
        }
        if source_chain:
            payload["source_chain"] = source_chain
        resp = await self._ensure_client().post("/bridge/lock", json=payload)
        resp.raise_for_status()
        return resp.json()

    async def confirm(
        self, transfer_id: str, proof: dict[str, Any],
        confirmer: str, signature: str,
    ) -> dict[str, Any]:
        """Confirm and release a bridged transfer."""
        payload = {
            "transfer_id": transfer_id,
            "proof": proof,
            "confirmer": confirmer,
            "signature": signature,
        }
        resp = await self._ensure_client().post("/bridge/confirm", json=payload)
        resp.raise_for_status()
        return resp.json()

    async def unlock(
        self, transfer_id: str, sender: str, signature: str,
    ) -> dict[str, Any]:
        """Refund/cancel a pending bridge transfer."""
        payload = {
            "transfer_id": transfer_id,
            "sender": sender,
            "signature": signature,
        }
        resp = await self._ensure_client().post("/bridge/unlock", json=payload)
        resp.raise_for_status()
        return resp.json()

    async def get_transfer(self, transfer_id: str) -> dict[str, Any]:
        """Get transfer status by ID."""
        resp = await self._ensure_client().get(f"/bridge/transfer/{transfer_id}")
        resp.raise_for_status()
        return resp.json()

    async def list_pending(self, chain_id: str | None = None) -> list[dict[str, Any]]:
        """List pending bridge transfers."""
        params = {"chain_id": chain_id} if chain_id else {}
        resp = await self._ensure_client().get("/bridge/pending", params=params)
        resp.raise_for_status()
        return resp.json()

    async def get_balance(self, chain_id: str) -> dict[str, Any]:
        """Get bridge balance for a chain."""
        resp = await self._ensure_client().get(f"/bridge/balance/{chain_id}")
        resp.raise_for_status()
        return resp.json()

    async def health(self) -> dict[str, Any]:
        """Check bridge health."""
        resp = await self._ensure_client().get("/bridge/health")
        resp.raise_for_status()
        return resp.json()

    async def batch_lock(
        self, transfers: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        """Batch lock multiple transfers."""
        resp = await self._ensure_client().post(
            "/bridge/batch/lock", json={"transfers": transfers}
        )
        resp.raise_for_status()
        return resp.json()

    async def batch_confirm(
        self, confirmations: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        """Batch confirm multiple transfers."""
        resp = await self._ensure_client().post(
            "/bridge/batch/confirm", json={"confirmations": confirmations}
        )
        resp.raise_for_status()
        return resp.json()

    async def close(self) -> None:
        """Close the HTTP client."""
        if self._client:
            await self._client.aclose()
            self._client = None
```

**`aitbc/bridge/__init__.py`** — re-exports:
```python
from .client import BridgeClient
from .types import BridgeConfig, BridgeProof, BridgeStatus, BridgeTransfer

__all__ = [
    "BridgeClient",
    "BridgeConfig",
    "BridgeProof",
    "BridgeStatus",
    "BridgeTransfer",
]
```

---

## A2: Proof Utilities

Create `aitbc/bridge/proof.py` — proof generation and basic validation. This is the "bridge SDK" proof layer. It uses `aitbc/crypto/crypto.py` `recover_signer()` for signature verification but does NOT implement Merkle proof verification (deferred to v0.7.2).

```python
"""Bridge proof generation and validation utilities (v0.7.0 §A2).

Basic proof validation: field equality, chain_id check, block anchor
format, proposer signature format verification.

Full Merkle proof verification + proposer-set membership checking
is deferred to v0.7.2.
"""

from __future__ import annotations

import logging
from typing import Any

from aitbc.crypto.crypto import recover_signer

from .types import BridgeProof, BridgeTransfer

logger = logging.getLogger(__name__)

REQUIRED_PROOF_FIELDS = [
    "source_chain",
    "lock_tx_hash",
    "amount",
    "sender",
    "recipient",
    "chain_id",
    "block_height",
    "block_hash",
    "proposer_signature",
]


def build_lock_proof(
    source_chain: str,
    lock_tx_hash: str,
    amount: int,
    sender: str,
    recipient: str,
    chain_id: str,
    block_height: int,
    block_hash: str,
    proposer_signature: str,
) -> BridgeProof:
    """Build a BridgeProof from lock event fields."""
    return BridgeProof(
        source_chain=source_chain,
        lock_tx_hash=lock_tx_hash,
        amount=amount,
        sender=sender,
        recipient=recipient,
        chain_id=chain_id,
        block_height=block_height,
        block_hash=block_hash,
        proposer_signature=proposer_signature,
    )


def validate_proof_fields(proof: BridgeProof, transfer: BridgeTransfer) -> list[str]:
    """Validate proof fields against a transfer record.

    Returns a list of error messages (empty if valid).
    Does NOT verify proposer-set membership (deferred to v0.7.2).
    """
    errors: list[str] = []

    if proof.source_chain != transfer.source_chain:
        errors.append(f"source_chain mismatch: proof={proof.source_chain} vs transfer={transfer.source_chain}")
    if proof.amount != transfer.amount:
        errors.append(f"amount mismatch: proof={proof.amount} vs transfer={transfer.amount}")
    if proof.sender != transfer.sender:
        errors.append(f"sender mismatch: proof={proof.sender} vs transfer={transfer.sender}")
    if proof.recipient != transfer.recipient:
        errors.append(f"recipient mismatch: proof={proof.recipient} vs transfer={transfer.recipient}")

    # Block anchor validation
    if proof.block_height < 0:
        errors.append(f"block_height must be non-negative, got {proof.block_height}")
    if not proof.block_hash:
        errors.append("block_hash must be non-empty")

    # Signature format validation
    if not proof.proposer_signature:
        errors.append("proposer_signature must be non-empty")
    elif not proof.proposer_signature.startswith("0x"):
        errors.append("proposer_signature must be hex-encoded with 0x prefix")

    return errors


def verify_proposer_signature(proof: BridgeProof) -> str | None:
    """Verify the proposer signature and return the recovered address.

    Uses aitbc.crypto.crypto.recover_signer() for secp256k1 verification.

    Returns:
        Recovered signer address if valid, None if invalid.

    Note: This does NOT check proposer-set membership. The recovered
    address could be any valid secp256k1 signer. Full proposer-set
    verification is deferred to v0.7.2.
    """
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
    return recover_signer(message_data, proof.proposer_signature)


def proof_to_dict(proof: BridgeProof) -> dict[str, Any]:
    """Convert a BridgeProof to a dict for RPC transmission."""
    return {
        "source_chain": proof.source_chain,
        "lock_tx_hash": proof.lock_tx_hash,
        "amount": proof.amount,
        "sender": proof.sender,
        "recipient": proof.recipient,
        "chain_id": proof.chain_id,
        "block_height": proof.block_height,
        "block_hash": proof.block_hash,
        "proposer_signature": proof.proposer_signature,
    }


def dict_to_proof(data: dict[str, Any]) -> BridgeProof:
    """Parse a BridgeProof from a dict (e.g., from RPC response)."""
    return BridgeProof(
        source_chain=data["source_chain"],
        lock_tx_hash=data["lock_tx_hash"],
        amount=data["amount"],
        sender=data["sender"],
        recipient=data["recipient"],
        chain_id=data["chain_id"],
        block_height=data["block_height"],
        block_hash=data["block_hash"],
        proposer_signature=data["proposer_signature"],
    )
```

---

## A3: Unit Tests

**`tests/unit/test_bridge_sdk.py`**:
- `test_bridge_status_values` — enum values match expected strings
- `test_bridge_transfer_defaults` — default field values
- `test_bridge_proof_dataclass` — all required fields
- `test_bridge_config_defaults` — default config values
- `test_bridge_client_init` — BridgeClient initializes with default config
- `test_bridge_client_custom_config` — BridgeClient with custom config
- `test_build_lock_proof` — proof construction
- `test_validate_proof_fields_valid` — no errors for matching proof+transfer
- `test_validate_proof_fields_source_chain_mismatch` — detects mismatch
- `test_validate_proof_fields_amount_mismatch` — detects mismatch
- `test_validate_proof_fields_sender_mismatch` — detects mismatch
- `test_validate_proof_fields_recipient_mismatch` — detects mismatch
- `test_validate_proof_fields_negative_block_height` — detects invalid height
- `test_validate_proof_fields_empty_block_hash` — detects empty hash
- `test_validate_proof_fields_empty_signature` — detects empty sig
- `test_validate_proof_fields_non_hex_signature` — detects non-0x prefix
- `test_proof_to_dict` — serialization round-trip
- `test_dict_to_proof` — deserialization
- `test_proof_roundtrip` — dict → proof → dict equality
- `test_package_reexport` — all names exported from aitbc.bridge

---

## Related Topics

- [Overview](./overview.md) - Release overview and status baseline
- [Agent B Tasks](./agent-b.md) - Apps & infrastructure implementation details

---

**Documentation Version**: 1.0
**Last Updated**: 2026-06-30
**Release**: v0.7.0 — Cross-Chain Bridge Basics
**Agent**: Agent A (Shared Core)
