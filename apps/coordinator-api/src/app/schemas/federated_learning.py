from pydantic import BaseModel
from typing import Optional, Dict
from .federated_learning import TrainingStatus

class FederatedSessionCreate(BaseModel):
    initiator_agent_id: str
    task_description: str
    model_architecture_cid: str
    initial_weights_cid: Optional[str] = None
    target_participants: int = 3
    total_rounds: int = 10
    aggregation_strategy: str = "fedavg"
    min_participants_per_round: int = 2
    reward_pool_amount: float = 0.0

class FederatedSessionResponse(BaseModel):
    id: str
    initiator_agent_id: str
    task_description: str
    target_participants: int
    current_round: int
    total_rounds: int
    status: TrainingStatus
    global_model_cid: Optional[str]

    class Config:
        orm_mode = True

class JoinSessionRequest(BaseModel):
    agent_id: str
    compute_power_committed: float

class SubmitUpdateRequest(BaseModel):
    agent_id: str
    weights_cid: str
    zk_proof_hash: Optional[str] = None
    data_samples_count: int
