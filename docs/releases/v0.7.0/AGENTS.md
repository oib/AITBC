# v0.7.0 — Agent Task Assignment

**Release Theme**: Cross-Chain Bridge Basics — Lock/Unlock, RPC, Simple Transfers, Monitoring

**Goal**: Complete the foundational cross-chain bridge infrastructure in blockchain-node. The core bridge logic already exists (`cross_chain/bridge.py` — 401 lines, lock/confirm flow, partial proof validation). This release adds the missing pieces: refund/unlock endpoint, bridge balance query, bridge health monitoring, CLI command fixes, batch operations, and a shared bridge client SDK in `aitbc/bridge/`.

> **Scope constraint**: This release targets bridge **basics** only — lock/unlock RPC, simple transfers, monitoring, CLI. It does NOT add multi-sig validation, time-locks, cross-chain signature verification (v0.7.1), or Merkle proof verification / proposer-set tracking / block header signatures (v0.7.2). The existing `BRIDGE_RELEASE_ENABLED=false` fence remains in place — the confirm/release path stays gated until v0.7.2 completes full cryptographic verification.

> **Prerequisites**: [v0.6.0](../v0.6.0/change.log) ✅, [v0.6.1](../v0.6.1/change.log) ✅, [v0.6.3](../v0.6.3/change.log) ✅, [v0.6.4](../v0.6.4/change.log) ✅, [v0.5.16](../v0.5.16/change.log) ✅. All technical prerequisites complete. v0.6.6/v0.6.7 (product track) are in progress but touch different code (marketplace/pool-hub) — no file conflicts with bridge work.

> **Risk**: Low-Medium. The bridge core already exists and is tested (401-line test suite). This release adds missing endpoints and monitoring — it does not change the proof validation logic. The `BRIDGE_RELEASE_ENABLED=false` fence prevents unauthorized fund release until v0.7.2.

---

## Status Baseline — Verified Code Targets (from subagent investigation, 2026-06-29)

