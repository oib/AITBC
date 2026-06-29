"""Shared bridge types for cross-chain transfers (v0.7.0 §A1).

These are the canonical shared SDK types for the AITBC cross-chain bridge.
They mirror the in-node types in
``apps/blockchain-node/src/aitbc_chain/cross_chain/bridge.py`` but are
standalone, dependency-free dataclasses/enums intended for consumption by
the CLI and other services.

Full Merkle proof verification + proposer-set membership checking is
deferred to v0.7.2; v0.7.0 ships basic field/signature validation only.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum


class BridgeStatus(StrEnum):
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
