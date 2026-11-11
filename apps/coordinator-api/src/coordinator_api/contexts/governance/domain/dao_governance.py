"""
DAO Governance Domain Models

Domain models for managing multi-jurisdictional DAOs, regional councils, and global treasuries.
"""

from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from uuid import uuid4

from sqlmodel import Field, SQLModel


class ProposalState(StrEnum):
    PENDING = "pending"
    ACTIVE = "active"
    CANCELED = "canceled"
    DEFEATED = "defeated"
    SUCCEEDED = "succeeded"
    QUEUED = "queued"
    EXPIRED = "expired"
    EXECUTED = "executed"


class ProposalType(StrEnum):
    GRANT = "grant"
    PARAMETER_CHANGE = "parameter_change"
    MEMBER_ELECTION = "member_election"
    GENERAL = "general"


class Vote(SQLModel, table=True):
    """A vote cast on a proposal"""

    __tablename__ = "dao_vote"

    id: str = Field(default_factory=lambda: uuid4().hex, primary_key=True)
    # #1840: dao_proposal/dao_member were dropped as dead tables — the FK
    # targets no longer exist, so these stay plain indexed columns.
    proposal_id: str = Field(index=True)
    member_id: str = Field(index=True)

    support: bool = Field()  # True = For, False = Against
    weight: float = Field()

    tx_hash: str | None = Field(default=None)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    # Relationships
    # DISABLED:     proposal: DAOProposal = Relationship(back_populates="votes")
    # DISABLED:     member: DAOMember = Relationship(back_populates="votes")


__all__ = [
    "Vote",
]
