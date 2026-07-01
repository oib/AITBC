"""
Decentralized Governance Models
Database models for agent DAO, voting, proposals, and governance analytics
"""

import uuid
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

from sqlalchemy import DateTime
from sqlmodel import JSON, Column, Field, Index, SQLModel


class ProposalStatus(StrEnum):
    DRAFT = "draft"
    ACTIVE = "active"
    SUCCEEDED = "succeeded"
    DEFEATED = "defeated"
    EXECUTED = "executed"
    CANCELLED = "cancelled"


class VoteType(StrEnum):
    FOR = "for"
    AGAINST = "against"
    ABSTAIN = "abstain"


class GovernanceRole(StrEnum):
    MEMBER = "member"
    DELEGATE = "delegate"
    COUNCIL = "council"
    ADMIN = "admin"


class GovernanceProfile(SQLModel, table=True):
    """Profile for a participant in the AITBC DAO"""

    __tablename__ = "governance_profiles"

    profile_id: str = Field(primary_key=True, default_factory=lambda: f"gov_{uuid.uuid4().hex[:8]}")
    user_id: str = Field(unique=True, index=True)

    role: GovernanceRole = Field(default=GovernanceRole.MEMBER)
    voting_power: float = Field(default=0.0)
    delegated_power: float = Field(default=0.0)

    total_votes_cast: int = Field(default=0)
    proposals_created: int = Field(default=0)
    proposals_passed: int = Field(default=0)

    delegate_to: str | None = Field(default=None)

    joined_at: datetime = Field(default_factory=lambda: datetime.now(UTC), sa_column=Column(DateTime(timezone=True)))
    last_voted_at: datetime | None = Field(default=None, sa_column=Column(DateTime(timezone=True)))


class Proposal(SQLModel, table=True):
    """A governance proposal submitted to the DAO"""

    __tablename__ = "proposals"
    __table_args__ = (
        Index("idx_proposals_status", "status"),
        Index("idx_proposals_voting_period", "voting_starts", "voting_ends"),
        Index("idx_proposals_proposer", "proposer_id"),
    )

    proposal_id: str = Field(primary_key=True, default_factory=lambda: f"prop_{uuid.uuid4().hex[:8]}")
    proposer_id: str = Field(foreign_key="governance_profiles.profile_id")

    title: str
    description: str
    category: str = Field(default="general")

    # v0.4.12 new fields
    proposal_type: str = Field(
        default="general"
    )  # marketplace_rule, fee_structure, service_approval, protocol_upgrade, dispute_resolution, parameter_change
    proposal_value: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))
    quorum_required: float = Field(default=1000000.0)
    yes_votes: float = Field(default=0.0)
    no_votes: float = Field(default=0.0)
    execution_tx_hash: str | None = None
    execution_timestamp: datetime | None = None
    proposal_metadata: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))

    # v0.7.3 on-chain governance fields
    chain_id: str = Field(default="ait-hub", index=True)
    block_height: int | None = Field(default=None)
    tx_hash: str | None = Field(default=None)  # GOVERNANCE_PROPOSE tx hash

    # Legacy fields (kept for compatibility)
    execution_payload: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))
    votes_for: float = Field(default=0.0)  # Legacy alias for yes_votes
    votes_against: float = Field(default=0.0)  # Legacy alias for no_votes
    votes_abstain: float = Field(default=0.0)
    passing_threshold: float = Field(default=0.5)
    snapshot_block: int | None = Field(default=None)
    snapshot_timestamp: datetime | None = Field(default=None)

    status: ProposalStatus = Field(default=ProposalStatus.DRAFT)

    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC), sa_column=Column(DateTime(timezone=True)))
    voting_starts: datetime = Field(sa_column=Column(DateTime(timezone=True)))
    voting_ends: datetime = Field(sa_column=Column(DateTime(timezone=True)))
    executed_at: datetime | None = Field(default=None, sa_column=Column(DateTime(timezone=True)))


