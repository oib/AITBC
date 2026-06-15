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
        response = client.get("/bounty/list")
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

        response = client.post("/bounty/create", json=bounty_data)
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert "bounty" in data
        assert data["bounty"]["title"] == "Test Bounty"
        assert data["bounty"]["reward"] == 5000

    def test_bounty_get_by_id(self, client: TestClient):
        """Test getting bounty by ID"""
        # First create a bounty
        bounty_data = {
            "title": "Test Bounty Get",
            "description": "Test description",
            "creator": "0x1234567890123456789012345678901234567890",
            "reward": 3000,
        }
        create_response = client.post("/bounty/create", json=bounty_data)
        bounty_id = create_response.json()["bounty"]["id"]

        # Get the bounty
        response = client.get(f"/bounty/{bounty_id}")
        assert response.status_code == 200
        data = response.json()
        assert data["id"] == bounty_id
        assert data["title"] == "Test Bounty Get"

    def test_bounty_get_not_found(self, client: TestClient):
        """Test getting non-existent bounty"""
        response = client.get("/bounty/NONEXISTENT")
        assert response.status_code == 404

    def test_bounty_claim(self, client: TestClient):
        """Test claiming a bounty"""
        # Create bounty first
        bounty_data = {
            "title": "Claimable Bounty",
            "description": "Test",
            "creator": "0x1111111111111111111111111111111111111111",
            "reward": 1000,
        }
        create_response = client.post("/bounty/create", json=bounty_data)
        bounty_id = create_response.json()["bounty"]["id"]

        # Claim the bounty
        claim_data = {"bounty_id": bounty_id, "hunter": "0x2222222222222222222222222222222222222222"}
        response = client.post("/bounty/claim", json=claim_data)
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["bounty_id"] == bounty_id

    def test_bounty_submit_solution(self, client: TestClient):
        """Test submitting a solution"""
        # Create and claim bounty
        bounty_data = {
            "title": "Solution Bounty",
            "description": "Test",
            "creator": "0x1111111111111111111111111111111111111111",
            "reward": 1000,
        }
        create_response = client.post("/bounty/create", json=bounty_data)
        bounty_id = create_response.json()["bounty"]["id"]

        client.post("/bounty/claim", json={"bounty_id": bounty_id, "hunter": "0x2222222222222222222222222222222222222222"})

        # Submit solution
        solution_data = {
            "bounty_id": bounty_id,
            "hunter": "0x2222222222222222222222222222222222222222",
            "solution_url": "https://github.com/solution/repo",
            "notes": "Solution completed",
        }
        response = client.post("/bounty/submit", json=solution_data)
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True

    def test_bounty_stats(self, client: TestClient):
        """Test getting bounty statistics"""
        response = client.get("/bounty/stats")
        assert response.status_code == 200
        data = response.json()
        assert "total_bounties" in data
        assert "total_reward_pool" in data
        assert "completion_rate" in data

    def test_bounty_health(self, client: TestClient):
        """Test bounty health endpoint"""
        response = client.get("/bounty/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
        assert "total_bounties" in data


@pytest.mark.integration
class TestBountyIntegration:
    """Integration tests for bounty workflow"""

    def test_full_bounty_lifecycle(self, client: TestClient):
        """Test complete bounty lifecycle"""
        # 1. Create bounty
        create_data = {
            "title": "Integration Test Bounty",
            "description": "Full workflow test",
            "creator": "0xCREATOR123",
            "reward": 5000,
            "requirements": ["test"],
            "tags": ["integration"],
        }
        create_response = client.post("/bounty/create", json=create_data)
        assert create_response.status_code == 200
        bounty_id = create_response.json()["bounty"]["id"]

        # 2. List bounties
        list_response = client.get("/bounty/list")
        assert list_response.status_code == 200
        assert any(b["id"] == bounty_id for b in list_response.json()["bounties"])

        # 3. Claim bounty
        claim_response = client.post("/bounty/claim", json={"bounty_id": bounty_id, "hunter": "0xHUNTER456"})
        assert claim_response.status_code == 200

        # 4. Submit solution
        submit_response = client.post(
            "/bounty/submit",
            json={"bounty_id": bounty_id, "hunter": "0xHUNTER456", "solution_url": "https://solution.example.com"},
        )
        assert submit_response.status_code == 200

        # 5. Verify solution
        verify_response = client.post(
            "/bounty/verify",
            json={"bounty_id": bounty_id, "verifier": "0xCREATOR123", "approved": True, "feedback": "Great work!"},
        )
        assert verify_response.status_code == 200
        assert verify_response.json()["approved"] is True
