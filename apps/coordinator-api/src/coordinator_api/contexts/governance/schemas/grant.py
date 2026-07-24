"""Grant proposal request/response schemas."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from ..domain.grant import GrantStatus, MilestoneStatus


class GrantProposalCreate(BaseModel):
    """Payload for creating a grant proposal."""

    developer_id: str
    title: str
    description: str = ""
    requested_amount: Decimal = Decimal("0")
    voting_days: int = Field(default=7, ge=1)


class GrantMilestoneCreate(BaseModel):
    """Payload for adding a milestone to a grant."""

    title: str
    description: str = ""
    amount: Decimal = Decimal("0")
    due_date: datetime | None = None


class GrantVoteRequest(BaseModel):
    """Payload for casting a vote on a grant."""

    vote: str
    voting_power: float = 0.0


class GrantDisburseRequest(BaseModel):
    """Payload for disbursing grant funds."""

    milestone_id: str | None = None
    amount: Decimal | None = None


class GrantProposalResponse(BaseModel):
    """Grant proposal response model."""

    model_config = ConfigDict(from_attributes=True)

    id: str
    developer_id: str
    title: str
    description: str
    requested_amount: Decimal
    approved_amount: Decimal
    disbursed_amount: Decimal
    status: GrantStatus
    votes_for: float
    votes_against: float
    votes_abstain: float
    quorum: float
    passing_threshold: float
    voting_starts: datetime | None
    voting_ends: datetime | None
    executed_at: datetime | None
    proposal_metadata: dict[str, Any]
    created_at: datetime
    updated_at: datetime


class GrantMilestoneResponse(BaseModel):
    """Grant milestone response model."""

    model_config = ConfigDict(from_attributes=True)

    id: str
    grant_id: str
    title: str
    description: str
    amount: Decimal
    status: MilestoneStatus
    due_date: datetime | None
    completed_at: datetime | None
    evidence: dict[str, Any]
    created_at: datetime
    updated_at: datetime
