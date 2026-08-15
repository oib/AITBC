"""
Tests for staking router
"""

import pytest
from fastapi.testclient import TestClient


pytestmark = pytest.mark.unit


class TestStakingRouter:
    """Test staking router endpoints"""

    def test_get_stake_requires_auth(self, client: TestClient):
        """Missing token should return 401."""
        response = client.get("/v1/stake/not-found")
        assert response.status_code == 401
