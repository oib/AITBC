"""Inter-chain trading domain models (v0.8.0 §B2).

SQLModel tables for inter-chain trading:
- ``InterChainTrade`` — a trade between two AITBC chains (source → dest)
- ``IslandRegistryEntry`` — registry of known AITBC chains for discovery

These extend the existing P2P trading models in ``trading.py`` with
cross-chain fields (source_chain, dest_chain) and bridge integration
fields (source_tx_hash, dest_tx_hash). Escrow locking and atomic
settlement are deferred to v0.9.0 — v0.8.0 only handles the
create → match → agree lifecycle.
"""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

from sqlmodel import Field, Index, SQLModel


class InterChainTrade(SQLModel, table=True):
    """An inter-chain trade between two AITBC chains."""

    __tablename__ = "inter_chain_trades"
    __table_args__ = (
        Index("idx_inter_chain_status", "status"),
        Index("idx_inter_chain_chains", "source_chain", "dest_chain"),
        Index("idx_inter_chain_sender", "sender"),
    )

    trade_id: str = Field(primary_key=True, default_factory=lambda: f"trade_{uuid4().hex[:8]}")
    source_chain: str = Field(index=True)
    dest_chain: str = Field(index=True)
    status: str = Field(default="pending", index=True)
    sender: str = Field(index=True)
    recipient: str
    amount: int
    offer_id: str | None = None
    price: float = Field(default=0.0)
    quantity: int = Field(default=0)
    source_tx_hash: str | None = None  # set in v0.9.0 (escrow lock)
    dest_tx_hash: str | None = None  # set in v0.9.0 (settlement)
    matched_trade_id: str | None = None  # ID of the counterparty trade (if matched)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    # v0.9.0 §B7: Atomic settlement (HTLC) fields
    escrow_id: str | None = None  # cross-chain escrow ID (set when escrow created)
    settlement_phase: str = Field(default="none", index=True)  # SettlementPhase value
    secret_hash: str = ""  # SHA256 hash of the HTLC secret (the hashlock)
    source_timelock: int = 0  # source chain timelock (block height)
    dest_timelock: int = 0  # destination chain timelock (must be < source)


class IslandRegistryEntry(SQLModel, table=True):
    """Registry of known AITBC chains for inter-chain trading."""

    __tablename__ = "island_registry"
    __table_args__ = (Index("idx_island_status", "status"),)

    chain_id: str = Field(primary_key=True)
    endpoint: str  # blockchain node RPC URL (e.g. http://node1:8202)
    status: str = Field(default="active", index=True)  # active, inactive, unreachable
    block_height: int = Field(default=0)
    offers_count: int = Field(default=0)
    registered_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    last_sync: datetime = Field(default_factory=lambda: datetime.now(UTC))
