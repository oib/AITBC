"""
Advanced Agent Performance Domain Models
Implements SQLModel definitions for meta-learning, resource management, and performance optimization
"""

from datetime import datetime, UTC
from enum import StrEnum
from typing import Any
from uuid import uuid4

from sqlmodel import JSON, Column, Field, SQLModel


class LearningStrategy(StrEnum):
    """Learning strategy enumeration"""

    META_LEARNING = "meta_learning"
    TRANSFER_LEARNING = "transfer_learning"
    REINFORCEMENT_LEARNING = "reinforcement_learning"
    SUPERVISED_LEARNING = "supervised_learning"
    UNSUPERVISED_LEARNING = "unsupervised_learning"
    FEDERATED_LEARNING = "federated_learning"


class PerformanceMetric(StrEnum):
    """Performance metric enumeration"""

    ACCURACY = "accuracy"
    PRECISION = "precision"
    RECALL = "recall"
    F1_SCORE = "f1_score"
    LATENCY = "latency"
    THROUGHPUT = "throughput"
    RESOURCE_EFFICIENCY = "resource_efficiency"
    COST_EFFICIENCY = "cost_efficiency"
    ADAPTATION_SPEED = "adaptation_speed"
    GENERALIZATION = "generalization"


class ResourceType(StrEnum):
    """Resource type enumeration"""

    CPU = "cpu"
    GPU = "gpu"
    MEMORY = "memory"
    STORAGE = "storage"
    NETWORK = "network"
    CACHE = "cache"


class OptimizationTarget(StrEnum):
    """Optimization target enumeration"""

    SPEED = "speed"
    ACCURACY = "accuracy"
    EFFICIENCY = "efficiency"
    COST = "cost"
    SCALABILITY = "scalability"
    RELIABILITY = "reliability"


class AgentPerformanceProfile(SQLModel, table=True):
    """Agent performance profiles and metrics"""

    __tablename__ = "agent_performance_profiles"
    __table_args__ = {"extend_existing": True}

    id: str = Field(default_factory=lambda: f"perf_{uuid4().hex[:8]}", primary_key=True)
    profile_id: str = Field(unique=True, index=True)

    # Agent identification
    agent_id: str = Field(index=True)
    agent_type: str = Field(default="openclaw")
    agent_version: str = Field(default="1.0.0")

    # Performance metrics
    overall_score: float = Field(default=0.0, ge=0, le=100)
    performance_metrics: dict[str, float] = Field(default={}, sa_column=Column(JSON))

    # Learning capabilities
    learning_strategies: list[str] = Field(default=[], sa_column=Column(JSON))
    adaptation_rate: float = Field(default=0.0, ge=0, le=1.0)
    generalization_score: float = Field(default=0.0, ge=0, le=1.0)

    # Resource utilization
    resource_efficiency: dict[str, float] = Field(default={}, sa_column=Column(JSON))
    cost_per_task: float = Field(default=0.0)
    throughput: float = Field(default=0.0)
    average_latency: float = Field(default=0.0)

    # Specialization areas
    specialization_areas: list[str] = Field(default=[], sa_column=Column(JSON))
    expertise_levels: dict[str, float] = Field(default={}, sa_column=Column(JSON))

    # Performance history
    performance_history: list[dict[str, Any]] = Field(default=[], sa_column=Column(JSON))
    improvement_trends: dict[str, float] = Field(default={}, sa_column=Column(JSON))

    # Benchmarking
    benchmark_scores: dict[str, float] = Field(default={}, sa_column=Column(JSON))
    ranking_position: int | None = None
    percentile_rank: float | None = None

    # Timestamps
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    last_assessed: datetime | None = None

    # Additional data
    profile_meta_data: dict[str, Any] = Field(default={}, sa_column=Column(JSON))
    performance_notes: str = Field(default="", max_length=1000)


