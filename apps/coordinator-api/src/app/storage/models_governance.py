"""
Governance models for AITBC
"""

from sqlmodel import SQLModel, Field, Relationship, Column, JSON
from typing import Optional, Dict, Any
from datetime import datetime
from uuid import uuid4


class GovernanceProposal(SQLModel, table=True):
    """A governance proposal"""
    
    id: str = Field(default_factory=lambda: str(uuid4()), primary_key=True)
    title: str = Field(max_length=200)
    description: str = Field(max_length=5000)
    type: str = Field(max_length=50)  # parameter_change, protocol_upgrade, fund_allocation, policy_change
    target: Optional[Dict[str, Any]] = Field(default_factory=dict, sa_column=Column(JSON))
    proposer: str = Field(max_length=255, index=True)
    status: str = Field(default="active", max_length=20)  # active, passed, rejected, executed, expired
    created_at: datetime = Field(default_factory=datetime.utcnow)
    voting_deadline: datetime
    quorum_threshold: float = Field(default=0.1)  # Percentage of total voting power
    approval_threshold: float = Field(default=0.5)  # Percentage of votes in favor
    executed_at: Optional[datetime] = None
    rejection_reason: Optional[str] = Field(max_length=500)
    
    # Relationships
    votes: list["ProposalVote"] = Relationship(back_populates="proposal")


class ProposalVote(SQLModel, table=True):
    """A vote on a governance proposal"""
    
    id: str = Field(default_factory=lambda: str(uuid4()), primary_key=True)
    proposal_id: str = Field(foreign_key="governanceproposal.id", index=True)
    voter_id: str = Field(max_length=255, index=True)
    vote: str = Field(max_length=10)  # for, against, abstain
    voting_power: int = Field(default=0)  # Amount of voting power at time of vote
    reason: Optional[str] = Field(max_length=500)
    voted_at: datetime = Field(default_factory=datetime.utcnow)
    
    # Relationships
    proposal: GovernanceProposal = Relationship(back_populates="votes")


class TreasuryTransaction(SQLModel, table=True):
    """A treasury transaction for fund allocations"""
    
    id: str = Field(default_factory=lambda: str(uuid4()), primary_key=True)
    proposal_id: Optional[str] = Field(foreign_key="governanceproposal.id", index=True)
    from_address: str = Field(max_length=255)
    to_address: str = Field(max_length=255)
    amount: int  # Amount in smallest unit (e.g., wei)
    token: str = Field(default="AITBC", max_length=20)
    transaction_hash: Optional[str] = Field(max_length=255)
    status: str = Field(default="pending", max_length=20)  # pending, confirmed, failed
    created_at: datetime = Field(default_factory=datetime.utcnow)
    confirmed_at: Optional[datetime] = None
    memo: Optional[str] = Field(max_length=500)


class GovernanceParameter(SQLModel, table=True):
    """A governance parameter that can be changed via proposals"""
    
    id: str = Field(default_factory=lambda: str(uuid4()), primary_key=True)
    key: str = Field(max_length=100, unique=True, index=True)
    value: str = Field(max_length=1000)
    description: str = Field(max_length=500)
    min_value: Optional[str] = Field(max_length=100)
    max_value: Optional[str] = Field(max_length=100)
    value_type: str = Field(max_length=20)  # string, number, boolean, json
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    updated_by_proposal: Optional[str] = Field(foreign_key="governanceproposal.id")


class VotingPowerSnapshot(SQLModel, table=True):
    """Snapshot of voting power at a specific time"""
    
    id: str = Field(default_factory=lambda: str(uuid4()), primary_key=True)
    user_id: str = Field(max_length=255, index=True)
    voting_power: int
    snapshot_time: datetime = Field(default_factory=datetime.utcnow, index=True)
    block_number: Optional[int] = Field(index=True)
    
    class Config:
        indexes = [
            {"name": "ix_user_snapshot", "fields": ["user_id", "snapshot_time"]},
        ]


class ProtocolUpgrade(SQLModel, table=True):
    """Track protocol upgrades"""
    
    id: str = Field(default_factory=lambda: str(uuid4()), primary_key=True)
    proposal_id: str = Field(foreign_key="governanceproposal.id", index=True)
    version: str = Field(max_length=50)
    upgrade_type: str = Field(max_length=50)  # hard_fork, soft_fork, patch
    activation_block: Optional[int]
    status: str = Field(default="pending", max_length=20)  # pending, active, failed
    created_at: datetime = Field(default_factory=datetime.utcnow)
    activated_at: Optional[datetime] = None
    rollback_available: bool = Field(default=False)
    
    # Upgrade details
    description: str = Field(max_length=2000)
    changes: Optional[Dict[str, Any]] = Field(default_factory=dict, sa_column=Column(JSON))
    required_node_version: Optional[str] = Field(max_length=50)
    migration_required: bool = Field(default=False)
