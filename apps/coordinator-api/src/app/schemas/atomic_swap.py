
from pydantic import BaseModel

from .atomic_swap import SwapStatus


class SwapCreateRequest(BaseModel):
    initiator_agent_id: str
    initiator_address: str
    source_chain_id: int
    source_token: str
    source_amount: float

    participant_agent_id: str
    participant_address: str
    target_chain_id: int
    target_token: str
    target_amount: float

    # Optional explicitly provided secret (if not provided, service generates one)
    secret: str | None = None

    # Optional explicitly provided timelocks (if not provided, service uses defaults)
    source_timelock_hours: int = 48
    target_timelock_hours: int = 24


class SwapResponse(BaseModel):
    id: str
    initiator_agent_id: str
    participant_agent_id: str
    source_chain_id: int
    target_chain_id: int
    hashlock: str
    status: SwapStatus
    source_timelock: int
    target_timelock: int

    class Config:
        orm_mode = True


class SwapActionRequest(BaseModel):
    tx_hash: str  # The hash of the on-chain transaction that performed the action


class SwapCompleteRequest(SwapActionRequest):
    secret: str  # Required when completing
