"""
OpenClaw Enhanced Service Tests - Phase 6.6
Tests for advanced agent orchestration, edge computing integration, and ecosystem development
"""

import pytest
import asyncio
from datetime import datetime
from uuid import uuid4

from sqlmodel import Session, create_engine
from sqlalchemy import StaticPool

from src.app.services.openclaw_enhanced import (
    OpenClawEnhancedService, SkillType, ExecutionMode
)
from src.app.domain import AIAgentWorkflow, AgentExecution, AgentStatus
from src.app.schemas.openclaw_enhanced import (
    SkillRoutingRequest, JobOffloadingRequest, AgentCollaborationRequest,
    HybridExecutionRequest, EdgeDeploymentRequest, EdgeCoordinationRequest,
    EcosystemDevelopmentRequest
)


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
    AIAgentWorkflow.metadata.create_all(engine)
    AgentExecution.metadata.create_all(engine)
    
    with Session(engine) as session:
        yield session


@pytest.fixture
def sample_workflow(session: Session):
    """Create sample AI agent workflow"""
    workflow = AIAgentWorkflow(
        id=f"workflow_{uuid4().hex[:8]}",
        owner_id="test_user",
        name="Test Workflow",
        description="Test workflow for OpenClaw integration",
        steps={"step1": {"type": "inference", "model": "test_model"}},
        dependencies={}
    )
    session.add(workflow)
    session.commit()
    return workflow


