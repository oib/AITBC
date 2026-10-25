"""Escrow relay persistence (ESCROW-ROUTE-1).

One narrow row per relayed escrow create: the JWT caller, the job_id it
named, the dedup hash of the buyer-signed lock transaction, and the
contract_id the chain returned. It gives the relay endpoint idempotent
replays (a repeat POST returns the stored contract_id without a second
chain call) plus an audit trail. No JobPayment row is created — market
escrows are tracked chain-side by job_id.
"""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

from sqlmodel import Field, SQLModel


class EscrowRelay(SQLModel, table=True):
    """A relayed /rpc/escrow/create submission."""

    __tablename__ = "escrow_relay"
    __table_args__ = {"extend_existing": True}

    id: str = Field(default_factory=lambda: uuid4().hex, primary_key=True)
    client_id: str = Field(index=True, max_length=255)
    job_id: str = Field(index=True, max_length=128)
    # sha256 of the canonical lock_tx JSON — the buyer-signed lock is the
    # authorization; its hash dedups relays of the same signed lock.
    lock_hash: str = Field(unique=True, index=True, max_length=64)
    contract_id: str | None = Field(default=None, max_length=128)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
