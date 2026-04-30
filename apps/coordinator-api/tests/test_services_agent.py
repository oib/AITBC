"""
Tests for agent service
"""

import pytest
from unittest.mock import Mock, patch


@pytest.mark.unit
class TestAgentService:
    """Test agent service"""

    @patch('app.services.agent_service.AITBCHTTPClient')
    def test_get_agent_status(self, mock_client_class):
        """Test getting agent status"""
        # Setup mock
        mock_client = Mock()
        mock_client_class.return_value = mock_client
        mock_client.get.return_value = {
            "id": "agent1",
            "name": "Agent 1",
            "status": "active",
            "current_task": None
        }

        # Import and test
        from app.services.agent_service import get_agent_status
        
        result = get_agent_status("agent1")
        assert result["id"] == "agent1"
        assert result["status"] == "active"

    @patch('app.services.agent_service.AITBCHTTPClient')
    def test_register_agent(self, mock_client_class):
        """Test registering a new agent"""
        # Setup mock
        mock_client = Mock()
        mock_client_class.return_value = mock_client
        mock_client.post.return_value = {
            "id": "agent2",
            "name": "Agent 2",
            "status": "registered"
        }

        # Import and test
        from app.services.agent_service import register_agent
        
        result = register_agent({"name": "Agent 2", "type": "compute"})
        assert result["id"] == "agent2"
        assert result["status"] == "registered"
