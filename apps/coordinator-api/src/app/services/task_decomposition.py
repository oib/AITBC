"""
Task Decomposition Service for OpenClaw Autonomous Economics
Implements intelligent task splitting and sub-task management
"""

from aitbc import get_logger

logger = get_logger(__name__)
from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from typing import Any


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
    estimated_duration: float  # hours
    gpu_tier: GPU_Tier
    memory_requirement: int  # GB
    compute_intensity: float  # 0-1
    data_size: int  # MB
    priority: int  # 1-10
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
    created_at: datetime = field(default_factory=datetime.utcnow)
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
    dependency_graph: dict[str, list[str]]  # sub_task_id -> dependencies
    execution_plan: list[list[str]]  # List of parallel execution stages
    estimated_total_duration: float
    estimated_total_cost: float
    confidence_score: float
    decomposition_strategy: str
    created_at: datetime = field(default_factory=datetime.utcnow)


@dataclass
class TaskAggregation:
    """Aggregation configuration for combining sub-task results"""

    aggregation_id: str
    parent_task_id: str
    aggregation_type: str  # "concat", "merge", "vote", "weighted_average", etc.
    input_sub_tasks: list[str]
    output_format: str
    aggregation_function: str
    created_at: datetime = field(default_factory=datetime.utcnow)


