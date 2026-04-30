"""
Tests for blockchain router
"""

import pytest
from unittest.mock import Mock, patch
from fastapi.testclient import TestClient


@pytest.mark.unit
class TestBlockchainRouter:
    """Test blockchain router endpoints"""

    @patch('app.routers.blockchain.settings')
    @patch('app.routers.blockchain.AITBCHTTPClient')
    def test_blockchain_status_connected(self, mock_client_class, mock_settings):
        """Test blockchain status when connected"""
        # Setup mocks
        mock_settings.blockchain_rpc_url = "http://localhost:8082"
        mock_client = Mock()
        mock_client_class.return_value = mock_client
        mock_client.get.return_value = {
            "height": 100,
            "hash": "abc123",
            "timestamp": "2024-01-01T00:00:00Z",
            "tx_count": 50
        }

        # Import and test
        from app.routers.blockchain import router
        from app.main import create_app
        
        app = create_app()
        app.include_router(router)
        client = TestClient(app)
        
        response = client.get("/blockchain/status")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "connected"
        assert data["height"] == 100
        assert data["hash"] == "abc123"

    @patch('app.routers.blockchain.settings')
    @patch('app.routers.blockchain.AITBCHTTPClient')
    def test_blockchain_status_error(self, mock_client_class, mock_settings):
        """Test blockchain status when RPC connection fails"""
        # Setup mocks
        mock_settings.blockchain_rpc_url = "http://localhost:8082"
        mock_client = Mock()
        mock_client_class.return_value = mock_client
        from aitbc import NetworkError
        mock_client.get.side_effect = NetworkError("Connection failed")

        # Import and test
        from app.routers.blockchain import router
        from app.main import create_app
        
        app = create_app()
        app.include_router(router)
        client = TestClient(app)
        
        response = client.get("/blockchain/status")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "error"
        assert "RPC connection failed" in data["error"]

    @patch('app.routers.blockchain.settings')
    @patch('app.routers.blockchain.AITBCHTTPClient')
    def test_blockchain_sync_status_syncing(self, mock_client_class, mock_settings):
        """Test blockchain sync status when syncing"""
        # Setup mocks
        mock_settings.blockchain_rpc_url = "http://localhost:8082"
        mock_client = Mock()
        mock_client_class.return_value = mock_client
        mock_client.get.return_value = {
            "syncing": True,
            "current_block": 90,
            "highest_block": 100
        }

        # Import and test
        from app.routers.blockchain import router
        from app.main import create_app
        
        app = create_app()
        app.include_router(router)
        client = TestClient(app)
        
        response = client.get("/blockchain/sync-status")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "syncing"
        assert data["current_block"] == 90
        assert data["highest_block"] == 100

    @patch('app.routers.blockchain.settings')
    @patch('app.routers.blockchain.AITBCHTTPClient')
    def test_blockchain_sync_status_synced(self, mock_client_class, mock_settings):
        """Test blockchain sync status when synced"""
        # Setup mocks
        mock_settings.blockchain_rpc_url = "http://localhost:8082"
        mock_client = Mock()
        mock_client_class.return_value = mock_client
        mock_client.get.return_value = {
            "syncing": False,
            "current_block": 100
        }

        # Import and test
        from app.routers.blockchain import router
        from app.main import create_app
        
        app = create_app()
        app.include_router(router)
        client = TestClient(app)
        
        response = client.get("/blockchain/sync-status")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "synced"
        assert data["block"] == 100
