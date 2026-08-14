"""
Tests for Agent Identity SDK
Unit tests for the Agent Identity client and models
"""

from datetime import UTC, datetime
from unittest.mock import AsyncMock

import pytest
from coordinator_api.agent_identity.sdk.client import AgentIdentityClient


def _make_mock_response(status: int = 200, json_data: dict | None = None) -> AsyncMock:
    """Build an AsyncMock that supports the async context manager protocol.

    ``aiohttp``'s ``session.request(...)`` returns an object used as
    ``async with ... as response``.  When the session is an ``AsyncMock``,
    calling ``request`` returns a *coroutine* rather than the configured
    return value, so the ``async with`` fails.  This helper produces a mock
    that can be returned synchronously from a ``MagicMock`` request and still
    be used as an async context manager.
    """
    mock_response = AsyncMock()
    mock_response.status = status
    mock_response.json = AsyncMock(return_value=json_data or {})
    mock_response.__aenter__ = AsyncMock(return_value=mock_response)
    mock_response.__aexit__ = AsyncMock(return_value=None)
    return mock_response


from coordinator_api.agent_identity.sdk.models import (
    AgentIdentity,
    AgentWallet,
    ChainType,
    CrossChainMapping,
    IdentityStatus,
    VerificationType,
)


class TestAgentIdentityClient:
    """Test cases for AgentIdentityClient"""

    @pytest.fixture
    def client(self):
        """Create a test client"""
        return AgentIdentityClient(base_url="http://test:8000/v1", api_key="test_key", timeout=10)

    @pytest.fixture
    def mock_session(self):
        """Create a mock HTTP session"""
        session = AsyncMock()
        session.closed = False
        return session


class TestModels:
    """Test cases for SDK models"""

    def test_agent_identity_model(self):
        """Test AgentIdentity model"""
        identity = AgentIdentity(
            id="identity_123",
            agent_id="agent_456",
            owner_address="0x123...",
            display_name="Test Agent",
            description="Test description",
            avatar_url="https://example.com/avatar.png",
            status=IdentityStatus.ACTIVE,
            verification_level=VerificationType.BASIC,
            is_verified=True,
            verified_at=datetime.now(UTC),
            supported_chains=["1", "137"],
            primary_chain=1,
            reputation_score=85.5,
            total_transactions=100,
            successful_transactions=95,
            success_rate=0.95,
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
            last_activity=datetime.now(UTC),
            metadata={"key": "value"},
            tags=["test", "agent"],
        )

        assert identity.id == "identity_123"
        assert identity.agent_id == "agent_456"
        assert identity.status == IdentityStatus.ACTIVE
        assert identity.verification_level == VerificationType.BASIC
        assert identity.success_rate == 0.95
        assert "test" in identity.tags

    def test_cross_chain_mapping_model(self):
        """Test CrossChainMapping model"""
        mapping = CrossChainMapping(
            id="mapping_123",
            agent_id="agent_456",
            chain_id=1,
            chain_type=ChainType.ETHEREUM,
            chain_address="0x123...",
            is_verified=True,
            verified_at=datetime.now(UTC),
            wallet_address="0x456...",
            wallet_type="agent-wallet",
            chain_metadata={"test": "data"},
            last_transaction=datetime.now(UTC),
            transaction_count=10,
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
        )

        assert mapping.id == "mapping_123"
        assert mapping.chain_id == 1
        assert mapping.chain_type == ChainType.ETHEREUM
        assert mapping.is_verified is True
        assert mapping.transaction_count == 10

    def test_agent_wallet_model(self):
        """Test AgentWallet model"""
        wallet = AgentWallet(
            id="wallet_123",
            agent_id="agent_456",
            chain_id=1,
            chain_address="0x123...",
            wallet_type="agent-wallet",
            contract_address="0x789...",
            balance=1.5,
            spending_limit=10.0,
            total_spent=0.5,
            is_active=True,
            permissions=["send", "receive"],
            requires_multisig=False,
            multisig_threshold=1,
            multisig_signers=["0x123..."],
            last_transaction=datetime.now(UTC),
            transaction_count=5,
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
        )

        assert wallet.id == "wallet_123"
        assert wallet.balance == 1.5
        assert wallet.spending_limit == 10.0
        assert wallet.is_active is True
        assert "send" in wallet.permissions
        assert wallet.requires_multisig is False


class TestConvenienceFunctions:
    """Test cases for convenience functions"""


# Integration tests would go here in a real implementation
# These would test the actual API endpoints


class TestIntegration:
    """Integration tests for the SDK"""


if __name__ == "__main__":
    pytest.main([__file__])
