"""Bearer-JWT branch of ``aitbc.auth.middleware`` + RateLimiter + deps (#1289 continuation).

``tests/security/test_auth_middleware.py`` pins the X-Api-Key fallback and the
miner-key contract. This file covers the other half of the same module — the
surface coordinator-api actually exercises after #1185/#1288:

- ``AuthMiddleware`` Bearer branch: ``verify_access_token`` result handling,
  role gate via the security matrix, request-state injection, and the
  HTTPException/ValueError -> 401/403 mappings.
- ``RateLimiter`` in-memory fallback: per-role caps, window eviction,
  ``remaining``/``reset_time`` accounting.
- ``get_current_user``: JWT and ApiKey schemes, missing-identity 401, and the
  429 rate-limit path.
- ``require_permissions`` / ``require_role`` decorators.
"""

from __future__ import annotations

import time
from collections import deque
from typing import Any
from unittest.mock import AsyncMock, Mock

import pytest
from fastapi import FastAPI, HTTPException, Request
from fastapi.security import HTTPAuthorizationCredentials
from fastapi.testclient import TestClient

import aitbc.auth.api_key as api_key_mod
import aitbc.auth.jwt as jwt_mod
import aitbc.auth.middleware as mw
from aitbc.auth.middleware import (
    AuthMiddleware,
    RateLimiter,
    get_current_user,
    require_permissions,
    require_role,
)


def _bearer(token: str = "tok") -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _make_app() -> FastAPI:
    app = FastAPI()
    app.add_middleware(AuthMiddleware)

    @app.get("/health")
    def health() -> dict[str, bool]:
        return {"ok": True}

    @app.get("/v1/admin/dashboard")
    def dashboard(request: Request) -> dict[str, Any]:
        return {
            "uid": request.state.user_id,
            "role": request.state.user_role,
            "sub": request.state.user.get("sub"),
        }

    return app


def _verify_returning(payload: dict[str, Any]):
    def _fake(token: str, required_role: str | None = None) -> dict[str, Any]:
        return payload

    return _fake


