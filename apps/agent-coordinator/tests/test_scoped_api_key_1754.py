"""#1754: scoped API keys must actually authenticate.

``HTTPBearer`` only parses the ``Bearer`` scheme, so ``Authorization:
ApiKey <key>`` yielded ``credentials=None`` → 401 and the
``APIKeyManager`` permission machinery was unreachable. These tests pin:

* the credential parser accepts ``ApiKey`` (and ``Bearer`` still works);
* ``get_current_user`` resolves a generated scoped key with its permissions;
* ``resolve_request_principal`` maps it to a non-admin, namespaced principal.
"""

from __future__ import annotations

import os
from typing import Annotated, Any

import pytest

os.environ.setdefault("SECRET_KEY", "test-secret-key")
os.environ.setdefault("JWT_SECRET", "test-secret-for-agent-coordinator-tests" * 2)

pytest.importorskip("fastapi", reason="agent-coordinator app dependencies not installed")

from fastapi import Depends, FastAPI  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from starlette.requests import Request  # noqa: E402

from aitbc.auth import api_key_manager, get_current_user  # noqa: E402
from aitbc.auth.middleware import security  # noqa: E402

from agent_app.services import agent_auth as agent_auth_svc  # noqa: E402


@pytest.fixture
def scoped_key() -> str:
    result = api_key_manager.generate_api_key("scoped-user-1", ["tasks:read", "media:write"])
    assert result["status"] == "success"
    return result["api_key"]


def _request_with_headers(headers: dict[str, str]) -> Request:
    scope = {
        "type": "http",
        "method": "GET",
        "path": "/",
        "headers": [(k.lower().encode(), v.encode()) for k, v in headers.items()],
        "query_string": b"",
    }
    return Request(scope)


class TestCredentialParser:
    async def test_apikey_scheme_parsed(self) -> None:
        request = _request_with_headers({"Authorization": "ApiKey abc123"})
        credentials = await security(request)
        assert credentials is not None
        assert credentials.scheme == "ApiKey"
        assert credentials.credentials == "abc123"

    async def test_bearer_scheme_still_parsed(self) -> None:
        request = _request_with_headers({"Authorization": "Bearer tok"})
        credentials = await security(request)
        assert credentials is not None
        assert credentials.scheme == "Bearer"
        assert credentials.credentials == "tok"

    async def test_other_scheme_yields_none(self) -> None:
        request = _request_with_headers({"Authorization": "Basic dXNlcjpwYXNz"})
        assert await security(request) is None


class TestGetCurrentUser:
    async def test_scoped_key_resolves_with_permissions(self, scoped_key: str) -> None:
        request = _request_with_headers({"Authorization": f"ApiKey {scoped_key}"})
        # Drive the dependency the way FastAPI would.
        credentials = await security(request)
        user = await get_current_user(credentials)  # type: ignore[arg-type]
        assert user["user_id"] == "scoped-user-1"
        assert user["auth_type"] == "api_key"
        assert user["permissions"] == ["tasks:read", "media:write"]

    async def test_invalid_scoped_key_401(self) -> None:
        request = _request_with_headers({"Authorization": "ApiKey not-a-real-key"})
        credentials = await security(request)
        from fastapi import HTTPException

        with pytest.raises(HTTPException) as exc:
            await get_current_user(credentials)  # type: ignore[arg-type]
        assert exc.value.status_code == 401

    def test_http_roundtrip(self, scoped_key: str) -> None:
        app = FastAPI()

        @app.get("/whoami")
        async def whoami(current_user: Annotated[dict[str, Any], Depends(get_current_user)]) -> dict[str, Any]:
            return current_user

        client = TestClient(app)
        resp = client.get("/whoami", headers={"Authorization": f"ApiKey {scoped_key}"})
        assert resp.status_code == 200
        assert resp.json()["user_id"] == "scoped-user-1"
        assert resp.json()["permissions"] == ["tasks:read", "media:write"]


class TestResolveRequestPrincipal:
    async def test_scoped_key_resolves_to_non_admin_principal(self, scoped_key: str) -> None:
        request = _request_with_headers({"Authorization": f"ApiKey {scoped_key}"})
        principal = await agent_auth_svc.resolve_request_principal(request)
        assert principal is not None
        assert principal.auth_type == "scoped_api_key"
        assert principal.is_admin is False
        assert principal.agent_id == "apikey:scoped-user-1"
        assert principal.permissions == ("tasks:read", "media:write")

    async def test_invalid_scoped_key_yields_no_principal(self) -> None:
        request = _request_with_headers({"Authorization": "ApiKey bogus"})
        assert await agent_auth_svc.resolve_request_principal(request) is None

    async def test_require_agent_accepts_scoped_key(self, scoped_key: str) -> None:
        request = _request_with_headers({"Authorization": f"ApiKey {scoped_key}"})
        principal = await agent_auth_svc.require_agent(request)
        assert principal.agent_id == "apikey:scoped-user-1"

    def test_scoped_key_never_admin(self, scoped_key: str, monkeypatch) -> None:
        # Admin-gated endpoints must keep rejecting scoped keys even when the
        # key's permission list is broad — under enforce a non-admin principal
        # gets 403.
        import asyncio

        from fastapi import HTTPException

        from agent_app.config import settings

        request = _request_with_headers({"Authorization": f"ApiKey {scoped_key}"})
        principal = asyncio.run(agent_auth_svc.resolve_request_principal(request))
        assert principal is not None
        monkeypatch.setattr(settings, "agent_msg_signature_mode", "enforce")
        with pytest.raises(HTTPException) as exc:
            agent_auth_svc.authorize_admin_scope(principal, "test")
        assert exc.value.status_code == 403
