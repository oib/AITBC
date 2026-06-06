"""Schemas for Hermes distributed decision making."""

from typing import Optional, List
from datetime import datetime
from pydantic import BaseModel, Field
from enum import Enum


class DecisionType(str, Enum):
    """Types of decisions agents can make."""
    RESOURCE_ALLOCATION = "resource_allocation"
    PRICING_ADJUSTMENT = "pricing_adjustment"
    TASK_ASSIGNMENT = "task_assignment"
    CONSENSUS_VOTE = "consensus_vote"
    EMERGENCY_RESPONSE = "emergency_response"


class VoteOption(str, Enum):
    """Vote options for decisions."""
    APPROVE = "approve"
    REJECT = "reject"
    ABSTAIN = "abstain"


class DecisionStatus(str, Enum):
    """Status of a decision."""
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    APPROVED = "approved"
    REJECTED = "rejected"
    EXPIRED = "expired"


class DecisionProposal(BaseModel):
    """Proposal for a distributed decision."""
    decision_type: DecisionType
    title: str
    description: str
    proposed_by: str
    voting_deadline: datetime
    min_participation: float = Field(default=0.5, ge=0.0, le=1.0)
    required_approval: float = Field(default=0.6, ge=0.0, le=1.0)
    metadata: Optional[dict] = None


class DecisionProposalResponse(BaseModel):
    """Response to a decision proposal."""
    decision_id: str
    status: DecisionStatus
    created_at: datetime
    voting_deadline: datetime
    message: str


class Vote(BaseModel):
    """Agent vote on a decision."""
    decision_id: str
    agent_id: str
    vote: VoteOption
    weight: float = Field(default=1.0, ge=0.0)
    reason: Optional[str] = None


class VoteResponse(BaseModel):
    """Response to a vote submission."""
    vote_id: str
    decision_id: str
    status: str
    message: str


class DecisionResult(BaseModel):
    """Result of a decision."""
    decision_id: str
    status: DecisionStatus
    total_votes: int
    approve_votes: int
    reject_votes: int
    abstain_votes: int
    weighted_approve: float
    weighted_reject: float
    weighted_abstain: float
    participation_rate: float
    approval_rate: float
    final_decision: Optional[VoteOption] = None
    concluded_at: Optional[datetime] = None


class DecisionListResponse(BaseModel):
    """Response listing decisions."""
    decisions: List[DecisionResult]
    total: int
