"""
Tests for disputes router (dispute resolution)
"""

import pytest
from fastapi.testclient import TestClient

from app.contexts.governance.services.dispute_resolution import init_dispute_service


@pytest.fixture(autouse=True)
def setup_dispute_service():
    """Initialize the dispute service for tests"""
    init_dispute_service(None)
    yield


@pytest.mark.unit
class TestDisputesRouter:
    """Test disputes router endpoints"""

    def test_create_dispute(self, client: TestClient):
        """Test creating a dispute"""
        dispute_data = {
            "job_id": "job-001",
            "client": "0xCLIENT123",
            "provider": "0xPROVIDER456",
            "amount": 1000,
            "reason": "Work not completed as agreed",
        }

        response = client.post("/v1/disputes/file", json=dispute_data)
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert "dispute_id" in data
        assert data["status"] == "evidence_phase"

    def test_get_dispute(self, client: TestClient):
        """Test getting dispute by ID"""
        # First create a dispute
        create_response = client.post(
            "/v1/disputes/file",
            json={
                "job_id": "job-002",
                "client": "0xCLIENT",
                "provider": "0xPROVIDER",
                "amount": 500,
                "reason": "Test dispute",
            },
        )
        dispute_id = create_response.json()["dispute_id"]

        # Get the dispute
        response = client.get(f"/v1/disputes/{dispute_id}")
        assert response.status_code == 200
        data = response.json()
        assert data["dispute_id"] == dispute_id
        assert "client" in data
        assert "provider" in data

    def test_list_disputes(self, client: TestClient):
        """Test listing all disputes"""
        response = client.get("/v1/disputes/")
        assert response.status_code == 200
        data = response.json()
        assert "disputes" in data
        assert "count" in data

    def test_submit_evidence(self, client: TestClient):
        """Test submitting evidence to a dispute"""
        # Create dispute first - client must be "client" to match router's hardcoded submitted_by
        create_response = client.post(
            "/v1/disputes/file",
            json={
                "job_id": "job-003",
                "client": "client",
                "provider": "0xPROVIDER",
                "amount": 500,
                "reason": "Evidence test",
            },
        )
        dispute_id = create_response.json()["dispute_id"]

        # Submit evidence
        evidence_data = {
            "dispute_id": dispute_id,
            "evidence_type": "document",
            "description": "Proof of incomplete work",
        }

        response = client.post("/v1/disputes/evidence", json=evidence_data)
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["dispute_id"] == dispute_id

    def test_vote_on_dispute(self, client: TestClient):
        """Test arbitrator voting on dispute"""
        # Register the hardcoded arbitrator that cast_vote uses
        client.post("/v1/disputes/arbitrators/register", params={"address": "arbitrator_001"})

        # Create dispute
        create_response = client.post(
            "/v1/disputes/file",
            json={
                "job_id": "job-004",
                "client": "0xCLIENT",
                "provider": "0xPROVIDER",
                "amount": 500,
                "reason": "Voting test",
            },
        )
        dispute_id = create_response.json()["dispute_id"]

        # Vote
        vote_data = {
            "dispute_id": dispute_id,
            "outcome": "client_wins",
            "reasoning": "Evidence supports client claim",
            "stake_amount": 5000,
        }

        response = client.post("/v1/disputes/vote", json=vote_data)
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["outcome"] == "client_wins"

    def test_register_arbitrator(self, client: TestClient):
        """Test registering as arbitrator"""
        response = client.post("/v1/disputes/arbitrators/register", params={"address": "0xARBITRATOR999"})
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["address"] == "0xARBITRATOR999"

    def test_disputes_health(self, client: TestClient):
        """Test disputes health endpoint"""
        response = client.get("/v1/disputes/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
        assert "active_disputes" in data


@pytest.mark.integration
class TestDisputesIntegration:
    """Integration tests for dispute resolution workflow"""

    def test_full_dispute_resolution(self, client: TestClient):
        """Test complete dispute lifecycle"""
        # 1. Register the hardcoded arbitrator that cast_vote uses
        client.post("/v1/disputes/arbitrators/register", params={"address": "arbitrator_001"})

        # 2. Create dispute - client must be "client" to match router's hardcoded submitted_by
        dispute_response = client.post(
            "/v1/disputes/file",
            json={
                "job_id": "integration-job",
                "client": "client",
                "provider": "0xINTEGRATION_PROVIDER",
                "amount": 2000,
                "reason": "Integration test dispute",
            },
        )
        dispute_id = dispute_response.json()["dispute_id"]

        # 3. Submit evidence
        client.post(
            "/v1/disputes/evidence",
            json={"dispute_id": dispute_id, "evidence_type": "document", "description": "client-evidence"},
        )

        # 4. Arbitrator votes
        client.post(
            "/v1/disputes/vote",
            json={
                "dispute_id": dispute_id,
                "outcome": "client_wins",
                "reasoning": "Client has strong evidence",
                "stake_amount": 5000,
            },
        )

        # 5. Verify dispute has votes
        dispute = client.get(f"/v1/disputes/{dispute_id}").json()
        assert dispute["vote_count"] >= 1
