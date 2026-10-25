"""Escrow release relay persistence (ESCROW-RELEASE-1).

One narrow row per relayed escrow release: the JWT caller, the job_id it
named, and the transaction hash the chain returned. It gives the release
endpoint idempotent replays (a repeat POST returns the stored tx_hash
without a second chain call) plus an audit trail. Unlike the create relay
there is no caller-signed payload to hash — the chain signs the release
itself — so ``job_id`` alone is the dedup key.
"""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

from sqlmodel import Field, SQLModel


class EscrowReleaseRelay(SQLModel, table=True):
    """A relayed /rpc/escrow/{job_id}/release submission."""

    __tablename__ = "escrow_release_relay"
    __table_args__ = {"extend_existing": True}

    id: str = Field(default_factory=lambda: uuid4().hex, primary_key=True)
    client_id: str = Field(index=True, max_length=255)
    # One release per escrow — the chain itself dedups a second release, so
    # the relay dedups on job_id alone (no signed payload to hash over).
    job_id: str = Field(unique=True, index=True, max_length=128)
    tx_hash: str | None = Field(default=None, max_length=128)
    contract_id: str | None = Field(default=None, max_length=128)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
