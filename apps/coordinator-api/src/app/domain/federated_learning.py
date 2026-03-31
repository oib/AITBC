"""
Federated Learning Domain Models

Domain models for managing cross-agent knowledge sharing and collaborative model training.
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from uuid import uuid4

from sqlalchemy import JSON, Column
from sqlmodel import Field, SQLModel


class TrainingStatus(StrEnum):
    INITIALIZED = "initiated"
    GATHERING_PARTICIPANTS = "gathering_participants"
    TRAINING = "training"
    AGGREGATING = "aggregating"
    COMPLETED = "completed"
    FAILED = "failed"


class ParticipantStatus(StrEnum):
    INVITED = "invited"
    JOINED = "joined"
    TRAINING = "training"
    SUBMITTED = "submitted"
    DROPPED = "dropped"


class FederatedLearningSession(SQLModel, table=True):
    """Represents a collaborative training session across multiple agents"""

    __tablename__ = "federated_learning_session"

    id: str = Field(default_factory=lambda: uuid4().hex, primary_key=True)
    initiator_agent_id: str = Field(index=True)
    task_description: str = Field()
    model_architecture_cid: str = Field()  # IPFS CID pointing to model structure definition
    initial_weights_cid: str | None = Field(default=None)  # Optional starting point

    target_participants: int = Field(default=3)
    current_round: int = Field(default=0)
    total_rounds: int = Field(default=10)

    aggregation_strategy: str = Field(default="fedavg")  # e.g. fedavg, fedprox
    min_participants_per_round: int = Field(default=2)

    reward_pool_amount: float = Field(default=0.0)  # Total AITBC allocated to reward participants

    status: TrainingStatus = Field(default=TrainingStatus.INITIALIZED, index=True)

    global_model_cid: str | None = Field(default=None)  # Final aggregated model

    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)

    # Relationships
    # DISABLED:     participants: List["TrainingParticipant"] = Relationship(back_populates="session")
    # DISABLED:     rounds: List["TrainingRound"] = Relationship(back_populates="session")


class TrainingParticipant(SQLModel, table=True):
    """An agent participating in a federated learning session"""

    __tablename__ = "training_participant"

    id: str = Field(default_factory=lambda: uuid4().hex, primary_key=True)
    session_id: str = Field(foreign_key="federated_learning_session.id", index=True)
    agent_id: str = Field(index=True)

    status: ParticipantStatus = Field(default=ParticipantStatus.JOINED, index=True)
    data_samples_count: int = Field(default=0)  # Claimed number of local samples used
    compute_power_committed: float = Field(default=0.0)  # TFLOPS

    reputation_score_at_join: float = Field(default=0.0)
    earned_reward: float = Field(default=0.0)

    joined_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)

    # Relationships
    # DISABLED:     session: FederatedLearningSession = Relationship(back_populates="participants")


class TrainingRound(SQLModel, table=True):
    """A specific round of federated learning"""

    __tablename__ = "training_round"

    id: str = Field(default_factory=lambda: uuid4().hex, primary_key=True)
    session_id: str = Field(foreign_key="federated_learning_session.id", index=True)
    round_number: int = Field()

    status: str = Field(default="pending")  # pending, active, aggregating, completed

    starting_model_cid: str = Field()  # Global model weights at start of round
    aggregated_model_cid: str | None = Field(default=None)  # Resulting weights after round

    metrics: dict[str, float] = Field(default_factory=dict, sa_column=Column(JSON))  # e.g. loss, accuracy

    started_at: datetime = Field(default_factory=datetime.utcnow)
    completed_at: datetime | None = Field(default=None)

    # Relationships
    # DISABLED:     session: FederatedLearningSession = Relationship(back_populates="rounds")
    # DISABLED:     updates: List["LocalModelUpdate"] = Relationship(back_populates="round")


class LocalModelUpdate(SQLModel, table=True):
    """A local model update submitted by a participant for a specific round"""

    __tablename__ = "local_model_update"

    id: str = Field(default_factory=lambda: uuid4().hex, primary_key=True)
    round_id: str = Field(foreign_key="training_round.id", index=True)
    participant_agent_id: str = Field(index=True)

    weights_cid: str = Field()  # IPFS CID of the locally trained weights
    zk_proof_hash: str | None = Field(default=None)  # Proof that training was executed correctly

    is_aggregated: bool = Field(default=False)
    rejected_reason: str | None = Field(default=None)  # e.g. "outlier", "failed zk verification"

    submitted_at: datetime = Field(default_factory=datetime.utcnow)

    # Relationships
    # DISABLED:     round: TrainingRound = Relationship(back_populates="updates")
