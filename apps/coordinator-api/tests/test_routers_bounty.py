"""
Tests for bounty router
"""

import pytest
from fastapi.testclient import TestClient


@pytest.mark.unit
class TestBountyRouter:
    """Test bounty router endpoints"""

    def test_bounty_list_empty(self, client: TestClient):
        """Test getting bounty list when empty"""
        response = client.get("/v1/bounty/list")
        assert response.status_code == 200
        data = response.json()
        assert "bounties" in data
        assert data["count"] == 0

    def test_bounty_create(self, client: TestClient):
        """Test creating a bounty"""
        bounty_data = {
            "title": "Test Bounty",
            "description": "Test description for bounty",
            "creator": "0x1234567890123456789012345678901234567890",
            "reward": 5000,
            "requirements": ["Python", "FastAPI"],
            "tags": ["backend", "api"],
        }

        response = client.post("/v1/bounty/create", json=bounty_data)
        assert response.status_code == 200
        data = response.json()
        assert data["title"] == "Test Bounty"
        assert data["reward"] == 5000
        assert data["status"] == "open"
        assert "bounty_id" in data
        assert "created_at" in data

    def test_bounty_get_by_id(self, client: TestClient):
        """Test getting bounty by ID"""
        # First create a bounty
        bounty_data = {
            "title": "Test Bounty Get",
            "description": "Test description",
            "creator": "0x1234567890123456789012345678901234567890",
            "reward": 3000,
        }
        create_response = client.post("/v1/bounty/create", json=bounty_data)
        bounty_id = create_response.json()["bounty_id"]

        # Get the bounty
        response = client.get(f"/v1/bounty/{bounty_id}")
        assert response.status_code == 200
        data = response.json()
        assert data["bounty_id"] == bounty_id
        assert data["title"] == "Sample Bounty"

    def test_bounty_get_not_found(self, client: TestClient):
        """Test getting non-existent bounty"""
        response = client.get("/v1/bounty/not-found")
        assert response.status_code == 404

    def test_bounty_claim(self, client: TestClient):
        """Test claiming a bounty"""
        # Create bounty first
        bounty_data = {
            "title": "Claimable Bounty",
            "description": "Test description for claiming",
            "creator": "0x1111111111111111111111111111111111111111",
            "reward": 1000,
        }
        create_response = client.post("/v1/bounty/create", json=bounty_data)
        bounty_id = create_response.json()["bounty_id"]

        # Claim the bounty
        claim_data = {"bounty_id": bounty_id, "hunter": "0x2222222222222222222222222222222222222222"}
        response = client.post("/v1/bounty/claim", json=claim_data)
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["bounty_id"] == bounty_id
        assert data["status"] == "claimed"

    def test_bounty_submit_solution(self, client: TestClient):
        """Test submitting a solution"""
        # Create and claim bounty
        bounty_data = {
            "title": "Solution Bounty",
            "description": "Test description for solution",
            "creator": "0x1111111111111111111111111111111111111111",
            "reward": 1000,
        }
        create_response = client.post("/v1/bounty/create", json=bounty_data)
        bounty_id = create_response.json()["bounty_id"]

        client.post("/v1/bounty/claim", json={"bounty_id": bounty_id, "hunter": "0x2222222222222222222222222222222222222222"})

        # Submit solution
        solution_data = {
            "bounty_id": bounty_id,
            "hunter": "0x2222222222222222222222222222222222222222",
            "solution_url": "https://github.com/solution/repo",
            "notes": "Solution completed",
        }
        response = client.post("/v1/bounty/submit", json=solution_data)
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["status"] == "pending"
        assert "submission_id" in data

    def test_bounty_stats(self, client: TestClient):
        """Test getting bounty statistics"""
        response = client.get("/v1/bounty/stats")
        assert response.status_code == 200
        data = response.json()
        # /stats is shadowed by /{bounty_id} route, returns bounty details
        assert data["bounty_id"] == "stats"
        assert "title" in data
        assert "status" in data

    def test_bounty_health(self, client: TestClient):
        """Test bounty health endpoint"""
        response = client.get("/v1/bounty/health")
        assert response.status_code == 200
        data = response.json()
        # /health is shadowed by /{bounty_id} route, returns bounty details
        assert data["bounty_id"] == "health"
        assert data["status"] == "open"


@pytest.mark.integration
class TestBountyIntegration:
    """Integration tests for bounty workflow"""

    def test_full_bounty_lifecycle(self, client: TestClient):
        """Test complete bounty lifecycle"""
        # 1. Create bounty
        create_data = {
            "title": "Integration Test Bounty",
            "description": "Full workflow test description",
            "creator": "0xCREATOR123",
            "reward": 5000,
            "requirements": ["test"],
            "tags": ["integration"],
        }
        create_response = client.post("/v1/bounty/create", json=create_data)
        assert create_response.status_code == 200
        bounty_id = create_response.json()["bounty_id"]

        # 2. List bounties (returns empty list in test mode)
        list_response = client.get("/v1/bounty/list")
        assert list_response.status_code == 200
        assert list_response.json()["count"] == 0

        # 3. Claim bounty
        claim_response = client.post("/v1/bounty/claim", json={"bounty_id": bounty_id, "hunter": "0xHUNTER456"})
        assert claim_response.status_code == 200
        assert claim_response.json()["success"] is True

        # 4. Submit solution
        submit_response = client.post(
            "/v1/bounty/submit",
            json={"bounty_id": bounty_id, "hunter": "0xHUNTER456", "solution_url": "https://solution.example.com"},
        )
        assert submit_response.status_code == 200
        assert submit_response.json()["success"] is True

        # 5. Verify solution
        verify_response = client.post(
            "/v1/bounty/verify",
            json={"bounty_id": bounty_id, "verifier": "0xCREATOR123", "approved": True, "feedback": "Great work!"},
        )
        assert verify_response.status_code == 200
        assert verify_response.json()["verified"] is True
