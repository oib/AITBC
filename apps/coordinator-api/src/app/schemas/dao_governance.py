
from pydantic import BaseModel, Field

from .dao_governance import ProposalType


class MemberCreate(BaseModel):
    wallet_address: str
    staked_amount: float = 0.0


class ProposalCreate(BaseModel):
    proposer_address: str
    title: str
    description: str
    proposal_type: ProposalType = ProposalType.GENERAL
    target_region: str | None = None
    execution_payload: dict[str, str] = Field(default_factory=dict)
    voting_period_days: int = 7


class VoteCreate(BaseModel):
    member_address: str
    proposal_id: str
    support: bool


class AllocationCreate(BaseModel):
    proposal_id: str | None = None
    amount: float
    token_symbol: str = "AITBC"
    recipient_address: str
    purpose: str
