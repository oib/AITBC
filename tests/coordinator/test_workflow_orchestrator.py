"""
Workflow Orchestration Tests
Tests for workflow definition, execution, step management, and orchestration
"""

import sys
from pathlib import Path

# Add coordinator path for imports
coordinator_path = Path("/opt/aitbc/apps/agent-coordinator/src")
if str(coordinator_path) not in sys.path:
    sys.path.insert(0, str(coordinator_path))

import pytest
from datetime import UTC, datetime

from app.workflow.orchestrator import (
    WorkflowStep,
    WorkflowDefinition,
    WorkflowExecution,
    WorkflowStatus,
    StepStatus,
    WorkflowOrchestrator,
)


class TestWorkflowStep:
    """Test workflow step creation and management"""

    def test_step_creation(self):
        """Test creating a workflow step"""
        step = WorkflowStep(
            step_id="step_001",
            agent_id="agent_001",
            action="process_data",
            parameters={"input": "test_data"},
            dependencies=["step_000"],
            timeout=300,
            max_retries=3
        )
        
        assert step.step_id == "step_001"
        assert step.agent_id == "agent_001"
        assert step.action == "process_data"
        assert step.status == StepStatus.PENDING
        assert step.retry_count == 0

    def test_step_serialization(self):
        """Test step to_dict and from_dict"""
        step = WorkflowStep(
            step_id="step_002",
            agent_id="agent_002",
            action="analyze",
            parameters={"model": "gpt-4"},
            timeout=600
        )
        
        # Convert to dict
        step_dict = step.to_dict()
        assert "step_id" in step_dict
        assert "agent_id" in step_dict
        assert "action" in step_dict
        assert "status" in step_dict
        
        # Convert from dict
        restored_step = WorkflowStep.from_dict(step_dict)
        assert restored_step.step_id == step.step_id
        assert restored_step.agent_id == step.agent_id
        assert restored_step.action == step.action

    def test_step_status_transitions(self):
        """Test step status transitions"""
        step = WorkflowStep(
            step_id="step_003",
            agent_id="agent_003",
            action="compute"
        )
        
        # Transition to running
        step.status = StepStatus.RUNNING
        step.started_at = datetime.now(UTC)
        assert step.status == StepStatus.RUNNING
        assert step.started_at is not None
        
        # Transition to completed
        step.status = StepStatus.COMPLETED
        step.completed_at = datetime.now(UTC)
        assert step.status == StepStatus.COMPLETED
        assert step.completed_at is not None


class TestWorkflowDefinition:
    """Test workflow definition creation and management"""

    def test_workflow_definition_creation(self):
        """Test creating a workflow definition"""
        steps = [
            WorkflowStep(
                step_id="step_001",
                agent_id="agent_001",
                action="process"
            ),
            WorkflowStep(
                step_id="step_002",
                agent_id="agent_002",
                action="analyze",
                dependencies=["step_001"]
            )
        ]
        
        workflow = WorkflowDefinition(
            workflow_id="wf_001",
            name="Data Processing Workflow",
            description="Processes and analyzes data",
            steps=steps,
            created_by="user_001"
        )
        
        assert workflow.workflow_id == "wf_001"
        assert workflow.name == "Data Processing Workflow"
        assert len(workflow.steps) == 2
        assert workflow.created_by == "user_001"

    def test_workflow_definition_serialization(self):
        """Test workflow definition to_dict and from_dict"""
        steps = [
            WorkflowStep(
                step_id="step_001",
                agent_id="agent_001",
                action="process"
            )
        ]
        
        workflow = WorkflowDefinition(
            workflow_id="wf_002",
            name="Test Workflow",
            steps=steps,
            created_by="user_002"
        )
        
        # Convert to dict
        workflow_dict = workflow.to_dict()
        assert "workflow_id" in workflow_dict
        assert "name" in workflow_dict
        assert "steps" in workflow_dict
        
        # Convert from dict
        restored_workflow = WorkflowDefinition.from_dict(workflow_dict)
        assert restored_workflow.workflow_id == workflow.workflow_id
        assert restored_workflow.name == workflow.name
        assert len(restored_workflow.steps) == len(workflow.steps)

    def test_workflow_step_dependencies(self):
        """Test workflow step dependencies"""
        steps = [
            WorkflowStep(
                step_id="step_001",
                agent_id="agent_001",
                action="fetch_data"
            ),
            WorkflowStep(
                step_id="step_002",
                agent_id="agent_002",
                action="process",
                dependencies=["step_001"]
            ),
            WorkflowStep(
                step_id="step_003",
                agent_id="agent_003",
                action="save",
                dependencies=["step_002"]
            )
        ]
        
        workflow = WorkflowDefinition(
            workflow_id="wf_003",
            name="Dependent Workflow",
            steps=steps
        )
        
        # Verify dependency chain
        assert len(workflow.steps[1].dependencies) == 1
        assert "step_001" in workflow.steps[1].dependencies
        assert len(workflow.steps[2].dependencies) == 1
        assert "step_002" in workflow.steps[2].dependencies

    def test_workflow_step_retry_logic(self):
        """Test workflow step retry configuration"""
        step = WorkflowStep(
            step_id="step_001",
            agent_id="agent_001",
            action="process",
            max_retries=5,
            timeout=600
        )
        
        assert step.max_retries == 5
        assert step.timeout == 600
        assert step.retry_count == 0
        
        # Simulate retry
        step.retry_count = 1
        assert step.retry_count == 1
        assert step.retry_count < step.max_retries


