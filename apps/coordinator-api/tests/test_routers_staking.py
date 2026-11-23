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

    def test_leaderboard_service_error_is_503_not_fallback(self, client):
        """#2717: a failing leaderboard lookup must not answer 200 with the
        three hard-coded invented agents — it is a 503."""
        from unittest.mock import MagicMock

        from coordinator_api.contexts.staking.routers import staking as staking_router
        from coordinator_api.main import app

        svc = MagicMock()
        svc.get_leaderboard.side_effect = RuntimeError("db down")
        app.dependency_overrides[staking_router.get_staking_service] = lambda: svc
        try:
            response = client.get("/v1/staking/leaderboard")
        finally:
            app.dependency_overrides.pop(staking_router.get_staking_service, None)

        assert response.status_code == 503
        assert "0x1234567890123456789012345678901234567890" not in response.text
        assert "Fallback" not in response.text
