"""
Multi-Modal Fusion Model Domain Model

Migrated from contexts/agent_coordination/domain/agent_performance.py in v0.5.14.
The multimodal context is the sole consumer of this model (fusion engine), so
ownership moved here to eliminate the cross-context domain-model import. The
SQLModel table name (`fusion_models`) is unchanged — no DB migration required.
"""

from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from sqlmodel import JSON, Column, Field, SQLModel


class FusionModel(SQLModel, table=True):
    """Multi-modal agent fusion models"""

    __tablename__ = "fusion_models"
    __table_args__ = {"extend_existing": True}

    id: str = Field(default_factory=lambda: f"fusion_{uuid4().hex[:8]}", primary_key=True)
    fusion_id: str = Field(unique=True, index=True)

    # Model identification
    model_name: str = Field(max_length=100)
    fusion_type: str = Field(max_length=50)  # ensemble, hybrid, multi_modal, cross_domain
    model_version: str = Field(default="1.0.0")

    # Component models
    base_models: list[str] = Field(default_factory=list, sa_column=Column(JSON))
    model_weights: dict[str, float] = Field(default_factory=dict, sa_column=Column(JSON))
    fusion_strategy: str = Field(default="weighted_average")

    # Input modalities
    input_modalities: list[str] = Field(default_factory=list, sa_column=Column(JSON))
    modality_weights: dict[str, float] = Field(default_factory=dict, sa_column=Column(JSON))

    # Performance metrics
    fusion_performance: dict[str, float] = Field(default_factory=dict, sa_column=Column(JSON))
    synergy_score: float = Field(default=0.0, ge=0, le=1.0)
    robustness_score: float = Field(default=0.0, ge=0, le=1.0)

    # Resource requirements
    computational_complexity: str = Field(default="medium")  # low, medium, high, very_high
    memory_requirement: float = Field(default=0.0)  # GB
    inference_time: float = Field(default=0.0)  # seconds

    # Training data
    training_datasets: list[str] = Field(default_factory=list, sa_column=Column(JSON))
    data_requirements: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))

    # Deployment status
    status: str = Field(default="training")  # training, ready, deployed, deprecated
    deployment_count: int = Field(default=0)
    performance_stability: float = Field(default=0.0, ge=0, le=1.0)

    # Timestamps
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    trained_at: datetime | None = None
    deployed_at: datetime | None = None

    # Additional data
    fusion_profile_meta_data: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))
    training_logs: list[dict[str, Any]] = Field(default_factory=list, sa_column=Column(JSON))
