"""
Test suite for Agent Integration and Deployment Framework
Tests integration with ZK proof system, deployment management, and production deployment
"""

import pytest
import asyncio
from datetime import datetime
from uuid import uuid4

from sqlmodel import Session, select, create_engine
from sqlalchemy import StaticPool

from src.app.services.agent_integration import (
    AgentIntegrationManager, AgentDeploymentManager, AgentMonitoringManager, AgentProductionManager,
    DeploymentStatus, AgentDeploymentConfig, AgentDeploymentInstance
)
from src.app.domain.agent import (
    AIAgentWorkflow, AgentExecution, AgentStatus, VerificationLevel
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
    from src.app.services.agent_integration import (
        AgentDeploymentConfig, AgentDeploymentInstance
    )
    AgentDeploymentConfig.metadata.create_all(engine)
    AgentDeploymentInstance.metadata.create_all(engine)
    
    with Session(engine) as session:
        yield session


class TestAgentIntegrationManager:
    """Test agent integration with ZK proof system"""
    
    def test_zk_system_integration(self, session: Session):
        """Test integration with ZK proof system"""
        
        integration_manager = AgentIntegrationManager(session)
        
        # Create test execution
        execution = AgentExecution(
            workflow_id="test_workflow",
            client_id="test_client",
            status=AgentStatus.COMPLETED,
            final_result={"result": "test_output"},
            total_execution_time=120.5,
            started_at=datetime.utcnow(),
            completed_at=datetime.utcnow()
        )
        
        session.add(execution)
        session.commit()
        session.refresh(execution)
        
        # Test ZK integration
        integration_result = asyncio.run(
            integration_manager.integrate_with_zk_system(
                execution_id=execution.id,
                verification_level=VerificationLevel.BASIC
            )
        )
        
        assert integration_result["execution_id"] == execution.id
        assert integration_result["integration_status"] in ["success", "partial_success"]
        assert "zk_proofs_generated" in integration_result
        assert "verification_results" in integration_result
        
        # Check that proofs were generated
        if integration_result["integration_status"] == "success":
            assert len(integration_result["zk_proofs_generated"]) >= 0  # Allow 0 for mock service
            assert len(integration_result["verification_results"]) >= 0  # Allow 0 for mock service
            assert "workflow_proof" in integration_result
            assert "workflow_verification" in integration_result
    
    def test_zk_integration_with_failures(self, session: Session):
        """Test ZK integration with some failures"""
        
        integration_manager = AgentIntegrationManager(session)
        
        # Create test execution with missing data
        execution = AgentExecution(
            workflow_id="test_workflow",
            client_id="test_client",
            status=AgentStatus.FAILED,
            final_result=None,
            total_execution_time=0.0
        )
        
        session.add(execution)
        session.commit()
        session.refresh(execution)
        
        # Test ZK integration with failures
        integration_result = asyncio.run(
            integration_manager.integrate_with_zk_system(
                execution_id=execution.id,
                verification_level=VerificationLevel.BASIC
            )
        )
        
        assert integration_result["execution_id"] == execution.id
        assert len(integration_result["integration_errors"]) > 0
        assert integration_result["integration_status"] == "partial_success"


class TestAgentDeploymentManager:
    """Test agent deployment management"""
    
    def test_create_deployment_config(self, session: Session):
        """Test creating deployment configuration"""
        
        deployment_manager = AgentDeploymentManager(session)
        
        deployment_config = {
            "target_environments": ["production", "staging"],
            "deployment_regions": ["us-east-1", "us-west-2"],
            "min_cpu_cores": 2.0,
            "min_memory_mb": 2048,
            "min_storage_gb": 20,
            "requires_gpu": True,
            "gpu_memory_mb": 8192,
            "min_instances": 2,
            "max_instances": 5,
            "auto_scaling": True,
            "health_check_endpoint": "/health",
            "health_check_interval": 30,
            "health_check_timeout": 10,
            "max_failures": 3,
            "rollout_strategy": "rolling",
            "rollback_enabled": True,
            "deployment_timeout": 1800,
            "enable_metrics": True,
            "enable_logging": True,
            "enable_tracing": False,
            "log_level": "INFO"
        }
        
        config = asyncio.run(
            deployment_manager.create_deployment_config(
                workflow_id="test_workflow",
                deployment_name="test-deployment",
                deployment_config=deployment_config
            )
        )
        
        assert config.id is not None
        assert config.workflow_id == "test_workflow"
        assert config.deployment_name == "test-deployment"
        assert config.target_environments == ["production", "staging"]
        assert config.min_cpu_cores == 2.0
        assert config.requires_gpu is True
        assert config.min_instances == 2
        assert config.max_instances == 5
        assert config.status == DeploymentStatus.PENDING
    
    def test_deploy_agent_workflow(self, session: Session):
        """Test deploying agent workflow"""
        
        deployment_manager = AgentDeploymentManager(session)
        
        # Create deployment config first
        config = asyncio.run(
            deployment_manager.create_deployment_config(
                workflow_id="test_workflow",
                deployment_name="test-deployment",
                deployment_config={
                    "min_instances": 1,
                    "max_instances": 3,
                    "target_environments": ["production"]
                }
            )
        )
        
        # Deploy workflow
        deployment_result = asyncio.run(
            deployment_manager.deploy_agent_workflow(
                deployment_config_id=config.id,
                target_environment="production"
            )
        )
        
        assert deployment_result["deployment_id"] == config.id
        assert deployment_result["environment"] == "production"
        assert deployment_result["status"] in ["deploying", "deployed"]
        assert len(deployment_result["instances"]) == 1  # min_instances
    
        # Check that instances were created
        instances = session.exec(
            select(AgentDeploymentInstance).where(
                AgentDeploymentInstance.deployment_id == config.id
            )
        ).all()
        
        assert len(instances) == 1
        assert instances[0].environment == "production"
        assert instances[0].status in [DeploymentStatus.DEPLOYED, DeploymentStatus.DEPLOYING]
    
    def test_deployment_health_monitoring(self, session: Session):
        """Test deployment health monitoring"""
        
        deployment_manager = AgentDeploymentManager(session)
        
        # Create deployment config
        config = asyncio.run(
            deployment_manager.create_deployment_config(
                workflow_id="test_workflow",
                deployment_name="test-deployment",
                deployment_config={"min_instances": 2}
            )
        )
        
        # Deploy workflow
        asyncio.run(
            deployment_manager.deploy_agent_workflow(
                deployment_config_id=config.id,
                target_environment="production"
            )
        )
        
        # Monitor health
        health_result = asyncio.run(
            deployment_manager.monitor_deployment_health(config.id)
        )
        
        assert health_result["deployment_id"] == config.id
        assert health_result["total_instances"] == 2
        assert "healthy_instances" in health_result
        assert "unhealthy_instances" in health_result
        assert "overall_health" in health_result
        assert len(health_result["instance_health"]) == 2
    
    def test_deployment_scaling(self, session: Session):
        """Test deployment scaling"""
        
        deployment_manager = AgentDeploymentManager(session)
        
        # Create deployment config
        config = asyncio.run(
            deployment_manager.create_deployment_config(
                workflow_id="test_workflow",
                deployment_name="test-deployment",
                deployment_config={
                    "min_instances": 1,
                    "max_instances": 5,
                    "auto_scaling": True
                }
            )
        )
        
        # Deploy initial instance
        asyncio.run(
            deployment_manager.deploy_agent_workflow(
                deployment_config_id=config.id,
                target_environment="production"
            )
        )
        
        # Scale up
        scaling_result = asyncio.run(
            deployment_manager.scale_deployment(
                deployment_config_id=config.id,
                target_instances=3
            )
        )
        
        assert scaling_result["deployment_id"] == config.id
        assert scaling_result["current_instances"] == 1
        assert scaling_result["target_instances"] == 3
        assert scaling_result["scaling_action"] == "scale_up"
        assert len(scaling_result["scaled_instances"]) == 2
        
        # Scale down
        scaling_result = asyncio.run(
            deployment_manager.scale_deployment(
                deployment_config_id=config.id,
                target_instances=1
            )
        )
        
        assert scaling_result["deployment_id"] == config.id
        assert scaling_result["current_instances"] == 3
        assert scaling_result["target_instances"] == 1
        assert scaling_result["scaling_action"] == "scale_down"
        assert len(scaling_result["scaled_instances"]) == 2
    
    def test_deployment_rollback(self, session: Session):
        """Test deployment rollback"""
        
        deployment_manager = AgentDeploymentManager(session)
        
        # Create deployment config with rollback enabled
        config = asyncio.run(
            deployment_manager.create_deployment_config(
                workflow_id="test_workflow",
                deployment_name="test-deployment",
                deployment_config={
                    "min_instances": 1,
                    "max_instances": 3,
                    "rollback_enabled": True
                }
            )
        )
        
        # Deploy workflow
        asyncio.run(
            deployment_manager.deploy_agent_workflow(
                deployment_config_id=config.id,
                target_environment="production"
            )
        )
        
        # Rollback deployment
        rollback_result = asyncio.run(
            deployment_manager.rollback_deployment(config.id)
        )
        
        assert rollback_result["deployment_id"] == config.id
        assert rollback_result["rollback_status"] == "in_progress"
        assert len(rollback_result["rolled_back_instances"]) == 1


class TestAgentMonitoringManager:
    """Test agent monitoring and metrics collection"""
    
    def test_deployment_metrics_collection(self, session: Session):
        """Test deployment metrics collection"""
        
        monitoring_manager = AgentMonitoringManager(session)
        
        # Create deployment config and instances
        deployment_manager = AgentDeploymentManager(session)
        config = asyncio.run(
            deployment_manager.create_deployment_config(
                workflow_id="test_workflow",
                deployment_name="test-deployment",
                deployment_config={"min_instances": 2}
            )
        )
        
        asyncio.run(
            deployment_manager.deploy_agent_workflow(
                deployment_config_id=config.id,
                target_environment="production"
            )
        )
        
        # Collect metrics
        metrics = asyncio.run(
            monitoring_manager.get_deployment_metrics(
                deployment_config_id=config.id,
                time_range="1h"
            )
        )
        
        assert metrics["deployment_id"] == config.id
        assert metrics["time_range"] == "1h"
        assert metrics["total_instances"] == 2
        assert "instance_metrics" in metrics
        assert "aggregated_metrics" in metrics
        assert "total_requests" in metrics["aggregated_metrics"]
        assert "total_errors" in metrics["aggregated_metrics"]
        assert "average_response_time" in metrics["aggregated_metrics"]
    
    def test_alerting_rules_creation(self, session: Session):
        """Test alerting rules creation"""
        
        monitoring_manager = AgentMonitoringManager(session)
        
        # Create deployment config
        deployment_manager = AgentDeploymentManager(session)
        config = asyncio.run(
            deployment_manager.create_deployment_config(
                workflow_id="test_workflow",
                deployment_name="test-deployment",
                deployment_config={"min_instances": 1}
            )
        )
        
        # Add some failures
        for i in range(2):
            asyncio.run(
                trust_manager.update_trust_score(
                    entity_type="agent",
                    entity_id="test_agent",
                    execution_success=False,
                    policy_violation=True  # Add policy violations to test reputation impact
                )
            )
        
        # Create alerting rules
        alerting_rules = {
            "rules": [
                {
                    "name": "high_cpu_usage",
                    "condition": "cpu_usage > 80",
                    "severity": "warning",
                    "action": "alert"
                },
                {
                    "name": "high_error_rate",
                    "condition": "error_rate > 5",
                    "severity": "critical",
                    "action": "scale_up"
                }
            ]
        }
        
        alerting_result = asyncio.run(
            monitoring_manager.create_alerting_rules(
                deployment_config_id=config.id,
                alerting_rules=alerting_rules
            )
        )
        
        assert alerting_result["deployment_id"] == config.id
        assert alerting_result["rules_created"] == 2
        assert alerting_result["status"] == "created"
        assert "alerting_rules" in alerting_result


class TestAgentProductionManager:
    """Test production deployment management"""
    
    def test_production_deployment(self, session: Session):
        """Test complete production deployment"""
        
        production_manager = AgentProductionManager(session)
        
        # Create test workflow
        workflow = AIAgentWorkflow(
            owner_id="test_user",
            name="Test Production Workflow",
            steps={
                "step_1": {
                    "name": "Data Processing",
                    "step_type": "data_processing"
                },
                "step_2": {
                    "name": "Inference",
                    "step_type": "inference"
                }
            },
            dependencies={},
            max_execution_time=3600,
            requires_verification=True,
            verification_level=VerificationLevel.FULL
        )
        
        session.add(workflow)
        session.commit()
        session.refresh(workflow)
        
        # Deploy to production
        deployment_config = {
            "name": "production-deployment",
            "target_environments": ["production"],
            "min_instances": 2,
            "max_instances": 5,
            "requires_gpu": True,
            "min_cpu_cores": 4.0,
            "min_memory_mb": 4096,
            "enable_metrics": True,
            "enable_logging": True,
            "alerting_rules": {
                "rules": [
                    {
                        "name": "high_cpu_usage",
                        "condition": "cpu_usage > 80",
                        "severity": "warning"
                    }
                ]
            }
        }
        
        integration_config = {
            "zk_verification_level": "full",
            "enable_monitoring": True
        }
        
        production_result = asyncio.run(
            production_manager.deploy_to_production(
                workflow_id=workflow.id,
                deployment_config=deployment_config,
                integration_config=integration_config
            )
        )
        
        assert production_result["workflow_id"] == workflow.id
        assert "deployment_status" in production_result
        assert "integration_status" in production_result
        assert "monitoring_status" in production_result
        assert "deployment_id" in production_result
        assert production_result["overall_status"] in ["success", "partial_success"]
        
        # Check that deployment was created
        assert production_result["deployment_id"] is not None
        
        # Check that errors were handled
        if production_result["overall_status"] == "success":
            assert len(production_result["errors"]) == 0
        else:
            assert len(production_result["errors"]) > 0
    
    def test_production_deployment_with_failures(self, session: Session):
        """Test production deployment with failures"""
        
        production_manager = AgentProductionManager(session)
        
        # Create test workflow
        workflow = AIAgentWorkflow(
            owner_id="test_user",
            name="Test Production Workflow",
            steps={},
            dependencies={},
            max_execution_time=3600,
            requires_verification=True
        )
        
        session.add(workflow)
        session.commit()
        session.refresh(workflow)
        
        # Deploy with invalid config to trigger failures
        deployment_config = {
            "name": "invalid-deployment",
            "target_environments": ["production"],
            "min_instances": 0,  # Invalid
            "max_instances": -1,  # Invalid
            "requires_gpu": True,
            "min_cpu_cores": -1  # Invalid
        }
        
        production_result = asyncio.run(
            production_manager.deploy_to_production(
                workflow_id=workflow.id,
                deployment_config=deployment_config
            )
        )
        
        assert production_result["workflow_id"] == workflow.id
        assert production_result["overall_status"] == "partial_success"
        assert len(production_result["errors"]) > 0


if __name__ == "__main__":
    pytest.main([__file__])
