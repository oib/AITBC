"""
Tests for payments router
"""

import pytest
from unittest.mock import Mock, patch
from fastapi.testclient import TestClient


@pytest.mark.unit
class TestPaymentsRouter:
    """Test payments router endpoints"""

    @patch('app.routers.payments.AITBCHTTPClient')
    def test_payment_create(self, mock_client_class):
        """Test creating a payment"""
        # Setup mock
        mock_client = Mock()
        mock_client_class.return_value = mock_client
        mock_client.post.return_value = {
            "id": "payment1",
            "amount": 100.0,
            "currency": "USDC",
            "status": "pending"
        }

        # Import and test
        from app.routers.payments import router
        from app.main import create_app
        
        app = create_app()
        app.include_router(router)
        client = TestClient(app)
        
        response = client.post("/payments", json={
            "amount": 100.0,
            "currency": "USDC",
            "recipient": "wallet123"
        })
        assert response.status_code == 200
        data = response.json()
        assert data["id"] == "payment1"
        assert data["amount"] == 100.0

    @patch('app.routers.payments.AITBCHTTPClient')
    def test_payment_status(self, mock_client_class):
        """Test getting payment status"""
        # Setup mock
        mock_client = Mock()
        mock_client_class.return_value = mock_client
        mock_client.get.return_value = {
            "id": "payment1",
            "amount": 100.0,
            "status": "completed",
            "transaction_hash": "0xabc123"
        }

        # Import and test
        from app.routers.payments import router
        from app.main import create_app
        
        app = create_app()
        app.include_router(router)
        client = TestClient(app)
        
        response = client.get("/payments/payment1/status")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "completed"
