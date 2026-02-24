"""
Test suite for AI Agent Orchestration functionality
Tests agent workflow creation, execution, and verification
"""

import pytest
import asyncio
import json
from datetime import datetime
from uuid import uuid4

from sqlmodel import Session, select, create_engine
from sqlalchemy import StaticPool

from src.app.domain.agent import (
    AIAgentWorkflow, AgentStep, AgentExecution, AgentStepExecution,
    AgentStatus, VerificationLevel, StepType,
    AgentWorkflowCreate, AgentExecutionRequest
)
from src.app.services.agent_service import AIAgentOrchestrator, AgentStateManager, AgentVerifier
# Mock CoordinatorClient for testing
class CoordinatorClient:
    """Mock coordinator client for testing"""
    pass


@pytest.fixture
def session():
    """Create test database session"""
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
        echo=False
    )
    
    # Create tables
    from src.app.domain.agent import AIAgentWorkflow, AgentStep, AgentExecution, AgentStepExecution, AgentMarketplace
    AIAgentWorkflow.metadata.create_all(engine)
    AgentStep.metadata.create_all(engine)
    AgentExecution.metadata.create_all(engine)
    AgentStepExecution.metadata.create_all(engine)
    AgentMarketplace.metadata.create_all(engine)
    
    with Session(engine) as session:
        yield session


class TestAgentWorkflowCreation:
    """Test agent workflow creation and management"""
    
    def test_create_workflow(self, session: Session):
        """Test creating a basic agent workflow"""
        
        workflow_data = AgentWorkflowCreate(
            name="Test ML Pipeline",
            description="A simple ML inference pipeline",
            steps={
                "step_1": {
                    "name": "Data Preprocessing",
                    "step_type": "data_processing",
                    "model_requirements": {"memory": "256MB"},
                    "timeout_seconds": 60
                },
                "step_2": {
                    "name": "Model Inference",
                    "step_type": "inference",
                    "model_requirements": {"model": "text_classifier", "memory": "512MB"},
                    "timeout_seconds": 120
                },
                "step_3": {
                    "name": "Post Processing",
                    "step_type": "data_processing",
                    "model_requirements": {"memory": "128MB"},
                    "timeout_seconds": 30
                }
            },
            dependencies={
                "step_2": ["step_1"],  # Inference depends on preprocessing
                "step_3": ["step_2"]   # Post processing depends on inference
            },
            max_execution_time=1800,
            requires_verification=True,
            verification_level=VerificationLevel.BASIC,
            tags=["ml", "inference", "test"]
        )
        
        workflow = AIAgentWorkflow(
            owner_id="test_user",
            name="Test ML Pipeline",
            description="A simple ML inference pipeline",
            steps=workflow_data.steps,
            dependencies=workflow_data.dependencies,
            max_execution_time=workflow_data.max_execution_time,
            max_cost_budget=workflow_data.max_cost_budget,
            requires_verification=workflow_data.requires_verification,
            verification_level=workflow_data.verification_level,
            tags=json.dumps(workflow_data.tags),  # Convert list to JSON string
            version="1.0.0",
            is_public=workflow_data.is_public
        )
        
        session.add(workflow)
        session.commit()
        session.refresh(workflow)
        
        assert workflow.id is not None
        assert workflow.name == "Test ML Pipeline"
        assert len(workflow.steps) == 3
        assert workflow.requires_verification is True
        assert workflow.verification_level == VerificationLevel.BASIC
        assert workflow.created_at is not None
    
    def test_workflow_steps_creation(self, session: Session):
        """Test creating workflow steps"""
        
        workflow = AIAgentWorkflow(
            owner_id="test_user",
            name="Test Workflow",
            steps=[{"name": "Step 1", "step_type": "inference"}]
        )
        
        session.add(workflow)
        session.commit()
        session.refresh(workflow)
        
        # Create steps
        step1 = AgentStep(
            workflow_id=workflow.id,
            step_order=0,
            name="Data Input",
            step_type=StepType.DATA_PROCESSING,
            timeout_seconds=30
        )
        
        step2 = AgentStep(
            workflow_id=workflow.id,
            step_order=1,
            name="Model Inference",
            step_type=StepType.INFERENCE,
            timeout_seconds=60,
            depends_on=[step1.id]
        )
        
        session.add(step1)
        session.add(step2)
        session.commit()
        
        # Verify steps
        steps = session.exec(
            select(AgentStep).where(AgentStep.workflow_id == workflow.id)
        ).all()
        
        assert len(steps) == 2
        assert steps[0].step_order == 0
        assert steps[1].step_order == 1
        assert steps[1].depends_on == [step1.id]