class TestOpenClawEnhancedService:
    """Test OpenClaw enhanced service functionality"""
    
    @pytest.mark.asyncio
    async def test_route_agent_skill_inference(self, session: Session):
        """Test routing agent skill for inference"""
        
        enhanced_service = OpenClawEnhancedService(session)
        
        requirements = {
            "model_type": "llm",
            "performance_requirement": 0.8,
            "max_cost": 0.5
        }
        
        result = await enhanced_service.route_agent_skill(
            skill_type=SkillType.INFERENCE,
            requirements=requirements,
            performance_optimization=True
        )
        
        assert "selected_agent" in result
        assert "routing_strategy" in result
        assert "expected_performance" in result
        assert "estimated_cost" in result
        
        # Check selected agent structure
        agent = result["selected_agent"]
        assert "agent_id" in agent
        assert "skill_type" in agent
        assert "performance_score" in agent
        assert "cost_per_hour" in agent
        assert agent["skill_type"] == SkillType.INFERENCE.value
        
        assert result["routing_strategy"] == "performance_optimized"
        assert isinstance(result["expected_performance"], (int, float))
        assert isinstance(result["estimated_cost"], (int, float))
    
    @pytest.mark.asyncio
    async def test_route_agent_skill_cost_optimization(self, session: Session):
        """Test routing agent skill with cost optimization"""
        
        enhanced_service = OpenClawEnhancedService(session)
        
        requirements = {
            "model_type": "training",
            "performance_requirement": 0.7,
            "max_cost": 1.0
        }
        
        result = await enhanced_service.route_agent_skill(
            skill_type=SkillType.TRAINING,
            requirements=requirements,
            performance_optimization=False
        )
        
        assert result["routing_strategy"] == "cost_optimized"
    
    @pytest.mark.asyncio
    async def test_intelligent_job_offloading(self, session: Session):
        """Test intelligent job offloading strategies"""
        
        enhanced_service = OpenClawEnhancedService(session)
        
        job_data = {
            "task_type": "inference",
            "model_size": "large",
            "batch_size": 32,
            "deadline": "2024-01-01T00:00:00Z"
        }
        
        result = await enhanced_service.offload_job_intelligently(
            job_data=job_data,
            cost_optimization=True,
            performance_analysis=True
        )
        
        assert "should_offload" in result
        assert "job_size" in result
        assert "cost_analysis" in result
        assert "performance_prediction" in result
        assert "fallback_mechanism" in result
        
        # Check job size analysis
        job_size = result["job_size"]
        assert "complexity" in job_size
        assert "estimated_duration" in job_size
        assert "resource_requirements" in job_size
        
        # Check cost analysis
        cost_analysis = result["cost_analysis"]
        assert "should_offload" in cost_analysis
        assert "estimated_savings" in cost_analysis
        
        # Check performance prediction
        performance = result["performance_prediction"]
        assert "local_time" in performance
        assert "aitbc_time" in performance
        
        assert result["fallback_mechanism"] == "local_execution"
    
    @pytest.mark.asyncio
    async def test_coordinate_agent_collaboration(self, session: Session):
        """Test agent collaboration and coordination"""
        
        enhanced_service = OpenClawEnhancedService(session)
        
        task_data = {
            "task_type": "distributed_inference",
            "complexity": "high",
            "requirements": {"coordination": "required"}
        }
        
        agent_ids = [f"agent_{i}" for i in range(3)]
        
        result = await enhanced_service.coordinate_agent_collaboration(
            task_data=task_data,
            agent_ids=agent_ids,
            coordination_algorithm="distributed_consensus"
        )
        
        assert "coordination_method" in result
        assert "selected_coordinator" in result
        assert "consensus_reached" in result
        assert "task_distribution" in result
        assert "estimated_completion_time" in result
        
        assert result["coordination_method"] == "distributed_consensus"
        assert result["consensus_reached"] is True
        assert result["selected_coordinator"] in agent_ids
        
        # Check task distribution
        task_dist = result["task_distribution"]
        for agent_id in agent_ids:
            assert agent_id in task_dist
        
        assert isinstance(result["estimated_completion_time"], (int, float))
    
    @pytest.mark.asyncio
    async def test_coordinate_agent_collaboration_central(self, session: Session):
        """Test agent collaboration with central coordination"""
        
        enhanced_service = OpenClawEnhancedService(session)
        
        task_data = {"task_type": "simple_task"}
        agent_ids = [f"agent_{i}" for i in range(2)]
        
        result = await enhanced_service.coordinate_agent_collaboration(
            task_data=task_data,
            agent_ids=agent_ids,
            coordination_algorithm="central_coordination"
        )
        
        assert result["coordination_method"] == "central_coordination"
    
    @pytest.mark.asyncio
    async def test_coordinate_agent_collaboration_insufficient_agents(self, session: Session):
        """Test agent collaboration with insufficient agents"""
        
        enhanced_service = OpenClawEnhancedService(session)
        
        task_data = {"task_type": "test"}
        agent_ids = ["single_agent"]  # Only one agent
        
        with pytest.raises(ValueError, match="At least 2 agents required"):
            await enhanced_service.coordinate_agent_collaboration(
                task_data=task_data,
                agent_ids=agent_ids
            )
    
    @pytest.mark.asyncio
    async def test_optimize_hybrid_execution_performance(self, session: Session):
        """Test hybrid execution optimization for performance"""
        
        enhanced_service = OpenClawEnhancedService(session)
        
        execution_request = {
            "task_type": "inference",
            "complexity": 0.8,
            "resources": {"gpu_required": True},
            "performance": {"target_latency": 100}
        }
        
        result = await enhanced_service.optimize_hybrid_execution(
            execution_request=execution_request,
            optimization_strategy="performance"
        )
        
        assert "execution_mode" in result
        assert "strategy" in result
        assert "resource_allocation" in result
        assert "performance_tuning" in result
        assert "expected_improvement" in result
        
        assert result["execution_mode"] == ExecutionMode.HYBRID.value
        
        # Check strategy
        strategy = result["strategy"]
        assert "local_ratio" in strategy
        assert "aitbc_ratio" in strategy
        assert "optimization_target" in strategy
        assert strategy["optimization_target"] == "maximize_throughput"
        
        # Check resource allocation
        resources = result["resource_allocation"]
        assert "local_resources" in resources
        assert "aitbc_resources" in resources
        
        # Check performance tuning
        tuning = result["performance_tuning"]
        assert "batch_size" in tuning
        assert "parallel_workers" in tuning
    
    @pytest.mark.asyncio
    async def test_optimize_hybrid_execution_cost(self, session: Session):
        """Test hybrid execution optimization for cost"""
        
        enhanced_service = OpenClawEnhancedService(session)
        
        execution_request = {
            "task_type": "training",
            "cost_constraints": {"max_budget": 100.0}
        }
        
        result = await enhanced_service.optimize_hybrid_execution(
            execution_request=execution_request,
            optimization_strategy="cost"
        )
        
        strategy = result["strategy"]
        assert strategy["optimization_target"] == "minimize_cost"
        assert strategy["local_ratio"] > strategy["aitbc_ratio"]  # More local for cost optimization
    
    @pytest.mark.asyncio
    async def test_deploy_to_edge(self, session: Session):
        """Test deploying agent to edge computing infrastructure"""
        
        enhanced_service = OpenClawEnhancedService(session)
        
        agent_id = f"agent_{uuid4().hex[:8]}"
        edge_locations = ["us-west", "us-east", "eu-central"]
        deployment_config = {
            "auto_scale": True,
            "instances": 3,
            "security_level": "high"
        }
        
        result = await enhanced_service.deploy_to_edge(
            agent_id=agent_id,
            edge_locations=edge_locations,
            deployment_config=deployment_config
        )
        
        assert "deployment_id" in result
        assert "agent_id" in result
        assert "edge_locations" in result
        assert "deployment_results" in result
        assert "status" in result
        
        assert result["agent_id"] == agent_id
        assert result["status"] == "deployed"
        
        # Check edge locations
        locations = result["edge_locations"]
        assert len(locations) == 3
        assert "us-west" in locations
        assert "us-east" in locations
        assert "eu-central" in locations
        
        # Check deployment results
        deployment_results = result["deployment_results"]
        assert len(deployment_results) == 3
        
        for deployment_result in deployment_results:
            assert "location" in deployment_result
            assert "deployment_status" in deployment_result
            assert "endpoint" in deployment_result
            assert "response_time_ms" in deployment_result
    
    @pytest.mark.asyncio
    async def test_deploy_to_edge_invalid_locations(self, session: Session):
        """Test deploying to invalid edge locations"""
        
        enhanced_service = OpenClawEnhancedService(session)
        
        agent_id = f"agent_{uuid4().hex[:8]}"
        edge_locations = ["invalid_location", "another_invalid"]
        deployment_config = {}
        
        result = await enhanced_service.deploy_to_edge(
            agent_id=agent_id,
            edge_locations=edge_locations,
            deployment_config=deployment_config
        )
        
        # Should filter out invalid locations
        assert len(result["edge_locations"]) == 0
        assert len(result["deployment_results"]) == 0
    
    @pytest.mark.asyncio
    async def test_coordinate_edge_to_cloud(self, session: Session):
        """Test coordinating edge-to-cloud agent operations"""
        
        enhanced_service = OpenClawEnhancedService(session)
        
        edge_deployment_id = f"deployment_{uuid4().hex[:8]}"
        coordination_config = {
            "sync_interval": 30,
            "load_balance_algorithm": "round_robin",
            "failover_enabled": True
        }
        
        result = await enhanced_service.coordinate_edge_to_cloud(
            edge_deployment_id=edge_deployment_id,
            coordination_config=coordination_config
        )
        
        assert "coordination_id" in result
        assert "edge_deployment_id" in result
        assert "synchronization" in result
        assert "load_balancing" in result
        assert "failover" in result
        assert "status" in result
        
        assert result["edge_deployment_id"] == edge_deployment_id
        assert result["status"] == "coordinated"
        
        # Check synchronization
        sync = result["synchronization"]
        assert "sync_status" in sync
        assert "last_sync" in sync
        assert "data_consistency" in sync
        
        # Check load balancing
        lb = result["load_balancing"]
        assert "balancing_algorithm" in lb
        assert "active_connections" in lb
        assert "average_response_time" in lb
        
        # Check failover
        failover = result["failover"]
        assert "failover_strategy" in failover
        assert "health_check_interval" in failover
        assert "backup_locations" in failover
    
    @pytest.mark.asyncio
    async def test_develop_openclaw_ecosystem(self, session: Session):
        """Test building comprehensive OpenClaw ecosystem"""
        
        enhanced_service = OpenClawEnhancedService(session)
        
        ecosystem_config = {
            "developer_tools": {"languages": ["python", "javascript"]},
            "marketplace": {"categories": ["inference", "training"]},
            "community": {"forum": True, "documentation": True},
            "partnerships": {"technology_partners": True}
        }
        
        result = await enhanced_service.develop_openclaw_ecosystem(
            ecosystem_config=ecosystem_config
        )
        
        assert "ecosystem_id" in result
        assert "developer_tools" in result
        assert "marketplace" in result
        assert "community" in result
        assert "partnerships" in result
        assert "status" in result
        
        assert result["status"] == "active"
        
        # Check developer tools
        dev_tools = result["developer_tools"]
        assert "sdk_version" in dev_tools
        assert "languages" in dev_tools
        assert "tools" in dev_tools
        assert "documentation" in dev_tools
        
        # Check marketplace
        marketplace = result["marketplace"]
        assert "marketplace_url" in marketplace
        assert "agent_categories" in marketplace
        assert "payment_methods" in marketplace
        assert "revenue_model" in marketplace
        
        # Check community
        community = result["community"]
        assert "governance_model" in community
        assert "voting_mechanism" in community
        assert "community_forum" in community
        
        # Check partnerships
        partnerships = result["partnerships"]
        assert "technology_partners" in partnerships
        assert "integration_partners" in partnerships
        assert "reseller_program" in partnerships