class TestWorkflowExecution:
    """Test workflow execution instance"""

    def test_execution_creation(self):
        """Test creating a workflow execution"""
        steps = [
            WorkflowStep(
                step_id="step_001",
                agent_id="agent_001",
                action="process"
            )
        ]
        
        execution = WorkflowExecution(
            execution_id="exec_001",
            workflow_id="wf_001",
            status=WorkflowStatus.PENDING,
            steps=steps,
            input_parameters={"data": "test_input"}
        )
        
        assert execution.execution_id == "exec_001"
        assert execution.workflow_id == "wf_001"
        assert execution.status == WorkflowStatus.PENDING
        assert execution.current_step_index == 0
        assert execution.input_parameters["data"] == "test_input"

    def test_execution_serialization(self):
        """Test execution to_dict and from_dict"""
        steps = [
            WorkflowStep(
                step_id="step_001",
                agent_id="agent_001",
                action="process"
            )
        ]
        
        execution = WorkflowExecution(
            execution_id="exec_002",
            workflow_id="wf_002",
            steps=steps
        )
        
        # Convert to dict
        exec_dict = execution.to_dict()
        assert "execution_id" in exec_dict
        assert "workflow_id" in exec_dict
        assert "status" in exec_dict
        
        # Convert from dict
        restored_exec = WorkflowExecution.from_dict(exec_dict)
        assert restored_exec.execution_id == execution.execution_id
        assert restored_exec.workflow_id == execution.workflow_id

    def test_execution_status_transitions(self):
        """Test execution status transitions"""
        execution = WorkflowExecution(
            execution_id="exec_003",
            workflow_id="wf_003"
        )
        
        # Start execution
        execution.status = WorkflowStatus.RUNNING
        assert execution.status == WorkflowStatus.RUNNING
        
        # Complete execution
        execution.status = WorkflowStatus.COMPLETED
        execution.completed_at = datetime.now(UTC)
        assert execution.status == WorkflowStatus.COMPLETED
        assert execution.completed_at is not None
        
        # Cancel execution
        execution.status = WorkflowStatus.CANCELLED
        assert execution.status == WorkflowStatus.CANCELLED


class TestWorkflowStatus:
    """Test workflow status enum"""

    def test_workflow_status_values(self):
        """Test workflow status enum values"""
        assert WorkflowStatus.PENDING.value == "pending"
        assert WorkflowStatus.RUNNING.value == "running"
        assert WorkflowStatus.COMPLETED.value == "completed"
        assert WorkflowStatus.FAILED.value == "failed"
        assert WorkflowStatus.CANCELLED.value == "cancelled"
        assert WorkflowStatus.PAUSED.value == "paused"

    def test_step_status_values(self):
        """Test step status enum values"""
        assert StepStatus.PENDING.value == "pending"
        assert StepStatus.RUNNING.value == "running"
        assert StepStatus.COMPLETED.value == "completed"
        assert StepStatus.FAILED.value == "failed"
        assert StepStatus.SKIPPED.value == "skipped"


