"""Tests for workflow orchestrator module"""

from datetime import UTC, datetime

from app.workflow.orchestrator import (
    StepStatus,
    WorkflowDefinition,
    WorkflowExecution,
    WorkflowStatus,
    WorkflowStep,
)


class TestWorkflowStatus:
    """Test WorkflowStatus enum"""

    def test_workflow_status_values(self):
        """Test WorkflowStatus enum values"""
        assert WorkflowStatus.PENDING.value == "pending"
        assert WorkflowStatus.RUNNING.value == "running"
        assert WorkflowStatus.COMPLETED.value == "completed"
        assert WorkflowStatus.FAILED.value == "failed"
        assert WorkflowStatus.CANCELLED.value == "cancelled"
        assert WorkflowStatus.PAUSED.value == "paused"


class TestStepStatus:
    """Test StepStatus enum"""

    def test_step_status_values(self):
        """Test StepStatus enum values"""
        assert StepStatus.PENDING.value == "pending"
        assert StepStatus.RUNNING.value == "running"
        assert StepStatus.COMPLETED.value == "completed"
        assert StepStatus.FAILED.value == "failed"
        assert StepStatus.SKIPPED.value == "skipped"


class TestWorkflowStep:
    """Test WorkflowStep dataclass"""

    def test_workflow_step_creation(self):
        """Test creating WorkflowStep with default values"""
        step = WorkflowStep(
            step_id="step-1",
            agent_id="agent-123",
            action="process_data",
        )
        assert step.step_id == "step-1"
        assert step.agent_id == "agent-123"
        assert step.action == "process_data"
        assert step.parameters == {}
        assert step.dependencies == []
        assert step.timeout == 300
        assert step.retry_count == 0
        assert step.max_retries == 3
        assert step.status == StepStatus.PENDING
        assert step.result == {}
        assert step.error is None
        assert step.started_at is None
        assert step.completed_at is None

    def test_workflow_step_with_values(self):
        """Test creating WorkflowStep with custom values"""
        step = WorkflowStep(
            step_id="step-1",
            agent_id="agent-123",
            action="process_data",
            parameters={"input": "test"},
            dependencies=["step-0"],
            timeout=600,
            max_retries=5,
            status=StepStatus.RUNNING,
            result={"output": "result"},
            error="Test error",
            started_at=datetime.now(UTC),
            completed_at=datetime.now(UTC),
        )
        assert step.parameters == {"input": "test"}
        assert step.dependencies == ["step-0"]
        assert step.timeout == 600
        assert step.max_retries == 5
        assert step.status == StepStatus.RUNNING
        assert step.result == {"output": "result"}
        assert step.error == "Test error"
        assert step.started_at is not None
        assert step.completed_at is not None

    def test_workflow_step_to_dict(self):
        """Test converting WorkflowStep to dictionary"""
        step = WorkflowStep(
            step_id="step-1",
            agent_id="agent-123",
            action="process_data",
        )
        result = step.to_dict()
        assert result["step_id"] == "step-1"
        assert result["agent_id"] == "agent-123"
        assert result["action"] == "process_data"
        assert result["status"] == "pending"
        assert result["started_at"] is None
        assert result["completed_at"] is None

    def test_workflow_step_to_dict_with_dates(self):
        """Test converting WorkflowStep with dates to dictionary"""
        now = datetime.now(UTC)
        step = WorkflowStep(
            step_id="step-1",
            agent_id="agent-123",
            action="process_data",
            started_at=now,
            completed_at=now,
        )
        result = step.to_dict()
        assert result["started_at"] == now.isoformat()
        assert result["completed_at"] == now.isoformat()

    def test_workflow_step_from_dict(self):
        """Test creating WorkflowStep from dictionary"""
        data = {
            "step_id": "step-1",
            "agent_id": "agent-123",
            "action": "process_data",
            "parameters": {"input": "test"},
            "dependencies": ["step-0"],
            "timeout": 600,
            "retry_count": 1,
            "max_retries": 5,
            "status": "running",
            "result": {"output": "result"},
            "error": "Test error",
            "started_at": datetime.now(UTC).isoformat(),
            "completed_at": datetime.now(UTC).isoformat(),
        }
        step = WorkflowStep.from_dict(data)
        assert step.step_id == "step-1"
        assert step.agent_id == "agent-123"
        assert step.action == "process_data"
        assert step.parameters == {"input": "test"}
        assert step.dependencies == ["step-0"]
        assert step.timeout == 600
        assert step.retry_count == 1
        assert step.max_retries == 5
        assert step.status == StepStatus.RUNNING
        assert step.result == {"output": "result"}
        assert step.error == "Test error"
        assert step.started_at is not None
        assert step.completed_at is not None


