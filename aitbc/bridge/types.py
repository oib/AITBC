"""Shared bridge types for cross-chain transfers (v0.7.0 §A1, v0.7.1 §A1).

These are the canonical shared SDK types for the AITBC cross-chain bridge.
They mirror the in-node types in
``apps/blockchain-node/src/aitbc_chain/cross_chain/bridge.py`` but are
standalone, dependency-free dataclasses/enums intended for consumption by
the CLI and other services.

v0.7.0 ships basic field/signature validation only. v0.7.1 adds the
validator-set registry types (ValidatorInfo, ValidatorSet) and the
multi-sig ThresholdProof type. Full Merkle proof verification +
proposer-set membership checking is deferred to v0.7.2.
"""

from __future__ import annotations

from dataclasses import dataclass, field
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

    v0.7.1 adds the optional ``validator_signatures`` list for M-of-N
    threshold multi-sig. Backward-compatible: old proofs with only
    ``proposer_signature`` still validate (single-signer fallback).

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
    validator_signatures: list[str] = field(default_factory=list)


@dataclass
class ValidatorInfo:
    """A bridge validator for a specific chain (v0.7.1 §A1)."""

    address: str  # checksum address (0x...)
    public_key: str  # secp256k1 public key hex (0x...)
    chain_id: str  # chain this validator serves
    epoch: int  # validator set epoch number
    is_active: bool = True
    registered_at: datetime | None = None


@dataclass
class ValidatorSet:
    """The set of validators for a chain at a specific epoch (v0.7.1 §A1)."""

    chain_id: str
    epoch: int
    validators: list[ValidatorInfo] = field(default_factory=list)
    threshold: int = 3  # M-of-N: minimum signatures required
    total: int = 5  # N: total validators in set

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
    ``validator_signatures`` is empty, falls back to ``proposer_signature``.
    """

    source_chain: str
    lock_tx_hash: str
    amount: int
    sender: str
    recipient: str
    chain_id: str
    block_height: int
    block_hash: str
    proposer_signature: str  # original single sig (backward compat)
    validator_signatures: list[str] = field(default_factory=list)


@dataclass
class BridgeConfig:
    """Configuration for bridge operations."""

    rpc_url: str = "http://localhost:8202"
    chain_id: str = "ait-hub"
    timeout: int = 30
    retry_limit: int = 3
    fee_basis_points: int = 10  # 0.1%
    batch_size: int = 10
    # v0.7.1 §A1 — multi-sig configuration
    multisig_enabled: bool = False  # require multi-sig for confirm
    multisig_threshold: int = 3  # M-of-N minimum signatures
    multisig_validators: int = 5  # N total validators
