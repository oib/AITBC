"""Merge-regression pin: JWT_ALGORITHM whitelist (#1585) on the
coordinator-api consumer path.

``aitbc/auth/jwt.py`` now validates ``JWT_ALGORITHM`` against a whitelist
(HMAC + the asymmetric PEM algs) and fails closed with
``ConfigurationError``. The unit pins in ``tests/coordinator/
test_jwt_handler.py`` cover the shared module; this file pins the *consumer*
side — the singleton ``coordinator_api.auth.jwt_auth`` and the
AuthMiddleware-protected routes actually refuse an ``alg=none`` forged
token and refuse to come up under a bad algorithm config.

Coder: C
"""

from __future__ import annotations

import base64
import json

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from aitbc.auth import jwt as jwt_module
from aitbc.auth.jwt import JWTAuth, get_jwt_auth
from aitbc.exceptions import ConfigurationError

SECRET = "test-secret-for-coordinator-tests" * 2


def _b64url(data: dict) -> str:
    raw = json.dumps(data, separators=(",", ":")).encode()
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode()


def _unsigned_token(payload: dict) -> str:
    """Hand-craft an ``alg=none`` JWT — the classic alg-confusion forgery."""
    header = {"alg": "none", "typ": "JWT"}
    return f"{_b64url(header)}.{_b64url(payload)}."


@pytest.fixture
def fresh_jwt_auth(monkeypatch):
    """Reset the process-wide JWTAuth singleton so env changes take effect."""
    monkeypatch.setattr(jwt_module, "_jwt_auth", None)
    yield
    monkeypatch.setattr(jwt_module, "_jwt_auth", None)


class TestJwtAlgorithmFailClosed:
    def test_algorithm_none_refused_at_first_use(self, monkeypatch, fresh_jwt_auth):
        """JWT_ALGORITHM=none must raise ConfigurationError when the
        coordinator-api auth singleton is (re)built — not mint unsigned
        tokens fleet-wide."""
        monkeypatch.setenv("JWT_ALGORITHM", "none")
        with pytest.raises(ConfigurationError, match="JWT_ALGORITHM"):
            get_jwt_auth()

    @pytest.mark.parametrize("alg", ["HS512-bogus", "", "RS512", "none"])
    def test_unknown_algorithm_refused(self, monkeypatch, fresh_jwt_auth, alg):
        monkeypatch.setenv("JWT_ALGORITHM", alg)
        with pytest.raises(ConfigurationError, match="JWT_ALGORITHM"):
            JWTAuth(secret=SECRET)

    def test_whitelisted_algorithm_still_works(self, monkeypatch, fresh_jwt_auth):
        monkeypatch.setenv("JWT_ALGORITHM", "hs384")
        auth = get_jwt_auth()
        assert auth.algorithm == "HS384"
        token = auth.create_token({"sub": "u1", "role": "client"})
        assert auth.decode_token(token)["sub"] == "u1"


class TestConsumerPathRejectsForgedAlg:
    """The decode path coordinator-api middleware actually calls."""

    def test_unsigned_none_token_rejected(self):
        auth = JWTAuth(secret=SECRET)
        forged = _unsigned_token({"sub": "attacker", "role": "admin", "type": "access"})
        with pytest.raises(HTTPException) as exc_info:
            auth.decode_token(forged)
        assert exc_info.value.status_code == 401

    def test_token_signed_under_other_algorithm_rejected(self, monkeypatch, fresh_jwt_auth):
        """A token minted while JWT_ALGORITHM=HS256 must not verify after the
        deployment is reconfigured to HS384 — the configured alg is pinned
        into decode, so there is no cross-alg acceptance."""
        monkeypatch.setenv("JWT_ALGORITHM", "HS256")
        token = get_jwt_auth().create_token({"sub": "u1", "role": "client"})

        monkeypatch.setenv("JWT_ALGORITHM", "HS384")
        monkeypatch.setattr(jwt_module, "_jwt_auth", None)
        with pytest.raises(HTTPException) as exc_info:
            get_jwt_auth().decode_token(token)
        assert exc_info.value.status_code == 401


@pytest.fixture(scope="module")
def auth_client() -> TestClient:
    """Auth-enabled app, same construction as test_authlevel_any_token_required."""
    from coordinator_api.config import settings
    from coordinator_api.main import create_app

    previous = (settings.test_mode, settings.auth_enabled)
    settings.test_mode = False
    settings.auth_enabled = True
    try:
        authed_app = create_app()
    finally:
        settings.test_mode, settings.auth_enabled = previous
    return TestClient(authed_app)


# /v1/developer-platform* resolves to AuthLevel.ADMIN_OR_CLIENT — a safe-method
# route behind the matrix, so it is a real consumer of the JWT decode path.
_HEALTH_PATH = "/v1/developer-platform/health"


def test_route_rejects_unsigned_none_token(auth_client: TestClient) -> None:
    forged = _unsigned_token({"sub": "attacker", "role": "admin", "type": "access"})
    response = auth_client.get(_HEALTH_PATH, headers={"Authorization": f"Bearer {forged}"})
    assert response.status_code == 401


def test_route_accepts_valid_client_token(auth_client: TestClient) -> None:
    from aitbc.auth import create_access_token

    token = create_access_token("jwt-pin-user", "client")
    response = auth_client.get(_HEALTH_PATH, headers={"Authorization": f"Bearer {token}"})
    assert response.status_code != 401