| Component | Location | Current State | v0.7.0 Target |
|-----------|----------|---------------|---------------|
| **Bridge core** | `apps/blockchain-node/src/aitbc_chain/cross_chain/bridge.py` (401 lines) | ✅ EXISTS — `CrossChainBridge` with `initiate_transfer()`, `confirm_transfer()`, `get_transfer()`, `list_pending_transfers()`, `_validate_proof()` (partial), `_verify_proposer_signature()` (accepts any valid sig) | No change to proof logic. Add `refund_transfer()` method for unlock/cancel. |
| **BridgeStatus enum** | `cross_chain/bridge.py:27-36` | ✅ EXISTS — pending, locked, confirmed, completed, failed, refunded | No change needed |
| **BridgeTransfer dataclass** | `cross_chain/bridge.py:38-55` | ✅ EXISTS — transfer_id, source_chain, target_chain, sender, recipient, amount, asset, status, source/target_tx_hash, lock/confirm_time, proof | No change needed |
| **CrossChainTransfer table** | `base_models.py:193-211` | ✅ EXISTS — SQLModel with transfer_id PK, indexed source/target_chain, sender, recipient, status | No change needed |
| **Bridge RPC — lock** | `rpc/bridge.py:18-88` | ✅ EXISTS — `POST /bridge/lock` with signature validation (Bug 7 fix) | No change needed |
| **Bridge RPC — confirm** | `rpc/bridge.py:90-152` | ✅ EXISTS — `POST /bridge/confirm`, gated by `BRIDGE_RELEASE_ENABLED` | No change needed |
| **Bridge RPC — transfer status** | `rpc/bridge.py:154-186` | ✅ EXISTS — `GET /bridge/transfer/{transfer_id}` | Add `/bridge/status/{transfer_id}` alias |
| **Bridge RPC — pending** | `rpc/bridge.py:188-216` | ✅ EXISTS — `GET /bridge/pending?chain_id=` | No change needed |
| **Bridge RPC — unlock** | — | ❌ MISSING — no refund/cancel endpoint | Add `POST /bridge/unlock` for refunding pending transfers |
| **Bridge RPC — balance** | — | ❌ MISSING — no bridge balance query | Add `GET /bridge/balance/{chain_id}` |
| **Bridge RPC — health** | — | ❌ MISSING — no health check endpoint | Add `GET /bridge/health` |
| **Bridge RPC — batch** | — | ❌ MISSING — no batch operations | Add `POST /bridge/batch/lock`, `POST /bridge/batch/confirm` |
| **Bridge manager** | `network/bridge_manager.py` (270 lines) | ✅ EXISTS — island-to-island connection management (request/approve/establish/terminate), in-memory only | Add health monitoring, stuck transfer detection, metrics collection |
| **Bridge config** | `config.py:223,252,284-290` | ⚠️ PARTIAL — `bridge_islands`, `bridge_request_monitor_interval`, `bridge_release_enabled` only | Add `bridge_timeout`, `bridge_retry_limit`, `bridge_fee_basis_points`, `bridge_supported_chains`, `bridge_batch_size`, `bridge_monitor_interval` |
| **Bridge tests** | `tests/test_bridge_suite.py` (401 lines) | ✅ EXISTS — proof verification, lock/confirm endpoints, lifecycle, cross-chain contamination | Add tests for unlock, balance, health, batch, monitoring |
| **CLI bridge commands** | `cli/aitbc_cli/commands/bridge.py` (78 lines) | ❌ BROKEN — calls non-existent `/rpc/bridge/start`, `/status`, `/stop` endpoints. Falls back to simulated data. | Replace with actual endpoints: `bridge lock`, `bridge confirm`, `bridge unlock`, `bridge status`, `bridge pending`, `bridge balance`, `bridge health` |
| **CLI node bridge** | `cli/aitbc_cli/commands/node/bridge.py` (52 lines) | ❌ STUBS — `request`, `approve`, `reject`, `list-bridges` all return simulated data | Wire to actual `/islands/bridge` + bridge_manager RPC |
| **Bridge constants** | `aitbc/constants.py` | ❌ NONE — no bridge-specific constants | Add bridge constants (fee default, timeout default, retry limit) |
| **Shared bridge SDK** | — | ❌ NONE — no shared bridge client library | Create `aitbc/bridge/` package with BridgeClient, types, proof utilities |
| **Block header signatures** | `base_models.py:25-76` | ❌ NOT IMPLEMENTED — `proposer` field is address string, no signature field | DEFERRED to v0.7.1 (adds block signing) |
| **Proposer-set tracking** | — | ❌ NONE — `_verify_proposer_signature` accepts any valid signer | DEFERRED to v0.7.2 (full proposer-set verification) |
| **Merkle proof verification** | `state/merkle_patricia_trie.py:73-121` | ✅ EXISTS — `verify_proof(key, value, proof)` ready | DEFERRED to v0.7.2 (bridge uses it for state proofs) |
| **Signature utilities** | `aitbc/crypto/crypto.py` | ✅ EXISTS — `recover_signer()`, `verify_signature()` using secp256k1 | Reuse in bridge proof utilities (A2) |
| **bridge-monitor app** | `apps/bridge-monitor/` (574 lines) | ⚠️ UNRELATED — monitors Ethereum→AIT deposits, not AITBC cross-chain bridges | No change needed (separate concern) |
| **Coordinator-api cross-chain** | `apps/coordinator-api/src/app/contexts/cross_chain/` | ⚠️ SEPARATE — has own bridge models, no integration with blockchain-node bridge RPC | DEFERRED — v0.7.0 focuses on blockchain-node bridge only |

### Already Fixed / Exists (verified — no work needed)

1. ✅ **Bridge core exists** — `CrossChainBridge` with lock/confirm/transfer/pending flow (401 lines)
2. ✅ **CrossChainTransfer table exists** — SQLModel with proper indexes
3. ✅ **Bridge RPC lock endpoint** — `POST /bridge/lock` with signature validation
4. ✅ **Bridge RPC confirm endpoint** — `POST /bridge/confirm` with `BRIDGE_RELEASE_ENABLED` fence
5. ✅ **Bridge RPC transfer status** — `GET /bridge/transfer/{transfer_id}`
6. ✅ **Bridge RPC pending list** — `GET /bridge/pending?chain_id=`
7. ✅ **Bridge manager exists** — island-to-island connection management (270 lines)
8. ✅ **Bridge test suite exists** — 401 lines covering proof verification, endpoints, lifecycle
9. ✅ **Merkle Patricia Trie ready** — `verify_proof()` available for v0.7.2
10. ✅ **Signature utilities ready** — `recover_signer()`, `verify_signature()` in `aitbc/crypto/crypto.py`
11. ✅ **Bridge release fence** — `BRIDGE_RELEASE_ENABLED=false` prevents unauthorized minting

