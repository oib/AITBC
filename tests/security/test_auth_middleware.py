"""
AuthMiddleware regression tests.

Validates that the route-based auth middleware supports both Bearer JWT and
miner API-key (X-Api-Key) authentication.

These tests configured the miner credential as ``COORDINATOR_API_KEY``, which is what
`require_miner_api_key` used to accept whenever no miner keys were set. V23-68 removed that
promotion — the coordinator key reaches a WebSocket handler that signs and submits, and it is
published in a world-readable bootstrap file — so the credential here is ``MINER_API_KEYS``,
and the removal is pinned by a test of its own rather than left to be re-introduced.
"""

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

MINER_KEY = "test-miner-key-32-chars-long-xxx"


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


def _configure_miner_key(monkeypatch, key: str = MINER_KEY) -> None:
    monkeypatch.setenv("MINER_API_KEYS", key)
    monkeypatch.setenv("ENVIRONMENT", "development")


def _no_miner_keys(monkeypatch) -> None:
    """Empty the merged miner-key list so the "no keys configured" branch runs.

    ``_configured_miner_keys`` merges ``coordinator_api.config.settings.miner_api_keys``
    with ``MINER_API_KEYS``. The Settings singleton bakes the env value at first
    import, which under pytest happens inside an earlier test's monkeypatch — so
    deleting the env var alone cannot empty the list (ENG-3).
    """
    monkeypatch.delenv("MINER_API_KEYS", raising=False)
    try:
        from coordinator_api.config import settings as coordinator_settings
    except ImportError:
        return  # coordinator_api not importable here; the env half is already empty
    monkeypatch.setattr(coordinator_settings, "miner_api_keys", [])


