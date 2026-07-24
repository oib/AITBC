"""Developer registry domain models for the DAO grant program."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

from sqlmodel import Field, SQLModel


class Developer(SQLModel, table=True):
    """A developer registered for the DAO grant program."""

    __tablename__ = "developer"

    id: str = Field(default_factory=lambda: uuid4().hex, primary_key=True)
    wallet_address: str = Field(index=True, unique=True)
    name: str | None = None
    email: str | None = None
    github_handle: str | None = None
    is_active: bool = Field(default=True)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
