"""
Tests for disputes router (dispute resolution)
"""

import pytest
from fastapi.testclient import TestClient


@pytest.mark.unit
class TestDisputesRouter:
    """Test disputes router endpoints"""

    def test_create_dispute(self, client: TestClient):
        """Test creating a dispute"""
        dispute_data = {
            "job_id": "job-001",
            "client_address": "0xCLIENT123",
            "provider_address": "0xPROVIDER456",
            "description": "Work not completed as agreed",
            "evidence": ["url1", "url2"],
            "claim_amount": 1000
        }
        
        response = client.post("/disputes/create", json=dispute_data)
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert "dispute_id" in data
        assert data["dispute"]["status"] == "open"

    def test_get_dispute(self, client: TestClient):
        """Test getting dispute by ID"""
        # First create a dispute
        create_response = client.post("/disputes/create", json={
            "job_id": "job-002",
            "client_address": "0xCLIENT",
            "provider_address": "0xPROVIDER",
            "description": "Test dispute",
            "claim_amount": 500
        })
        dispute_id = create_response.json()["dispute_id"]
        
        # Get the dispute
        response = client.get(f"/disputes/{dispute_id}")
        assert response.status_code == 200
        data = response.json()
        assert data["dispute_id"] == dispute_id
        assert "client_address" in data

    def test_list_disputes(self, client: TestClient):
        """Test listing all disputes"""
        response = client.get("/disputes/list")
        assert response.status_code == 200
        data = response.json()
        assert "disputes" in data
        assert "count" in data

    def test_submit_evidence(self, client: TestClient):
        """Test submitting evidence to a dispute"""
        # Create dispute first
        create_response = client.post("/disputes/create", json={
            "job_id": "job-003",
            "client_address": "0xCLIENT",
            "provider_address": "0xPROVIDER",
            "description": "Evidence test"
        })
        dispute_id = create_response.json()["dispute_id"]
        
        # Submit evidence
        evidence_data = {
            "dispute_id": dispute_id,
            "submitter": "0xCLIENT",
            "evidence_url": "https://evidence.example.com/proof",
            "description": "Proof of incomplete work"
        }
        
        response = client.post("/disputes/evidence", json=evidence_data)
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["evidence_count"] > 0

    def test_vote_on_dispute(self, client: TestClient):
        """Test arbitrator voting on dispute"""
        # Create and assign arbitrator
        client.post("/disputes/arbitrators/register", json={
            "address": "0xARBITRATOR789",
            "stake": 5000
        })
        
        # Create dispute
        create_response = client.post("/disputes/create", json={
            "job_id": "job-004",
            "client_address": "0xCLIENT",
            "provider_address": "0xPROVIDER",
            "description": "Voting test"
        })
        dispute_id = create_response.json()["dispute_id"]
        
        # Vote
        vote_data = {
            "dispute_id": dispute_id,
            "arbitrator": "0xARBITRATOR789",
            "vote": "client",
            "reason": "Evidence supports client claim"
        }
        
        response = client.post("/disputes/vote", json=vote_data)
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["vote"] == "client"

    def test_register_arbitrator(self, client: TestClient):
        """Test registering as arbitrator"""
        arb_data = {
            "address": "0xARBITRATOR999",
            "stake": 10000
        }
        
        response = client.post("/disputes/arbitrators/register", json=arb_data)
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["arbitrator"]["address"] == "0xARBITRATOR999"

    def test_disputes_health(self, client: TestClient):
        """Test disputes health endpoint"""
        response = client.get("/disputes/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
        assert "open_disputes" in data


@pytest.mark.integration
class TestDisputesIntegration:
    """Integration tests for dispute resolution workflow"""

    def test_full_dispute_resolution(self, client: TestClient):
        """Test complete dispute lifecycle"""
        # 1. Register arbitrators
        for i in range(3):
            client.post("/disputes/arbitrators/register", json={
                "address": f"0xARB{i}",
                "stake": 5000
            })
        
        # 2. Create dispute
        dispute_response = client.post("/disputes/create", json={
            "job_id": "integration-job",
            "client_address": "0xINTEGRATION_CLIENT",
            "provider_address": "0xINTEGRATION_PROVIDER",
            "description": "Integration test dispute",
            "evidence": ["evidence1"],
            "claim_amount": 2000
        })
        dispute_id = dispute_response.json()["dispute_id"]
        
        # 3. Submit evidence from both sides
        client.post("/disputes/evidence", json={
            "dispute_id": dispute_id,
            "submitter": "0xINTEGRATION_CLIENT",
            "evidence_url": "client-evidence"
        })
        
        client.post("/disputes/evidence", json={
            "dispute_id": dispute_id,
            "submitter": "0xINTEGRATION_PROVIDER",
            "evidence_url": "provider-evidence"
        })
        
        # 4. Arbitrators vote
        for i in range(3):
            client.post("/disputes/vote", json={
                "dispute_id": dispute_id,
                "arbitrator": f"0xARB{i}",
                "vote": "client" if i < 2 else "provider"
            })
        
        # 5. Verify dispute has votes
        dispute = client.get(f"/disputes/{dispute_id}").json()
        assert len(dispute.get("votes", [])) >= 3
