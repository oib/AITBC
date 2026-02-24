"""
AI Agent Domain Models for Verifiable AI Agent Orchestration
Implements SQLModel definitions for agent workflows, steps, and execution tracking
"""

from datetime import datetime
from typing import Optional, Dict, List, Any
from uuid import uuid4
from enum import Enum

from sqlmodel import SQLModel, Field, Column, JSON
from sqlalchemy import DateTime


class AgentStatus(str, Enum):
    """Agent execution status enumeration"""
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class VerificationLevel(str, Enum):
    """Verification level for agent execution"""
    BASIC = "basic"
    FULL = "full"
    ZERO_KNOWLEDGE = "zero-knowledge"


class StepType(str, Enum):
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
    steps: Dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON, nullable=False))
    dependencies: Dict[str, List[str]] = Field(default_factory=dict, sa_column=Column(JSON, nullable=False))
    
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
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)


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
    model_requirements: Dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))
    input_mappings: Dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))
    output_mappings: Dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))
    
    # Execution parameters
    timeout_seconds: int = Field(default=300)
    retry_policy: Dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))
    max_retries: int = Field(default=3)
    
    # Verification
    requires_proof: bool = Field(default=False)
    verification_level: VerificationLevel = Field(default=VerificationLevel.BASIC)
    
    # Dependencies
    depends_on: str = Field(default="")  # JSON string of step IDs
    
    # Timestamps
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)


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
    step_states: Dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON, nullable=False))
    
    # Results and verification
    final_result: Optional[Dict[str, Any]] = Field(default=None, sa_column=Column(JSON))
    execution_receipt: Optional[Dict[str, Any]] = Field(default=None, sa_column=Column(JSON))
    verification_proof: Optional[Dict[str, Any]] = Field(default=None, sa_column=Column(JSON))
    
    # Error handling
    error_message: Optional[str] = Field(default=None)
    failed_step: Optional[str] = Field(default=None)
    
    # Timing and cost
    started_at: Optional[datetime] = Field(default=None)
    completed_at: Optional[datetime] = Field(default=None)
    total_execution_time: Optional[float] = Field(default=None)  # seconds
    total_cost: float = Field(default=0.0)
    
    # Progress tracking
    total_steps: int = Field(default=0)
    completed_steps: int = Field(default=0)
    
    # Timestamps
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)


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
    input_data: Optional[Dict[str, Any]] = Field(default=None, sa_column=Column(JSON))
    output_data: Optional[Dict[str, Any]] = Field(default=None, sa_column=Column(JSON))
    
    # Performance metrics
    execution_time: Optional[float] = Field(default=None)  # seconds
    gpu_accelerated: bool = Field(default=False)
    memory_usage: Optional[float] = Field(default=None)  # MB
    
    # Verification
    step_proof: Optional[Dict[str, Any]] = Field(default=None, sa_column=Column(JSON))
    verification_status: Optional[str] = Field(default=None)
    
    # Error handling
    error_message: Optional[str] = Field(default=None)
    retry_count: int = Field(default=0)
    
    # Timing
    started_at: Optional[datetime] = Field(default=None)
    completed_at: Optional[datetime] = Field(default=None)
    
    # Timestamps
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)


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
    average_execution_time: Optional[float] = Field(default=None)
    
    # Access control
    is_public: bool = Field(default=True)
    authorized_users: str = Field(default="")  # JSON string of authorized users
    
    # Performance metrics
    last_execution_status: Optional[AgentStatus] = Field(default=None)
    last_execution_at: Optional[datetime] = Field(default=None)
    
    # Timestamps
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)


# Request/Response Models for API
class AgentWorkflowCreate(SQLModel):
    """Request model for creating agent workflows"""
    name: str = Field(max_length=100)
    description: str = Field(default="")
    steps: Dict[str, Any]
    dependencies: Dict[str, List[str]] = Field(default_factory=dict)
    max_execution_time: int = Field(default=3600)
    max_cost_budget: float = Field(default=0.0)
    requires_verification: bool = Field(default=True)
    verification_level: VerificationLevel = Field(default=VerificationLevel.BASIC)
    tags: List[str] = Field(default_factory=list)
    is_public: bool = Field(default=False)


class AgentWorkflowUpdate(SQLModel):
    """Request model for updating agent workflows"""
    name: Optional[str] = Field(default=None, max_length=100)
    description: Optional[str] = Field(default=None)
    steps: Optional[Dict[str, Any]] = Field(default=None)
    dependencies: Optional[Dict[str, List[str]]] = Field(default=None)
    max_execution_time: Optional[int] = Field(default=None)
    max_cost_budget: Optional[float] = Field(default=None)
    requires_verification: Optional[bool] = Field(default=None)
    verification_level: Optional[VerificationLevel] = Field(default=None)
    tags: Optional[List[str]] = Field(default=None)
    is_public: Optional[bool] = Field(default=None)


class AgentExecutionRequest(SQLModel):
    """Request model for executing agent workflows"""
    workflow_id: str
    inputs: Dict[str, Any]
    verification_level: Optional[VerificationLevel] = Field(default=VerificationLevel.BASIC)
    max_execution_time: Optional[int] = Field(default=None)
    max_cost_budget: Optional[float] = Field(default=None)


class AgentExecutionResponse(SQLModel):
    """Response model for agent execution"""
    execution_id: str
    workflow_id: str
    status: AgentStatus
    current_step: int
    total_steps: int
    started_at: Optional[datetime]
    estimated_completion: Optional[datetime]
    current_cost: float
    estimated_total_cost: Optional[float]


class AgentExecutionStatus(SQLModel):
    """Response model for execution status"""
    execution_id: str
    workflow_id: str
    status: AgentStatus
    current_step: int
    total_steps: int
    step_states: Dict[str, Any]
    final_result: Optional[Dict[str, Any]]
    error_message: Optional[str]
    started_at: Optional[datetime]
    completed_at: Optional[datetime]
    total_execution_time: Optional[float]
    total_cost: float
    verification_proof: Optional[Dict[str, Any]]
