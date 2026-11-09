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
        # #1337: mutations are honest 501 until the lifecycle is wired
        assert response.status_code == 501

    def test_bounty_get_by_id(self, client: TestClient):
        """Test getting bounty by ID"""
        # #1337: create is an honest 501, so there is no bounty to fetch;
        # the real read path is covered by test_routers_bounty_flat.py
        response = client.get("/v1/bounty/bounty-does-not-exist")
        assert response.status_code == 404

    def test_bounty_get_not_found(self, client: TestClient):
        """Test getting non-existent bounty"""
        response = client.get("/v1/bounty/not-found")
        assert response.status_code == 404

    def test_bounty_claim(self, client: TestClient):
        """Test claiming a bounty"""
        response = client.post(
            "/v1/bounty/claim",
            json={"bounty_id": "bounty-x", "hunter": "0x2222222222222222222222222222222222222222"},
        )
        # #1337: claim is an honest 501 — no fabricated "claimed" state
        assert response.status_code == 501

    def test_bounty_submit_solution(self, client: TestClient):
        """Test submitting a solution"""
        response = client.post(
            "/v1/bounty/submit",
            json={
                "bounty_id": "bounty-x",
                "hunter": "0x2222222222222222222222222222222222222222",
                "solution_url": "https://github.com/solution/repo",
            },
        )
        # #1337: submit is an honest 501 — no fabricated submission
        assert response.status_code == 501

    def test_bounty_stats(self, client: TestClient):
        """Test getting bounty statistics"""
        response = client.get("/v1/bounty/stats")
        assert response.status_code == 200
        data = response.json()
        # A "bounty_id" key here means /{bounty_id} was declared first and swallowed
        # this path -- see tests/security/test_no_unreachable_routes.py.
        assert "bounty_id" not in data
        # #1337: real BountyService aggregates, not the old fabricated shape
        assert data["total_bounties"] == 0
        assert data["open_bounties"] == 0
        assert data["completed_bounties"] == 0
        assert "total_reward" in data
        assert "success_rate" in data
        assert "tier_distribution" in data

    def test_bounty_health(self, client: TestClient):
        """Test bounty health endpoint"""
        response = client.get("/v1/bounty/health")
        assert response.status_code == 200
        data = response.json()
        # status "open" would mean get_bounty() answered instead of bounty_health().
        assert data == {"status": "healthy", "total_bounties": 0, "service": "bounty"}


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
        # #1337: mutations are honest 501 — the fabricated lifecycle is gone
        create_response = client.post("/v1/bounty/create", json=create_data)
        assert create_response.status_code == 501

        list_response = client.get("/v1/bounty/list")
        assert list_response.status_code == 200
        assert list_response.json()["count"] == 0

        claim_response = client.post("/v1/bounty/claim", json={"bounty_id": "bounty-x", "hunter": "0xHUNTER456"})
        assert claim_response.status_code == 501

        submit_response = client.post(
            "/v1/bounty/submit",
            json={"bounty_id": "bounty-x", "hunter": "0xHUNTER456", "solution_url": "https://solution.example.com"},
        )
        assert submit_response.status_code == 501

        # 5. Verify solution — honest 501 like the other mutations (#1337)
        verify_response = client.post(
            "/v1/bounty/verify",
            json={"bounty_id": "bounty-x", "verifier": "0xCREATOR123", "approved": True, "feedback": "Great work!"},
        )
        assert verify_response.status_code == 501
