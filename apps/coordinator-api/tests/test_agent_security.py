"""
Test suite for Agent Security and Audit Framework
Tests security policies, audit logging, trust scoring, and sandboxing
"""

import pytest
import asyncio
import json
import hashlib
from datetime import datetime
from uuid import uuid4

from sqlmodel import Session, select, create_engine
from sqlalchemy import StaticPool

from src.app.services.agent_security import (
    AgentAuditor, AgentTrustManager, AgentSandboxManager, AgentSecurityManager,
    SecurityLevel, AuditEventType, AgentSecurityPolicy, AgentTrustScore, AgentSandboxConfig
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
    from src.app.services.agent_security import (
        AgentAuditLog, AgentSecurityPolicy, AgentTrustScore, AgentSandboxConfig
    )
    AgentAuditLog.metadata.create_all(engine)
    AgentSecurityPolicy.metadata.create_all(engine)
    AgentTrustScore.metadata.create_all(engine)
    AgentSandboxConfig.metadata.create_all(engine)
    
    with Session(engine) as session:
        yield session


class TestAgentAuditor:
    """Test agent auditing functionality"""
    
    def test_log_basic_event(self, session: Session):
        """Test logging a basic audit event"""
        
        auditor = AgentAuditor(session)
        
        audit_log = asyncio.run(
            auditor.log_event(
                event_type=AuditEventType.WORKFLOW_CREATED,
                workflow_id="test_workflow",
                user_id="test_user",
                security_level=SecurityLevel.PUBLIC,
                event_data={"workflow_name": "Test Workflow"}
            )
        )
        
        assert audit_log.id is not None
        assert audit_log.event_type == AuditEventType.WORKFLOW_CREATED
        assert audit_log.workflow_id == "test_workflow"
        assert audit_log.user_id == "test_user"
        assert audit_log.security_level == SecurityLevel.PUBLIC
        assert audit_log.risk_score >= 0
        assert audit_log.cryptographic_hash is not None
    
    def test_risk_score_calculation(self, session: Session):
        """Test risk score calculation for different event types"""
        
        auditor = AgentAuditor(session)
        
        # Test low-risk event
        low_risk_event = asyncio.run(
            auditor.log_event(
                event_type=AuditEventType.EXECUTION_COMPLETED,
                workflow_id="test_workflow",
                user_id="test_user",
                security_level=SecurityLevel.PUBLIC,
                event_data={"execution_time": 60}
            )
        )
        
        # Test high-risk event
        high_risk_event = asyncio.run(
            auditor.log_event(
                event_type=AuditEventType.SECURITY_VIOLATION,
                workflow_id="test_workflow",
                user_id="test_user",
                security_level=SecurityLevel.RESTRICTED,
                event_data={"error_message": "Unauthorized access attempt"}
            )
        )
        
        assert low_risk_event.risk_score < high_risk_event.risk_score
        assert high_risk_event.requires_investigation is True
        assert high_risk_event.investigation_notes is not None
    
    def test_cryptographic_hashing(self, session: Session):
        """Test cryptographic hash generation for event data"""
        
        auditor = AgentAuditor(session)
        
        event_data = {"test": "data", "number": 123}
        audit_log = asyncio.run(
            auditor.log_event(
                event_type=AuditEventType.WORKFLOW_CREATED,
                workflow_id="test_workflow",
                user_id="test_user",
                event_data=event_data
            )
        )
        
        # Verify hash is generated correctly
        expected_hash = hashlib.sha256(
            json.dumps(event_data, sort_keys=True, separators=(',', ':')).encode()
        ).hexdigest()
        
        assert audit_log.cryptographic_hash == expected_hash


class TestAgentTrustManager:
    """Test agent trust and reputation management"""
    
    def test_create_trust_score(self, session: Session):
        """Test creating initial trust score"""
        
        trust_manager = AgentTrustManager(session)
        
        trust_score = asyncio.run(
            trust_manager.update_trust_score(
                entity_type="agent",
                entity_id="test_agent",
                execution_success=True,
                execution_time=120.5
            )
        )
        
        assert trust_score.id is not None
        assert trust_score.entity_type == "agent"
        assert trust_score.entity_id == "test_agent"
        assert trust_score.total_executions == 1
        assert trust_score.successful_executions == 1
        assert trust_score.failed_executions == 0
        assert trust_score.trust_score > 50  # Should be above neutral for successful execution
        assert trust_score.average_execution_time == 120.5
    
    def test_trust_score_calculation(self, session: Session):
        """Test trust score calculation with multiple executions"""
        
        trust_manager = AgentTrustManager(session)
        
        # Add multiple successful executions
        for i in range(10):
            asyncio.run(
                trust_manager.update_trust_score(
                    entity_type="agent",
                    entity_id="test_agent",
                    execution_success=True,
                    execution_time=100 + i
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
        
        # Get final trust score
        trust_score = session.exec(
            select(AgentTrustScore).where(
                (AgentTrustScore.entity_type == "agent") &
                (AgentTrustScore.entity_id == "test_agent")
            )
        ).first()
        
        assert trust_score.total_executions == 12
        assert trust_score.successful_executions == 10
        assert trust_score.failed_executions == 2
        assert abs(trust_score.verification_success_rate - 83.33) < 0.01  # 10/12 * 100
        assert trust_score.trust_score > 0  # Should have some positive trust score despite violations
        assert trust_score.reputation_score > 30  # Should have decent reputation despite violations
    
    def test_security_violation_impact(self, session: Session):
        """Test impact of security violations on trust score"""
        
        trust_manager = AgentTrustManager(session)
        
        # Start with good reputation
        for i in range(5):
            asyncio.run(
                trust_manager.update_trust_score(
                    entity_type="agent",
                    entity_id="test_agent",
                    execution_success=True
                )
            )
        
        # Add security violation
        trust_score_after_good = asyncio.run(
            trust_manager.update_trust_score(
                entity_type="agent",
                entity_id="test_agent",
                execution_success=True,
                security_violation=True
            )
        )
        
        # Trust score should decrease significantly
        assert trust_score_after_good.security_violations == 1
        assert trust_score_after_good.last_violation is not None
        assert len(trust_score_after_good.violation_history) == 1
        assert trust_score_after_good.trust_score < 50  # Should be below neutral after violation
    
    def test_reputation_score_calculation(self, session: Session):
        """Test reputation score calculation"""
        
        trust_manager = AgentTrustManager(session)
        
        # Build up reputation with many successful executions
        for i in range(50):
            asyncio.run(
                trust_manager.update_trust_score(
                    entity_type="agent",
                    entity_id="test_agent_reputation",  # Use different entity ID
                    execution_success=True,
                    execution_time=120,
                    policy_violation=False  # Ensure no policy violations
                )
            )
        
        trust_score = session.exec(
            select(AgentTrustScore).where(
                (AgentTrustScore.entity_type == "agent") &
                (AgentTrustScore.entity_id == "test_agent_reputation")
            )
        ).first()
        
        assert trust_score.reputation_score > 70  # Should have high reputation
        assert trust_score.trust_score > 70  # Should have high trust


class TestAgentSandboxManager:
    """Test agent sandboxing and isolation"""
    
    def test_create_sandbox_environment(self, session: Session):
        """Test creating sandbox environment"""
        
        sandbox_manager = AgentSandboxManager(session)
        
        sandbox = asyncio.run(
            sandbox_manager.create_sandbox_environment(
                execution_id="test_execution",
                security_level=SecurityLevel.PUBLIC
            )
        )
        
        assert sandbox.id is not None
        assert sandbox.sandbox_type == "process"
        assert sandbox.security_level == SecurityLevel.PUBLIC
        assert sandbox.cpu_limit == 1.0
        assert sandbox.memory_limit == 1024
        assert sandbox.network_access is False
        assert sandbox.enable_monitoring is True
    
    def test_security_level_sandbox_config(self, session: Session):
        """Test sandbox configuration for different security levels"""
        
        sandbox_manager = AgentSandboxManager(session)
        
        # Test PUBLIC level
        public_sandbox = asyncio.run(
            sandbox_manager.create_sandbox_environment(
                execution_id="public_exec",
                security_level=SecurityLevel.PUBLIC
            )
        )
        
        # Test RESTRICTED level
        restricted_sandbox = asyncio.run(
            sandbox_manager.create_sandbox_environment(
                execution_id="restricted_exec",
                security_level=SecurityLevel.RESTRICTED
            )
        )
        
        # RESTRICTED should have more resources and stricter controls
        assert restricted_sandbox.cpu_limit > public_sandbox.cpu_limit
        assert restricted_sandbox.memory_limit > public_sandbox.memory_limit
        assert restricted_sandbox.sandbox_type != public_sandbox.sandbox_type
        assert restricted_sandbox.max_execution_time > public_sandbox.max_execution_time
    
    def test_workflow_requirements_customization(self, session: Session):
        """Test sandbox customization based on workflow requirements"""
        
        sandbox_manager = AgentSandboxManager(session)
        
        workflow_requirements = {
            "cpu_cores": 4.0,
            "memory_mb": 8192,
            "disk_mb": 40960,
            "max_execution_time": 7200,
            "allowed_commands": ["python", "node", "java", "git"],
            "network_access": True
        }
        
        sandbox = asyncio.run(
            sandbox_manager.create_sandbox_environment(
                execution_id="custom_exec",
                security_level=SecurityLevel.INTERNAL,
                workflow_requirements=workflow_requirements
            )
        )
        
        # Should be customized based on requirements
        assert sandbox.cpu_limit >= 4.0
        assert sandbox.memory_limit >= 8192
        assert sandbox.disk_limit >= 40960
        assert sandbox.max_execution_time <= 7200  # Should be limited by policy
        assert "git" in sandbox.allowed_commands
        assert sandbox.network_access is True
    
    def test_sandbox_monitoring(self, session: Session):
        """Test sandbox monitoring functionality"""
        
        sandbox_manager = AgentSandboxManager(session)
        
        # Create sandbox first
        sandbox = asyncio.run(
            sandbox_manager.create_sandbox_environment(
                execution_id="monitor_exec",
                security_level=SecurityLevel.PUBLIC
            )
        )
        
        # Monitor sandbox
        monitoring_data = asyncio.run(
            sandbox_manager.monitor_sandbox("monitor_exec")
        )
        
        assert monitoring_data["execution_id"] == "monitor_exec"
        assert monitoring_data["sandbox_type"] == sandbox.sandbox_type
        assert monitoring_data["security_level"] == sandbox.security_level
        assert "resource_usage" in monitoring_data
        assert "security_events" in monitoring_data
        assert "command_count" in monitoring_data
    
    def test_sandbox_cleanup(self, session: Session):
        """Test sandbox cleanup functionality"""
        
        sandbox_manager = AgentSandboxManager(session)
        
        # Create sandbox
        sandbox = asyncio.run(
            sandbox_manager.create_sandbox_environment(
                execution_id="cleanup_exec",
                security_level=SecurityLevel.PUBLIC
            )
        )
        
        assert sandbox.is_active is True
        
        # Cleanup sandbox
        cleanup_success = asyncio.run(
            sandbox_manager.cleanup_sandbox("cleanup_exec")
        )
        
        assert cleanup_success is True
        
        # Check sandbox is marked as inactive
        updated_sandbox = session.get(AgentSandboxConfig, sandbox.id)
        assert updated_sandbox.is_active is False


class TestAgentSecurityManager:
    """Test overall security management"""
    
    def test_create_security_policy(self, session: Session):
        """Test creating security policies"""
        
        security_manager = AgentSecurityManager(session)
        
        policy_rules = {
            "allowed_step_types": ["inference", "data_processing"],
            "max_execution_time": 3600,
            "max_memory_usage": 4096,
            "require_verification": True,
            "require_sandbox": True
        }
        
        policy = asyncio.run(
            security_manager.create_security_policy(
                name="Test Policy",
                description="Test security policy",
                security_level=SecurityLevel.INTERNAL,
                policy_rules=policy_rules
            )
        )
        
        assert policy.id is not None
        assert policy.name == "Test Policy"
        assert policy.security_level == SecurityLevel.INTERNAL
        assert policy.allowed_step_types == ["inference", "data_processing"]
        assert policy.require_verification is True
        assert policy.require_sandbox is True
    
    def test_workflow_security_validation(self, session: Session):
        """Test workflow security validation"""
        
        security_manager = AgentSecurityManager(session)
        
        # Create test workflow
        workflow = AIAgentWorkflow(
            owner_id="test_user",
            name="Test Workflow",
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
            max_execution_time=7200,
            requires_verification=True,
            verification_level=VerificationLevel.FULL
        )
        
        validation_result = asyncio.run(
            security_manager.validate_workflow_security(workflow, "test_user")
        )
        
        assert validation_result["valid"] is True
        assert validation_result["required_security_level"] == SecurityLevel.CONFIDENTIAL
        assert len(validation_result["warnings"]) > 0  # Should warn about long execution time
        assert len(validation_result["recommendations"]) > 0
    
    def test_execution_security_monitoring(self, session: Session):
        """Test execution security monitoring"""
        
        security_manager = AgentSecurityManager(session)
        
        # This would normally monitor a real execution
        # For testing, we'll simulate the monitoring
        monitoring_result = asyncio.run(
            security_manager.monitor_execution_security(
                execution_id="test_execution",
                workflow_id="test_workflow"
            )
        )
        
        assert monitoring_result["execution_id"] == "test_execution"
        assert monitoring_result["workflow_id"] == "test_workflow"
        assert "security_status" in monitoring_result
        assert "violations" in monitoring_result
        assert "alerts" in monitoring_result


if __name__ == "__main__":
    pytest.main([__file__])
