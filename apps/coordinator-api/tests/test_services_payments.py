"""
Tests for payments service
"""

import pytest
from unittest.mock import Mock, patch


@pytest.mark.unit
class TestPaymentsService:
    """Test payments service"""

    @patch('app.services.payments.AITBCHTTPClient')
    def test_create_payment(self, mock_client_class):
        """Test creating a payment"""
        # Setup mock
        mock_client = Mock()
        mock_client_class.return_value = mock_client
        mock_client.post.return_value = {
            "id": "payment1",
            "amount": 100.0,
            "status": "pending"
        }

        # Import and test
        from app.services.payments import create_payment
        
        result = create_payment({"amount": 100.0, "recipient": "wallet123"})
        assert result["id"] == "payment1"
        assert result["status"] == "pending"

    @patch('app.services.payments.AITBCHTTPClient')
    def test_get_payment_status(self, mock_client_class):
        """Test getting payment status"""
        # Setup mock
        mock_client = Mock()
        mock_client_class.return_value = mock_client
        mock_client.get.return_value = {
            "id": "payment1",
            "status": "completed",
            "transaction_hash": "0xabc123"
        }

        # Import and test
        from app.services.payments import get_payment_status
        
        result = get_payment_status("payment1")
        assert result["status"] == "completed"