class TaskDecompositionEngine:
    """Engine for intelligent task decomposition and sub-task management"""

    def __init__(self, config: dict[str, Any]):
        self.config = config
        self.decomposition_history: list[TaskDecomposition] = []
        self.sub_task_registry: dict[str, SubTask] = {}
        self.aggregation_registry: dict[str, TaskAggregation] = {}

        # Decomposition strategies
        self.strategies = {
            "sequential": self._sequential_decomposition,
            "parallel": self._parallel_decomposition,
            "hierarchical": self._hierarchical_decomposition,
            "pipeline": self._pipeline_decomposition,
            "adaptive": self._adaptive_decomposition,
        }

        # Task type complexity mapping
        self.complexity_thresholds = {
            TaskType.TEXT_PROCESSING: 0.3,
            TaskType.IMAGE_PROCESSING: 0.5,
            TaskType.AUDIO_PROCESSING: 0.4,
            TaskType.VIDEO_PROCESSING: 0.8,
            TaskType.DATA_ANALYSIS: 0.6,
            TaskType.MODEL_INFERENCE: 0.4,
            TaskType.MODEL_TRAINING: 0.9,
            TaskType.COMPUTE_INTENSIVE: 0.8,
            TaskType.IO_BOUND: 0.2,
            TaskType.MIXED_MODAL: 0.7,
        }

        # GPU tier performance mapping
        self.gpu_performance = {
            GPU_Tier.CPU_ONLY: 1.0,
            GPU_Tier.LOW_END_GPU: 2.5,
            GPU_Tier.MID_RANGE_GPU: 5.0,
            GPU_Tier.HIGH_END_GPU: 10.0,
            GPU_Tier.PREMIUM_GPU: 20.0,
        }

    async def decompose_task(
        self,
        task_id: str,
        task_requirements: TaskRequirement,
        strategy: str | None = None,
        max_subtasks: int = 10,
        min_subtask_duration: float = 0.1,  # hours
    ) -> TaskDecomposition:
        """Decompose a complex task into sub-tasks"""

        try:
            logger.info(f"Decomposing task {task_id} with strategy {strategy}")

            # Select decomposition strategy
            if strategy is None:
                strategy = await self._select_decomposition_strategy(task_requirements)

            # Execute decomposition
            decomposition_func = self.strategies.get(strategy, self._adaptive_decomposition)
            sub_tasks = await decomposition_func(task_id, task_requirements, max_subtasks, min_subtask_duration)

            # Build dependency graph
            dependency_graph = await self._build_dependency_graph(sub_tasks)

            # Create execution plan
            execution_plan = await self._create_execution_plan(dependency_graph)

            # Estimate total duration and cost
            total_duration = await self._estimate_total_duration(sub_tasks, execution_plan)
            total_cost = await self._estimate_total_cost(sub_tasks)

            # Calculate confidence score
            confidence_score = await self._calculate_decomposition_confidence(task_requirements, sub_tasks, strategy)

            # Create decomposition result
            decomposition = TaskDecomposition(
                original_task_id=task_id,
                sub_tasks=sub_tasks,
                dependency_graph=dependency_graph,
                execution_plan=execution_plan,
                estimated_total_duration=total_duration,
                estimated_total_cost=total_cost,
                confidence_score=confidence_score,
                decomposition_strategy=strategy,
            )

            # Register sub-tasks
            for sub_task in sub_tasks:
                self.sub_task_registry[sub_task.sub_task_id] = sub_task

            # Store decomposition history
            self.decomposition_history.append(decomposition)

            logger.info(f"Task {task_id} decomposed into {len(sub_tasks)} sub-tasks")
            return decomposition

        except Exception as e:
            logger.error(f"Failed to decompose task {task_id}: {e}")
            raise

    async def create_aggregation(
        self, parent_task_id: str, input_sub_tasks: list[str], aggregation_type: str, output_format: str
    ) -> TaskAggregation:
        """Create aggregation configuration for combining sub-task results"""

        aggregation_id = f"agg_{parent_task_id}_{datetime.utcnow().timestamp()}"

        aggregation = TaskAggregation(
            aggregation_id=aggregation_id,
            parent_task_id=parent_task_id,
            aggregation_type=aggregation_type,
            input_sub_tasks=input_sub_tasks,
            output_format=output_format,
            aggregation_function=await self._get_aggregation_function(aggregation_type, output_format),
        )

        self.aggregation_registry[aggregation_id] = aggregation

        logger.info(f"Created aggregation {aggregation_id} for task {parent_task_id}")
        return aggregation

    async def update_sub_task_status(
        self, sub_task_id: str, status: SubTaskStatus, error_message: str | None = None
    ) -> bool:
        """Update sub-task status"""

        if sub_task_id not in self.sub_task_registry:
            logger.error(f"Sub-task {sub_task_id} not found")
            return False

        sub_task = self.sub_task_registry[sub_task_id]
        old_status = sub_task.status
        sub_task.status = status

        if error_message:
            sub_task.error_message = error_message

        # Update timestamps
        if status == SubTaskStatus.IN_PROGRESS and old_status != SubTaskStatus.IN_PROGRESS:
            sub_task.started_at = datetime.utcnow()
        elif status == SubTaskStatus.COMPLETED:
            sub_task.completed_at = datetime.utcnow()
        elif status == SubTaskStatus.FAILED:
            sub_task.retry_count += 1

        logger.info(f"Updated sub-task {sub_task_id} status: {old_status} -> {status}")
        return True

    async def get_ready_sub_tasks(self, parent_task_id: str | None = None) -> list[SubTask]:
        """Get sub-tasks ready for execution"""

        ready_tasks = []

        for sub_task in self.sub_task_registry.values():
            if parent_task_id and sub_task.parent_task_id != parent_task_id:
                continue

            if sub_task.status != SubTaskStatus.PENDING:
                continue

            # Check if dependencies are satisfied
            dependencies_satisfied = True
            for dep_id in sub_task.dependencies:
                if dep_id not in self.sub_task_registry:
                    dependencies_satisfied = False
                    break
                if self.sub_task_registry[dep_id].status != SubTaskStatus.COMPLETED:
                    dependencies_satisfied = False
                    break

            if dependencies_satisfied:
                ready_tasks.append(sub_task)

        return ready_tasks

    async def get_execution_status(self, parent_task_id: str) -> dict[str, Any]:
        """Get execution status for all sub-tasks of a parent task"""

        sub_tasks = [st for st in self.sub_task_registry.values() if st.parent_task_id == parent_task_id]

        if not sub_tasks:
            return {"status": "no_sub_tasks", "sub_tasks": []}

        status_counts = {}
        for status in SubTaskStatus:
            status_counts[status.value] = 0

        for sub_task in sub_tasks:
            status_counts[sub_task.status.value] += 1

        # Determine overall status
        if status_counts["completed"] == len(sub_tasks):
            overall_status = "completed"
        elif status_counts["failed"] > 0:
            overall_status = "failed"
        elif status_counts["in_progress"] > 0:
            overall_status = "in_progress"
        else:
            overall_status = "pending"

        return {
            "status": overall_status,
            "total_sub_tasks": len(sub_tasks),
            "status_counts": status_counts,
            "sub_tasks": [
                {
                    "sub_task_id": st.sub_task_id,
                    "name": st.name,
                    "status": st.status.value,
                    "assigned_agent": st.assigned_agent,
                    "created_at": st.created_at.isoformat(),
                    "started_at": st.started_at.isoformat() if st.started_at else None,
                    "completed_at": st.completed_at.isoformat() if st.completed_at else None,
                }
                for st in sub_tasks
            ],
        }

    async def retry_failed_sub_tasks(self, parent_task_id: str) -> list[str]:
        """Retry failed sub-tasks"""

        retried_tasks = []

        for sub_task in self.sub_task_registry.values():
            if sub_task.parent_task_id != parent_task_id:
                continue

            if sub_task.status == SubTaskStatus.FAILED and sub_task.retry_count < sub_task.max_retries:
                await self.update_sub_task_status(sub_task.sub_task_id, SubTaskStatus.PENDING)
                retried_tasks.append(sub_task.sub_task_id)
                logger.info(f"Retrying sub-task {sub_task.sub_task_id} (attempt {sub_task.retry_count + 1})")

        return retried_tasks

    async def _select_decomposition_strategy(self, task_requirements: TaskRequirement) -> str:
        """Select optimal decomposition strategy"""

        # Base selection on task type and complexity
        complexity = self.complexity_thresholds.get(task_requirements.task_type, 0.5)

        # Adjust for duration and compute intensity
        if task_requirements.estimated_duration > 4.0:
            complexity += 0.2
        if task_requirements.compute_intensity > 0.8:
            complexity += 0.2
        if task_requirements.data_size > 1000:  # > 1GB
            complexity += 0.1

        # Select strategy based on complexity
        if complexity < 0.3:
            return "sequential"
        elif complexity < 0.5:
            return "parallel"
        elif complexity < 0.7:
            return "hierarchical"
        elif complexity < 0.9:
            return "pipeline"
        else:
            return "adaptive"

    async def _sequential_decomposition(
        self, task_id: str, task_requirements: TaskRequirement, max_subtasks: int, min_duration: float
    ) -> list[SubTask]:
        """Sequential decomposition strategy"""

        sub_tasks = []

        # For simple tasks, create minimal decomposition
        if task_requirements.estimated_duration <= min_duration * 2:
            # Single sub-task
            sub_task = SubTask(
                sub_task_id=f"{task_id}_seq_1",
                parent_task_id=task_id,
                name="Main Task",
                description="Sequential execution of main task",
                requirements=task_requirements,
            )
            sub_tasks.append(sub_task)
        else:
            # Split into sequential chunks
            num_chunks = min(int(task_requirements.estimated_duration / min_duration), max_subtasks)
            chunk_duration = task_requirements.estimated_duration / num_chunks

            for i in range(num_chunks):
                chunk_requirements = TaskRequirement(
                    task_type=task_requirements.task_type,
                    estimated_duration=chunk_duration,
                    gpu_tier=task_requirements.gpu_tier,
                    memory_requirement=task_requirements.memory_requirement,
                    compute_intensity=task_requirements.compute_intensity,
                    data_size=task_requirements.data_size // num_chunks,
                    priority=task_requirements.priority,
                    deadline=task_requirements.deadline,
                    max_cost=task_requirements.max_cost,
                )

                sub_task = SubTask(
                    sub_task_id=f"{task_id}_seq_{i+1}",
                    parent_task_id=task_id,
                    name=f"Sequential Chunk {i+1}",
                    description=f"Sequential execution chunk {i+1}",
                    requirements=chunk_requirements,
                    dependencies=[f"{task_id}_seq_{i}"] if i > 0 else [],
                )
                sub_tasks.append(sub_task)

        return sub_tasks

    async def _parallel_decomposition(
        self, task_id: str, task_requirements: TaskRequirement, max_subtasks: int, min_duration: float
    ) -> list[SubTask]:
        """Parallel decomposition strategy"""

        sub_tasks = []

        # Determine optimal number of parallel tasks
        optimal_parallel = min(
            max(2, int(task_requirements.data_size / 100)),  # Based on data size
            max(2, int(task_requirements.estimated_duration / min_duration)),  # Based on duration
            max_subtasks,
        )

        # Split data and requirements
        chunk_data_size = task_requirements.data_size // optimal_parallel
        chunk_duration = task_requirements.estimated_duration / optimal_parallel

        for i in range(optimal_parallel):
            chunk_requirements = TaskRequirement(
                task_type=task_requirements.task_type,
                estimated_duration=chunk_duration,
                gpu_tier=task_requirements.gpu_tier,
                memory_requirement=task_requirements.memory_requirement // optimal_parallel,
                compute_intensity=task_requirements.compute_intensity,
                data_size=chunk_data_size,
                priority=task_requirements.priority,
                deadline=task_requirements.deadline,
                max_cost=task_requirements.max_cost / optimal_parallel if task_requirements.max_cost else None,
            )

            sub_task = SubTask(
                sub_task_id=f"{task_id}_par_{i+1}",
                parent_task_id=task_id,
                name=f"Parallel Task {i+1}",
                description=f"Parallel execution task {i+1}",
                requirements=chunk_requirements,
                inputs=[f"input_chunk_{i}"],
                outputs=[f"output_chunk_{i}"],
            )
            sub_tasks.append(sub_task)

        return sub_tasks

    async def _hierarchical_decomposition(
        self, task_id: str, task_requirements: TaskRequirement, max_subtasks: int, min_duration: float
    ) -> list[SubTask]:
        """Hierarchical decomposition strategy"""

        sub_tasks = []

        # Create hierarchical structure
        # Level 1: Main decomposition
        level1_tasks = await self._parallel_decomposition(task_id, task_requirements, max_subtasks // 2, min_duration)

        # Level 2: Further decomposition if needed
        for level1_task in level1_tasks:
            if level1_task.requirements.estimated_duration > min_duration * 2:
                # Decompose further
                level2_tasks = await self._sequential_decomposition(
                    level1_task.sub_task_id, level1_task.requirements, 2, min_duration / 2
                )

                # Update dependencies
                for level2_task in level2_tasks:
                    level2_task.dependencies = level1_task.dependencies
                    level2_task.parent_task_id = task_id

                sub_tasks.extend(level2_tasks)
            else:
                sub_tasks.append(level1_task)

        return sub_tasks

    async def _pipeline_decomposition(
        self, task_id: str, task_requirements: TaskRequirement, max_subtasks: int, min_duration: float
    ) -> list[SubTask]:
        """Pipeline decomposition strategy"""

        sub_tasks = []

        # Define pipeline stages based on task type
        if task_requirements.task_type == TaskType.IMAGE_PROCESSING:
            stages = ["preprocessing", "processing", "postprocessing"]
        elif task_requirements.task_type == TaskType.DATA_ANALYSIS:
            stages = ["data_loading", "cleaning", "analysis", "visualization"]
        elif task_requirements.task_type == TaskType.MODEL_TRAINING:
            stages = ["data_preparation", "model_training", "validation", "deployment"]
        else:
            stages = ["stage1", "stage2", "stage3"]

        # Create pipeline sub-tasks
        stage_duration = task_requirements.estimated_duration / len(stages)

        for i, stage in enumerate(stages):
            stage_requirements = TaskRequirement(
                task_type=task_requirements.task_type,
                estimated_duration=stage_duration,
                gpu_tier=task_requirements.gpu_tier,
                memory_requirement=task_requirements.memory_requirement,
                compute_intensity=task_requirements.compute_intensity,
                data_size=task_requirements.data_size,
                priority=task_requirements.priority,
                deadline=task_requirements.deadline,
                max_cost=task_requirements.max_cost / len(stages) if task_requirements.max_cost else None,
            )

            sub_task = SubTask(
                sub_task_id=f"{task_id}_pipe_{i+1}",
                parent_task_id=task_id,
                name=f"Pipeline Stage: {stage}",
                description=f"Pipeline stage: {stage}",
                requirements=stage_requirements,
                dependencies=[f"{task_id}_pipe_{i}"] if i > 0 else [],
                inputs=[f"stage_{i}_input"],
                outputs=[f"stage_{i}_output"],
            )
            sub_tasks.append(sub_task)

        return sub_tasks

    async def _adaptive_decomposition(
        self, task_id: str, task_requirements: TaskRequirement, max_subtasks: int, min_duration: float
    ) -> list[SubTask]:
        """Adaptive decomposition strategy"""

        # Analyze task characteristics
        characteristics = await self._analyze_task_characteristics(task_requirements)

        # Select best strategy based on analysis
        if characteristics["parallelizable"] > 0.7:
            return await self._parallel_decomposition(task_id, task_requirements, max_subtasks, min_duration)
        elif characteristics["sequential_dependency"] > 0.7:
            return await self._sequential_decomposition(task_id, task_requirements, max_subtasks, min_duration)
        elif characteristics["hierarchical_structure"] > 0.7:
            return await self._hierarchical_decomposition(task_id, task_requirements, max_subtasks, min_duration)
        else:
            return await self._pipeline_decomposition(task_id, task_requirements, max_subtasks, min_duration)

    async def _analyze_task_characteristics(self, task_requirements: TaskRequirement) -> dict[str, float]:
        """Analyze task characteristics for adaptive decomposition"""

        characteristics = {
            "parallelizable": 0.5,
            "sequential_dependency": 0.5,
            "hierarchical_structure": 0.5,
            "pipeline_suitable": 0.5,
        }

        # Analyze based on task type
        if task_requirements.task_type in [TaskType.DATA_ANALYSIS, TaskType.IMAGE_PROCESSING]:
            characteristics["parallelizable"] = 0.8
        elif task_requirements.task_type in [TaskType.MODEL_TRAINING]:
            characteristics["sequential_dependency"] = 0.7
            characteristics["pipeline_suitable"] = 0.8
        elif task_requirements.task_type == TaskType.MIXED_MODAL:
            characteristics["hierarchical_structure"] = 0.8

        # Adjust based on data size
        if task_requirements.data_size > 1000:  # > 1GB
            characteristics["parallelizable"] += 0.2

        # Adjust based on compute intensity
        if task_requirements.compute_intensity > 0.8:
            characteristics["sequential_dependency"] += 0.1

        return characteristics

    async def _build_dependency_graph(self, sub_tasks: list[SubTask]) -> dict[str, list[str]]:
        """Build dependency graph from sub-tasks"""

        dependency_graph = {}

        for sub_task in sub_tasks:
            dependency_graph[sub_task.sub_task_id] = sub_task.dependencies

        return dependency_graph

    async def _create_execution_plan(self, dependency_graph: dict[str, list[str]]) -> list[list[str]]:
        """Create execution plan from dependency graph"""

        execution_plan = []
        remaining_tasks = set(dependency_graph.keys())
        completed_tasks = set()

        while remaining_tasks:
            # Find tasks with no unmet dependencies
            ready_tasks = []
            for task_id in remaining_tasks:
                dependencies = dependency_graph[task_id]
                if all(dep in completed_tasks for dep in dependencies):
                    ready_tasks.append(task_id)

            if not ready_tasks:
                # Circular dependency or error
                logger.warning("Circular dependency detected in task decomposition")
                break

            # Add ready tasks to current execution stage
            execution_plan.append(ready_tasks)

            # Mark tasks as completed
            for task_id in ready_tasks:
                completed_tasks.add(task_id)
                remaining_tasks.remove(task_id)

        return execution_plan

    async def _estimate_total_duration(self, sub_tasks: list[SubTask], execution_plan: list[list[str]]) -> float:
        """Estimate total duration for task execution"""

        total_duration = 0.0

        for stage in execution_plan:
            # Find longest task in this stage (parallel execution)
            stage_duration = 0.0
            for task_id in stage:
                if task_id in self.sub_task_registry:
                    stage_duration = max(stage_duration, self.sub_task_registry[task_id].requirements.estimated_duration)

            total_duration += stage_duration

        return total_duration

    async def _estimate_total_cost(self, sub_tasks: list[SubTask]) -> float:
        """Estimate total cost for task execution"""

        total_cost = 0.0

        for sub_task in sub_tasks:
            # Simple cost estimation based on GPU tier and duration
            gpu_performance = self.gpu_performance.get(sub_task.requirements.gpu_tier, 1.0)
            hourly_rate = 0.05 * gpu_performance  # Base rate * performance multiplier
            task_cost = hourly_rate * sub_task.requirements.estimated_duration
            total_cost += task_cost

        return total_cost

    async def _calculate_decomposition_confidence(
        self, task_requirements: TaskRequirement, sub_tasks: list[SubTask], strategy: str
    ) -> float:
        """Calculate confidence in decomposition"""

        # Base confidence from strategy
        strategy_confidence = {"sequential": 0.9, "parallel": 0.8, "hierarchical": 0.7, "pipeline": 0.8, "adaptive": 0.6}

        confidence = strategy_confidence.get(strategy, 0.5)

        # Adjust based on task complexity
        complexity = self.complexity_thresholds.get(task_requirements.task_type, 0.5)
        if complexity > 0.7:
            confidence *= 0.8  # Lower confidence for complex tasks

        # Adjust based on number of sub-tasks
        if len(sub_tasks) > 8:
            confidence *= 0.9  # Slightly lower confidence for many sub-tasks

        return max(0.3, min(0.95, confidence))

    async def _get_aggregation_function(self, aggregation_type: str, output_format: str) -> str:
        """Get aggregation function for combining results"""

        # Map aggregation types to functions
        function_map = {
            "concat": "concatenate_results",
            "merge": "merge_results",
            "vote": "majority_vote",
            "average": "weighted_average",
            "sum": "sum_results",
            "max": "max_results",
            "min": "min_results",
        }

        base_function = function_map.get(aggregation_type, "concatenate_results")

        # Add format-specific suffix
        if output_format == "json":
            return f"{base_function}_json"
        elif output_format == "array":
            return f"{base_function}_array"
        else:
            return base_function
