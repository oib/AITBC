"""
Workflow Orchestration Engine for AITBC Agent Coordinator
Implements multi-agent workflow execution with Redis persistence
"""

import asyncio
import json
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum
from typing import Any

redis: Any = None
try:
    import redis.asyncio as redis
except ImportError:
    pass

from aitbc import get_logger

logger = get_logger(__name__)


class WorkflowStatus(str, Enum):
    """Workflow execution status"""
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    PAUSED = "paused"


class StepStatus(str, Enum):
    """Workflow step status"""
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"


@dataclass
class WorkflowStep:
    """Single step in a workflow"""
    step_id: str
    agent_id: str
    action: str
    parameters: dict[str, Any] = field(default_factory=dict)
    dependencies: list[str] = field(default_factory=list)  # step_ids this step depends on
    timeout: int = 300  # seconds
    retry_count: int = 0
    max_retries: int = 3
    status: StepStatus = StepStatus.PENDING
    result: dict[str, Any] = field(default_factory=dict)
    error: str | None = None
    started_at: datetime | None = None
    completed_at: datetime | None = None

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary"""
        # Ensure status is stored as string value, not enum
        status_value = self.status.value if hasattr(self.status, "value") else str(self.status)
        return {
            "step_id": self.step_id,
            "agent_id": self.agent_id,
            "action": self.action,
            "parameters": self.parameters,
            "dependencies": self.dependencies,
            "timeout": self.timeout,
            "retry_count": self.retry_count,
            "max_retries": self.max_retries,
            "status": status_value,
            "result": self.result,
            "error": self.error,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "WorkflowStep":
        """Create from dictionary"""
        # Handle status conversion from string
        status_str = data.get("status", "pending")
        status = StepStatus(status_str) if isinstance(status_str, str) else status_str

        return cls(
            step_id=data["step_id"],
            agent_id=data["agent_id"],
            action=data["action"],
            parameters=data.get("parameters", {}),
            dependencies=data.get("dependencies", []),
            timeout=data.get("timeout", 300),
            retry_count=data.get("retry_count", 0),
            max_retries=data.get("max_retries", 3),
            status=status,
            result=data.get("result", {}),
            error=data.get("error"),
            started_at=datetime.fromisoformat(data["started_at"]) if data.get("started_at") else None,
            completed_at=datetime.fromisoformat(data["completed_at"]) if data.get("completed_at") else None
        )


@dataclass
class WorkflowDefinition:
    """Workflow definition"""
    workflow_id: str
    name: str
    description: str = ""
    steps: list[WorkflowStep] = field(default_factory=list)
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    created_by: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary"""
        return {
            "workflow_id": self.workflow_id,
            "name": self.name,
            "description": self.description,
            "steps": [step.to_dict() for step in self.steps],
            "created_at": self.created_at.isoformat(),
            "created_by": self.created_by,
            "metadata": self.metadata
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "WorkflowDefinition":
        """Create from dictionary"""
        return cls(
            workflow_id=data["workflow_id"],
            name=data["name"],
            description=data.get("description", ""),
            steps=[WorkflowStep.from_dict(s) for s in data.get("steps", [])],
            created_at=datetime.fromisoformat(data["created_at"]),
            created_by=data.get("created_by", ""),
            metadata=data.get("metadata", {})
        )


@dataclass
class WorkflowExecution:
    """Workflow execution instance"""
    execution_id: str
    workflow_id: str
    status: WorkflowStatus = WorkflowStatus.PENDING
    current_step_index: int = 0
    results: dict[str, Any] = field(default_factory=dict)
    error: str | None = None
    started_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    completed_at: datetime | None = None
    steps: list[WorkflowStep] = field(default_factory=list)
    input_parameters: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary"""
        # Ensure status is stored as string value, not enum
        status_value = self.status.value if hasattr(self.status, "value") else str(self.status)
        return {
            "execution_id": self.execution_id,
            "workflow_id": self.workflow_id,
            "status": status_value,
            "current_step_index": self.current_step_index,
            "results": self.results,
            "error": self.error,
            "started_at": self.started_at.isoformat(),
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "steps": [step.to_dict() for step in self.steps],
            "input_parameters": self.input_parameters
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "WorkflowExecution":
        """Create from dictionary"""
        # Handle status conversion from string
        status_str = data.get("status", "pending")
        status = WorkflowStatus(status_str) if isinstance(status_str, str) else status_str

        return cls(
            execution_id=data["execution_id"],
            workflow_id=data["workflow_id"],
            status=status,
            current_step_index=data.get("current_step_index", 0),
            results=data.get("results", {}),
            error=data.get("error"),
            started_at=datetime.fromisoformat(data["started_at"]),
            completed_at=datetime.fromisoformat(data["completed_at"]) if data.get("completed_at") else None,
            steps=[WorkflowStep.from_dict(s) for s in data.get("steps", [])],
            input_parameters=data.get("input_parameters", {})
        )


class WorkflowOrchestrator:
    """Workflow orchestration engine with Redis persistence"""

    def __init__(self, redis_url: str = "redis://localhost:6379/1") -> None:
        self.redis_url = redis_url
        self.redis_client: redis.Redis | None = None
        self.active_executions: dict[str, WorkflowExecution] = {}

    async def start(self) -> Any:
        """Start the orchestrator"""
        if not redis:
            logger.warning("Redis not available, workflow orchestrator running in memory-only mode")
            return

        self.redis_client = redis.from_url(self.redis_url)
        await self._load_active_executions()
        logger.info("Workflow orchestrator started")

    async def stop(self) -> Any:
        """Stop the orchestrator"""
        if self.redis_client:
            await self.redis_client.close()
        logger.info("Workflow orchestrator stopped")

    async def create_workflow(self, name: str, steps: list[dict[str, Any]], created_by: str = "", description: str = "") -> WorkflowDefinition:
        """Create a new workflow definition"""
        workflow_id = f"wf_{datetime.now(UTC).strftime('%Y%m%d%H%M%S')}_{uuid.uuid4().hex[:8]}"

        # Convert step dicts to WorkflowStep objects
        workflow_steps = []
        for i, step_data in enumerate(steps):
            step = WorkflowStep(
                step_id=f"{workflow_id}_step_{i}",
                agent_id=step_data.get("agent_id", ""),
                action=step_data.get("action", ""),
                parameters=step_data.get("parameters", {}),
                dependencies=step_data.get("dependencies", []),
                timeout=step_data.get("timeout", 300),
                max_retries=step_data.get("max_retries", 3)
            )
            workflow_steps.append(step)

        workflow = WorkflowDefinition(
            workflow_id=workflow_id,
            name=name,
            description=description,
            steps=workflow_steps,
            created_by=created_by
        )

        # Save to Redis
        await self._save_workflow_definition(workflow)

        logger.info(f"Created workflow {workflow_id}: {name}")
        return workflow

    async def execute_workflow(self, workflow_id: str, input_parameters: dict[str, Any] | None = None) -> WorkflowExecution:
        """Execute a workflow"""
        # Load workflow definition
        workflow = await self._load_workflow_definition(workflow_id)
        if not workflow:
            raise ValueError(f"Workflow {workflow_id} not found")

        # Create execution instance
        execution_id = f"exec_{datetime.now(UTC).strftime('%Y%m%d%H%M%S')}_{uuid.uuid4().hex[:8]}"
        execution = WorkflowExecution(
            execution_id=execution_id,
            workflow_id=workflow_id,
            input_parameters=input_parameters or {},
            steps=[WorkflowStep(**s.to_dict()) for s in workflow.steps]  # Copy steps
        )

        # Save execution
        await self._save_workflow_execution(execution)
        self.active_executions[execution_id] = execution

        # Start execution in background
        asyncio.create_task(self._execute_workflow_async(execution))

        logger.info(f"Started workflow execution {execution_id} for workflow {workflow_id}")
        return execution

    async def get_execution_status(self, execution_id: str) -> WorkflowExecution | None:
        """Get workflow execution status"""
        # Check active executions first
        if execution_id in self.active_executions:
            return self.active_executions[execution_id]

        # Load from Redis
        return await self._load_workflow_execution(execution_id)

    async def cancel_execution(self, execution_id: str) -> bool:
        """Cancel a workflow execution"""
        execution = await self.get_execution_status(execution_id)
        if not execution:
            return False

        execution.status = WorkflowStatus.CANCELLED
        execution.completed_at = datetime.now(UTC)
        await self._save_workflow_execution(execution)

        if execution_id in self.active_executions:
            del self.active_executions[execution_id]

        logger.info(f"Cancelled workflow execution {execution_id}")
        return True

    async def list_workflows(self) -> list[WorkflowDefinition]:
        """List all workflow definitions"""
        if not self.redis_client:
            return []

        try:
            keys = await self.redis_client.keys("workflow:*")
            workflows = []
            for key in keys:
                data = await self.redis_client.get(key)
                if data:
                    workflows.append(WorkflowDefinition.from_dict(json.loads(data)))
            return workflows
        except Exception as e:
            logger.error(f"Error listing workflows: {e}")
            return []

    async def list_executions(self, workflow_id: str | None = None) -> list[WorkflowExecution]:
        """List workflow executions"""
        if not self.redis_client:
            return []

        try:
            pattern = f"execution:{workflow_id}:*" if workflow_id else "execution:*"
            keys = await self.redis_client.keys(pattern)
            executions = []
            for key in keys:
                data = await self.redis_client.get(key)
                if data:
                    executions.append(WorkflowExecution.from_dict(json.loads(data)))
            return executions
        except Exception as e:
            logger.error(f"Error listing executions: {e}")
            return []

    async def _execute_workflow_async(self, execution: WorkflowExecution) -> Any:
        """Execute workflow steps asynchronously"""
        execution.status = WorkflowStatus.RUNNING
        await self._save_workflow_execution(execution)

        try:
            # Execute steps in dependency order
            completed_steps = set()
            while execution.current_step_index < len(execution.steps):
                step = execution.steps[execution.current_step_index]

                # Check if dependencies are satisfied
                if not all(dep in completed_steps for dep in step.dependencies):
                    execution.current_step_index += 1
                    continue

                # Execute step
                step.status = StepStatus.RUNNING
                step.started_at = datetime.now(UTC)
                await self._save_workflow_execution(execution)

                try:
                    # Simulate step execution (in real implementation, this would call the agent)
                    await self._execute_step(step, execution.input_parameters)

                    step.status = StepStatus.COMPLETED
                    step.completed_at = datetime.now(UTC)
                    completed_steps.add(step.step_id)
                    execution.results[step.step_id] = step.result

                except Exception as e:
                    step.status = StepStatus.FAILED
                    step.error = str(e)
                    step.completed_at = datetime.now(UTC)

                    # Retry if possible
                    if step.retry_count < step.max_retries:
                        step.retry_count += 1
                        step.status = StepStatus.PENDING
                        logger.warning(f"Step {step.step_id} failed, retrying ({step.retry_count}/{step.max_retries})")
                        continue
                    else:
                        logger.error(f"Step {step.step_id} failed after {step.max_retries} retries")
                        execution.status = WorkflowStatus.FAILED
                        execution.error = f"Step {step.step_id} failed: {str(e)}"
                        execution.completed_at = datetime.now(UTC)
                        await self._save_workflow_execution(execution)
                        return

                await self._save_workflow_execution(execution)
                execution.current_step_index += 1

            # Mark execution as completed
            execution.status = WorkflowStatus.COMPLETED
            execution.completed_at = datetime.now(UTC)
            await self._save_workflow_execution(execution)

            logger.info(f"Workflow execution {execution.execution_id} completed successfully")

        except Exception as e:
            logger.error(f"Workflow execution {execution.execution_id} failed: {e}")
            execution.status = WorkflowStatus.FAILED
            execution.error = str(e)
            execution.completed_at = datetime.now(UTC)
            await self._save_workflow_execution(execution)

        finally:
            if execution.execution_id in self.active_executions:
                del self.active_executions[execution.execution_id]

    async def _execute_step(self, step: WorkflowStep, input_parameters: dict[str, Any]) -> Any:
        """Execute a single workflow step"""
        # In a real implementation, this would:
        # 1. Send a message to the agent
        # 2. Wait for response
        # 3. Handle timeout
        # 4. Store result

        # Simulate execution
        await asyncio.sleep(0.1)

        # Mock result
        step.result = {
            "status": "success",
            "output": f"Executed {step.action} on agent {step.agent_id}",
            "timestamp": datetime.now(UTC).isoformat()
        }

        logger.info(f"Executed step {step.step_id}: {step.action} on {step.agent_id}")

    async def _save_workflow_definition(self, workflow: WorkflowDefinition) -> Any:
        """Save workflow definition to Redis"""
        if not self.redis_client:
            return

        key = f"workflow:{workflow.workflow_id}"
        # WorkflowStatus and StepStatus inherit from str, so they serialize correctly
        await self.redis_client.setex(key, 86400, json.dumps(workflow.to_dict()))  # 24 hour TTL

    async def _load_workflow_definition(self, workflow_id: str) -> WorkflowDefinition | None:
        """Load workflow definition from Redis"""
        if not self.redis_client:
            return None

        key = f"workflow:{workflow_id}"
        data = await self.redis_client.get(key)
        if data:
            return WorkflowDefinition.from_dict(json.loads(data))
        return None

    async def _save_workflow_execution(self, execution: WorkflowExecution) -> Any:
        """Save workflow execution to Redis"""
        if not self.redis_client:
            return

        key = f"execution:{execution.workflow_id}:{execution.execution_id}"
        await self.redis_client.setex(key, 86400, json.dumps(execution.to_dict()))  # 24 hour TTL

    async def _load_workflow_execution(self, execution_id: str) -> WorkflowExecution | None:
        """Load workflow execution from Redis"""
        if not self.redis_client:
            return None

        # Try to find execution by ID
        keys = await self.redis_client.keys("execution:*")
        for key in keys:
            key_str = key.decode() if isinstance(key, bytes) else key
            if key_str.endswith(f":{execution_id}"):
                data = await self.redis_client.get(key)
                if data:
                    return WorkflowExecution.from_dict(json.loads(data))
        return None

    async def _load_active_executions(self) -> Any:
        """Load active executions from Redis"""
        if not self.redis_client:
            return

        try:
            keys = await self.redis_client.keys("execution:*")
            for key in keys:
                key_str = key.decode() if isinstance(key, bytes) else key
                data = await self.redis_client.get(key)
                if data:
                    execution = WorkflowExecution.from_dict(json.loads(data))
                    if execution.status in [WorkflowStatus.RUNNING, WorkflowStatus.PENDING]:
                        self.active_executions[execution.execution_id] = execution

            logger.info(f"Loaded {len(self.active_executions)} active executions")

        except Exception as e:
            logger.error(f"Error loading active executions: {e}")


# Global orchestrator instance
_orchestrator: WorkflowOrchestrator | None = None


def get_orchestrator() -> WorkflowOrchestrator:
    """Get global orchestrator instance"""
    global _orchestrator
    if _orchestrator is None:
        _orchestrator = WorkflowOrchestrator()
    return _orchestrator