"""
Tests for governance router
"""

import pytest


@pytest.mark.unit
class TestGovernanceRouter:
    """Test governance router endpoints"""

    def test_submit_slash_appeal(self, client):
        """POST /v1/governance/slash-appeals stores an appeal and returns it."""
        response = client.post(
            "/v1/governance/slash-appeals",
            json={
                "bond_id": "bond-123",
                "reason": "false positive",
                "evidence": ["ipfs://QmEvidence"],
            },
        )

        assert response.status_code == 201, response.text
        body = response.json()
        assert body["bond_id"] == "bond-123"
        assert body["status"] == "submitted"
        assert body["id"]
        assert body["created_at"]

    def test_submit_slash_appeal_requires_bond_id(self, client):
        """bond_id is required."""
        response = client.post("/v1/governance/slash-appeals", json={"reason": "x"})

        assert response.status_code == 422
