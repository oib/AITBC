"""Economic parameter proposal request/response schemas."""

from datetime import datetime
from decimal import Decimal
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from ..domain.economic_proposal import EconomicProposalStatus


class EconomicProposalCreate(BaseModel):
    """Payload for creating an economic parameter proposal."""

    proposer_id: str
    parameter_name: str
    unit: str | None = None
    current_value: str = "0"
    proposed_value: str = "0"
    voting_days: int = Field(default=7, ge=1)


class EconomicProposalVoteRequest(BaseModel):
    """Payload for casting a vote on an economic proposal."""

    vote: str  # "for", "against", or "abstain"
    voting_power: float = 0.0


class EconomicProposalResponse(BaseModel):
    """Economic parameter proposal response model."""

    model_config = ConfigDict(from_attributes=True)

    id: str
    proposer_id: str
    parameter_name: str
    unit: str | None
    current_value: Decimal
    proposed_value: Decimal
    status: EconomicProposalStatus
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
