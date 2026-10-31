"""#759 regression: Agent/ComputeProvider bind AsyncAITBCHTTPClient and consume
its dict-return contract.

Pre-fix, `Agent.http_client` was the *sync* AITBCHTTPClient and five call
sites awaited it (TypeError on first call) while also using
requests.Response semantics (`.status_code`/`.json()`) that neither client
exposes. Each test below exercises a real call path that would have raised
pre-fix.
"""

from __future__ import annotations

import asyncio
from decimal import Decimal
from unittest.mock import AsyncMock, Mock, patch

import pytest
from aitbc.exceptions import NetworkError
from aitbc.network import AsyncAITBCHTTPClient
from aitbc_agent.agent import Agent
from aitbc_agent.compute_provider import ComputeProvider, ResourceOffer


def _agent() -> Agent:
    return Agent.create(name="t", agent_type="worker", capabilities={"compute_type": "inference"})


def _provider() -> ComputeProvider:
    return ComputeProvider.create(name="p", agent_type="compute_provider", capabilities={"compute_type": "gpu"})


def _offer() -> ResourceOffer:
    return ResourceOffer(
        provider_id="prov-1",
        compute_type="gpu",
        gpu_memory=80,
        supported_models=["m"],
        price_per_hour=Decimal("1.5"),
        availability_schedule={},
        max_concurrent_jobs=1,
    )


class TestClientBinding:
    def test_http_client_is_async(self):
        assert isinstance(_agent().http_client, AsyncAITBCHTTPClient)


class TestAgentCallPaths:
    def test_register_posts_and_sets_flag(self):
        agent = _agent()
        agent.http_client.post = AsyncMock(return_value={"status": "success", "agent_id": agent.identity.id})
        assert asyncio.run(agent.register()) is True
        assert agent.registered is True
        agent.http_client.post.assert_awaited_once()

    def test_register_network_error(self):
        agent = _agent()
        agent.http_client.post = AsyncMock(side_effect=NetworkError("down"))
        assert asyncio.run(agent.register()) is False
        assert agent.registered is False

    def test_get_reputation_updates_score(self):
        agent = _agent()
        agent.http_client.get = AsyncMock(return_value={"overall_score": 4.2, "job_success_rate": 0.9})
        result = asyncio.run(agent.get_reputation())
        assert result["overall_score"] == 4.2
        assert agent.reputation_score == 4.2

    def test_get_reputation_network_error_falls_back(self):
        agent = _agent()
        agent.reputation_score = 3.3
        agent.http_client.get = AsyncMock(side_effect=NetworkError("down"))
        result = asyncio.run(agent.get_reputation())
        assert result["overall_score"] == 3.3

    def test_get_earnings_updates_total(self):
        agent = _agent()
        agent.http_client.get = AsyncMock(return_value={"total": 42.0, "period": "30d"})
        result = asyncio.run(agent.get_earnings())
        assert result["total"] == 42.0
        assert agent.earnings == 42.0

    def test_get_earnings_network_error_falls_back(self):
        agent = _agent()
        agent.earnings = 10.0
        agent.http_client.get = AsyncMock(side_effect=NetworkError("down"))
        result = asyncio.run(agent.get_earnings())
        assert result["total"] == 10.0

    def test_send_message_true_on_success(self):
        agent = _agent()
        agent.http_client.post = AsyncMock(return_value={"message_id": "m1"})
        assert asyncio.run(agent.send_message("agent-2", "direct", {"text": "hi"})) is True

    def test_send_message_false_on_network_error(self):
        agent = _agent()
        agent.http_client.post = AsyncMock(side_effect=NetworkError("down"))
        assert asyncio.run(agent.send_message("agent-2", "direct", {"text": "hi"})) is False

    def test_fetch_sender_public_key(self):
        agent = _agent()
        client = Mock()
        client.get = AsyncMock(return_value={"public_key": "PUBKEY"})
        client.close = AsyncMock()
        with patch("aitbc_agent.agent.AsyncAITBCHTTPClient", return_value=client):
            result = asyncio.run(agent._fetch_sender_public_key("sender-1"))
        assert result == "PUBKEY"
        client.close.assert_awaited_once()

    def test_aexit_closes_client(self):
        agent = _agent()
        agent.http_client.close = AsyncMock()

        async def _run():
            async with agent:
                pass

        asyncio.run(_run())
        agent.http_client.close.assert_awaited_once()


class TestComputeProviderCallPaths:
    def test_submit_to_market_returns_offer_id(self):
        provider = _provider()
        provider.http_client.post = AsyncMock(return_value={"offer_id": "offer-9"})
        assert asyncio.run(provider._submit_to_market(_offer())) == "offer-9"

    def test_submit_to_market_network_error_raises(self):
        provider = _provider()
        provider.http_client.post = AsyncMock(side_effect=NetworkError("down"))
        with pytest.raises(NetworkError):
            asyncio.run(provider._submit_to_market(_offer()))

    def test_submit_to_market_empty_response_raises(self):
        provider = _provider()
        provider.http_client.post = AsyncMock(return_value={})
        with pytest.raises(NetworkError):
            asyncio.run(provider._submit_to_market(_offer()))

    def test_update_market_offer_completes(self):
        provider = _provider()
        provider.http_client.put = AsyncMock(return_value={})
        asyncio.run(provider._update_market_offer(_offer()))
        provider.http_client.put.assert_awaited_once()

    def test_update_market_offer_network_error_raises(self):
        provider = _provider()
        provider.http_client.put = AsyncMock(side_effect=NetworkError("down"))
        with pytest.raises(NetworkError):
            asyncio.run(provider._update_market_offer(_offer()))