class MetaLearningModel(SQLModel, table=True):
    """Meta-learning models and configurations"""

    __tablename__ = "meta_learning_models"
    __table_args__ = {"extend_existing": True}

    id: str = Field(default_factory=lambda: f"meta_{uuid4().hex[:8]}", primary_key=True)
    model_id: str = Field(unique=True, index=True)

    # Model identification
    model_name: str = Field(max_length=100)
    model_type: str = Field(default="meta_learning")
    model_version: str = Field(default="1.0.0")

    # Learning configuration
    base_algorithms: list[str] = Field(default=[], sa_column=Column(JSON))
    meta_strategy: LearningStrategy
    adaptation_targets: list[str] = Field(default=[], sa_column=Column(JSON))

    # Training data
    training_tasks: list[str] = Field(default=[], sa_column=Column(JSON))
    task_distributions: dict[str, float] = Field(default={}, sa_column=Column(JSON))
    meta_features: list[str] = Field(default=[], sa_column=Column(JSON))

    # Model performance
    meta_accuracy: float = Field(default=0.0, ge=0, le=1.0)
    adaptation_speed: float = Field(default=0.0, ge=0, le=1.0)
    generalization_ability: float = Field(default=0.0, ge=0, le=1.0)

    # Resource requirements
    training_time: float | None = None  # hours
    computational_cost: float | None = None  # cost units
    memory_requirement: float | None = None  # GB
    gpu_requirement: bool | None = Field(default=False)

    # Deployment status
    status: str = Field(default="training")  # training, ready, deployed, deprecated
    deployment_count: int = Field(default=0)
    success_rate: float = Field(default=0.0, ge=0, le=1.0)

    # Timestamps
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    trained_at: datetime | None = None
    deployed_at: datetime | None = None

    # Additional data
    model_profile_meta_data: dict[str, Any] = Field(default={}, sa_column=Column(JSON))
    training_logs: list[dict[str, Any]] = Field(default=[], sa_column=Column(JSON))


class ResourceAllocation(SQLModel, table=True):
    """Resource allocation and optimization records"""

    __tablename__ = "resource_allocations"
    __table_args__ = {"extend_existing": True}

    id: str = Field(default_factory=lambda: f"alloc_{uuid4().hex[:8]}", primary_key=True)
    allocation_id: str = Field(unique=True, index=True)

    # Allocation details
    agent_id: str = Field(index=True)
    task_id: str | None = None
    session_id: str | None = None

    # Resource requirements
    cpu_cores: float = Field(default=1.0)
    memory_gb: float = Field(default=2.0)
    gpu_count: float = Field(default=0.0)
    gpu_memory_gb: float = Field(default=0.0)
    storage_gb: float = Field(default=10.0)
    network_bandwidth: float = Field(default=100.0)  # Mbps

    # Optimization targets
    optimization_target: OptimizationTarget
    priority_level: str = Field(default="normal")  # low, normal, high, critical

    # Performance metrics
    actual_performance: dict[str, float] = Field(default={}, sa_column=Column(JSON))
    efficiency_score: float = Field(default=0.0, ge=0, le=1.0)
    cost_efficiency: float = Field(default=0.0, ge=0, le=1.0)

    # Allocation status
    status: str = Field(default="pending")  # pending, allocated, active, completed, failed
    allocated_at: datetime | None = None
    started_at: datetime | None = None
    completed_at: datetime | None = None

    # Optimization results
    optimization_applied: bool = Field(default=False)
    optimization_savings: float = Field(default=0.0)
    performance_improvement: float = Field(default=0.0)

    # Timestamps
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.now(datetime.UTC))

    # Additional data
    allocation_profile_meta_data: dict[str, Any] = Field(default={}, sa_column=Column(JSON))
    resource_utilization: dict[str, float] = Field(default={}, sa_column=Column(JSON))


