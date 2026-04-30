"""
AI Agent Domain Models for Verifiable AI Agent Orchestration
Implements SQLModel definitions for agent workflows, steps, and execution tracking
"""

from datetime import datetime
from enum import StrEnum
from typing import Any
from uuid import uuid4

from sqlmodel import JSON, Column, Field, SQLModel


class AgentStatus(StrEnum):
    """Agent execution status enumeration"""

    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class VerificationLevel(StrEnum):
    """Verification level for agent execution"""

    BASIC = "basic"
    FULL = "full"
    ZERO_KNOWLEDGE = "zero-knowledge"


class StepType(StrEnum):
    """Agent step type enumeration"""

    INFERENCE = "inference"
    TRAINING = "training"
    DATA_PROCESSING = "data_processing"
    VERIFICATION = "verification"
    CUSTOM = "custom"


class AIAgentWorkflow(SQLModel, table=True):
    """Definition of an AI agent workflow"""

    __tablename__ = "ai_agent_workflows"
    __table_args__ = {"extend_existing": True}

    id: str = Field(default_factory=lambda: f"agent_{uuid4().hex[:8]}", primary_key=True)
    owner_id: str = Field(index=True)
    name: str = Field(max_length=100)
    description: str = Field(default="")

    # Workflow specification
    steps: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON, nullable=False))
    dependencies: dict[str, list[str]] = Field(default_factory=dict, sa_column=Column(JSON, nullable=False))

    # Execution constraints
    max_execution_time: int = Field(default=3600)  # seconds
    max_cost_budget: float = Field(default=0.0)

    # Verification requirements
    requires_verification: bool = Field(default=True)
    verification_level: VerificationLevel = Field(default=VerificationLevel.BASIC)

    # Metadata
    tags: str = Field(default="")  # JSON string of tags
    version: str = Field(default="1.0.0")
    is_public: bool = Field(default=False)

    # Timestamps
    created_at: datetime = Field(default_factory=datetime.now(datetime.UTC))
    updated_at: datetime = Field(default_factory=datetime.now(datetime.UTC))


class AgentStep(SQLModel, table=True):
    """Individual step in an AI agent workflow"""

    __tablename__ = "agent_steps"
    __table_args__ = {"extend_existing": True}

    id: str = Field(default_factory=lambda: f"step_{uuid4().hex[:8]}", primary_key=True)
    workflow_id: str = Field(index=True)
    step_order: int = Field(default=0)

    # Step specification
    name: str = Field(max_length=100)
    step_type: StepType = Field(default=StepType.INFERENCE)
    model_requirements: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))
    input_mappings: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))
    output_mappings: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))

    # Execution parameters
    timeout_seconds: int = Field(default=300)
    retry_policy: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))
    max_retries: int = Field(default=3)

    # Verification
    requires_proof: bool = Field(default=False)
    verification_level: VerificationLevel = Field(default=VerificationLevel.BASIC)

    # Dependencies
    depends_on: str = Field(default="")  # JSON string of step IDs

    # Timestamps
    created_at: datetime = Field(default_factory=datetime.now(datetime.UTC))
    updated_at: datetime = Field(default_factory=datetime.now(datetime.UTC))


class AgentExecution(SQLModel, table=True):
    """Tracks execution state of AI agent workflows"""

    __tablename__ = "agent_executions"
    __table_args__ = {"extend_existing": True}

    id: str = Field(default_factory=lambda: f"exec_{uuid4().hex[:10]}", primary_key=True)
    workflow_id: str = Field(index=True)
    client_id: str = Field(index=True)

    # Execution state
    status: AgentStatus = Field(default=AgentStatus.PENDING)
    current_step: int = Field(default=0)
    step_states: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON, nullable=False))

    # Results and verification
    final_result: dict[str, Any] | None = Field(default=None, sa_column=Column(JSON))
    execution_receipt: dict[str, Any] | None = Field(default=None, sa_column=Column(JSON))
    verification_proof: dict[str, Any] | None = Field(default=None, sa_column=Column(JSON))

    # Error handling
    error_message: str | None = Field(default=None)
    failed_step: str | None = Field(default=None)

    # Timing and cost
    started_at: datetime | None = Field(default=None)
    completed_at: datetime | None = Field(default=None)
    total_execution_time: float | None = Field(default=None)  # seconds
    total_cost: float = Field(default=0.0)

    # Progress tracking
    total_steps: int = Field(default=0)
    completed_steps: int = Field(default=0)

    # Timestamps
    created_at: datetime = Field(default_factory=datetime.now(datetime.UTC))
    updated_at: datetime = Field(default_factory=datetime.now(datetime.UTC))


