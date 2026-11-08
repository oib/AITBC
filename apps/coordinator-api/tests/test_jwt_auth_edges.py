"""JWT verification edge cases through the coordinator-api auth surface (#1289).

The verify logic lives in the shared ``aitbc.auth`` package; coordinator-api
consumes it via ``coordinator_api.auth`` re-exports and the ``*Dep`` FastAPI
dependencies. These tests pin the branches that matter to this service after
#1185 (iss/aud claims minted) and #1288 (expiry enforcement): issuer/audience
binding, ``JWT_REQUIRE_EXP``, token-type confusion, and the dependency
surface (``verify_access_token``, ``require_admin_or_client``) that routers
consume via ``AdminDep``/``AuthDep``/``ClientDep``.
"""

from __future__ import annotations

import time
from typing import Any

import jwt
import pytest
from fastapi import HTTPException

import aitbc.auth.jwt as jwt_mod
from aitbc.auth import require_admin_or_client, verify_access_token
from aitbc.auth.jwt import JWTAuth

SECRET = "coordcover1289-edge-test-secret-" + "x" * 40


def _payload(**overrides: Any) -> dict[str, Any]:
    now = int(time.time())
    payload: dict[str, Any] = {
        "sub": "user-1",
        "user_id": "user-1",
        "role": "admin",
        "type": "access",
        "iat": now,
        "exp": now + 3600,
        "iss": "aitbc",
        "aud": "aitbc",
    }
    payload.update(overrides)
    return payload


def _mint(payload: dict[str, Any], secret: str = SECRET) -> str:
    return jwt.encode(payload, secret, algorithm="HS256")


@pytest.fixture
def auth() -> JWTAuth:
    """A JWTAuth bound to the test secret; env flags are read per call."""
    return JWTAuth(secret=SECRET)


@pytest.fixture
def fresh_singleton(monkeypatch: pytest.MonkeyPatch):
    """Reset the lazy ``get_jwt_auth()`` singleton so env changes apply."""
    monkeypatch.setenv("JWT_SECRET", SECRET)
    monkeypatch.setattr(jwt_mod, "_jwt_auth", None)
    yield
    monkeypatch.setattr(jwt_mod, "_jwt_auth", None)


