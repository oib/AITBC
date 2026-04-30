"""
Tests for governance service
"""

import pytest
from unittest.mock import Mock, patch


@pytest.mark.unit
class TestGovernanceService:
    """Test governance service"""

    @patch('app.services.governance_service.AITBCHTTPClient')
    def test_get_proposals(self, mock_client_class):
        """Test getting governance proposals"""
        # Setup mock
        mock_client = Mock()
        mock_client_class.return_value = mock_client
        mock_client.get.return_value = {
            "proposals": [
                {"id": 1, "title": "Proposal 1", "status": "active"},
                {"id": 2, "title": "Proposal 2", "status": "pending"}
            ]
        }

        # Import and test
        from app.services.governance_service import get_proposals
        
        result = get_proposals()
        assert len(result["proposals"]) == 2

    @patch('app.services.governance_service.AITBCHTTPClient')
    def test_vote_on_proposal(self, mock_client_class):
        """Test voting on a proposal"""
        # Setup mock
        mock_client = Mock()
        mock_client_class.return_value = mock_client
        mock_client.post.return_value = {
            "success": True,
            "proposal_id": 1,
            "vote": "yes"
        }

        # Import and test
        from app.services.governance_service import vote_on_proposal
        
        result = vote_on_proposal(1, "yes")
        assert result["success"] is True
