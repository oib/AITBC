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
