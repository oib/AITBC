"""
Reinforcement Learning Configuration Domain Model

Migrated from contexts/agent_coordination/domain/agent_performance.py in v0.5.14.
The advanced_rl context is the sole consumer of this model (engine + marketplace
optimizer), so ownership moved here to eliminate the cross-context domain-model
import. The SQLModel table name (`rl_configurations`) is unchanged — no DB
migration required.
"""

from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from sqlmodel import JSON, Column, Field, SQLModel


class ReinforcementLearningConfig(SQLModel, table=True):
    """Reinforcement learning configurations and policies"""

    __tablename__ = "rl_configurations"
    __table_args__ = {"extend_existing": True}

    id: str = Field(default_factory=lambda: f"rl_{uuid4().hex[:8]}", primary_key=True)
    config_id: str = Field(unique=True, index=True)

    # Configuration details
    agent_id: str = Field(index=True)
    environment_type: str = Field(max_length=50)
    algorithm: str = Field(default="ppo")  # ppo, a2c, dqn, sac, td3

    # Learning parameters
    learning_rate: float = Field(default=0.001)
    discount_factor: float = Field(default=0.99)
    exploration_rate: float = Field(default=0.1)
    batch_size: int = Field(default=64)

    # Network architecture
    network_layers: list[int] = Field(default=[256, 256, 128], sa_column=Column(JSON))
    activation_functions: list[str] = Field(default=["relu", "relu", "tanh"], sa_column=Column(JSON))

    # Training configuration
    max_episodes: int = Field(default=1000)
    max_steps_per_episode: int = Field(default=1000)
    save_frequency: int = Field(default=100)

    # Performance metrics
    reward_history: list[float] = Field(default_factory=list, sa_column=Column(JSON))
    success_rate_history: list[float] = Field(default_factory=list, sa_column=Column(JSON))
    convergence_episode: int | None = None

    # Policy details
    policy_type: str = Field(default="stochastic")  # stochastic, deterministic
    action_space: list[str] = Field(default_factory=list, sa_column=Column(JSON))
    state_space: list[str] = Field(default_factory=list, sa_column=Column(JSON))

    # Status and deployment
    status: str = Field(default="training")  # training, ready, deployed, deprecated
    training_progress: float = Field(default=0.0, ge=0, le=1.0)
    deployment_performance: dict[str, float] = Field(default_factory=dict, sa_column=Column(JSON))

    # Timestamps
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    trained_at: datetime | None = None
    deployed_at: datetime | None = None

    # Additional data
    rl_profile_meta_data: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))
    training_logs: list[dict[str, Any]] = Field(default_factory=list, sa_column=Column(JSON))