class TestAuthMiddlewareBearer:
    def test_valid_admin_token_reaches_route_and_injects_state(self, monkeypatch):
        monkeypatch.setattr(
            jwt_mod,
            "verify_access_token",
            _verify_returning({"sub": "admin-1", "user_id": "legacy-1", "role": "admin"}),
        )
        client = TestClient(_make_app())
        resp = client.get("/v1/admin/dashboard", headers=_bearer())
        assert resp.status_code == 200
        body = resp.json()
        assert body["uid"] == "admin-1"  # canonical sub wins over legacy user_id
        assert body["sub"] == "admin-1"
        assert body["role"] == "admin"

    def test_user_id_fallback_when_sub_absent(self, monkeypatch):
        monkeypatch.setattr(
            jwt_mod,
            "verify_access_token",
            _verify_returning({"user_id": "legacy-9", "role": "admin"}),
        )
        client = TestClient(_make_app())
        resp = client.get("/v1/admin/dashboard", headers=_bearer())
        assert resp.status_code == 200
        assert resp.json()["uid"] == "legacy-9"

    def test_wrong_role_gets_403(self, monkeypatch):
        monkeypatch.setattr(
            jwt_mod,
            "verify_access_token",
            _verify_returning({"sub": "c1", "role": "client"}),
        )
        client = TestClient(_make_app())
        resp = client.get("/v1/admin/dashboard", headers=_bearer())
        assert resp.status_code == 403
        assert resp.json() == {"detail": "Forbidden"}

    def test_verify_401_maps_to_invalid_token_401(self, monkeypatch):
        def _raise(token: str, required_role: str | None = None):
            raise HTTPException(status_code=401, detail="expired")

        monkeypatch.setattr(jwt_mod, "verify_access_token", _raise)
        client = TestClient(_make_app())
        resp = client.get("/v1/admin/dashboard", headers=_bearer())
        assert resp.status_code == 401
        assert resp.json() == {"detail": "Invalid token"}
        assert resp.headers["www-authenticate"] == "Bearer"

    def test_verify_403_maps_to_forbidden_403(self, monkeypatch):
        def _raise(token: str, required_role: str | None = None):
            raise HTTPException(status_code=403, detail="role")

        monkeypatch.setattr(jwt_mod, "verify_access_token", _raise)
        client = TestClient(_make_app())
        resp = client.get("/v1/admin/dashboard", headers=_bearer())
        assert resp.status_code == 403
        assert resp.json() == {"detail": "Forbidden"}

    def test_verify_value_error_maps_to_401(self, monkeypatch):
        def _raise(token: str, required_role: str | None = None):
            raise ValueError("bad token shape")

        monkeypatch.setattr(jwt_mod, "verify_access_token", _raise)
        client = TestClient(_make_app())
        resp = client.get("/v1/admin/dashboard", headers=_bearer())
        assert resp.status_code == 401
        assert resp.json() == {"detail": "Invalid token"}

    def test_unregistered_route_denies_even_valid_admin(self, monkeypatch):
        """CORE-03: paths absent from the matrix resolve to DENY — a valid
        admin token still gets 403, never silent access."""
        monkeypatch.setattr(
            jwt_mod,
            "verify_access_token",
            _verify_returning({"sub": "admin-1", "role": "admin"}),
        )
        client = TestClient(_make_app())
        resp = client.get("/v1/no-such-route", headers=_bearer())
        assert resp.status_code == 403

    def test_public_route_skips_verification_entirely(self, monkeypatch):
        called = False

        def _fake(token: str, required_role: str | None = None):
            nonlocal called
            called = True
            return {"sub": "x", "role": "admin"}

        monkeypatch.setattr(jwt_mod, "verify_access_token", _fake)
        client = TestClient(_make_app())
        resp = client.get("/health", headers=_bearer("garbage"))
        assert resp.status_code == 200
        assert called is False

    def test_non_bearer_authorization_falls_through_to_401(self):
        """A non-Bearer Authorization scheme is not a credential here; with no
        X-Api-Key the request ends at 'Authentication required'."""
        client = TestClient(_make_app())
        resp = client.get(
            "/v1/admin/dashboard",
            headers={"Authorization": "Basic dXNlcjpwYXNz"},
        )
        assert resp.status_code == 401
        assert resp.json() == {"detail": "Authentication required"}


class _MemoryRateLimiter:
    """Hermetic RateLimiter: force the in-memory fallback regardless of redis."""

    @staticmethod
    def make(**role_limits: dict[str, int]) -> RateLimiter:
        rl = RateLimiter(redis_url="redis://127.0.0.1:1/0")
        rl.redis_client = None
        if role_limits:
            rl.limits.update(role_limits)
        return rl


class TestRateLimiterMemoryFallback:
    async def test_allows_up_to_limit_then_denies(self):
        rl = _MemoryRateLimiter.make()
        rl.limits["default"] = {"requests": 3, "window": 3600}
        t0 = time.time()
        for _ in range(3):
            res = await rl.is_allowed("user-1")
            assert res["allowed"] is True
        res = await rl.is_allowed("user-1")
        assert res["allowed"] is False
        assert res["remaining"] == 0
        # reset_time is oldest request + window
        assert abs(res["reset_time"] - (t0 + 3600)) < 5

    async def test_remaining_counts_down(self):
        rl = _MemoryRateLimiter.make()
        rl.limits["default"] = {"requests": 3, "window": 3600}
        await rl.is_allowed("user-1")
        await rl.is_allowed("user-1")
        res = await rl.is_allowed("user-1")
        assert res["allowed"] is True
        assert res["remaining"] == 0

    async def test_window_eviction_readmits(self):
        rl = _MemoryRateLimiter.make()
        rl.limits["default"] = {"requests": 2, "window": 60}
        await rl.is_allowed("user-1")
        await rl.is_allowed("user-1")
        denied = await rl.is_allowed("user-1")
        assert denied["allowed"] is False
        # Age every recorded request past the window — next call must pass.
        rl.memory_requests["user-1"] = deque([time.time() - 61] * 2)
        res = await rl.is_allowed("user-1")
        assert res["allowed"] is True

    async def test_role_specific_limit_with_shared_bucket(self):
        """Limits are keyed by role but the request deque is keyed by user_id
        alone — pin that actual (shared-bucket) semantics."""
        rl = _MemoryRateLimiter.make(admin={"requests": 5, "window": 60})
        rl.limits["default"] = {"requests": 2, "window": 60}
        await rl.is_allowed("user-1", "default")
        await rl.is_allowed("user-1", "default")
        denied = await rl.is_allowed("user-1", "default")
        assert denied["allowed"] is False
        # Same user under the admin role shares the deque (len=2) but gets the
        # higher cap — allowed, and the count keeps accumulating.
        res = await rl.is_allowed("user-1", "admin")
        assert res["allowed"] is True

    async def test_unknown_role_falls_back_to_default_limit(self):
        rl = _MemoryRateLimiter.make()
        rl.limits["default"] = {"requests": 1, "window": 60}
        rl.limits["admin"] = {"requests": 100, "window": 60}
        await rl.is_allowed("user-1", "nonexistent-role")
        denied = await rl.is_allowed("user-1", "nonexistent-role")
        assert denied["allowed"] is False


