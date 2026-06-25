"""
Integration tests for blockchain and payments interaction
"""

from unittest.mock import AsyncMock, Mock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient


@pytest.mark.integration
class TestBlockchainPaymentsIntegration:
    """Test integration between blockchain and payment services"""

    @patch("app.contexts.payments.routers.payments.PaymentService")
    @patch("app.contexts.blockchain.routers.blockchain.AITBCHTTPClient")
    def test_payment_recorded_on_blockchain(self, mock_blockchain_client, mock_payment_service_cls):
        """Test that a payment is recorded and the blockchain is accessible"""
        # Blockchain mock
        mock_blockchain = Mock()
        mock_blockchain_client.return_value = mock_blockchain
        mock_blockchain.get.return_value = {"height": 1000, "hash": "0xabc123", "tx_count": 50}

        # Payment service mock
        mock_service = Mock()
        mock_payment_service_cls.return_value = mock_service
        mock_service.create_payment = AsyncMock(return_value=Mock())
        mock_service.to_view.return_value = {
            "job_id": "job1",
            "payment_id": "payment1",
            "amount": 100.0,
            "currency": "USDT",
            "status": "pending",
            "payment_method": "aitbc_token",
            "escrow_address": None,
            "refund_address": None,
            "created_at": "2024-01-01T00:00:00",
            "updated_at": "2024-01-01T00:00:00",
            "released_at": None,
            "refunded_at": None,
            "transaction_hash": "0xdef456",
            "refund_transaction_hash": None,
        }

        from app.auth import require_client
        from app.contexts.blockchain.routers.blockchain import router as blockchain_router
        from app.contexts.payments.routers.payments import router as payments_router
        from app.storage import get_session

        app = FastAPI()
        app.include_router(blockchain_router, prefix="/v1")
        app.include_router(payments_router, prefix="/v1")
        app.dependency_overrides[require_client] = lambda: {"sub": "user1", "role": "client"}
        app.dependency_overrides[get_session] = lambda: Mock()
        try:
            client = TestClient(app)

            # Create payment
            response = client.post("/v1/payments", json={"job_id": "job1", "amount": 100.0, "currency": "USDT"})
            assert response.status_code == 201
            payment_data = response.json()
            assert payment_data["transaction_hash"] == "0xdef456"

            # Verify blockchain is accessible
            response = client.get("/v1/status")
            assert response.status_code == 200
            blockchain_data = response.json()
            assert blockchain_data["height"] == 1000
        finally:
            app.dependency_overrides.clear()
