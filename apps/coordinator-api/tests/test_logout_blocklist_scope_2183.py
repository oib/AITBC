"""#2183 — AuthMiddleware must honour the logout blocklist on every authenticated route.

``POST /v1/logout`` revoked the JWT in the shared sqlite blocklist, but only the three
users-router endpoints consulted it; the global ``AuthMiddleware`` verified signature and
expiry only, so every other authenticated route accepted a logged-out token until JWT
expiry. The middleware now asks a registered revocation check (coordinator-api wires the
sqlite blocklist); with none registered it behaves exactly as before.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from aitbc.auth import create_access_token
from aitbc.auth import middleware as auth_middleware

# A non-users route that is authenticated (AuthLevel.ANY) and needs no DB state.
PATH = "/v1/ipfs/stats"


@pytest.fixture(scope="module")
def auth_client() -> TestClient:
    """coordinator-api app built with AuthMiddleware on (same recipe as test_authlevel_any_token_required)."""
    from coordinator_api.config import settings
    from coordinator_api.main import create_app

    previous = (settings.test_mode, settings.auth_enabled)
    settings.test_mode = False
    settings.auth_enabled = True
    try:
        app = create_app()
    finally:
        settings.test_mode, settings.auth_enabled = previous
    return TestClient(app)


@pytest.fixture(autouse=True)
def _restore_hook():
    previous = auth_middleware._token_revocation_check
    yield
    auth_middleware.set_token_revocation_check(previous)


def _get(client: TestClient, token: str):
    return client.get(PATH, headers={"Authorization": f"Bearer {token}"})


def test_route_is_authenticated_not_public() -> None:
    from aitbc.auth.security_matrix import AuthLevel, get_auth_level

    assert get_auth_level(PATH) is not AuthLevel.NONE


def test_revoked_token_is_rejected_on_a_non_users_route(auth_client: TestClient) -> None:
    from coordinator_api.contexts.infrastructure.routers.users import _revoke_token

    live = create_access_token("user-live", "client")
    gone = create_access_token("user-gone", "client")
    _revoke_token(gone)

    denied = _get(auth_client, gone)
    assert denied.status_code == 401
    assert denied.headers.get("www-authenticate") == "Bearer"
    # an unrevoked token still gets through the middleware (whatever the route then does)
    assert _get(auth_client, live).status_code not in (401, 403)


def test_create_app_registers_the_blocklist() -> None:
    from coordinator_api.contexts.infrastructure.routers.users import _is_token_revoked

    assert auth_middleware._token_revocation_check is _is_token_revoked


def test_without_a_registered_check_behaviour_is_unchanged(auth_client: TestClient) -> None:
    """Dormant path: no store wired (other services) -> a valid token is never rejected for revocation."""
    from coordinator_api.contexts.infrastructure.routers.users import _revoke_token

    token = create_access_token("user-dormant", "client")
    _revoke_token(token)
    auth_middleware.set_token_revocation_check(None)
    assert _get(auth_client, token).status_code not in (401, 403)


def test_failing_store_fails_closed(auth_client: TestClient, caplog: pytest.LogCaptureFixture) -> None:
    def broken(_token: str) -> bool:
        raise OSError("auth db unavailable")

    auth_middleware.set_token_revocation_check(broken)
    token = create_access_token("user-broken", "client")
    assert _get(auth_client, token).status_code == 401
    assert "revocation store unavailable" in caplog.text


def test_invalid_signature_is_still_rejected_before_the_store(auth_client: TestClient) -> None:
    calls: list[str] = []

    def spy(token: str) -> bool:
        calls.append(token)
        return False

    auth_middleware.set_token_revocation_check(spy)
    assert _get(auth_client, "not.a.jwt").status_code == 401
    assert calls == []


def test_logout_endpoint_end_to_end_revokes_other_routes(auth_client: TestClient) -> None:
    """The real POST /v1/logout path: revoke via the endpoint, reject on a non-users route."""
    token = create_access_token("user-e2e", "client")
    assert _get(auth_client, token).status_code not in (401, 403)
    out = auth_client.post(f"/v1/logout?token={token}", headers={"Authorization": f"Bearer {token}"})
    assert out.status_code == 200
    assert _get(auth_client, token).status_code == 401
