"""
Tests for blockchain router
"""

from unittest.mock import Mock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient


@pytest.mark.unit
class TestBlockchainRouter:
    """Test blockchain router endpoints"""

    @patch("app.config.settings")
    @patch("app.contexts.blockchain.routers.blockchain.AITBCHTTPClient")
    def test_blockchain_status_connected(self, mock_client_class, mock_settings):
        """Test blockchain status when connected"""
        # Setup mocks
        mock_settings.blockchain_rpc_url = "http://localhost:8082"
        mock_client = Mock()
        mock_client_class.return_value = mock_client
        mock_client.get.return_value = {"height": 100, "hash": "abc123", "timestamp": "2024-01-01T00:00:00Z", "tx_count": 50}

        from app.contexts.blockchain.routers.blockchain import router

        app = FastAPI()
        app.include_router(router, prefix="/v1")
        client = TestClient(app)

        response = client.get("/v1/status")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "connected"
        assert data["height"] == 100
        assert data["hash"] == "abc123"

    @patch("app.config.settings")
    @patch("app.contexts.blockchain.routers.blockchain.AITBCHTTPClient")
    def test_blockchain_status_error(self, mock_client_class, mock_settings):
        """Test blockchain status when RPC connection fails"""
        # Setup mocks
        mock_settings.blockchain_rpc_url = "http://localhost:8082"
        mock_client = Mock()
        mock_client_class.return_value = mock_client
        from aitbc.exceptions import NetworkError

        mock_client.get.side_effect = NetworkError("Connection failed")

        from app.contexts.blockchain.routers.blockchain import router

        app = FastAPI()
        app.include_router(router, prefix="/v1")
        client = TestClient(app)

        response = client.get("/v1/status")
        assert response.status_code == 200
        data = response.json()
        # On NetworkError, the router returns mock data with "synced" status
        assert data["status"] == "synced"
        assert data["block"] == 0

    @patch("app.config.settings")
    @patch("app.contexts.blockchain.routers.blockchain.AITBCHTTPClient")
    def test_blockchain_sync_status_syncing(self, mock_client_class, mock_settings):
        """Test blockchain sync status when syncing"""
        # Setup mocks
        mock_settings.blockchain_rpc_url = "http://localhost:8082"
        mock_client = Mock()
        mock_client_class.return_value = mock_client
        mock_client.get.return_value = {"syncing": True, "current_block": 90, "highest_block": 100}

        from app.contexts.blockchain.routers.blockchain import router

        app = FastAPI()
        app.include_router(router, prefix="/v1")
        client = TestClient(app)

        response = client.get("/v1/sync-status")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "syncing"
        assert data["current_block"] == 90
        assert data["highest_block"] == 100

    @patch("app.config.settings")
    @patch("app.contexts.blockchain.routers.blockchain.AITBCHTTPClient")
    def test_blockchain_sync_status_synced(self, mock_client_class, mock_settings):
        """Test blockchain sync status when synced"""
        # Setup mocks
        mock_settings.blockchain_rpc_url = "http://localhost:8082"
        mock_client = Mock()
        mock_client_class.return_value = mock_client
        mock_client.get.return_value = {"syncing": False, "current_block": 100}

        from app.contexts.blockchain.routers.blockchain import router

        app = FastAPI()
        app.include_router(router, prefix="/v1")
        client = TestClient(app)

        response = client.get("/v1/sync-status")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "synced"
        assert data["block"] == 100
