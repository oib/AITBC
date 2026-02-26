"""
Decentralized Governance Models
Database models for OpenClaw DAO, voting, proposals, and governance analytics
"""

from typing import Optional, List, Dict, Any
from sqlmodel import Field, SQLModel, Column, JSON, Relationship
from datetime import datetime
from enum import Enum
import uuid

class ProposalStatus(str, Enum):
    DRAFT = "draft"
    ACTIVE = "active"
    SUCCEEDED = "succeeded"
    DEFEATED = "defeated"
    EXECUTED = "executed"
    CANCELLED = "cancelled"

class VoteType(str, Enum):
    FOR = "for"
    AGAINST = "against"
    ABSTAIN = "abstain"

class GovernanceRole(str, Enum):
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
    voting_power: float = Field(default=0.0) # Calculated based on staked AITBC and reputation
    delegated_power: float = Field(default=0.0) # Power delegated to them by others
    
    total_votes_cast: int = Field(default=0)
    proposals_created: int = Field(default=0)
    proposals_passed: int = Field(default=0)
    
    delegate_to: Optional[str] = Field(default=None) # Profile ID they delegate their vote to
    
    joined_at: datetime = Field(default_factory=datetime.utcnow)
    last_voted_at: Optional[datetime] = None

class Proposal(SQLModel, table=True):
    """A governance proposal submitted to the DAO"""
    __tablename__ = "proposals"

    proposal_id: str = Field(primary_key=True, default_factory=lambda: f"prop_{uuid.uuid4().hex[:8]}")
    proposer_id: str = Field(foreign_key="governance_profiles.profile_id")
    
    title: str
    description: str
    category: str = Field(default="general") # parameters, funding, protocol, marketplace
    
    execution_payload: Dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))
    
    status: ProposalStatus = Field(default=ProposalStatus.DRAFT)
    
    votes_for: float = Field(default=0.0)
    votes_against: float = Field(default=0.0)
    votes_abstain: float = Field(default=0.0)
    
    quorum_required: float = Field(default=0.0)
    passing_threshold: float = Field(default=0.5) # Usually 50%
    
    snapshot_block: Optional[int] = Field(default=None)
    snapshot_timestamp: Optional[datetime] = Field(default=None)
    
    created_at: datetime = Field(default_factory=datetime.utcnow)
    voting_starts: datetime
    voting_ends: datetime
    executed_at: Optional[datetime] = None

class Vote(SQLModel, table=True):
    """A vote cast on a specific proposal"""
    __tablename__ = "votes"

    vote_id: str = Field(primary_key=True, default_factory=lambda: f"vote_{uuid.uuid4().hex[:8]}")
    proposal_id: str = Field(foreign_key="proposals.proposal_id", index=True)
    voter_id: str = Field(foreign_key="governance_profiles.profile_id")
    
    vote_type: VoteType
    voting_power_used: float
    reason: Optional[str] = None
    power_at_snapshot: float = Field(default=0.0)
    delegated_power_at_snapshot: float = Field(default=0.0)
    
    created_at: datetime = Field(default_factory=datetime.utcnow)

class DaoTreasury(SQLModel, table=True):
    """Record of the DAO's treasury funds and allocations"""
    __tablename__ = "dao_treasury"

    treasury_id: str = Field(primary_key=True, default="main_treasury")
    
    total_balance: float = Field(default=0.0)
    allocated_funds: float = Field(default=0.0)
    
    asset_breakdown: Dict[str, float] = Field(default_factory=dict, sa_column=Column(JSON))
    
    last_updated: datetime = Field(default_factory=datetime.utcnow)

class TransparencyReport(SQLModel, table=True):
    """Automated transparency and analytics report for the governance system"""
    __tablename__ = "transparency_reports"

    report_id: str = Field(primary_key=True, default_factory=lambda: f"rep_{uuid.uuid4().hex[:8]}")
    period: str # e.g., "2026-Q1", "2026-02"
    
    total_proposals: int
    passed_proposals: int
    active_voters: int
    total_voting_power_participated: float
    
    treasury_inflow: float
    treasury_outflow: float
    
    metrics: Dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))
    
    generated_at: datetime = Field(default_factory=datetime.utcnow)