class TestAgentStateManager:
    """Test agent state management functionality"""
    
    def test_create_execution(self, session: Session):
        """Test creating an agent execution"""
        
        # Create workflow
        workflow = AIAgentWorkflow(
            owner_id="test_user",
            name="Test Workflow",
            steps=[{"name": "Step 1", "step_type": "inference"}]
        )
        session.add(workflow)
        session.commit()
        
        # Create execution
        state_manager = AgentStateManager(session)
        execution = asyncio.run(
            state_manager.create_execution(
                workflow_id=workflow.id,
                client_id="test_client",
                verification_level=VerificationLevel.BASIC
            )
        )
        
        assert execution.id is not None
        assert execution.workflow_id == workflow.id
        assert execution.client_id == "test_client"
        assert execution.status == AgentStatus.PENDING
        assert execution.verification_level == VerificationLevel.BASIC
    
    def test_update_execution_status(self, session: Session):
        """Test updating execution status"""
        
        # Create workflow and execution
        workflow = AIAgentWorkflow(
            owner_id="test_user",
            name="Test Workflow",
            steps=[{"name": "Step 1", "step_type": "inference"}]
        )
        session.add(workflow)
        session.commit()
        
        state_manager = AgentStateManager(session)
        execution = asyncio.run(
            state_manager.create_execution(workflow.id, "test_client")
        )
        
        # Update status
        updated_execution = asyncio.run(
            state_manager.update_execution_status(
                execution.id,
                AgentStatus.RUNNING,
                started_at=datetime.utcnow(),
                total_steps=3
            )
        )
        
        assert updated_execution.status == AgentStatus.RUNNING
        assert updated_execution.started_at is not None
        assert updated_execution.total_steps == 3


class TestAgentVerifier:
    """Test agent verification functionality"""
    
    def test_basic_verification(self, session: Session):
        """Test basic step verification"""
        
        verifier = AgentVerifier()
        
        # Create step execution
        step_execution = AgentStepExecution(
            execution_id="test_exec",
            step_id="test_step",
            status=AgentStatus.COMPLETED,
            output_data={"result": "success"},
            execution_time=1.5
        )
        
        verification_result = asyncio.run(
            verifier.verify_step_execution(step_execution, VerificationLevel.BASIC)
        )
        
        assert verification_result["verified"] is True
        assert verification_result["verification_level"] == VerificationLevel.BASIC
        assert verification_result["verification_time"] > 0
        assert "completion" in verification_result["checks"]
    
    def test_basic_verification_failure(self, session: Session):
        """Test basic verification with failed step"""
        
        verifier = AgentVerifier()
        
        # Create failed step execution
        step_execution = AgentStepExecution(
            execution_id="test_exec",
            step_id="test_step",
            status=AgentStatus.FAILED,
            error_message="Processing failed"
        )
        
        verification_result = asyncio.run(
            verifier.verify_step_execution(step_execution, VerificationLevel.BASIC)
        )
        
        assert verification_result["verified"] is False
        assert verification_result["verification_level"] == VerificationLevel.BASIC
    
    def test_full_verification(self, session: Session):
        """Test full verification with additional checks"""
        
        verifier = AgentVerifier()
        
        # Create successful step execution with performance data
        step_execution = AgentStepExecution(
            execution_id="test_exec",
            step_id="test_step",
            status=AgentStatus.COMPLETED,
            output_data={"result": "success"},
            execution_time=10.5,  # Reasonable time
            memory_usage=512.0    # Reasonable memory
        )
        
        verification_result = asyncio.run(
            verifier.verify_step_execution(step_execution, VerificationLevel.FULL)
        )
        
        assert verification_result["verified"] is True
        assert verification_result["verification_level"] == VerificationLevel.FULL
        assert "reasonable_execution_time" in verification_result["checks"]
        assert "reasonable_memory_usage" in verification_result["checks"]


