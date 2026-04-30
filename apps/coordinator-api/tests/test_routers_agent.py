"""
Tests for agent router
"""

import pytest
from unittest.mock import Mock, patch
from fastapi.testclient import TestClient


@pytest.mark.unit
class TestAgentRouter:
    """Test agent router endpoints"""

    @patch('app.routers.agent_router.AITBCHTTPClient')
    def test_agent_list(self, mock_client_class):
        """Test getting agent list"""
        # Setup mock
        mock_client = Mock()
        mock_client_class.return_value = mock_client
        mock_client.get.return_value = {
            "agents": [
                {"id": "agent1", "name": "Agent 1", "status": "active"},
                {"id": "agent2", "name": "Agent 2", "status": "idle"}
            ],
            "total": 2
        }

        # Import and test
        from app.routers.agent_router import router
        from app.main import create_app
        
        app = create_app()
        app.include_router(router)
        client = TestClient(app)
        
        response = client.get("/agents")
        assert response.status_code == 200
        data = response.json()
        assert "agents" in data
        assert data["total"] == 2

    @patch('app.routers.agent_router.AITBCHTTPClient')
    def test_agent_register(self, mock_client_class):
        """Test registering a new agent"""
        # Setup mock
        mock_client = Mock()
        mock_client_class.return_value = mock_client
        mock_client.post.return_value = {
            "id": "agent3",
            "name": "Agent 3",
            "status": "registered"
        }

        # Import and test
        from app.routers.agent_router import router
        from app.main import create_app
        
        app = create_app()
        app.include_router(router)
        client = TestClient(app)
        
        response = client.post("/agents", json={
            "name": "Agent 3",
            "type": "compute",
            "capabilities": ["gpu", "inference"]
        })
        assert response.status_code == 200
        data = response.json()
        assert data["id"] == "agent3"
        assert data["status"] == "registered"

    @patch('app.routers.agent_router.AITBCHTTPClient')
    def test_agent_status(self, mock_client_class):
        """Test getting agent status"""
        # Setup mock
        mock_client = Mock()
        mock_client_class.return_value = mock_client
        mock_client.get.return_value = {
            "id": "agent1",
            "name": "Agent 1",
            "status": "active",
            "current_task": None,
            "uptime": 3600
        }

        # Import and test
        from app.routers.agent_router import router
        from app.main import create_app
        
        app = create_app()
        app.include_router(router)
        client = TestClient(app)
        
        response = client.get("/agents/agent1/status")
        assert response.status_code == 200
        data = response.json()
        assert data["id"] == "agent1"
        assert data["status"] == "active"
