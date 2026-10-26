"""Escrow refund relay persistence (ESCROW-REFUND-1).

One narrow row per relayed escrow refund: the JWT caller, the job_id it
named, and the refund transaction hash the chain returned. It gives the
refund endpoint idempotent replays (a repeat POST returns the stored
refund_tx_hash without a second chain call) plus an audit trail. There is
no caller-signed payload to hash — the chain signs the refund itself — so
``job_id`` alone is the dedup key, same as the release relay.
"""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

from sqlmodel import Field, SQLModel


class EscrowRefundRelay(SQLModel, table=True):
    """A relayed /rpc/escrow/{job_id}/refund submission."""

    __tablename__ = "escrow_refund_relay"
    __table_args__ = {"extend_existing": True}

    id: str = Field(default_factory=lambda: uuid4().hex, primary_key=True)
    client_id: str = Field(index=True, max_length=255)
    # One refund per escrow — the chain itself dedups a second refund, so
    # the relay dedups on job_id alone (no signed payload to hash over).
    job_id: str = Field(unique=True, index=True, max_length=128)
    tx_hash: str | None = Field(default=None, max_length=128)
    contract_id: str | None = Field(default=None, max_length=128)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
