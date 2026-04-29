"""Test suite for AITBC Agent SDK"""

import pytest
import asyncio
from unittest.mock import Mock, AsyncMock, patch
from aitbc_agent.agent import AITBCAgent, Agent, AgentCapabilities, AgentIdentity
from aitbc_agent.compute_provider import ComputeProvider, ResourceOffer, JobExecution
from aitbc_agent.compute_consumer import ComputeConsumer, JobRequest, JobResult


class TestAITBCAgent:
    """Test AITBC Agent high-level wrapper"""

    def test_agent_initialization(self):
        """Test agent can be initialized"""
        agent = AITBCAgent(agent_id="test-agent")
        assert agent.agent_id == "test-agent"
        assert agent.status == "initialized"

    def test_agent_config_validation(self):
        """Test agent configuration validation"""
        config = {
            "agent_id": "test-agent",
            "compute_type": "gpu",
            "capabilities": ["inference", "training"],
        }
        agent = AITBCAgent(**config)
        assert agent.compute_type == "gpu"
        assert "inference" in agent.capabilities


class TestAgentCore:
    """Test core Agent class"""

    def test_create_agent(self):
        """Test Agent.create factory"""
        agent = Agent.create(
            name="provider-1",
            agent_type="compute_provider",
            capabilities={"compute_type": "inference"},
        )
        assert agent.identity.name == "provider-1"
        assert agent.capabilities.compute_type == "inference"
        assert agent.registered is False

    def test_agent_to_dict(self):
        """Test agent serialisation round-trip"""
        agent = Agent.create(
            name="worker",
            agent_type="general",
            capabilities={"compute_type": "processing"},
        )
        d = agent.to_dict()
        assert "id" in d
        assert d["capabilities"]["compute_type"] == "processing"

    def test_capabilities_defaults(self):
        """Test AgentCapabilities default values"""
        caps = AgentCapabilities(compute_type="inference")
        assert caps.supported_models == []
        assert caps.max_concurrent_jobs == 1
        assert caps.gpu_memory is None

    def test_agent_identity_sign_message(self):
        """Test AgentIdentity message signing"""
        agent = Agent.create(
            name="test-agent",
            agent_type="general",
            capabilities={"compute_type": "inference"},
        )
        message = {"test": "data"}
        signature = agent.identity.sign_message(message)
        assert signature is not None
        assert len(signature) > 0

    def test_agent_identity_verify_signature(self):
        """Test AgentIdentity signature verification"""
        agent = Agent.create(
            name="test-agent",
            agent_type="general",
            capabilities={"compute_type": "inference"},
        )
        message = {"test": "data"}
        signature = agent.identity.sign_message(message)
        # Verification should succeed with own signature
        assert agent.identity.verify_signature(message, signature) is True


class TestComputeProvider:
    """Test ComputeProvider agent"""

    def test_create_provider(self):
        """Test ComputeProvider factory"""
        provider = ComputeProvider.create_provider(
            name="gpu-provider",
            capabilities={"compute_type": "inference", "gpu_memory": 8},
            pricing_model={"base_rate": 50.0}
        )
        assert provider.identity.name == "gpu-provider"
        assert provider.capabilities.compute_type == "inference"
        assert provider.pricing_model["base_rate"] == 50.0

    def test_provider_capabilities_assessment(self):
        """Test GPU capabilities assessment"""
        # This test will use fallback values if nvidia-smi is not available
        capabilities = ComputeProvider.assess_capabilities()
        assert "gpu_memory" in capabilities
        assert "supported_models" in capabilities
        assert "performance_score" in capabilities
        assert "max_concurrent_jobs" in capabilities

    def test_resource_offer_creation(self):
        """Test ResourceOffer dataclass"""
        offer = ResourceOffer(
            provider_id="provider-1",
            compute_type="inference",
            gpu_memory=8,
            supported_models=["llama2"],
            price_per_hour=50.0,
            availability_schedule={"start": "09:00", "end": "18:00"},
            max_concurrent_jobs=3
        )
        assert offer.provider_id == "provider-1"
        assert offer.price_per_hour == 50.0
        assert offer.max_concurrent_jobs == 3

    def test_job_execution_tracking(self):
        """Test JobExecution dataclass"""
        from datetime import timedelta
        job = JobExecution(
            job_id="job-1",
            consumer_id="consumer-1",
            start_time=None,
            expected_duration=timedelta(hours=1)
        )
        assert job.job_id == "job-1"
        assert job.status == "running"

    @pytest.mark.asyncio
    async def test_provider_get_performance_metrics(self):
        """Test performance metrics retrieval"""
        provider = ComputeProvider.create_provider(
            name="test-provider",
            capabilities={"compute_type": "inference"},
            pricing_model={"base_rate": 50.0}
        )
        metrics = await provider.get_performance_metrics()
        assert "utilization_rate" in metrics
        assert "active_jobs" in metrics
        assert "total_earnings" in metrics


