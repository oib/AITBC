"""#3003 AUTH-WF-FOLLOWER-KEY-1 pins: the six ``/api/v1/agent/workflows``
routes are operator-grade, not coin-request grade.

They briefly reused the coin-request ``_require_api_key`` pass-through,
which accepts ``FOLLOWER_API_KEY`` — a credential the fleet distributes to
every follower. Workflow create/execute/cancel must instead go through the
shared principal machinery: ``COORDINATOR_API_KEY`` or an admin/operator
JWT resolves an ``is_admin`` principal; follower keys, agent JWTs, scoped
keys and anonymous callers do not.
"""

import os

os.environ.setdefault("SECRET_KEY", "test-secret-key")
os.environ.setdefault("JWT_SECRET", "test-secret-for-agent-coordinator-tests" * 2)

import pytest
from fastapi.testclient import TestClient

from agent_app.config import settings
from agent_app.main import app

from aitbc.auth.jwt import create_access_token

OPERATOR_KEY = "test-operator-key"
FOLLOWER_KEY = "test-follower-key"

# (method, path, json body or None) — all six workflow routes.
ROUTES = [
    ("POST", "/api/v1/agent/workflows", {"name": "w", "steps": []}),
    ("POST", "/api/v1/agent/workflows/wf-1/execute", {}),
    ("GET", "/api/v1/agent/workflows/wf-1/status", None),
    ("GET", "/api/v1/agent/workflows", None),
    ("GET", "/api/v1/agent/workflows/executions", None),
    ("POST", "/api/v1/agent/workflows/executions/ex1/cancel", None),
]


def _call(client: TestClient, method: str, path: str, headers: dict | None = None, body=None):
    return client.request(method, path, headers=headers or {}, json=body)


def _enforce(monkeypatch):
    monkeypatch.setattr(settings, "agent_msg_signature_mode", "enforce")


def _keys(monkeypatch):
    monkeypatch.setenv("COORDINATOR_API_KEY", OPERATOR_KEY)
    monkeypatch.setenv("FOLLOWER_API_KEY", FOLLOWER_KEY)
    monkeypatch.delenv("AITBC_ALLOW_LEGACY_SHARED_KEYS", raising=False)


@pytest.mark.parametrize("method,path,body", ROUTES)
def test_workflow_routes_reject_follower_key(method, path, body, monkeypatch):
    """The headline defect: the widely-distributed follower key must not
    reach workflow administration — on any of the six routes."""
    _enforce(monkeypatch)
    _keys(monkeypatch)
    client = TestClient(app)
    resp = _call(client, method, path, headers={"X-Api-Key": FOLLOWER_KEY}, body=body)
    assert resp.status_code in (401, 403), f"{method} {path}: {resp.status_code}"


@pytest.mark.parametrize("method,path,body", ROUTES)
def test_workflow_routes_reject_anonymous(method, path, body, monkeypatch):
    _enforce(monkeypatch)
    _keys(monkeypatch)
    client = TestClient(app)
    resp = _call(client, method, path, body=body)
    assert resp.status_code in (401, 403), f"{method} {path}: {resp.status_code}"


@pytest.mark.parametrize("method,path,body", ROUTES)
def test_workflow_routes_reject_wrong_key(method, path, body, monkeypatch):
    _enforce(monkeypatch)
    _keys(monkeypatch)
    client = TestClient(app)
    resp = _call(client, method, path, headers={"X-Api-Key": "wrong"}, body=body)
    assert resp.status_code in (401, 403), f"{method} {path}: {resp.status_code}"


@pytest.mark.parametrize("method,path,body", ROUTES)
def test_workflow_routes_reject_non_admin_jwt(method, path, body, monkeypatch):
    """A valid user/agent-grade JWT is a principal but not admin — enforce
    mode must 403 it, matching every other admin surface."""
    _enforce(monkeypatch)
    _keys(monkeypatch)
    client = TestClient(app)
    token = create_access_token(user_id="human-1", role="user")
    resp = _call(client, method, path, headers={"Authorization": f"Bearer {token}"}, body=body)
    assert resp.status_code in (401, 403), f"{method} {path}: {resp.status_code}"


@pytest.mark.parametrize("method,path,body", ROUTES)
def test_workflow_routes_accept_operator_key(method, path, body, monkeypatch):
    """``COORDINATOR_API_KEY`` resolves the shared operator principal
    (``is_admin``) — the intended credential for this surface."""
    _enforce(monkeypatch)
    _keys(monkeypatch)
    client = TestClient(app)
    resp = _call(client, method, path, headers={"X-Api-Key": OPERATOR_KEY}, body=body)
    assert resp.status_code not in (401, 403), f"{method} {path}: {resp.status_code} {resp.text[:200]}"


def test_workflow_routes_accept_admin_jwt(monkeypatch):
    """An admin/operator JWT is the other intended credential."""
    _enforce(monkeypatch)
    _keys(monkeypatch)
    client = TestClient(app)
    token = create_access_token(user_id="admin-1", role="admin")
    resp = client.get("/api/v1/agent/workflows", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code not in (401, 403), resp.text[:200]


def test_create_body_invalid_still_auth_first(monkeypatch):
    """Auth runs in a dependency — an invalid body with no credential gets
    the auth answer, not a 422 validation leak."""
    _enforce(monkeypatch)
    _keys(monkeypatch)
    client = TestClient(app)
    resp = client.post("/api/v1/agent/workflows", json={})
    assert resp.status_code in (401, 403)
