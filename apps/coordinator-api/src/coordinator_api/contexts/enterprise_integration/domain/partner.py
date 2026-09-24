"""Partner integration registry models."""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import JSON, Column
from sqlmodel import Field, SQLModel


def _utcnow() -> datetime:
    return datetime.now(UTC)


class Partner(SQLModel, table=True):
    """A registered third-party integration partner.

    ``api_key_hash`` is the SHA-256 hex digest of the issued ``aitbc_*`` key;
    the plaintext key is returned once at registration and never stored.
    ``api_secret_hash`` likewise stores only the digest of the issued secret.
    """

    __tablename__ = "integration_partner"
    __table_args__ = {"extend_existing": True}

    id: str = Field(primary_key=True)
    name: str
    description: str
    website: str
    contact: str
    integration_type: str
    api_key_hash: str = Field(index=True)
    api_secret_hash: str
    rate_limit: dict = Field(default_factory=dict, sa_column=Column(JSON))
    status: str = "active"
    created_at: datetime = Field(default_factory=_utcnow)


class PartnerWebhook(SQLModel, table=True):
    """A partner's webhook subscription.

    ``secret`` signs outbound deliveries, so the server must retain it; it is
    never returned by the API after creation.
    """

    __tablename__ = "partner_webhook"
    __table_args__ = {"extend_existing": True}

    id: str = Field(primary_key=True)
    partner_id: str = Field(foreign_key="integration_partner.id", index=True)
    url: str
    events: list = Field(default_factory=list, sa_column=Column(JSON))
    secret: str
    status: str = "active"
    created_at: datetime = Field(default_factory=_utcnow)