### Architecture: Bridge Basics (v0.7.0)

```
┌──────────────────────────────────────────────────────────────────────┐
│ Shared Core (aitbc/bridge/ — NEW)                                    │
│                                                                      │
│  BridgeClient (A1) — HTTP client for bridge RPC:                     │
│    lock(), confirm(), unlock(), get_transfer(),                      │
│    list_pending(), get_balance(), health()                           │
│                                                                      │
│  Bridge types (A1) — BridgeStatus, BridgeTransfer,                   │
│    BridgeProof, BridgeConfig (shared dataclasses)                    │
│                                                                      │
│  Proof utilities (A2) — build_lock_proof(), validate_proof_fields()  │
│    using aitbc/crypto/crypto.py recover_signer()                     │
│    (basic validation only — NOT Merkle verification, deferred v0.7.2)│
└──────────────────────────────────────────────────────────────────────┘
         ↑ consumed by                    ↑ consumed by
┌─────────────────────────┐    ┌──────────────────────────────────────┐
│ CLI (cli/aitbc_cli/)    │    │ Blockchain Node                      │
│                         │    │ (apps/blockchain-node/)              │
│  bridge lock            │    │                                      │
│  bridge confirm         │    │  RPC endpoints (B2):                 │
│  bridge unlock          │───▶│    POST /bridge/lock        ✅ exists │
│  bridge status          │    │    POST /bridge/confirm     ✅ exists │
│  bridge pending         │    │    POST /bridge/unlock      ❌ NEW    │
│  bridge balance         │    │    GET  /bridge/balance/{c} ❌ NEW    │
│  bridge health          │    │    GET  /bridge/health      ❌ NEW    │
│                         │    │    GET  /bridge/status/{id} ❌ alias  │
│  Uses BridgeClient (A1) │    │    POST /bridge/batch/lock  ❌ NEW    │
│  instead of raw HTTP    │    │    POST /bridge/batch/confirm❌ NEW   │
│                         │    │                                      │
│  Fix broken commands    │    │  Bridge config (B1):                 │
│  (currently calls       │    │    bridge_timeout, bridge_retry,     │
│   non-existent          │    │    bridge_fee, bridge_supported_     │
│   /rpc/bridge/start)    │    │    chains, bridge_batch_size,        │
│                         │    │    bridge_monitor_interval           │
│                         │    │                                      │
│                         │    │  Bridge monitoring (B4):             │
│                         │    │    health checks, stuck transfer     │
│                         │    │    detection, metrics                │
│                         │    │                                      │
│                         │    │  Tests (B6):                         │
│                         │    │    unlock, balance, health, batch,   │
│                         │    │    monitoring, CLI integration       │
└─────────────────────────┘    └──────────────────────────────────────┘
```

---

## Task Split Overview

| Agent | Domain | Tasks | Files |
|-------|--------|-------|-------|
| **Agent A** | Shared core (`aitbc/`) | 3 items | `aitbc/bridge/__init__.py` (new), `aitbc/bridge/client.py` (new), `aitbc/bridge/types.py` (new), `aitbc/bridge/proof.py` (new), `tests/unit/` |
| **Agent B** | Apps & infrastructure | 7 items | `apps/blockchain-node/src/aitbc_chain/config.py`, `rpc/bridge.py`, `cross_chain/bridge.py`, `network/bridge_manager.py`, `rpc/router.py`, `cli/aitbc_cli/commands/bridge.py`, `cli/aitbc_cli/commands/node/bridge.py`, `aitbc/constants.py`, `apps/blockchain-node/tests/` |

**Conflict boundary**: Agent A owns new `aitbc/bridge/` package. Agent B owns all `apps/` and `cli/` files. Agent B consumes Agent A's `BridgeClient` and types. No shared files are touched by both agents. Agent B also owns `aitbc/constants.py` (bridge constants).

---

## Agent A — Shared Core (`aitbc/`)