class TestWorkflowOrchestrator:
    """Test workflow orchestrator initialization and basic operations"""

    def test_orchestrator_initialization(self):
        """Test orchestrator initialization"""
        orchestrator = WorkflowOrchestrator()
        
        assert orchestrator.redis_url == "redis://localhost:6379/1"
        assert len(orchestrator.active_executions) == 0
        assert orchestrator.redis_client is None

    def test_orchestrator_custom_redis_url(self):
        """Test orchestrator with custom Redis URL"""
        orchestrator = WorkflowOrchestrator(redis_url="redis://localhost:6380/2")
        
        assert orchestrator.redis_url == "redis://localhost:6380/2"

    def test_orchestrator_active_executions_tracking(self):
        """Test orchestrator tracks active executions"""
        orchestrator = WorkflowOrchestrator()
        
        # Initially empty
        assert len(orchestrator.active_executions) == 0
        
        # Simulate adding an execution (would normally be done via execute_workflow)
        orchestrator.active_executions["exec_001"] = WorkflowExecution(
            execution_id="exec_001",
            workflow_id="wf_001"
        )
        
        assert len(orchestrator.active_executions) == 1
        assert "exec_001" in orchestrator.active_executions

    def test_orchestrator_execution_removal(self):
        """Test removing executions from tracking"""
        orchestrator = WorkflowOrchestrator()
        orchestrator.active_executions["exec_001"] = WorkflowExecution(
            execution_id="exec_001",
            workflow_id="wf_001"
        )
        
        # Remove execution
        del orchestrator.active_executions["exec_001"]
        
        assert len(orchestrator.active_executions) == 0
        assert "exec_001" not in orchestrator.active_executions

    def test_workflow_definition_with_dependencies(self):
        """Test workflow definition with step dependencies"""
        definition = WorkflowDefinition(
            workflow_id="wf_deps",
            name="Workflow with Dependencies",
            steps={
                "step1": {"name": "Data Load", "order": 1},
                "step2": {"name": "Process", "order": 2, "depends_on": "step1"},
                "step3": {"name": "Save", "order": 3, "depends_on": "step2"}
            }
        )
        
        assert len(definition.steps) == 3
        assert "step2" in definition.steps

    def test_workflow_execution_progress_tracking(self):
        """Test workflow execution progress tracking"""
        execution = WorkflowExecution(
            execution_id="exec_progress",
            workflow_id="wf_001"
        )
        
        # Mark steps as completed
        execution.completed_steps = 2
        execution.current_step = 2
        
        assert execution.completed_steps == 2
        assert execution.current_step == 2

    def test_workflow_step_status_transitions(self):
        """Test workflow step status transitions"""
        step = WorkflowStep(
            step_id="step_001",
            agent_id="agent_001",
            action="process"
        )
        
        # Initial status
        assert step.status == StepStatus.PENDING
        
        # Mark as running
        step.status = StepStatus.RUNNING
        assert step.status == StepStatus.RUNNING
        
        # Mark as completed
        step.status = StepStatus.COMPLETED
        assert step.status == StepStatus.COMPLETED

    def test_workflow_status_transitions(self):
        """Test workflow execution status transitions"""
        execution = WorkflowExecution(
            execution_id="exec_transitions",
            workflow_id="wf_001"
        )
        
        # Initial status
        assert execution.status == WorkflowStatus.PENDING
        
        # Mark as running
        execution.status = WorkflowStatus.RUNNING
        assert execution.status == WorkflowStatus.RUNNING
        
        # Mark as completed
        execution.status = WorkflowStatus.COMPLETED
        assert execution.status == WorkflowStatus.COMPLETED

    def test_workflow_definition_creation(self):
        """Test workflow definition creation with minimal fields"""
        definition = WorkflowDefinition(
            workflow_id="wf_minimal",
            name="Minimal Workflow",
            steps={"step1": {"name": "Task 1"}}
        )
        
        assert definition.workflow_id == "wf_minimal"
        assert definition.name == "Minimal Workflow"
        assert len(definition.steps) == 1

    def test_workflow_execution_creation(self):
        """Test workflow execution creation with minimal fields"""
        execution = WorkflowExecution(
            execution_id="exec_minimal",
            workflow_id="wf_001"
        )
        
        assert execution.execution_id == "exec_minimal"
        assert execution.workflow_id == "wf_001"
        assert execution.status == WorkflowStatus.PENDING


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
