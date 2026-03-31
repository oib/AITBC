"""
DAO Governance Domain Models

Domain models for managing multi-jurisdictional DAOs, regional councils, and global treasuries.
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from uuid import uuid4

from sqlalchemy import JSON, Column
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


class DAOMember(SQLModel, table=True):
    """A member participating in DAO governance"""

    __tablename__ = "dao_member"

    id: str = Field(default_factory=lambda: uuid4().hex, primary_key=True)
    wallet_address: str = Field(index=True, unique=True)

    staked_amount: float = Field(default=0.0)
    voting_power: float = Field(default=0.0)

    is_council_member: bool = Field(default=False)
    council_region: str | None = Field(default=None, index=True)

    joined_at: datetime = Field(default_factory=datetime.utcnow)
    last_active: datetime = Field(default_factory=datetime.utcnow)

    # Relationships
    # DISABLED:     votes: List["Vote"] = Relationship(back_populates="member")


class DAOProposal(SQLModel, table=True):
    """A governance proposal"""

    __tablename__ = "dao_proposal"

    id: str = Field(default_factory=lambda: uuid4().hex, primary_key=True)
    contract_proposal_id: str | None = Field(default=None, index=True)

    proposer_address: str = Field(index=True)
    title: str = Field()
    description: str = Field()

    proposal_type: ProposalType = Field(default=ProposalType.GENERAL)
    target_region: str | None = Field(default=None, index=True)  # None = Global

    status: ProposalState = Field(default=ProposalState.PENDING, index=True)

    for_votes: float = Field(default=0.0)
    against_votes: float = Field(default=0.0)
    abstain_votes: float = Field(default=0.0)

    execution_payload: dict[str, str] = Field(default_factory=dict, sa_column=Column(JSON))

    start_time: datetime = Field(default_factory=datetime.utcnow)
    end_time: datetime = Field(default_factory=datetime.utcnow)

    created_at: datetime = Field(default_factory=datetime.utcnow)

    # Relationships
    # DISABLED:     votes: List["Vote"] = Relationship(back_populates="proposal")


class Vote(SQLModel, table=True):
    """A vote cast on a proposal"""

    __tablename__ = "dao_vote"

    id: str = Field(default_factory=lambda: uuid4().hex, primary_key=True)
    proposal_id: str = Field(foreign_key="dao_proposal.id", index=True)
    member_id: str = Field(foreign_key="dao_member.id", index=True)

    support: bool = Field()  # True = For, False = Against
    weight: float = Field()

    tx_hash: str | None = Field(default=None)
    created_at: datetime = Field(default_factory=datetime.utcnow)

    # Relationships
    # DISABLED:     proposal: DAOProposal = Relationship(back_populates="votes")
    # DISABLED:     member: DAOMember = Relationship(back_populates="votes")


class TreasuryAllocation(SQLModel, table=True):
    """Tracks allocations and spending from the global treasury"""

    __tablename__ = "treasury_allocation"

    id: str = Field(default_factory=lambda: uuid4().hex, primary_key=True)
    proposal_id: str | None = Field(foreign_key="dao_proposal.id", default=None)

    amount: float = Field()
    token_symbol: str = Field(default="AITBC")

    recipient_address: str = Field()
    purpose: str = Field()

    tx_hash: str | None = Field(default=None)
    executed_at: datetime = Field(default_factory=datetime.utcnow)