**Scope**: Create (1) a shared bridge client SDK with types, (2) proof generation/validation utilities. Both are consumed by Agent B's CLI and blockchain-node work.

**Working directory**: `/opt/aitbc/aitbc/bridge/`

**Verification command**:
```bash
cd /opt/aitbc && ./venv/bin/python -m mypy --show-error-codes aitbc/bridge/ && ./venv/bin/python -m ruff check aitbc/bridge/ tests/unit/test_bridge_sdk.py && ./venv/bin/python -m pytest tests/unit/test_bridge_sdk.py -q -o addopts=""
```

### Tasks

| # | Task | Priority | Files | Status |
|---|------|----------|-------|--------|
| A1 | Create `aitbc/bridge/` package — BridgeClient (HTTP client), bridge types (BridgeStatus, BridgeTransfer, BridgeProof, BridgeConfig) | 🔴 P0 | `aitbc/bridge/__init__.py` (new), `aitbc/bridge/types.py` (new), `aitbc/bridge/client.py` (new) | ✅ |
| A2 | Create `aitbc/bridge/proof.py` — proof generation + basic validation utilities using `aitbc/crypto/crypto.py` | 🔴 P0 | `aitbc/bridge/proof.py` (new) | ✅ |
| A3 | Unit tests for A1-A2 + verify mypy/ruff/pytest clean | High | `tests/unit/test_bridge_sdk.py` (new) | ✅ |

### Agent A — Detailed Instructions

#### A1: BridgeClient + Bridge Types

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

#### A2: Proof Utilities

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

#### A3: Unit Tests

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

## Agent B — Apps & Infrastructure

**Scope**: Add bridge config fields, missing RPC endpoints (unlock, balance, health, batch), fix CLI bridge commands, add bridge monitoring, and write integration tests.

**Working directory**: `/opt/aitbc/apps/blockchain-node/` and `/opt/aitbc/cli/`

**Verification command**:
```bash
cd /opt/aitbc && ./venv/bin/python -m ruff check apps/blockchain-node/src/aitbc_chain/rpc/bridge.py apps/blockchain-node/src/aitbc_chain/cross_chain/bridge.py apps/blockchain-node/src/aitbc_chain/network/bridge_manager.py apps/blockchain-node/src/aitbc_chain/config.py cli/aitbc_cli/commands/bridge.py aitbc/constants.py
cd /opt/aitbc && ./venv/bin/python -m pytest apps/blockchain-node/tests/test_bridge_suite.py apps/blockchain-node/tests/test_v070_bridge_basics.py -q -o addopts="" --timeout=30
```

### Tasks

| # | Task | Priority | Files | Status |
|---|------|----------|-------|--------|
| B1 | Add bridge config fields + bridge constants | 🔴 P0 | `apps/blockchain-node/src/aitbc_chain/config.py`, `aitbc/constants.py` | ⬜ |
| B2 | Add missing RPC endpoints: unlock, balance, health, status alias, batch | 🔴 P0 | `apps/blockchain-node/src/aitbc_chain/rpc/bridge.py`, `apps/blockchain-node/src/aitbc_chain/rpc/router.py`, `apps/blockchain-node/src/aitbc_chain/cross_chain/bridge.py` | ⬜ |
| B3 | Fix CLI bridge commands — replace broken stubs with BridgeClient calls | 🔴 P0 | `cli/aitbc_cli/commands/bridge.py` | ⬜ |
| B4 | Add bridge monitoring — health checks, stuck transfer detection, metrics | High | `apps/blockchain-node/src/aitbc_chain/network/bridge_manager.py` | ⬜ |
| B5 | Wire CLI node bridge commands to actual RPC | Medium | `cli/aitbc_cli/commands/node/bridge.py` | ⬜ |
| B6 | Integration tests — unlock, balance, health, batch, monitoring, CLI | 🔴 P0 | `apps/blockchain-node/tests/test_v070_bridge_basics.py` (new) | ⬜ |
| B7 | Verify mypy + ruff + pytest clean | High | — | ⬜ |

### Agent B — Detailed Instructions

#### B1: Bridge Config + Constants

