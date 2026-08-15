"""
AuthMiddleware regression tests.

Validates that the route-based auth middleware supports both Bearer JWT and
miner API-key (X-Api-Key) authentication.
"""

from fastapi import FastAPI
from fastapi.testclient import TestClient


def _make_app() -> FastAPI:
    from aitbc.auth.middleware import AuthMiddleware

    app = FastAPI()
    app.add_middleware(AuthMiddleware)

    @app.get("/v1/miners/register")
    def register() -> dict[str, bool]:
        return {"ok": True}

    @app.get("/v1/admin/dashboard")
    def admin_dashboard() -> dict[str, bool]:
        return {"ok": True}

    return app


def test_auth_middleware_accepts_miner_api_key(monkeypatch):
    """Test that /v1/miners/* accepts X-Api-Key authentication"""
    monkeypatch.setenv("COORDINATOR_API_KEY", "test-miner-key-32-chars-long-xxx")
    monkeypatch.setenv("ENVIRONMENT", "development")

    app = _make_app()
    client = TestClient(app)

    response = client.get(
        "/v1/miners/register",
        headers={
            "X-Api-Key": "test-miner-key-32-chars-long-xxx",
            "X-Miner-ID": "miner-1",
        },
    )

    assert response.status_code == 200
    assert response.json() == {"ok": True}


def test_auth_middleware_rejects_missing_credentials():
    """Test that protected routes reject requests without credentials"""
    app = _make_app()
    client = TestClient(app)

    response = client.get("/v1/miners/register")

    assert response.status_code == 401


def test_auth_middleware_rejects_invalid_api_key(monkeypatch):
    """Test that an invalid X-Api-Key is rejected"""
    monkeypatch.setenv("COORDINATOR_API_KEY", "test-miner-key-32-chars-long-xxx")
    monkeypatch.setenv("ENVIRONMENT", "development")

    app = _make_app()
    client = TestClient(app)

    response = client.get(
        "/v1/miners/register",
        headers={"X-Api-Key": "wrong-key"},
    )

    assert response.status_code == 401


def test_auth_middleware_blocks_miner_key_on_admin_route(monkeypatch):
    """Test that a miner API key cannot access admin-only routes"""
    monkeypatch.setenv("COORDINATOR_API_KEY", "test-miner-key-32-chars-long-xxx")
    monkeypatch.setenv("ENVIRONMENT", "development")

    app = _make_app()
    client = TestClient(app)

    response = client.get(
        "/v1/admin/dashboard",
        headers={"X-Api-Key": "test-miner-key-32-chars-long-xxx"},
    )

    assert response.status_code == 403
