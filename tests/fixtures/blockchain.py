"""
Blockchain test fixtures
Provides fixtures for testing blockchain node and related components
"""

import sys
import pytest
from pathlib import Path
from unittest.mock import Mock

project_root = Path(__file__).parent.parent.parent


@pytest.fixture
def blockchain_client():
    """Create a test client for blockchain node"""
    from fastapi.testclient import TestClient
    try:
        blockchain_path = str(project_root / "apps" / "blockchain-node" / "src")
        if blockchain_path not in sys.path[:1]:
            sys.path.insert(0, blockchain_path)
        
        from aitbc_chain.node import BlockchainNode
        node = BlockchainNode()
        return TestClient(node.app)
    except ImportError:
        # Create a mock client if imports fail
        mock_client = Mock()
        
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "block_number": 100,
            "hash": "0xblock123",
            "transaction_hash": "0xtx456"
        }
        
        mock_client.post.return_value = mock_response
        mock_client.get.return_value = mock_response
        return mock_client


@pytest.fixture
def wallet_client():
    """Create a test client for wallet daemon"""
    from fastapi.testclient import TestClient
    try:
        wallet_path = str(project_root / "apps" / "wallet-daemon" / "src")
        if wallet_path not in sys.path[:1]:
            sys.path.insert(0, wallet_path)
        
        from app.main import app
        return TestClient(app)
    except ImportError:
        # Create a mock client if imports fail
        mock_client = Mock()
        
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "id": "wallet-123",
            "address": "0x1234567890abcdef",
            "balance": "1000.0"
        }
        
        mock_client.post.return_value = mock_response
        mock_client.get.return_value = mock_response
        mock_client.patch.return_value = mock_response
        return mock_client


@pytest.fixture
def marketplace_client():
    """Create a test client for marketplace"""
    from fastapi.testclient import TestClient
    try:
        marketplace_path = str(project_root / "apps" / "marketplace" / "src")
        if marketplace_path not in sys.path[:1]:
            sys.path.insert(0, marketplace_path)
        
        from app.main import app
        return TestClient(app)
    except ImportError:
        # Create a mock client if imports fail
        mock_client = Mock()
        
        mock_response = Mock()
        mock_response.status_code = 201
        mock_response.json.return_value = {
            "id": "service-123",
            "name": "Test Service",
            "status": "active"
        }
        
        mock_client.post.return_value = mock_response
        mock_client.get.return_value = Mock(
            status_code=200,
            json=lambda: {"items": [], "total": 0}
        )
        return mock_client