class AgentStepExecution(SQLModel, table=True):
    """Tracks execution of individual steps within an agent workflow"""

    __tablename__ = "agent_step_executions"
    __table_args__ = {"extend_existing": True}

    id: str = Field(default_factory=lambda: f"step_exec_{uuid4().hex[:10]}", primary_key=True)
    execution_id: str = Field(index=True)
    step_id: str = Field(index=True)

    # Execution state
    status: AgentStatus = Field(default=AgentStatus.PENDING)

    # Step-specific data
    input_data: dict[str, Any] | None = Field(default=None, sa_column=Column(JSON))
    output_data: dict[str, Any] | None = Field(default=None, sa_column=Column(JSON))

    # Performance metrics
    execution_time: float | None = Field(default=None)  # seconds
    gpu_accelerated: bool = Field(default=False)
    memory_usage: float | None = Field(default=None)  # MB

    # Verification
    step_proof: dict[str, Any] | None = Field(default=None, sa_column=Column(JSON))
    verification_status: str | None = Field(default=None)

    # Error handling
    error_message: str | None = Field(default=None)
    retry_count: int = Field(default=0)

    # Timing
    started_at: datetime | None = Field(default=None)
    completed_at: datetime | None = Field(default=None)

    # Timestamps
    created_at: datetime = Field(default_factory=datetime.now(datetime.UTC))
    updated_at: datetime = Field(default_factory=datetime.now(datetime.UTC))


class AgentMarketplace(SQLModel, table=True):
    """Marketplace for AI agent workflows"""

    __tablename__ = "agent_marketplace"
    __table_args__ = {"extend_existing": True}

    id: str = Field(default_factory=lambda: f"amkt_{uuid4().hex[:8]}", primary_key=True)
    workflow_id: str = Field(index=True)

    # Marketplace metadata
    title: str = Field(max_length=200)
    description: str = Field(default="")
    tags: str = Field(default="")  # JSON string of tags
    category: str = Field(default="general")

    # Pricing
    execution_price: float = Field(default=0.0)
    subscription_price: float = Field(default=0.0)
    pricing_model: str = Field(default="pay-per-use")  # pay-per-use, subscription, freemium

    # Reputation and usage
    rating: float = Field(default=0.0)
    total_executions: int = Field(default=0)
    successful_executions: int = Field(default=0)
    average_execution_time: float | None = Field(default=None)

    # Access control
    is_public: bool = Field(default=True)
    authorized_users: str = Field(default="")  # JSON string of authorized users

    # Performance metrics
    last_execution_status: AgentStatus | None = Field(default=None)
    last_execution_at: datetime | None = Field(default=None)

    # Timestamps
    created_at: datetime = Field(default_factory=datetime.now(datetime.UTC))
    updated_at: datetime = Field(default_factory=datetime.now(datetime.UTC))


# Request/Response Models for API
class AgentWorkflowCreate(SQLModel):
    """Request model for creating agent workflows"""

    name: str = Field(max_length=100)
    description: str = Field(default="")
    steps: dict[str, Any]
    dependencies: dict[str, list[str]] = Field(default_factory=dict)
    max_execution_time: int = Field(default=3600)
    max_cost_budget: float = Field(default=0.0)
    requires_verification: bool = Field(default=True)
    verification_level: VerificationLevel = Field(default=VerificationLevel.BASIC)
    tags: list[str] = Field(default_factory=list)
    is_public: bool = Field(default=False)


class AgentWorkflowUpdate(SQLModel):
    """Request model for updating agent workflows"""

    name: str | None = Field(default=None, max_length=100)
    description: str | None = Field(default=None)
    steps: dict[str, Any] | None = Field(default=None)
    dependencies: dict[str, list[str]] | None = Field(default=None)
    max_execution_time: int | None = Field(default=None)
    max_cost_budget: float | None = Field(default=None)
    requires_verification: bool | None = Field(default=None)
    verification_level: VerificationLevel | None = Field(default=None)
    tags: list[str] | None = Field(default=None)
    is_public: bool | None = Field(default=None)


class AgentExecutionRequest(SQLModel):
    """Request model for executing agent workflows"""

    workflow_id: str
    inputs: dict[str, Any]
    verification_level: VerificationLevel | None = Field(default=VerificationLevel.BASIC)
    max_execution_time: int | None = Field(default=None)
    max_cost_budget: float | None = Field(default=None)


class AgentExecutionResponse(SQLModel):
    """Response model for agent execution"""

    execution_id: str
    workflow_id: str
    status: AgentStatus
    current_step: int
    total_steps: int
    started_at: datetime | None
    estimated_completion: datetime | None
    current_cost: float
    estimated_total_cost: float | None


class AgentExecutionStatus(SQLModel):
    """Response model for execution status"""

    execution_id: str
    workflow_id: str
    status: AgentStatus
    current_step: int
    total_steps: int
    step_states: dict[str, Any]
    final_result: dict[str, Any] | None
    error_message: str | None
    started_at: datetime | None
    completed_at: datetime | None
    total_execution_time: float | None
    total_cost: float
    verification_proof: dict[str, Any] | None