def test_auth_middleware_accepts_miner_api_key(monkeypatch):
    """Test that /v1/miners/* accepts X-Api-Key authentication"""
    _configure_miner_key(monkeypatch)

    app = _make_app()
    client = TestClient(app)

    response = client.get(
        "/v1/miners/register",
        headers={
            "X-Api-Key": MINER_KEY,
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
    _configure_miner_key(monkeypatch)

    app = _make_app()
    client = TestClient(app)

    response = client.get(
        "/v1/miners/register",
        headers={"X-Api-Key": "wrong-key"},
    )

    assert response.status_code == 401


def test_the_coordinator_key_is_not_a_miner_credential(monkeypatch):
    """V23-68: the published hub key must not open the miner routes."""
    monkeypatch.setenv("COORDINATOR_API_KEY", "hub-key-32-chars-long-xxxxxxxxxx")
    _no_miner_keys(monkeypatch)
    monkeypatch.setenv("ENVIRONMENT", "development")

    app = _make_app()
    client = TestClient(app)

    response = client.get(
        "/v1/miners/register",
        headers={"X-Api-Key": "hub-key-32-chars-long-xxxxxxxxxx"},
    )

    assert response.status_code == 401


def test_the_reason_for_a_401_reaches_the_log(monkeypatch, caplog):
    """V23-68c: the two 401s need different actions, so the log has to tell them apart.

    An unset `MINER_API_KEYS` and a wrong key both answered `Invalid API key`, which sent
    operators looking at the credential when the list was simply empty. The response stays
    generic — an anonymous caller is told nothing about the server's configuration.
    """
    import logging

    _no_miner_keys(monkeypatch)
    monkeypatch.setenv("ENVIRONMENT", "development")

    client = TestClient(_make_app())

    with caplog.at_level(logging.WARNING):
        response = client.get("/v1/miners/register", headers={"X-Api-Key": "anything"})

    assert response.status_code == 401
    assert response.json() == {"detail": "Invalid API key"}
    assert "No miner API keys configured" in caplog.text
    assert "/v1/miners/register" in caplog.text


def test_a_wrong_key_is_logged_as_a_wrong_key(monkeypatch, caplog):
    """The contrast that gives the test above its meaning."""
    import logging

    _configure_miner_key(monkeypatch)

    client = TestClient(_make_app())

    with caplog.at_level(logging.WARNING):
        response = client.get("/v1/miners/register", headers={"X-Api-Key": "wrong-key"})

    assert response.status_code == 401
    assert "No miner API keys configured" not in caplog.text
    assert "Invalid or missing API key" in caplog.text


def test_auth_middleware_blocks_miner_key_on_admin_route(monkeypatch):
    """Test that a miner API key cannot access admin-only routes"""
    _configure_miner_key(monkeypatch)

    app = _make_app()
    client = TestClient(app)

    response = client.get(
        "/v1/admin/dashboard",
        headers={"X-Api-Key": MINER_KEY},
    )

    assert response.status_code == 403


def test_configured_miner_keys_merges_settings_and_env(monkeypatch):
    """Settings list + env var merge with dedup, order kept (ENG-3 optional).

    This is the contract _no_miner_keys() manipulates: the merged list stays
    empty only when BOTH sources are empty.
    """
    config = pytest.importorskip("coordinator_api.config")
    from aitbc.auth.dependencies import _configured_miner_keys

    monkeypatch.setattr(config.settings, "miner_api_keys", ["a", "b"])
    monkeypatch.setenv("MINER_API_KEYS", "b,c")

    assert _configured_miner_keys() == ["a", "b", "c"]


def _miner_key_app():
    """Minimal app exposing require_miner_api_key so tests can inspect `sub`."""
    from fastapi import Depends, FastAPI

    from aitbc.auth.dependencies import require_miner_api_key

    from typing import Annotated

    app = FastAPI()

    @app.get("/whoami")
    def whoami(user: Annotated[dict, Depends(require_miner_api_key)]) -> dict:
        return user

    return app


def test_bound_miner_key_rejects_foreign_miner_id(monkeypatch):
    """#1597: MINER_API_KEY_BINDINGS pins a key to one miner id — a shared key
    can no longer impersonate an arbitrary X-Miner-ID."""
    key = "bound-miner-key-32-chars-long"
    _configure_miner_key(monkeypatch, key)
    monkeypatch.setenv("MINER_API_KEY_BINDINGS", f'{{"{key}": "miner-a"}}')

    client = TestClient(_miner_key_app())
    ok = client.get("/whoami", headers={"X-Api-Key": key, "X-Miner-ID": "miner-a"})
    assert ok.status_code == 200 and ok.json()["sub"] == "miner-a"

    bad = client.get("/whoami", headers={"X-Api-Key": key, "X-Miner-ID": "miner-b"})
    assert bad.status_code == 403

    # No X-Miner-ID at all: the bound id is used, never caller-asserted.
    none_ = client.get("/whoami", headers={"X-Api-Key": key})
    assert none_.status_code == 200 and none_.json()["sub"] == "miner-a"


def test_unbound_miner_key_keeps_legacy_miner_id(monkeypatch):
    """Backward compatibility: keys without a binding still honour X-Miner-ID."""
    _configure_miner_key(monkeypatch)
    monkeypatch.setenv("MINER_API_KEY_BINDINGS", '{"some-other-key": "miner-x"}')

    client = TestClient(_miner_key_app())
    resp = client.get("/whoami", headers={"X-Api-Key": MINER_KEY, "X-Miner-ID": "miner-9"})
    assert resp.status_code == 200 and resp.json()["sub"] == "miner-9"


def test_miner_key_bindings_pair_syntax(monkeypatch):
    """The comma-separated key=miner_id form parses as well as JSON."""
    key = "pair-miner-key-32-chars-long"
    _configure_miner_key(monkeypatch, key)
    monkeypatch.setenv("MINER_API_KEY_BINDINGS", f"{key}=miner-pair, other=ignored")

    client = TestClient(_miner_key_app())
    resp = client.get("/whoami", headers={"X-Api-Key": key})
    assert resp.status_code == 200 and resp.json()["sub"] == "miner-pair"
