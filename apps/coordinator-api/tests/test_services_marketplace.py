"""
Tests for marketplace service
"""

import pytest
from unittest.mock import Mock, patch


@pytest.mark.unit
class TestMarketplaceService:
    """Test marketplace service"""

    @patch('app.services.marketplace.AITBCHTTPClient')
    def test_list_marketplace_items(self, mock_client_class):
        """Test listing marketplace items"""
        # Setup mock
        mock_client = Mock()
        mock_client_class.return_value = mock_client
        mock_client.get.return_value = {
            "items": [
                {"id": 1, "name": "GPU 1", "price": 0.50},
                {"id": 2, "name": "GPU 2", "price": 0.75}
            ],
            "total": 2
        }

        # Import and test
        from app.services.marketplace import list_marketplace_items
        
        result = list_marketplace_items()
        assert result["total"] == 2
        assert len(result["items"]) == 2

    @patch('app.services.marketplace.AITBCHTTPClient')
    def test_create_marketplace_item(self, mock_client_class):
        """Test creating a marketplace item"""
        # Setup mock
        mock_client = Mock()
        mock_client_class.return_value = mock_client
        mock_client.post.return_value = {
            "id": 3,
            "name": "GPU 3",
            "price": 1.00,
            "status": "active"
        }

        # Import and test
        from app.services.marketplace import create_marketplace_item
        
        result = create_marketplace_item({"name": "GPU 3", "price": 1.00})
        assert result["id"] == 3
        assert result["status"] == "active"
