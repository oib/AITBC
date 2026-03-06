from pydantic import BaseModel, Field
from typing import Optional, Dict
from datetime import datetime
from .dao_governance import ProposalState, ProposalType

class MemberCreate(BaseModel):
    wallet_address: str
    staked_amount: float = 0.0

class ProposalCreate(BaseModel):
    proposer_address: str
    title: str
    description: str
    proposal_type: ProposalType = ProposalType.GENERAL
    target_region: Optional[str] = None
    execution_payload: Dict[str, str] = Field(default_factory=dict)
    voting_period_days: int = 7

class VoteCreate(BaseModel):
    member_address: str
    proposal_id: str
    support: bool
    
class AllocationCreate(BaseModel):
    proposal_id: Optional[str] = None
    amount: float
    token_symbol: str = "AITBC"
    recipient_address: str
    purpose: str
