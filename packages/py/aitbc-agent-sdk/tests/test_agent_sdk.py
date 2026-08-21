"""Test suite for AITBC Agent SDK"""

from decimal import Decimal

import asyncio
from unittest.mock import AsyncMock, Mock, patch

import pytest
from aitbc_agent.agent import Agent, AgentCapabilities, AITBCAgent
from aitbc_agent.compute_consumer import ComputeConsumer, JobRequest, JobResult
from aitbc_agent.compute_provider import ComputeProvider, JobExecution, ResourceOffer


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
            name="gpu-provider", capabilities={"compute_type": "inference", "gpu_memory": 8}, pricing_model={"base_rate": 50.0}
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
            price_per_hour=Decimal("50"),
            availability_schedule={"start": "09:00", "end": "18:00"},
            max_concurrent_jobs=3,
        )
        assert offer.provider_id == "provider-1"
        assert offer.price_per_hour == Decimal("50")
        assert offer.max_concurrent_jobs == 3

    def test_job_execution_tracking(self):
        """Test JobExecution dataclass"""
        from datetime import timedelta

        job = JobExecution(job_id="job-1", consumer_id="consumer-1", start_time=None, expected_duration=timedelta(hours=1))
        assert job.job_id == "job-1"
        assert job.status == "running"


class TestComputeConsumer:
    """Test ComputeConsumer agent"""

    def test_create_consumer(self):
        """Test ComputeConsumer factory"""
        consumer = ComputeConsumer.create(name="ml-consumer", agent_type="consumer", capabilities={"compute_type": "training"})
        assert consumer.identity.name == "ml-consumer"
        assert consumer.capabilities.compute_type == "training"

    def test_job_request_creation(self):
        """Test JobRequest dataclass"""
        job = JobRequest(
            consumer_id="consumer-1",
            job_type="training",
            model_id="resnet50",
            input_data={"dataset": "imagenet"},
            max_price_per_hour=Decimal("100"),
        )
        assert job.consumer_id == "consumer-1"
        assert job.job_type == "training"
        assert job.max_price_per_hour == Decimal("100")

    def test_job_result_creation(self):
        """Test JobResult dataclass"""
        result = JobResult(
            job_id="job-1",
            provider_id="provider-1",
            status="completed",
            output={"accuracy": 0.95},
            execution_time=3600.0,
            cost=Decimal("50"),
        )
        assert result.job_id == "job-1"
        assert result.status == "completed"
        assert result.cost == Decimal("50")

    def test_consumer_spending_summary(self):
        """Test spending summary"""
        consumer = ComputeConsumer.create(
            name="test-consumer", agent_type="consumer", capabilities={"compute_type": "training"}
        )
        summary = consumer.get_spending_summary()
        assert "total_spent" in summary
        assert "completed_jobs" in summary
        assert "pending_jobs" in summary

    def test_create_consumer_with_auth_token(self):
        """ComputeConsumer factory accepts and stores an auth token"""
        consumer = ComputeConsumer.create(
            name="auth-consumer",
            agent_type="consumer",
            capabilities={"compute_type": "inference"},
            coordinator_url="http://coordinator:8203",
            auth_token="test-jwt-token",
        )
        assert consumer.auth_token == "test-jwt-token"
        assert consumer.coordinator_url == "http://coordinator:8203"

    def test_submit_job_sends_auth_and_payload_shape(self):
        """submit_job sends Bearer token and a JobCreate-compatible payload"""
        consumer = ComputeConsumer.create(
            name="auth-consumer",
            agent_type="consumer",
            capabilities={"compute_type": "inference"},
            coordinator_url="http://coordinator:8203",
            auth_token="test-jwt-token",
        )

        mock_response = AsyncMock()
        mock_response.status_code = 201
        mock_response.json = Mock(return_value={"job_id": "job_123"})

        mock_client = AsyncMock()
        mock_client.__aenter__.return_value = mock_client
        mock_client.__aexit__.return_value = False
        mock_client.post.return_value = mock_response

        async def _run():
            with patch("aitbc_agent.compute_consumer.httpx.AsyncClient", return_value=mock_client):
                return await consumer.submit_job(
                    job_type="inference",
                    input_data={"prompt": "hello"},
                    requirements={"gpu": True},
                    max_price=Decimal("5.0"),
                    buyer_address="0xBuyer1",
                    provider_address="0xProvider1",
                )

        job_id = asyncio.run(_run())
        assert job_id == "job_123"

        call_kwargs = mock_client.post.call_args.kwargs
        assert call_kwargs["headers"] == {"Authorization": "Bearer test-jwt-token"}

        sent = call_kwargs["json"]
        assert sent["consumer_id"] == consumer.identity.id
        assert sent["payload"] == {"type": "inference", "prompt": "hello"}
        assert sent["constraints"] == {"gpu": True}
        assert sent["payment_amount"] == Decimal("5.0")
        assert sent["payment_currency"] == "AIT"
        assert sent["buyer_address"] == "0xBuyer1"
        assert sent["provider_address"] == "0xProvider1"
        assert "ttl_seconds" in sent

    def test_get_job_status_sends_auth_header(self):
        """get_job_status includes the Bearer token"""
        consumer = ComputeConsumer.create(
            name="auth-consumer",
            agent_type="consumer",
            capabilities={"compute_type": "inference"},
            coordinator_url="http://coordinator:8203",
            auth_token="test-jwt-token",
        )

        mock_response = AsyncMock()
        mock_response.status_code = 200
        mock_response.json = Mock(return_value={"job_id": "job_123", "state": "COMPLETED"})

        mock_client = AsyncMock()
        mock_client.__aenter__.return_value = mock_client
        mock_client.__aexit__.return_value = False
        mock_client.get.return_value = mock_response

        async def _run():
            with patch("aitbc_agent.compute_consumer.httpx.AsyncClient", return_value=mock_client):
                return await consumer.get_job_status("job_123")

        result = asyncio.run(_run())
        assert result["state"] == "COMPLETED"

        call_kwargs = mock_client.get.call_args.kwargs
        assert call_kwargs["headers"] == {"Authorization": "Bearer test-jwt-token"}


