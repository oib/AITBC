"""
Tests for governance router
"""

from unittest.mock import Mock, patch

import pytest
from fastapi.testclient import TestClient


@pytest.mark.unit
class TestGovernanceRouter:
    """Test governance router endpoints"""

    @patch("app.routers.governance.AITBCHTTPClient")
    def test_governance_proposals_list(self, mock_client_class):
        """Test getting governance proposals list"""
        # Setup mock
        mock_client = Mock()
        mock_client_class.return_value = mock_client
        mock_client.get.return_value = {
            "proposals": [
                {"id": 1, "title": "Proposal 1", "status": "active"},
                {"id": 2, "title": "Proposal 2", "status": "pending"},
            ]
        }

        # Import and test
        from app.main import create_app
        from app.contexts.governance.routers.governance import router

        app = create_app()
        app.include_router(router)
        client = TestClient(app)

        response = client.get("/governance/proposals")
        assert response.status_code == 200
        data = response.json()
        assert "proposals" in data
        assert len(data["proposals"]) == 2

    @patch("app.routers.governance.AITBCHTTPClient")
    def test_governance_vote(self, mock_client_class):
        """Test voting on a governance proposal"""
        # Setup mock
        mock_client = Mock()
        mock_client_class.return_value = mock_client
        mock_client.post.return_value = {"success": True, "proposal_id": 1, "vote": "yes"}

        # Import and test
        from app.main import create_app
        from app.contexts.governance.routers.governance import router

        app = create_app()
        app.include_router(router)
        client = TestClient(app)

        response = client.post("/governance/proposals/1/vote", json={"vote": "yes"})
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