class TestWorkflowDefinition:
    """Test WorkflowDefinition dataclass"""

    def test_workflow_definition_creation(self):
        """Test creating WorkflowDefinition with default values"""
        definition = WorkflowDefinition(
            workflow_id="workflow-1",
            name="Test Workflow",
        )
        assert definition.workflow_id == "workflow-1"
        assert definition.name == "Test Workflow"
        assert definition.description == ""
        assert definition.steps == []
        assert definition.created_by == ""
        assert definition.metadata == {}
        assert isinstance(definition.created_at, datetime)

    def test_workflow_definition_with_values(self):
        """Test creating WorkflowDefinition with custom values"""
        step = WorkflowStep(
            step_id="step-1",
            agent_id="agent-123",
            action="process_data",
        )
        definition = WorkflowDefinition(
            workflow_id="workflow-1",
            name="Test Workflow",
            description="A test workflow",
            steps=[step],
            created_by="user-123",
            metadata={"version": "1.0"},
        )
        assert definition.description == "A test workflow"
        assert len(definition.steps) == 1
        assert definition.created_by == "user-123"
        assert definition.metadata == {"version": "1.0"}

    def test_workflow_definition_to_dict(self):
        """Test converting WorkflowDefinition to dictionary"""
        definition = WorkflowDefinition(
            workflow_id="workflow-1",
            name="Test Workflow",
        )
        result = definition.to_dict()
        assert result["workflow_id"] == "workflow-1"
        assert result["name"] == "Test Workflow"
        assert result["description"] == ""
        assert result["steps"] == []
        assert isinstance(result["created_at"], str)

    def test_workflow_definition_from_dict(self):
        """Test creating WorkflowDefinition from dictionary"""
        data = {
            "workflow_id": "workflow-1",
            "name": "Test Workflow",
            "description": "A test workflow",
            "steps": [],
            "created_at": datetime.now(UTC).isoformat(),
            "created_by": "user-123",
            "metadata": {"version": "1.0"},
        }
        definition = WorkflowDefinition.from_dict(data)
        assert definition.workflow_id == "workflow-1"
        assert definition.name == "Test Workflow"
        assert definition.description == "A test workflow"
        assert definition.created_by == "user-123"
        assert definition.metadata == {"version": "1.0"}


class TestWorkflowExecution:
    """Test WorkflowExecution dataclass"""

    def test_workflow_execution_creation(self):
        """Test creating WorkflowExecution with default values"""
        execution = WorkflowExecution(
            execution_id="exec-1",
            workflow_id="workflow-1",
        )
        assert execution.execution_id == "exec-1"
        assert execution.workflow_id == "workflow-1"
        assert execution.status == WorkflowStatus.PENDING
        assert execution.current_step_index == 0
        assert execution.results == {}
        assert execution.error is None
        assert execution.steps == []
        assert execution.input_parameters == {}
        assert isinstance(execution.started_at, datetime)
        assert execution.completed_at is None

    def test_workflow_execution_with_values(self):
        """Test creating WorkflowExecution with custom values"""
        step = WorkflowStep(
            step_id="step-1",
            agent_id="agent-123",
            action="process_data",
        )
        execution = WorkflowExecution(
            execution_id="exec-1",
            workflow_id="workflow-1",
            status=WorkflowStatus.RUNNING,
            current_step_index=1,
            results={"output": "result"},
            error="Test error",
            steps=[step],
            input_parameters={"input": "test"},
            completed_at=datetime.now(UTC),
        )
        assert execution.status == WorkflowStatus.RUNNING
        assert execution.current_step_index == 1
        assert execution.results == {"output": "result"}
        assert execution.error == "Test error"
        assert len(execution.steps) == 1
        assert execution.input_parameters == {"input": "test"}
        assert execution.completed_at is not None
