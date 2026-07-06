"""
Task Decomposition Service for agent Autonomous Economics
Implements intelligent task splitting and sub-task management
"""

from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum

from aitbc.aitbc_logging import get_logger

logger = get_logger(__name__)


class TaskType(StrEnum):
    """Types of tasks"""

    TEXT_PROCESSING = "text_processing"
    IMAGE_PROCESSING = "image_processing"
    AUDIO_PROCESSING = "audio_processing"
    VIDEO_PROCESSING = "video_processing"
    DATA_ANALYSIS = "data_analysis"
    MODEL_INFERENCE = "model_inference"
    MODEL_TRAINING = "model_training"
    COMPUTE_INTENSIVE = "compute_intensive"
    IO_BOUND = "io_bound"
    MIXED_MODAL = "mixed_modal"


class SubTaskStatus(StrEnum):
    """Sub-task status"""

    PENDING = "pending"
    ASSIGNED = "assigned"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class DependencyType(StrEnum):
    """Dependency types between sub-tasks"""

    SEQUENTIAL = "sequential"
    PARALLEL = "parallel"
    CONDITIONAL = "conditional"
    AGGREGATION = "aggregation"


class GPU_Tier(StrEnum):
    """GPU resource tiers"""

    CPU_ONLY = "cpu_only"
    LOW_END_GPU = "low_end_gpu"
    MID_RANGE_GPU = "mid_range_gpu"
    HIGH_END_GPU = "high_end_gpu"
    PREMIUM_GPU = "premium_gpu"


@dataclass
class TaskRequirement:
    """Requirements for a task or sub-task"""

    task_type: TaskType
    estimated_duration: float
    gpu_tier: GPU_Tier
    memory_requirement: int
    compute_intensity: float
    data_size: int
    priority: int
    deadline: datetime | None = None
    max_cost: float | None = None


@dataclass
class SubTask:
    """Individual sub-task"""

    sub_task_id: str
    parent_task_id: str
    name: str
    description: str
    requirements: TaskRequirement
    status: SubTaskStatus = SubTaskStatus.PENDING
    assigned_agent: str | None = None
    dependencies: list[str] = field(default_factory=list)
    outputs: list[str] = field(default_factory=list)
    inputs: list[str] = field(default_factory=list)
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    started_at: datetime | None = None
    completed_at: datetime | None = None
    error_message: str | None = None
    retry_count: int = 0
    max_retries: int = 3


@dataclass
class TaskDecomposition:
    """Result of task decomposition"""

    original_task_id: str
    sub_tasks: list[SubTask]
    dependency_graph: dict[str, list[str]]
    execution_plan: list[list[str]]
    estimated_total_duration: float
    estimated_total_cost: float
    confidence_score: float
    decomposition_strategy: str
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))


@dataclass
class TaskAggregation:
    """Aggregation configuration for combining sub-task results"""

    aggregation_id: str
    parent_task_id: str
    aggregation_type: str
    input_sub_tasks: list[str]
    output_format: str
    aggregation_function: str
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