class TestIssuerAudienceEnforcement:
    """JWT_ENFORCE_ISS_AUD / JWT_EXPECTED_ISSUER binding (#1185)."""

    def test_dormant_default_accepts_foreign_issuer(self, auth: JWTAuth, monkeypatch: pytest.MonkeyPatch) -> None:
        """Without the flag, iss/aud are minted but not enforced."""
        monkeypatch.delenv("JWT_ENFORCE_ISS_AUD", raising=False)
        token = _mint(_payload(iss="other-service", aud="other"))
        assert auth.decode_token(token)["iss"] == "other-service"

    def test_enforce_rejects_wrong_issuer(self, auth: JWTAuth, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("JWT_ENFORCE_ISS_AUD", "1")
        with pytest.raises(HTTPException) as exc:
            auth.decode_token(_mint(_payload(iss="agent-coordinator")))
        assert exc.value.status_code == 401

    def test_enforce_rejects_missing_issuer(self, auth: JWTAuth, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("JWT_ENFORCE_ISS_AUD", "1")
        payload = _payload()
        del payload["iss"]
        with pytest.raises(HTTPException) as exc:
            auth.decode_token(_mint(payload))
        assert exc.value.status_code == 401

    def test_enforce_rejects_wrong_and_missing_audience(self, auth: JWTAuth, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("JWT_ENFORCE_ISS_AUD", "1")
        for aud in ("other-audience", None):
            payload = _payload()
            if aud is None:
                del payload["aud"]
            else:
                payload["aud"] = aud
            with pytest.raises(HTTPException) as exc:
                auth.decode_token(_mint(payload))
            assert exc.value.status_code == 401

    def test_enforce_accepts_list_valued_audience(self, auth: JWTAuth, monkeypatch: pytest.MonkeyPatch) -> None:
        """jwt.py treats a list ``aud`` as any-of; ``aitbc`` member passes."""
        monkeypatch.setenv("JWT_ENFORCE_ISS_AUD", "1")
        token = _mint(_payload(aud=["other", "aitbc"]))
        assert auth.decode_token(token)["aud"] == ["other", "aitbc"]

    def test_expected_issuer_override(self, auth: JWTAuth, monkeypatch: pytest.MonkeyPatch) -> None:
        """JWT_EXPECTED_ISSUER decouples the required iss from the local mint."""
        monkeypatch.setenv("JWT_ENFORCE_ISS_AUD", "1")
        monkeypatch.setenv("JWT_EXPECTED_ISSUER", "svc-b")
        assert auth.decode_token(_mint(_payload(iss="svc-b")))["iss"] == "svc-b"
        with pytest.raises(HTTPException) as exc:
            auth.decode_token(_mint(_payload(iss="aitbc")))
        assert exc.value.status_code == 401


class TestExpiryAndTypeConfusion:
    """JWT_REQUIRE_EXP and the access/refresh ``type`` fail-closed checks."""

    def test_require_exp_rejects_exp_less_token(self, auth: JWTAuth, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("JWT_REQUIRE_EXP", "1")
        payload = _payload()
        del payload["exp"]
        with pytest.raises(HTTPException) as exc:
            auth.decode_token(_mint(payload))
        assert exc.value.status_code == 401

    def test_require_exp_accepts_token_with_exp(self, auth: JWTAuth, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("JWT_REQUIRE_EXP", "1")
        assert auth.decode_token(_mint(_payload()))["sub"] == "user-1"

    def test_exp_less_accepted_when_flag_off(self, auth: JWTAuth, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("JWT_REQUIRE_EXP", raising=False)
        payload = _payload()
        del payload["exp"]
        assert auth.decode_token(_mint(payload))["sub"] == "user-1"

    def test_expired_token_rejected(self, auth: JWTAuth) -> None:
        token = _mint(_payload(exp=int(time.time()) - 10))
        with pytest.raises(HTTPException) as exc:
            auth.decode_token(token)
        assert exc.value.status_code == 401

    def test_refresh_type_refused_as_access(self, auth: JWTAuth) -> None:
        """AUTH-JWT-TYPE-CONFUSION-1: a refresh token must not authenticate."""
        token = _mint(_payload(type="refresh"))
        with pytest.raises(HTTPException) as exc:
            auth.decode_token(token)
        assert exc.value.status_code == 401

    def test_missing_type_refused(self, auth: JWTAuth) -> None:
        payload = _payload()
        del payload["type"]
        with pytest.raises(HTTPException) as exc:
            auth.decode_token(_mint(payload))
        assert exc.value.status_code == 401

    def test_wrong_secret_rejected(self, auth: JWTAuth) -> None:
        token = _mint(_payload(), secret="a-different-secret-" + "y" * 40)
        with pytest.raises(HTTPException) as exc:
            auth.decode_token(token)
        assert exc.value.status_code == 401


class TestVerifyTokenRoleGate:
    def test_role_match_returns_payload(self, auth: JWTAuth) -> None:
        payload = auth.verify_token(_mint(_payload(role="admin")), required_role="admin")
        assert payload["sub"] == "user-1"

    def test_role_mismatch_is_403(self, auth: JWTAuth) -> None:
        with pytest.raises(HTTPException) as exc:
            auth.verify_token(_mint(_payload(role="client")), required_role="admin")
        assert exc.value.status_code == 403


class TestDependencySurface:
    """The ``aitbc.auth`` functions coordinator-api routers consume."""

    def test_verify_access_token_garbage_is_401(self, fresh_singleton: None) -> None:
        with pytest.raises(HTTPException) as exc:
            verify_access_token("not-a-jwt")
        assert exc.value.status_code == 401

    def test_verify_access_token_returns_payload(self, fresh_singleton: None) -> None:
        token = _mint(_payload(sub="dep-user", role="client"))
        payload = verify_access_token(token)
        assert payload["sub"] == "dep-user"

    def test_require_admin_or_client_accepts_admin_and_client(self, fresh_singleton: None) -> None:
        for role in ("admin", "client"):
            token = _mint(_payload(role=role))
            assert require_admin_or_client(token=token)["role"] == role

    def test_require_admin_or_client_rejects_miner(self, fresh_singleton: None) -> None:
        with pytest.raises(HTTPException) as exc:
            require_admin_or_client(token=_mint(_payload(role="miner")))
        assert exc.value.status_code == 403

    def test_require_admin_or_client_rejects_bad_token(self, fresh_singleton: None) -> None:
        with pytest.raises(HTTPException) as exc:
            require_admin_or_client(token="garbage")
        assert exc.value.status_code == 401
