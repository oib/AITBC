"""
Tests for marketplace router
"""

import pytest
from unittest.mock import Mock, patch
from fastapi.testclient import TestClient


@pytest.mark.unit
class TestMarketplaceRouter:
    """Test marketplace router endpoints"""

    @patch('app.routers.marketplace.AITBCHTTPClient')
    def test_marketplace_list(self, mock_client_class):
        """Test getting marketplace listings"""
        # Setup mock
        mock_client = Mock()
        mock_client_class.return_value = mock_client
        mock_client.get.return_value = {
            "listings": [
                {"id": 1, "name": "GPU Instance 1", "price": 0.50},
                {"id": 2, "name": "GPU Instance 2", "price": 0.75}
            ],
            "total": 2
        }

        # Import and test
        from app.routers.marketplace import router
        from app.main import create_app
        
        app = create_app()
        app.include_router(router)
        client = TestClient(app)
        
        response = client.get("/marketplace/listings")
        assert response.status_code == 200
        data = response.json()
        assert "listings" in data
        assert data["total"] == 2

    @patch('app.routers.marketplace.AITBCHTTPClient')
    def test_marketplace_create_listing(self, mock_client_class):
        """Test creating a marketplace listing"""
        # Setup mock
        mock_client = Mock()
        mock_client_class.return_value = mock_client
        mock_client.post.return_value = {
            "id": 3,
            "name": "GPU Instance 3",
            "price": 1.00,
            "status": "active"
        }

        # Import and test
        from app.routers.marketplace import router
        from app.main import create_app
        
        app = create_app()
        app.include_router(router)
        client = TestClient(app)
        
        response = client.post("/marketplace/listings", json={
            "name": "GPU Instance 3",
            "price": 1.00,
            "specs": {"gpu": "RTX 4090", "memory": "24GB"}
        })
        assert response.status_code == 200
        data = response.json()
        assert data["id"] == 3
        assert data["status"] == "active"