class TestAIAgentOrchestrator:
    """Test AI agent orchestration functionality"""
    
    def test_workflow_execution_request(self, session: Session, monkeypatch):
        """Test workflow execution request"""
        
        # Create workflow
        workflow = AIAgentWorkflow(
            owner_id="test_user",
            name="Test Workflow",
            steps=[
                {"name": "Step 1", "step_type": "inference"},
                {"name": "Step 2", "step_type": "data_processing"}
            ],
            dependencies={},
            max_execution_time=300
        )
        session.add(workflow)
        session.commit()
        
        # Mock coordinator client
        class MockCoordinatorClient:
            pass
        
        monkeypatch.setattr("app.services.agent_service.CoordinatorClient", MockCoordinatorClient)
        
        # Create orchestrator
        orchestrator = AIAgentOrchestrator(session, MockCoordinatorClient())
        
        # Create execution request
        request = AgentExecutionRequest(
            workflow_id=workflow.id,
            inputs={"data": "test_input"},
            verification_level=VerificationLevel.BASIC
        )
        
        # Execute workflow (this will start async execution)
        response = asyncio.run(
            orchestrator.execute_workflow(request, "test_client")
        )
        
        assert response.execution_id is not None
        assert response.workflow_id == workflow.id
        assert response.status == AgentStatus.RUNNING
        assert response.total_steps == 2
        assert response.current_step == 0
        assert response.started_at is not None
    
    def test_execution_status_retrieval(self, session: Session, monkeypatch):
        """Test getting execution status"""
        
        # Create workflow and execution
        workflow = AIAgentWorkflow(
            owner_id="test_user",
            name="Test Workflow",
            steps=[{"name": "Step 1", "step_type": "inference"}]
        )
        session.add(workflow)
        session.commit()
        
        state_manager = AgentStateManager(session)
        execution = asyncio.run(
            state_manager.create_execution(workflow.id, "test_client")
        )
        
        # Mock coordinator client
        class MockCoordinatorClient:
            pass
        
        monkeypatch.setattr("app.services.agent_service.CoordinatorClient", MockCoordinatorClient)
        
        # Create orchestrator
        orchestrator = AIAgentOrchestrator(session, MockCoordinatorClient())
        
        # Get status
        status = asyncio.run(orchestrator.get_execution_status(execution.id))
        
        assert status.execution_id == execution.id
        assert status.workflow_id == workflow.id
        assert status.status == AgentStatus.PENDING
    
    def test_step_execution_order(self, session: Session):
        """Test step execution order with dependencies"""
        
        # Create workflow with dependencies
        workflow = AIAgentWorkflow(
            owner_id="test_user",
            name="Test Workflow",
            steps=[
                {"name": "Step 1", "step_type": "data_processing"},
                {"name": "Step 2", "step_type": "inference"},
                {"name": "Step 3", "step_type": "data_processing"}
            ],
            dependencies={
                "step_2": ["step_1"],  # Step 2 depends on Step 1
                "step_3": ["step_2"]   # Step 3 depends on Step 2
            }
        )
        session.add(workflow)
        session.commit()
        
        # Create steps
        steps = [
            AgentStep(workflow_id=workflow.id, step_order=0, name="Step 1", id="step_1"),
            AgentStep(workflow_id=workflow.id, step_order=1, name="Step 2", id="step_2"),
            AgentStep(workflow_id=workflow.id, step_order=2, name="Step 3", id="step_3")
        ]
        
        for step in steps:
            session.add(step)
        session.commit()
        
        # Mock coordinator client
        class MockCoordinatorClient:
            pass
        
        orchestrator = AIAgentOrchestrator(session, MockCoordinatorClient())
        
        # Test execution order
        execution_order = orchestrator._build_execution_order(
            steps, workflow.dependencies
        )
        
        assert execution_order == ["step_1", "step_2", "step_3"]
    
    def test_circular_dependency_detection(self, session: Session):
        """Test circular dependency detection"""
        
        # Create workflow with circular dependencies
        workflow = AIAgentWorkflow(
            owner_id="test_user",
            name="Test Workflow",
            steps=[
                {"name": "Step 1", "step_type": "data_processing"},
                {"name": "Step 2", "step_type": "inference"}
            ],
            dependencies={
                "step_1": ["step_2"],  # Step 1 depends on Step 2
                "step_2": ["step_1"]   # Step 2 depends on Step 1 (circular!)
            }
        )
        session.add(workflow)
        session.commit()
        
        # Create steps
        steps = [
            AgentStep(workflow_id=workflow.id, step_order=0, name="Step 1", id="step_1"),
            AgentStep(workflow_id=workflow.id, step_order=1, name="Step 2", id="step_2")
        ]
        
        for step in steps:
            session.add(step)
        session.commit()
        
        # Mock coordinator client
        class MockCoordinatorClient:
            pass
        
        orchestrator = AIAgentOrchestrator(session, MockCoordinatorClient())
        
        # Test circular dependency detection
        with pytest.raises(ValueError, match="Circular dependency"):
            orchestrator._build_execution_order(steps, workflow.dependencies)


