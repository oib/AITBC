"""
Integration tests for blockchain and payments interaction
"""

import pytest
from unittest.mock import Mock, patch
from fastapi.testclient import TestClient


@pytest.mark.integration
class TestBlockchainPaymentsIntegration:
    """Test integration between blockchain and payment services"""

    @patch('app.routers.blockchain.AITBCHTTPClient')
    @patch('app.routers.payments.AITBCHTTPClient')
    def test_payment_recorded_on_blockchain(self, mock_payments_client, mock_blockchain_client):
        """Test that a payment is recorded on the blockchain"""
        # Setup mocks
        mock_blockchain = Mock()
        mock_blockchain_client.return_value = mock_blockchain
        mock_blockchain.get.return_value = {
            "height": 1000,
            "hash": "0xabc123",
            "tx_count": 50
        }

        mock_payments = Mock()
        mock_payments_client.return_value = mock_payments
        mock_payments.post.return_value = {
            "id": "payment1",
            "amount": 100.0,
            "status": "pending",
            "transaction_hash": "0xdef456"
        }

        # Import and test
        from app.routers.blockchain import router as blockchain_router
        from app.routers.payments import router as payments_router
        from app.main import create_app
        
        app = create_app()
        app.include_router(blockchain_router)
        app.include_router(payments_router)
        client = TestClient(app)
        
        # Create payment
        response = client.post("/payments", json={
            "amount": 100.0,
            "currency": "USDC",
            "recipient": "wallet123"
        })
        assert response.status_code == 200
        payment_data = response.json()
        assert payment_data["transaction_hash"] == "0xdef456"
        
        # Verify blockchain is accessible
        response = client.get("/blockchain/status")
        assert response.status_code == 200
        blockchain_data = response.json()
        assert blockchain_data["height"] == 1000
