"""
Domain model protocols for agent execution.
These protocols define the interface for agent-related domain models
without coupling to specific app implementations.
"""

from abc import ABC, abstractmethod
from enum import Enum
from typing import Any


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


class IAgentExecution(ABC):
    """Protocol for agent execution domain model"""

    @property
    @abstractmethod
    def id(self) -> str:
        """Unique identifier for the execution"""
        ...

    @property
    @abstractmethod
    def workflow_id(self) -> str:
        """ID of the workflow being executed"""
        ...

    @property
    @abstractmethod
    def status(self) -> AgentStatus:
        """Current execution status"""
        ...

    @property
    @abstractmethod
    def verification_level(self) -> VerificationLevel:
        """Required verification level"""
        ...

    @abstractmethod
    def to_dict(self) -> dict[str, Any]:
        """Convert execution to dictionary representation"""
        ...


class IAgentStepExecution(ABC):
    """Protocol for agent step execution domain model"""

    @property
    @abstractmethod
    def id(self) -> str:
        """Unique identifier for the step execution"""
        ...

    @property
    @abstractmethod
    def execution_id(self) -> str:
        """ID of the parent execution"""
        ...

    @property
    @abstractmethod
    def step_type(self) -> StepType:
        """Type of step being executed"""
        ...

    @abstractmethod
    def to_dict(self) -> dict[str, Any]:
        """Convert step execution to dictionary representation"""
        ...