class Vote(SQLModel, table=True):
    """A vote cast on a specific proposal"""

    __tablename__ = "votes"
    __table_args__ = (
        Index("idx_votes_proposal", "proposal_id"),
        Index("idx_votes_voter", "voter_id"),
        Index("idx_votes_delegated", "delegated_from"),
    )

    vote_id: str = Field(primary_key=True, default_factory=lambda: f"vote_{uuid.uuid4().hex[:8]}")
    proposal_id: str = Field(foreign_key="proposals.proposal_id", index=True)
    voter_id: str = Field(foreign_key="governance_profiles.profile_id")

    vote_type: VoteType
    voting_power_used: float
    reason: str | None = None
    power_at_snapshot: float = Field(default=0.0)
    delegated_power_at_snapshot: float = Field(default=0.0)

    # v0.4.12 new fields
    voting_power: float = Field(default=0.0)  # Token-weighted power used
    vote_weight: float = Field(default=0.0)  # Calculated weight
    delegated_from: str | None = None  # For delegated votes
    signature: str | None = None  # 130 char ECDSA signature

    # v0.7.3 on-chain governance fields
    chain_id: str = Field(default="ait-hub", index=True)
    block_height: int | None = Field(default=None)
    tx_hash: str | None = Field(default=None)  # GOVERNANCE_VOTE tx hash

    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC), sa_column=Column(DateTime(timezone=True)))


class Delegation(SQLModel, table=True):
    """Voting power delegation from one address to another"""

    __tablename__ = "delegations"
    __table_args__ = (
        Index("idx_delegations_delegator", "delegator_address"),
        Index("idx_delegations_delegate", "delegate_address"),
        Index("idx_delegations_active", "is_active"),
    )

    delegation_id: str = Field(primary_key=True, default_factory=lambda: f"del_{uuid.uuid4().hex[:8]}")
    delegator_address: str = Field(index=True)
    delegate_address: str = Field(index=True)
    voting_power: float = Field(default=0.0)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    expires_at: datetime | None = None
    is_active: bool = Field(default=True)


class GovernanceToken(SQLModel, table=True):
    """Governance token holdings and voting power for an address"""

    __tablename__ = "governance_tokens"
    __table_args__ = (
        Index("idx_tokens_holder", "holder_address"),
        Index("idx_tokens_voting_power", "voting_power"),
    )

    token_id: str = Field(primary_key=True, default_factory=lambda: f"tok_{uuid.uuid4().hex[:8]}")
    holder_address: str = Field(unique=True, index=True)
    token_balance: float = Field(default=0.0)
    staked_tokens: float = Field(default=0.0)
    voting_power: float = Field(default=0.0)
    rewards_claimed: float = Field(default=0.0)
    rewards_pending: float = Field(default=0.0)
    last_updated: datetime = Field(default_factory=lambda: datetime.now(UTC))


class TokenStake(SQLModel, table=True):
    """Token staking for enhanced voting power"""

    __tablename__ = "token_stakes"
    __table_args__ = (
        Index("idx_stakes_staker", "staker_address"),
        Index("idx_stakes_active", "is_active"),
        Index("idx_stakes_unstake", "unstakes_at"),
    )

    stake_id: str = Field(primary_key=True, default_factory=lambda: f"stake_{uuid.uuid4().hex[:8]}")
    staker_address: str = Field(index=True)
    amount_staked: float = Field(default=0.0)
    lock_period_days: int = Field(default=30)
    staked_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    unstakes_at: datetime | None = None
    is_active: bool = Field(default=True)
    rewards_earned: float = Field(default=0.0)


class ProposalExecutionLog(SQLModel, table=True):
    """Log of proposal execution steps and results"""

    __tablename__ = "proposal_execution_log"
    __table_args__ = (
        Index("idx_exec_log_proposal", "proposal_id"),
        Index("idx_exec_log_status", "status"),
        Index("idx_exec_log_timestamp", "executed_at"),
    )

    log_id: str = Field(primary_key=True, default_factory=lambda: f"log_{uuid.uuid4().hex[:8]}")
    proposal_id: str = Field(foreign_key="proposals.proposal_id", index=True)
    execution_step: str
    status: str
    result: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))
    error_message: str | None = None
    executed_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class DaoTreasury(SQLModel, table=True):
    """Record of the DAO's treasury funds and allocations"""

    __tablename__ = "dao_treasury"

    treasury_id: str = Field(primary_key=True, default="main_treasury")

    total_balance: float = Field(default=0.0)
    allocated_funds: float = Field(default=0.0)

    asset_breakdown: dict[str, float] = Field(default_factory=dict, sa_column=Column(JSON))

    last_updated: datetime = Field(default_factory=lambda: datetime.now(UTC))


class TransparencyReport(SQLModel, table=True):
    """Automated transparency and analytics report for the governance system"""

    __tablename__ = "transparency_reports"

    report_id: str = Field(primary_key=True, default_factory=lambda: f"rep_{uuid.uuid4().hex[:8]}")
    period: str

    total_proposals: int
    passed_proposals: int
    active_voters: int
    total_voting_power_participated: float

    treasury_inflow: float
    treasury_outflow: float

    metrics: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))

    generated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