def _creds(scheme: str, token: str) -> HTTPAuthorizationCredentials:
    return HTTPAuthorizationCredentials(scheme=scheme, credentials=token)


class _FakeJWTHandler:
    def __init__(self, result: dict[str, Any]) -> None:
        self._result = result
        self.seen: list[str] = []

    def validate_token(self, token: str, expected_type: str | None = "access") -> dict[str, Any]:
        self.seen.append(token)
        return self._result


class TestGetCurrentUser:
    async def test_bearer_jwt_returns_user_dict(self, monkeypatch):
        handler = _FakeJWTHandler(
            {
                "valid": True,
                "payload": {
                    "sub": "u-1",
                    "user_id": "u-1",
                    "username": "alice",
                    "role": "admin",
                    "permissions": ["read", "write"],
                },
            }
        )
        monkeypatch.setattr(mw, "get_jwt_handler", lambda: handler)
        allowed = AsyncMock(return_value={"allowed": True, "remaining": 9, "reset_time": time.time() + 60})
        monkeypatch.setattr(mw.rate_limiter, "is_allowed", allowed)

        user = await get_current_user(_creds("Bearer", "tok-1"))
        assert user["auth_type"] == "jwt"
        assert user["sub"] == "u-1"
        assert user["user_id"] == "u-1"
        assert user["username"] == "alice"
        assert user["role"] == "admin"
        assert user["permissions"] == ["read", "write"]
        allowed.assert_awaited_once_with("u-1", "admin")

    async def test_jwt_payload_without_identity_401(self, monkeypatch):
        handler = _FakeJWTHandler({"valid": True, "payload": {"role": "admin"}})
        monkeypatch.setattr(mw, "get_jwt_handler", lambda: handler)
        with pytest.raises(HTTPException) as exc:
            await get_current_user(_creds("Bearer", "tok"))
        assert exc.value.status_code == 401

    async def test_invalid_jwt_falls_through_to_401(self, monkeypatch):
        handler = _FakeJWTHandler({"valid": False, "message": "Invalid token"})
        monkeypatch.setattr(mw, "get_jwt_handler", lambda: handler)
        with pytest.raises(HTTPException) as exc:
            await get_current_user(_creds("Bearer", "bad"))
        assert exc.value.status_code == 401
        assert exc.value.detail == "Authentication required"

    async def test_apikey_scheme_returns_api_user(self, monkeypatch):
        manager = Mock()
        manager.validate_api_key = Mock(return_value={"valid": True, "user_id": "key-user-1", "permissions": ["api:read"]})
        monkeypatch.setattr(api_key_mod, "get_api_key_manager", lambda: manager)
        allowed = AsyncMock(return_value={"allowed": True, "remaining": 9, "reset_time": time.time() + 60})
        monkeypatch.setattr(mw.rate_limiter, "is_allowed", allowed)

        user = await get_current_user(_creds("ApiKey", "sekret"))
        assert user["auth_type"] == "api_key"
        assert user["sub"] == "key-user-1"
        assert user["role"] == "api"
        assert user["permissions"] == ["api:read"]
        assert user["username"] == "api_user_key-user-1"
        allowed.assert_awaited_once_with("key-user-1", "api_key")

    async def test_invalid_apikey_401(self, monkeypatch):
        manager = Mock()
        manager.validate_api_key = Mock(return_value={"valid": False})
        monkeypatch.setattr(api_key_mod, "get_api_key_manager", lambda: manager)
        with pytest.raises(HTTPException) as exc:
            await get_current_user(_creds("ApiKey", "wrong"))
        assert exc.value.status_code == 401

    async def test_rate_limited_jwt_gets_429_with_retry_after(self, monkeypatch):
        handler = _FakeJWTHandler({"valid": True, "payload": {"sub": "u-1", "role": "default"}})
        monkeypatch.setattr(mw, "get_jwt_handler", lambda: handler)
        monkeypatch.setattr(
            mw.rate_limiter,
            "is_allowed",
            AsyncMock(return_value={"allowed": False, "remaining": 0, "reset_time": time.time() + 42}),
        )
        with pytest.raises(HTTPException) as exc:
            await get_current_user(_creds("Bearer", "tok"))
        assert exc.value.status_code == 429
        assert exc.value.detail == "Rate limit exceeded"
        assert 40 <= int(exc.value.headers["Retry-After"]) <= 43

    async def test_rate_limited_apikey_gets_429(self, monkeypatch):
        manager = Mock()
        manager.validate_api_key = Mock(return_value={"valid": True, "user_id": "k1", "permissions": []})
        monkeypatch.setattr(api_key_mod, "get_api_key_manager", lambda: manager)
        monkeypatch.setattr(
            mw.rate_limiter,
            "is_allowed",
            AsyncMock(return_value={"allowed": False, "remaining": 0, "reset_time": time.time() + 10}),
        )
        with pytest.raises(HTTPException) as exc:
            await get_current_user(_creds("ApiKey", "k"))
        assert exc.value.status_code == 429

    async def test_no_credentials_401(self):
        with pytest.raises(HTTPException) as exc:
            await get_current_user(None)
        assert exc.value.status_code == 401
        assert exc.value.detail == "Authentication required"