class TestAgentIntegration:
    """Integration tests for agent workflows"""


class TestImports:
    """Verify public API surface"""

    def test_all_exports(self):
        import aitbc_agent

        for name in (
            "Agent",
            "AITBCAgent",
            "ComputeProvider",
            "ComputeConsumer",
            "PlatformBuilder",
            "SwarmCoordinator",
        ):
            assert hasattr(aitbc_agent, name), f"Missing export: {name}"


class TestAgentMessaging:
    """SDK message send uses the Agent Coordinator /api/v1/agent/messages/send route."""

    def test_send_message_uses_coordinator_endpoint(self):
        """send_message posts to the correct coordinator route with a signed payload."""
        agent = Agent.create(name="test", agent_type="general", capabilities={"compute_type": "inference"})
        agent.http_client.post = AsyncMock(return_value=Mock(status_code=200))

        payload = {"text": "hello"}
        result = asyncio.run(agent.send_message("agent-2", "direct", payload))

        assert result is True
        agent.http_client.post.assert_called_once()
        call_args = agent.http_client.post.call_args
        assert call_args.args[0] == "/api/v1/agent/messages/send"

        body = call_args.kwargs["json"]
        assert body["sender"] == agent.identity.id
        assert body["recipient"] == "agent-2"
        assert body["message_type"] == "direct"
        assert body["encrypt"] is False
        assert body["priority"] == "normal"
        assert body["ttl"] == 300
        assert body["content"]["payload"] == payload
        assert "signature" in body["content"]
        assert body["content"]["from"] == agent.identity.id
        assert body["content"]["to"] == "agent-2"


if __name__ == "__main__":
    pytest.main([__file__])