class TestComputeConsumer:
    """Test ComputeConsumer agent"""

    def test_create_consumer(self):
        """Test ComputeConsumer factory"""
        consumer = ComputeConsumer.create(
            name="ml-consumer",
            agent_type="consumer",
            capabilities={"compute_type": "training"}
        )
        assert consumer.identity.name == "ml-consumer"
        assert consumer.capabilities.compute_type == "training"

    def test_job_request_creation(self):
        """Test JobRequest dataclass"""
        job = JobRequest(
            consumer_id="consumer-1",
            job_type="training",
            model_id="resnet50",
            input_data={"dataset": "imagenet"},
            max_price_per_hour=100.0
        )
        assert job.consumer_id == "consumer-1"
        assert job.job_type == "training"
        assert job.max_price_per_hour == 100.0

    def test_job_result_creation(self):
        """Test JobResult dataclass"""
        result = JobResult(
            job_id="job-1",
            provider_id="provider-1",
            status="completed",
            output={"accuracy": 0.95},
            execution_time=3600.0,
            cost=50.0
        )
        assert result.job_id == "job-1"
        assert result.status == "completed"
        assert result.cost == 50.0

    def test_consumer_spending_summary(self):
        """Test spending summary"""
        consumer = ComputeConsumer.create(
            name="test-consumer",
            agent_type="consumer",
            capabilities={"compute_type": "training"}
        )
        summary = consumer.get_spending_summary()
        assert "total_spent" in summary
        assert "completed_jobs" in summary
        assert "pending_jobs" in summary

    @pytest.mark.asyncio
    async def test_consumer_submit_job(self):
        """Test job submission with mocked coordinator"""
        consumer = ComputeConsumer.create(
            name="test-consumer",
            agent_type="consumer",
            capabilities={"compute_type": "training"}
        )
        
        # Mock the HTTP client to avoid actual network calls
        with patch('aitbc_agent.compute_consumer.httpx.AsyncClient') as mock_client:
            mock_response = Mock()
            mock_response.status_code = 201
            mock_response.json.return_value = {"job_id": "test-job-123"}
            mock_client.return_value.__aenter__.return_value.post.return_value = mock_response
            
            job_id = await consumer.submit_job(
                job_type="training",
                input_data={"model": "resnet50"},
                requirements={"gpu_memory": 16},
                max_price=100.0
            )
            
            assert job_id is not None
            assert "job_" in job_id

    @pytest.mark.asyncio
    async def test_consumer_get_job_status(self):
        """Test job status query"""
        consumer = ComputeConsumer.create(
            name="test-consumer",
            agent_type="consumer",
            capabilities={"compute_type": "training"}
        )
        
        with patch('aitbc_agent.compute_consumer.httpx.AsyncClient') as mock_client:
            mock_response = Mock()
            mock_response.status_code = 200
            mock_response.json.return_value = {
                "job_id": "job-123",
                "status": "running",
                "progress": 0.5
            }
            mock_client.return_value.__aenter__.return_value.get.return_value = mock_response
            
            status = await consumer.get_job_status("job-123")
            assert status["job_id"] == "job-123"
            assert status["status"] == "running"