In `aitbc/constants.py`, add bridge constants:
```python
# Bridge defaults
BRIDGE_FEE_BASIS_POINTS = 10       # 0.1% bridge fee
BRIDGE_TIMEOUT_SECONDS = 300       # 5 minutes for cross-chain transfer
BRIDGE_RETRY_LIMIT = 3             # retry attempts for failed bridge ops
BRIDGE_BATCH_SIZE = 10             # max transfers per batch operation
BRIDGE_MONITOR_INTERVAL = 60       # seconds between health checks
BRIDGE_STUCK_TRANSFER_TIMEOUT = 3600  # 1 hour — transfers pending longer are flagged
```

In `apps/blockchain-node/src/aitbc_chain/config.py`, add to `Settings` class (near existing `bridge_release_enabled` at line 290):
```python
    # Bridge configuration (v0.7.0)
    bridge_timeout: int = 300
    bridge_retry_limit: int = 3
    bridge_fee_basis_points: int = 10
    bridge_supported_chains: str = ""  # comma-separated list of chain IDs
    bridge_batch_size: int = 10
    bridge_monitor_interval: int = 60
    bridge_stuck_transfer_timeout: int = 3600
```

#### B2: Missing RPC Endpoints

In `cross_chain/bridge.py`, add a `refund_transfer()` method to `CrossChainBridge`:
```python
async def refund_transfer(self, transfer_id: str, sender: str) -> BridgeTransfer:
    """Refund a pending bridge transfer — return locked funds to sender.

    Only transfers in 'pending' or 'locked' status can be refunded.
    Completed/confirmed transfers cannot be refunded.
    """
    # Get transfer record, verify status is pending/locked
    # Return amount (minus fee) to sender balance
    # Create BRIDGE_REFUND transaction
    # Update transfer record to 'refunded'
```

Also add `get_bridge_balance()` method:
```python
async def get_bridge_balance(self, chain_id: str | None = None) -> dict[str, int]:
    """Get total locked amount per chain (sum of pending/locked transfers)."""
    # Query CrossChainTransfer where status in (pending, locked)
    # Group by source_chain, sum amount
```

Also add `batch_lock()` and `batch_confirm()` methods.

In `rpc/bridge.py`, add endpoints:
- `POST /bridge/unlock` — calls `refund_transfer()`, requires signature
- `GET /bridge/balance/{chain_id}` — calls `get_bridge_balance()`
- `GET /bridge/health` — returns bridge health status (active transfers, pending count, last error)
- `GET /bridge/status/{transfer_id}` — alias to existing `GET /bridge/transfer/{transfer_id}`
- `POST /bridge/batch/lock` — calls `batch_lock()`
- `POST /bridge/batch/confirm` — calls `batch_confirm()`

Register all new endpoints in `rpc/router.py` (following the existing pattern at lines 776-810).

#### B3: Fix CLI Bridge Commands

In `cli/aitbc_cli/commands/bridge.py` (currently 78 lines, broken), replace the three broken commands (`start`, `status`, `stop` — which call non-existent endpoints) with:

- `aitbc bridge lock --target-chain --sender --recipient --amount [--asset] [--source-chain]` — calls `BridgeClient.lock()`
- `aitbc bridge confirm --transfer-id --confirmer --signature --proof-file` — calls `BridgeClient.confirm()`
- `aitbc bridge unlock --transfer-id --sender --signature` — calls `BridgeClient.unlock()`
- `aitbc bridge status --transfer-id` — calls `BridgeClient.get_transfer()`
- `aitbc bridge pending [--chain-id]` — calls `BridgeClient.list_pending()`
- `aitbc bridge balance --chain-id` — calls `BridgeClient.get_balance()`
- `aitbc bridge health` — calls `BridgeClient.health()`

Use `aitbc.bridge.BridgeClient` (from A1) instead of raw `AITBCHTTPClient`. The CLI commands should be async-compatible (use `asyncio.run()` wrapper if needed, following existing CLI patterns).

Remove the fallback-to-simulated-data pattern — if the RPC endpoint is unavailable, report the error clearly.

#### B4: Bridge Monitoring

In `network/bridge_manager.py`, add:
1. `health_check()` method — ping active bridges, return health status per bridge
2. `detect_stuck_transfers()` method — query `CrossChainTransfer` for transfers pending longer than `bridge_stuck_transfer_timeout`, log warnings
3. `get_metrics()` method — return dict with: active_bridge_count, pending_transfer_count, stuck_transfer_count, total_locked_amount
4. `_monitor_loop()` background task — runs every `bridge_monitor_interval` seconds, calls `health_check()` + `detect_stuck_transfers()`, logs anomalies