class TestAgentAPIEndpoints:
    """Test agent API endpoints"""
    
    def test_create_workflow_endpoint(self, client, session):
        """Test workflow creation API endpoint"""
        
        workflow_data = {
            "name": "API Test Workflow",
            "description": "Created via API",
            "steps": [
                {
                    "name": "Data Input",
                    "step_type": "data_processing",
                    "timeout_seconds": 30
                }
            ],
            "dependencies": {},
            "requires_verification": True,
            "tags": ["api", "test"]
        }
        
        response = client.post("/agents/workflows", json=workflow_data)
        
        assert response.status_code == 200
        data = response.json()
        assert data["name"] == "API Test Workflow"
        assert data["owner_id"] is not None
        assert len(data["steps"]) == 1
    
    def test_list_workflows_endpoint(self, client, session):
        """Test workflow listing API endpoint"""
        
        # Create test workflow
        workflow = AIAgentWorkflow(
            owner_id="test_user",
            name="List Test Workflow",
            steps=[{"name": "Step 1", "step_type": "inference"}],
            is_public=True
        )
        session.add(workflow)
        session.commit()
        
        response = client.get("/agents/workflows")
        
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        assert len(data) >= 1
    
    def test_execute_workflow_endpoint(self, client, session):
        """Test workflow execution API endpoint"""
        
        # Create test workflow
        workflow = AIAgentWorkflow(
            owner_id="test_user",
            name="Execute Test Workflow",
            steps=[
                {"name": "Step 1", "step_type": "inference"},
                {"name": "Step 2", "step_type": "data_processing"}
            ],
            dependencies={},
            is_public=True
        )
        session.add(workflow)
        session.commit()
        
        execution_request = {
            "inputs": {"data": "test_input"},
            "verification_level": "basic"
        }
        
        response = client.post(
            f"/agents/workflows/{workflow.id}/execute",
            json=execution_request
        )
        
        assert response.status_code == 200
        data = response.json()
        assert data["execution_id"] is not None
        assert data["workflow_id"] == workflow.id
        assert data["status"] == "running"
    
    def test_get_execution_status_endpoint(self, client, session):
        """Test execution status API endpoint"""
        
        # Create test workflow and execution
        workflow = AIAgentWorkflow(
            owner_id="test_user",
            name="Status Test Workflow",
            steps=[{"name": "Step 1", "step_type": "inference"}],
            is_public=True
        )
        session.add(workflow)
        session.commit()
        
        execution = AgentExecution(
            workflow_id=workflow.id,
            client_id="test_client",
            status=AgentStatus.PENDING
        )
        session.add(execution)
        session.commit()
        
        response = client.get(f"/agents/executions/{execution.id}/status")
        
        assert response.status_code == 200
        data = response.json()
        assert data["execution_id"] == execution.id
        assert data["workflow_id"] == workflow.id
        assert data["status"] == "pending"


if __name__ == "__main__":
    pytest.main([__file__])
