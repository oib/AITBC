import os

os.environ.setdefault("SECRET_KEY", "test-secret-key")
from fastapi.testclient import TestClient
from agent_app.main import app


def test_cancel_requires_key():
    c = TestClient(app)
    r = c.post("/api/v1/agent/workflows/executions/ex1/cancel")
    assert r.status_code in (401, 403)


def test_cancel_wrong_key_403(monkeypatch):
    monkeypatch.setenv("COORDINATOR_API_KEY", "real-key")
    c = TestClient(app)
    r = c.post("/api/v1/agent/workflows/executions/ex1/cancel", headers={"X-Api-Key": "wrong"})
    assert r.status_code in (401, 403)


def test_create_body_invalid_still_auth_first(monkeypatch):
    monkeypatch.setenv("COORDINATOR_API_KEY", "real-key")
    c = TestClient(app)
    # invalid body but no key -> auth answer, not 422
    r = c.post("/api/v1/agent/workflows", json={})
    assert r.status_code in (401, 403)


# #1853: reads disclosed workflow definitions + execution results/steps
# anonymously while mutations required the key — reads now take the same gate.
def test_workflow_reads_require_key():
    c = TestClient(app)
    for path in (
        "/api/v1/agent/workflows",
        "/api/v1/agent/workflows/wf-1/status",
        "/api/v1/agent/workflows/executions",
    ):
        r = c.get(path)
        assert r.status_code in (401, 403), path


def test_workflow_reads_wrong_key_rejected(monkeypatch):
    monkeypatch.setenv("COORDINATOR_API_KEY", "real-key")
    c = TestClient(app)
    for path in (
        "/api/v1/agent/workflows",
        "/api/v1/agent/workflows/wf-1/status",
        "/api/v1/agent/workflows/executions",
    ):
        r = c.get(path, headers={"X-Api-Key": "wrong"})
        assert r.status_code in (401, 403), path


def test_workflow_reads_accept_configured_key():
    # SECRET_KEY defaults to "test-secret-key" in this module — a configured
    # key must still reach the handlers (404/200, never 401).
    c = TestClient(app)
    r = c.get("/api/v1/agent/workflows", headers={"X-Api-Key": "test-secret-key"})
    assert r.status_code != 401
