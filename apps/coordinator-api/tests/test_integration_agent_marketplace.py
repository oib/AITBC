"""
Integration tests for agent and marketplace interaction
"""

import pytest
from unittest.mock import Mock, patch
from fastapi.testclient import TestClient


@pytest.mark.integration
class TestAgentMarketplaceIntegration:
    """Test integration between agent and marketplace services"""

    @patch('app.routers.agent_router.AITBCHTTPClient')
    @patch('app.routers.marketplace.AITBCHTTPClient')
    def test_agent_registers_in_marketplace(self, mock_marketplace_client, mock_agent_client):
        """Test that an agent can register and appear in marketplace"""
        # Setup mocks
        mock_agent = Mock()
        mock_agent_client.return_value = mock_agent
        mock_agent.post.return_value = {
            "id": "agent1",
            "name": "Agent 1",
            "status": "registered"
        }

        mock_marketplace = Mock()
        mock_marketplace_client.return_value = mock_marketplace
        mock_marketplace.get.return_value = {
            "listings": [
                {"id": 1, "name": "Agent 1", "agent_id": "agent1", "price": 0.50}
            ],
            "total": 1
        }

        # Import and test
        from app.routers.agent_router import router as agent_router
        from app.routers.marketplace import router as marketplace_router
        from app.main import create_app
        
        app = create_app()
        app.include_router(agent_router)
        app.include_router(marketplace_router)
        client = TestClient(app)
        
        # Register agent
        response = client.post("/agents", json={
            "name": "Agent 1",
            "type": "compute",
            "capabilities": ["gpu", "inference"]
        })
        assert response.status_code == 200
        
        # Check marketplace listing
        response = client.get("/marketplace/listings")
        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 1
        assert data["listings"][0]["agent_id"] == "agent1"
