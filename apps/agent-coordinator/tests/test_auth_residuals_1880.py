"""#1880 pins: residual unauthenticated GET/AI routes now require a principal.

Pre-fix these routes had no auth dependency at all (or an OptionalAgent
that never raises and was never scope-checked), so anonymous callers could
read metrics, queue/task state, escrow metadata, agent registry entries,
and drive the AI/ML training endpoints in every signature mode.
"""

import os

os.environ.setdefault("SECRET_KEY", "test-secret-key")

import pytest
from fastapi.testclient import TestClient

from agent_app.main import app


@pytest.fixture
def operator_headers(monkeypatch):
    monkeypatch.setenv("COORDINATOR_API_KEY", "op-key-1880")
    return {"X-Api-Key": "op-key-1880"}


GATED_GETS = [
    "/v1/metrics",
    "/v1/metrics/summary",
    "/v1/metrics/health",
    "/v1/tasks/status",
    "/v1/tasks/queues",
    "/v1/tasks/queues/stats",
    "/v1/tasks/escrow/esc-1",
    "/v1/tasks/task-1/escrow",
    "/v1/tasks/escrow-config",
    "/v1/ai/statistics",
    "/v1/ai/learning/statistics",
    "/v1/agents/some-agent",
    "/api/v1/agent/messages/agents/service/compute",
    "/api/v1/agent/messages/agents/capability/gpu",
    "/api/v1/agent/messages/discover",
]


@pytest.mark.parametrize("path", GATED_GETS)
def test_residual_gets_reject_anonymous(path):
    c = TestClient(app)
    r = c.get(path)
    assert r.status_code in (401, 403), f"{path} returned {r.status_code} anonymously"


@pytest.mark.parametrize("path", ["/v1/ai/statistics", "/v1/tasks/status"])
def test_residual_gets_accept_operator_key(path, operator_headers):
    c = TestClient(app)
    r = c.get(path, headers=operator_headers)
    assert r.status_code != 401, f"{path} rejected a valid operator key: {r.status_code}"
    assert r.status_code != 403, f"{path} forbidden a valid operator key: {r.status_code}"


def test_ai_mutations_reject_anonymous():
    """ai.py POSTs were equally anonymous — OptionalAgent never raises."""
    c = TestClient(app)
    for path, payload in (
        ("/v1/ai/learning/experience", {"data": {}}),
        ("/v1/ai/neural-network/create", {"config": {}}),
        ("/v1/ai/ml-model/create", {"config": {}}),
    ):
        r = c.post(path, json=payload)
        assert r.status_code in (401, 403), f"{path} returned {r.status_code} anonymously"


def test_agents_discover_post_rejects_anonymous():
    c = TestClient(app)
    r = c.post("/v1/agents/discover", json={"query": {}})
    assert r.status_code in (401, 403)
