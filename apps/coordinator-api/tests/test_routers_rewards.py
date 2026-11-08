"""Tests for /v1/rewards profile branches (#1289).

The rewards router declares no auth dependency — enforcement is the
``AuthMiddleware`` + route-security matrix (ADMIN_OR_CLIENT), which is off
under ``TEST_MODE``. These tests pin the handler-level branches that remain:
the agent_id guard, the not-found path through ``RewardEngine``, profile
creation, and the tier listing. Deeper reward math is covered by the service
tests; this file covers the HTTP surface only.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient


@pytest.mark.unit
class TestRewardProfileRoutes:
    def test_profile_without_agent_id_is_400(self, client: TestClient) -> None:
        resp = client.get("/v1/rewards/profile")
        assert resp.status_code == 400
        assert "agent_id" in resp.json()["detail"]

    def test_profile_unknown_agent_is_404(self, client: TestClient) -> None:
        resp = client.get("/v1/rewards/profile/agent-ghost")
        assert resp.status_code == 404
        assert resp.json()["detail"] == "Reward profile not found"

    def test_create_then_read_profile(self, client: TestClient) -> None:
        create = client.post("/v1/rewards/profile/agent-new")
        assert create.status_code == 200
        assert create.json()["agent_id"] == "agent-new"

        resp = client.get("/v1/rewards/profile/agent-new")
        assert resp.status_code == 200
        body = resp.json()
        assert body["agent_id"] == "agent-new"
        assert body["current_tier"] == "bronze"

    def test_create_is_idempotent_for_existing_agent(self, client: TestClient) -> None:
        first = client.post("/v1/rewards/profile/agent-dupe")
        second = client.post("/v1/rewards/profile/agent-dupe")
        assert first.status_code == 200
        assert second.status_code == 200
        assert first.json()["agent_id"] == second.json()["agent_id"] == "agent-dupe"


@pytest.mark.unit
class TestRewardTiers:
    def test_tiers_returns_list(self, client: TestClient) -> None:
        resp = client.get("/v1/rewards/tiers")
        assert resp.status_code == 200
        assert isinstance(resp.json(), list)
