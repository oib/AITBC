"""#1204 WALLET-AUTH-ENABLE-1 pins: the staged auth flip must fail closed.

Covers the flip contract itself: ``WALLET_AUTH_ENABLED=true`` with no
``WALLET_API_KEY`` must refuse (501), missing/wrong keys must 401, the right
key must pass — at both the dependency level and on the real ``/v1/wallets``
and ``/v1/rpc`` routes. Internal callers already send ``X-API-Key`` (exchange
``wallet_auth_headers``, coordinator portfolio service, CLI
``wallet_api_key``); these pins keep the enforcement side honest.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from typing import Annotated

from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient

from wallet_app.deps import get_keystore, get_ledger, get_receipt_service, require_admin_api_key
from wallet_app.settings import Settings, settings

_TEST_KEY = "wallet-auth-flip-pin-key-0123456789abcdef"


def _probe_app() -> FastAPI:
    app = FastAPI()

    @app.get("/probe")
    def probe(_admin: Annotated[None, Depends(require_admin_api_key)]) -> dict[str, bool]:
        return {"ok": True}

    return app


@pytest.fixture
def probe_client():
    return TestClient(_probe_app())


@pytest.fixture
def auth_on(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(settings, "auth_enabled", True, raising=False)
    monkeypatch.setattr(settings, "api_key", _TEST_KEY, raising=False)


class TestAuthenticatorMatrix:
    """require_admin_api_key against the real APIKeyAuthenticator."""

    def test_disabled_allows_keyless(self, probe_client, monkeypatch):
        monkeypatch.setattr(settings, "auth_enabled", False, raising=False)
        monkeypatch.setattr(settings, "api_key", _TEST_KEY, raising=False)
        assert probe_client.get("/probe").status_code == 200

    def test_enabled_without_key_fails_closed_501(self, probe_client, monkeypatch):
        """Flip without provisioning must not open the routes — 501, not 200."""
        monkeypatch.setattr(settings, "auth_enabled", True, raising=False)
        monkeypatch.setattr(settings, "api_key", None, raising=False)
        resp = probe_client.get("/probe", headers={"X-API-Key": "anything"})
        assert resp.status_code == 501

    def test_missing_header_401(self, probe_client, auth_on):
        assert probe_client.get("/probe").status_code == 401

    def test_wrong_key_401(self, probe_client, auth_on):
        resp = probe_client.get("/probe", headers={"X-API-Key": "wrong-key"})
        assert resp.status_code == 401

    def test_correct_key_200(self, probe_client, auth_on):
        resp = probe_client.get("/probe", headers={"X-API-Key": _TEST_KEY})
        assert resp.status_code == 200


class TestRouteLevelGates:
    """The real /v1/wallets and /v1/rpc routes run the real auth dependency."""

    @pytest.fixture
    def rest_client(self, auth_on):
        from wallet_app.api_rest import router as rest_router

        keystore = MagicMock()
        keystore.list_records.return_value = []
        app = FastAPI()
        app.include_router(rest_router, prefix="/v1")
        app.dependency_overrides[get_keystore] = lambda: keystore
        app.dependency_overrides[get_ledger] = lambda: MagicMock()
        app.dependency_overrides[get_receipt_service] = lambda: MagicMock()
        return TestClient(app)

    def test_wallets_list_401_without_key(self, rest_client):
        assert rest_client.get("/v1/wallets").status_code == 401

    def test_wallets_list_200_with_key(self, rest_client):
        resp = rest_client.get("/v1/wallets", headers={"X-API-Key": _TEST_KEY})
        assert resp.status_code == 200

    @pytest.fixture
    def rpc_client(self, auth_on):
        from wallet_app.api_jsonrpc import router as rpc_router

        app = FastAPI()
        app.include_router(rpc_router, prefix="/v1")
        app.dependency_overrides[get_keystore] = lambda: MagicMock()
        app.dependency_overrides[get_ledger] = lambda: MagicMock()
        app.dependency_overrides[get_receipt_service] = lambda: MagicMock()
        return TestClient(app)

    def test_jsonrpc_401_without_key(self, rpc_client):
        resp = rpc_client.post("/v1/rpc", json={"jsonrpc": "2.0", "id": 1, "method": "receipts.verify_latest"})
        assert resp.status_code == 401

    def test_jsonrpc_passes_auth_with_key(self, rpc_client):
        # Unknown method: auth passes, handler returns a JSON-RPC error payload.
        resp = rpc_client.post(
            "/v1/rpc",
            json={"jsonrpc": "2.0", "id": 1, "method": "no.such.method"},
            headers={"X-API-Key": _TEST_KEY},
        )
        assert resp.status_code == 200
        assert resp.json().get("error") is not None


class TestSettingsMapping:
    """The flip env names map onto the settings fields callers rely on."""

    def test_env_names_map(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setenv("WALLET_API_KEY", _TEST_KEY)
        monkeypatch.setenv("WALLET_AUTH_ENABLED", "true")
        s = Settings()
        assert s.api_key == _TEST_KEY
        assert s.auth_enabled is True

    def test_auth_enabled_defaults_true(self, monkeypatch: pytest.MonkeyPatch):
        """Fresh installs are secure by default; the fleet's false is an explicit env override."""
        monkeypatch.delenv("WALLET_AUTH_ENABLED", raising=False)
        s = Settings()
        assert s.auth_enabled is True