class TestPermissionRoleDecorators:
    async def test_require_permissions_missing_user_401(self):
        @require_permissions(["read"])
        async def view(*, current_user: dict | None = None):
            return "ok"

        with pytest.raises(HTTPException) as exc:
            await view()
        assert exc.value.status_code == 401

    async def test_require_permissions_missing_perms_403(self):
        @require_permissions(["read", "admin"])
        async def view(*, current_user: dict | None = None):
            return "ok"

        with pytest.raises(HTTPException) as exc:
            await view(current_user={"permissions": ["read"]})
        assert exc.value.status_code == 403
        assert exc.value.detail["missing_permissions"] == ["admin"]

    async def test_require_permissions_all_present_calls_through(self):
        @require_permissions(["read"])
        async def view(*, current_user: dict | None = None):
            return "done"

        assert await view(current_user={"permissions": ["read", "write"]}) == "done"

    async def test_require_role_wrong_role_403(self):
        @require_role(["admin"])
        async def view(*, current_user: dict | None = None):
            return "ok"

        with pytest.raises(HTTPException) as exc:
            await view(current_user={"role": "client"})
        assert exc.value.status_code == 403
        assert exc.value.detail["current_role"] == "client"
        assert exc.value.detail["required_roles"] == ["admin"]

    async def test_require_role_enum_and_nonstring_normalized(self):
        class _Role:
            value = "admin"

        @require_role([_Role()])
        async def view(*, current_user: dict | None = None):
            return "ok"

        # current_user role as an enum-like object is normalized via .value
        assert await view(current_user={"role": _Role()}) == "ok"

    async def test_require_role_missing_user_401(self):
        @require_role(["admin"])
        async def view(*, current_user: dict | None = None):
            return "ok"

        with pytest.raises(HTTPException) as exc:
            await view(current_user=None)
        assert exc.value.status_code == 401