The monitoring is additive — it does not change the existing bridge connection management logic.

#### B5: CLI Node Bridge Commands

In `cli/aitbc_cli/commands/node/bridge.py` (currently 52 lines, stubs), replace simulated data with actual RPC calls:
- `aitbc node bridge request <target_island_id>` — calls `POST /islands/bridge`
- `aitbc node bridge approve <request_id> <approving_node_id>` — calls bridge manager approve
- `aitbc node bridge reject <request_id> [--reason]` — calls bridge manager reject
- `aitbc node bridge list-bridges` — calls `GET /bridge/health` or bridge manager list

#### B6: Integration Tests

Create `apps/blockchain-node/tests/test_v070_bridge_basics.py`:
- `test_bridge_unlock_refund` — lock then unlock returns funds to sender
- `test_bridge_unlock_completed_rejected` — cannot unlock a completed transfer
- `test_bridge_balance` — balance reflects locked transfers
- `test_bridge_balance_empty_chain` — zero balance for chain with no transfers
- `test_bridge_health` — health endpoint returns status
- `test_bridge_status_alias` — /bridge/status/{id} returns same as /bridge/transfer/{id}
- `test_bridge_batch_lock` — batch lock creates multiple transfers
- `test_bridge_batch_confirm` — batch confirm processes multiple transfers
- `test_bridge_batch_lock_empty_rejected` — empty batch rejected
- `test_bridge_batch_lock_exceeds_limit_rejected` — batch over max size rejected
- `test_bridge_monitor_stuck_detection` — stuck transfer detected after timeout
- `test_bridge_monitor_metrics` — metrics endpoint returns correct counts
- `test_cli_bridge_lock` — CLI lock command calls correct endpoint
- `test_cli_bridge_status` — CLI status command calls correct endpoint
- `test_cli_bridge_health` — CLI health command calls correct endpoint

#### B7: Verification

```bash
cd /opt/aitbc && ./venv/bin/python -m ruff check apps/blockchain-node/src/aitbc_chain/ cli/aitbc_cli/commands/bridge.py cli/aitbc_cli/commands/node/bridge.py aitbc/constants.py
cd /opt/aitbc && ./venv/bin/python -m pytest apps/blockchain-node/tests/test_bridge_suite.py apps/blockchain-node/tests/test_v070_bridge_basics.py tests/unit/test_bridge_sdk.py -q -o addopts="" --timeout=30
```

---

## Coordination Protocol

No shared files are touched by both agents. Agent A creates new files in `aitbc/bridge/`. Agent B modifies files in `apps/blockchain-node/` and `cli/`. Agent B consumes Agent A's `BridgeClient` and types — Agent A must complete A1 before Agent B starts B3 (CLI uses BridgeClient).

### Sequencing

1. **Agent A goes first** — A1 (BridgeClient + types) and A2 (proof utils) can proceed immediately
2. **Agent B B1, B2, B4 can proceed in parallel** with Agent A — they don't depend on `aitbc/bridge/`
3. **Agent B B3 (CLI fix) depends on A1** — CLI uses `BridgeClient`
4. **Agent B B5 (node bridge CLI) can proceed in parallel** — uses existing `/islands/bridge` endpoint
5. **Agent B B6 (tests) depends on B2** — tests the new endpoints
6. **Agent B B7 (verify) runs last**

### Deferred to v0.7.1 / v0.7.2

The following are explicitly **NOT** in v0.7.0 scope:
- **v0.7.1**: Block header signing by proposers, multi-sig validation, time-locked transactions, cross-chain signature verification, bridge event auditing, external security audit
- **v0.7.2**: Merkle proof verification (`merkle_patricia_trie.verify_proof`), proposer-set membership checking, block header signature verification, finality tracking, validator set epoch transitions, `BRIDGE_RELEASE_ENABLED` fence removal

The `BRIDGE_RELEASE_ENABLED=false` fence **remains in place** throughout v0.7.0. The confirm/release path stays gated until v0.7.2 completes full cryptographic verification.