class TestAgentIntegration:
    """Integration tests for agent workflows"""

    @pytest.mark.asyncio
    async def test_agent_registration_flow(self):
        """Test complete agent registration flow"""
        agent = Agent.create(
            name="integration-test-agent",
            agent_type="provider",
            capabilities={"compute_type": "inference", "gpu_memory": 8}
        )
        
        # Mock the HTTP client for registration
        with patch.object(agent, 'http_client') as mock_client:
            mock_response = Mock()
            mock_response.status_code = 201
            mock_response.json.return_value = {"agent_id": agent.identity.id}
            mock_client.post = AsyncMock(return_value=mock_response)
            
            success = await agent.register()
            assert success is True
            assert agent.registered is True

    @pytest.mark.asyncio
    async def test_agent_messaging_flow(self):
        """Test agent-to-agent messaging"""
        agent1 = Agent.create(
            name="sender",
            agent_type="provider",
            capabilities={"compute_type": "inference"}
        )
        
        agent2 = Agent.create(
            name="receiver",
            agent_type="consumer",
            capabilities={"compute_type": "training"}
        )
        
        # Mock HTTP client for message sending
        with patch.object(agent1, 'http_client') as mock_client:
            mock_response = Mock()
            mock_response.status_code = 200
            mock_client.post = AsyncMock(return_value=mock_response)
            
            success = await agent1.send_message(
                recipient_id=agent2.identity.id,
                message_type="job_request",
                payload={"model": "llama2", "prompt": "test"}
            )
            
            assert success is True

    @pytest.mark.asyncio
    async def test_agent_reputation_tracking(self):
        """Test agent reputation updates"""
        agent = Agent.create(
            name="reputation-test",
            agent_type="provider",
            capabilities={"compute_type": "inference"}
        )
        
        # Update reputation
        await agent.update_reputation(0.85)
        assert agent.reputation_score == 0.85
        
        # Get reputation (will use local values if network unavailable)
        reputation = await agent.get_reputation()
        assert reputation["overall_score"] == 0.85

    @pytest.mark.asyncio
    async def test_agent_earnings_tracking(self):
        """Test agent earnings tracking"""
        agent = Agent.create(
            name="earnings-test",
            agent_type="provider",
            capabilities={"compute_type": "inference"}
        )
        
        # Get earnings (will use local values if network unavailable)
        earnings = await agent.get_earnings(period="30d")
        assert "total" in earnings
        assert "period" in earnings
        assert earnings["period"] == "30d"

    @pytest.mark.asyncio
    async def test_agent_context_manager(self):
        """Test agent as async context manager"""
        agent = Agent.create(
            name="context-test",
            agent_type="provider",
            capabilities={"compute_type": "inference"}
        )
        
        # Mock the HTTP client for registration
        with patch.object(agent, 'http_client') as mock_client:
            mock_response = Mock()
            mock_response.status_code = 201
            mock_response.json.return_value = {"agent_id": agent.identity.id}
            mock_client.post = AsyncMock(return_value=mock_response)
            
            async with agent:
                assert agent.registered is True
                assert agent.identity.name == "context-test"
            
            # After context exit, agent should still be registered
            # (cleanup happens but registration state persists)
            assert agent.identity.name == "context-test"


class TestImports:
    """Verify public API surface"""

    def test_all_exports(self):
        import aitbc_agent
        for name in (
            "Agent", "AITBCAgent", "ComputeProvider",
            "ComputeConsumer", "PlatformBuilder", "SwarmCoordinator",
        ):
            assert hasattr(aitbc_agent, name), f"Missing export: {name}"


if __name__ == "__main__":
    pytest.main([__file__])