class PerformanceOptimization(SQLModel, table=True):
    """Performance optimization records and results"""

    __tablename__ = "performance_optimizations"
    __table_args__ = {"extend_existing": True}

    id: str = Field(default_factory=lambda: f"opt_{uuid4().hex[:8]}", primary_key=True)
    optimization_id: str = Field(unique=True, index=True)

    # Optimization details
    agent_id: str = Field(index=True)
    optimization_type: str = Field(max_length=50)  # resource, algorithm, hyperparameter, architecture
    target_metric: PerformanceMetric

    # Before optimization
    baseline_performance: dict[str, float] = Field(default={}, sa_column=Column(JSON))
    baseline_resources: dict[str, float] = Field(default={}, sa_column=Column(JSON))
    baseline_cost: float = Field(default=0.0)

    # Optimization configuration
    optimization_parameters: dict[str, Any] = Field(default={}, sa_column=Column(JSON))
    optimization_algorithm: str = Field(default="auto")
    search_space: dict[str, Any] = Field(default={}, sa_column=Column(JSON))

    # After optimization
    optimized_performance: dict[str, float] = Field(default={}, sa_column=Column(JSON))
    optimized_resources: dict[str, float] = Field(default={}, sa_column=Column(JSON))
    optimized_cost: float = Field(default=0.0)

    # Improvement metrics
    performance_improvement: float = Field(default=0.0)
    resource_savings: float = Field(default=0.0)
    cost_savings: float = Field(default=0.0)
    overall_efficiency_gain: float = Field(default=0.0)

    # Optimization process
    optimization_duration: float | None = None  # seconds
    iterations_required: int = Field(default=0)
    convergence_achieved: bool = Field(default=False)

    # Status and deployment
    status: str = Field(default="pending")  # pending, running, completed, failed, deployed
    applied_at: datetime | None = None
    rollback_available: bool = Field(default=True)

    # Timestamps
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    completed_at: datetime | None = None

    # Additional data
    optimization_profile_meta_data: dict[str, Any] = Field(default={}, sa_column=Column(JSON))
    performance_logs: list[dict[str, Any]] = Field(default=[], sa_column=Column(JSON))


class AgentCapability(SQLModel, table=True):
    """Agent capabilities and skill assessments"""

    __tablename__ = "agent_capabilities"
    __table_args__ = {"extend_existing": True}

    id: str = Field(default_factory=lambda: f"cap_{uuid4().hex[:8]}", primary_key=True)
    capability_id: str = Field(unique=True, index=True)

    # Capability details
    agent_id: str = Field(index=True)
    capability_name: str = Field(max_length=100)
    capability_type: str = Field(max_length=50)  # cognitive, creative, analytical, technical
    domain_area: str = Field(max_length=50)

    # Skill level assessment
    skill_level: float = Field(default=0.0, ge=0, le=10.0)
    proficiency_score: float = Field(default=0.0, ge=0, le=1.0)
    experience_years: float = Field(default=0.0)

    # Capability metrics
    performance_metrics: dict[str, float] = Field(default={}, sa_column=Column(JSON))
    success_rate: float = Field(default=0.0, ge=0, le=1.0)
    average_quality: float = Field(default=0.0, ge=0, le=5.0)

    # Learning and adaptation
    learning_rate: float = Field(default=0.0, ge=0, le=1.0)
    adaptation_speed: float = Field(default=0.0, ge=0, le=1.0)
    knowledge_retention: float = Field(default=0.0, ge=0, le=1.0)

    # Specialization
    specializations: list[str] = Field(default=[], sa_column=Column(JSON))
    sub_capabilities: list[str] = Field(default=[], sa_column=Column(JSON))
    tool_proficiency: dict[str, float] = Field(default={}, sa_column=Column(JSON))

    # Development history
    acquired_at: datetime = Field(default_factory=datetime.utcnow)
    last_improved: datetime | None = None
    improvement_count: int = Field(default=0)

    # Certification and validation
    certified: bool = Field(default=False)
    certification_level: str | None = None
    last_validated: datetime | None = None

    # Timestamps
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)

    # Additional data
    capability_profile_meta_data: dict[str, Any] = Field(default={}, sa_column=Column(JSON))
    training_history: list[dict[str, Any]] = Field(default=[], sa_column=Column(JSON))


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
    base_models: list[str] = Field(default=[], sa_column=Column(JSON))
    model_weights: dict[str, float] = Field(default={}, sa_column=Column(JSON))
    fusion_strategy: str = Field(default="weighted_average")

    # Input modalities
    input_modalities: list[str] = Field(default=[], sa_column=Column(JSON))
    modality_weights: dict[str, float] = Field(default={}, sa_column=Column(JSON))

    # Performance metrics
    fusion_performance: dict[str, float] = Field(default={}, sa_column=Column(JSON))
    synergy_score: float = Field(default=0.0, ge=0, le=1.0)
    robustness_score: float = Field(default=0.0, ge=0, le=1.0)

    # Resource requirements
    computational_complexity: str = Field(default="medium")  # low, medium, high, very_high
    memory_requirement: float = Field(default=0.0)  # GB
    inference_time: float = Field(default=0.0)  # seconds

    # Training data
    training_datasets: list[str] = Field(default=[], sa_column=Column(JSON))
    data_requirements: dict[str, Any] = Field(default={}, sa_column=Column(JSON))

    # Deployment status
    status: str = Field(default="training")  # training, ready, deployed, deprecated
    deployment_count: int = Field(default=0)
    performance_stability: float = Field(default=0.0, ge=0, le=1.0)

    # Timestamps
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    trained_at: datetime | None = None
    deployed_at: datetime | None = None

    # Additional data
    fusion_profile_meta_data: dict[str, Any] = Field(default={}, sa_column=Column(JSON))
    training_logs: list[dict[str, Any]] = Field(default=[], sa_column=Column(JSON))


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
    reward_history: list[float] = Field(default=[], sa_column=Column(JSON))
    success_rate_history: list[float] = Field(default=[], sa_column=Column(JSON))
    convergence_episode: int | None = None

    # Policy details
    policy_type: str = Field(default="stochastic")  # stochastic, deterministic
    action_space: list[str] = Field(default=[], sa_column=Column(JSON))
    state_space: list[str] = Field(default=[], sa_column=Column(JSON))

    # Status and deployment
    status: str = Field(default="training")  # training, ready, deployed, deprecated
    training_progress: float = Field(default=0.0, ge=0, le=1.0)
    deployment_performance: dict[str, float] = Field(default={}, sa_column=Column(JSON))

    # Timestamps
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    trained_at: datetime | None = None
    deployed_at: datetime | None = None

    # Additional data
    rl_profile_meta_data: dict[str, Any] = Field(default={}, sa_column=Column(JSON))
    training_logs: list[dict[str, Any]] = Field(default=[], sa_column=Column(JSON))


