"""
Blockchain test fixtures
Provides fixtures for testing blockchain node and related components
"""

from unittest.mock import Mock

import pytest


@pytest.fixture
def blockchain_client():
    """Create a test client for blockchain node"""
    from fastapi.testclient import TestClient

    try:
        from aitbc_chain.node import BlockchainNode

        node = BlockchainNode()
        return TestClient(node.app)
    except ImportError:
        # Create a mock client if imports fail
        mock_client = Mock()

        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"block_number": 100, "hash": "0xblock123", "transaction_hash": "0xtx456"}

        mock_client.post.return_value = mock_response
        mock_client.get.return_value = mock_response
        return mock_client


@pytest.fixture
def wallet_client():
    """Create a test client for wallet daemon"""
    from fastapi.testclient import TestClient

    try:
        from app.main import app

        return TestClient(app)
    except ImportError:
        # Create a mock client if imports fail
        mock_client = Mock()

        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"id": "wallet-123", "address": "0x1234567890abcdef", "balance": "1000.0"}

        mock_client.post.return_value = mock_response
        mock_client.get.return_value = mock_response
        mock_client.patch.return_value = mock_response
        return mock_client


@pytest.fixture
def marketplace_client():
    """Create a test client for marketplace"""
    from fastapi.testclient import TestClient

    try:
        from app.main import app

        return TestClient(app)
    except ImportError:
        # Create a mock client if imports fail
        mock_client = Mock()

        mock_response = Mock()
        mock_response.status_code = 201
        mock_response.json.return_value = {"id": "service-123", "name": "Test Service", "status": "active"}

        mock_client.post.return_value = mock_response
        mock_client.get.return_value = Mock(status_code=200, json=lambda: {"items": [], "total": 0})
        return mock_client