class CreativeCapability(SQLModel, table=True):
    """Creative and specialized AI capabilities"""

    __tablename__ = "creative_capabilities"
    __table_args__ = {"extend_existing": True}

    id: str = Field(default_factory=lambda: f"creative_{uuid4().hex[:8]}", primary_key=True)
    capability_id: str = Field(unique=True, index=True)

    # Capability details
    agent_id: str = Field(index=True)
    creative_domain: str = Field(max_length=50)  # art, music, writing, design, innovation
    capability_type: str = Field(max_length=50)  # generative, compositional, analytical, innovative

    # Creative metrics
    originality_score: float = Field(default=0.0, ge=0, le=1.0)
    novelty_score: float = Field(default=0.0, ge=0, le=1.0)
    aesthetic_quality: float = Field(default=0.0, ge=0, le=5.0)
    coherence_score: float = Field(default=0.0, ge=0, le=1.0)

    # Generation capabilities
    generation_models: list[str] = Field(default=[], sa_column=Column(JSON))
    style_variety: int = Field(default=1)
    output_quality: float = Field(default=0.0, ge=0, le=5.0)

    # Learning and adaptation
    creative_learning_rate: float = Field(default=0.0, ge=0, le=1.0)
    style_adaptation: float = Field(default=0.0, ge=0, le=1.0)
    cross_domain_transfer: float = Field(default=0.0, ge=0, le=1.0)

    # Specialization
    creative_specializations: list[str] = Field(default=[], sa_column=Column(JSON))
    tool_proficiency: dict[str, float] = Field(default={}, sa_column=Column(JSON))
    domain_knowledge: dict[str, float] = Field(default={}, sa_column=Column(JSON))

    # Performance tracking
    creations_generated: int = Field(default=0)
    user_ratings: list[float] = Field(default=[], sa_column=Column(JSON))
    expert_evaluations: list[dict[str, Any]] = Field(default=[], sa_column=Column(JSON))

    # Status and certification
    status: str = Field(default="developing")  # developing, ready, certified, deprecated
    certification_level: str | None = None
    last_evaluation: datetime | None = None

    # Timestamps
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)

    # Additional data
    creative_profile_meta_data: dict[str, Any] = Field(default={}, sa_column=Column(JSON))
    portfolio_samples: list[dict[str, Any]] = Field(default=[], sa_column=Column(JSON))
