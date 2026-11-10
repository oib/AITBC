"""Pin: AuthLevel.ANY routes actually enforce token presence.

The route security matrix resolves ``/v1/ipfs*`` to ``AuthLevel.ANY`` —
"any valid JWT". The mutating-route contract sweep
(``test_mutating_route_auth_contract.py``) only walks POST/PUT/DELETE/PATCH,
so the safe-method routes under ANY-level prefixes (``GET /v1/ipfs/stats``,
``GET /v1/ipfs/list/{agent_id}``, ``GET /v1/ipfs/health``) had no credential
pin: a middleware regression that stopped gating GETs would have shipped
silently.

This module builds the same auth-enabled app fixture and hits representative
/v1/ipfs routes with no credentials, asserting 401 — plus a matrix-level
assertion so the pin fails loudly if the prefix is ever downgraded to NONE
(which would make the 401 expectation itself wrong).

Coder: C
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from aitbc.auth.security_matrix import AuthLevel, get_auth_level


@pytest.fixture(scope="module")
def auth_client() -> TestClient:
    """TestClient on a coordinator-api app built with AuthMiddleware enabled.

    Same construction as ``test_mutating_route_auth_contract.py``: the shared
    ``app`` fixture runs under ``TEST_MODE=true`` so the matrix middleware is
    never installed; flip the two settings flags for one ``create_app()``.
    """
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


def test_ipfs_prefix_resolves_to_any() -> None:
    """Matrix pin: /v1/ipfs* must stay AuthLevel.ANY, not NONE or DENY."""
    for path in (
        "/v1/ipfs/stats",
        "/v1/ipfs/health",
        "/v1/ipfs/list/some-agent",
        "/v1/ipfs/upload",
        "/v1/ipfs/island/swarm-key",
    ):
        assert get_auth_level(path) is AuthLevel.ANY, f"{path} resolved to {get_auth_level(path)}"


@pytest.mark.parametrize(
    ("method", "path"),
    [
        ("GET", "/v1/ipfs/stats"),
        ("GET", "/v1/ipfs/health"),
        ("GET", "/v1/ipfs/list/some-agent"),
        ("POST", "/v1/ipfs/upload"),
        ("POST", "/v1/ipfs/retrieve"),
        ("POST", "/v1/ipfs/island/swarm-key"),
    ],
)
def test_ipfs_route_rejects_missing_credentials(auth_client: TestClient, method: str, path: str) -> None:
    """No Authorization header -> 401 on every /v1/ipfs route shape."""
    response = auth_client.request(method, path, json={})
    assert response.status_code == 401, (
        f"{method} {path} answered {response.status_code} without credentials; "
        "AuthLevel.ANY must require a token on safe methods too"
    )


def test_ipfs_route_rejects_garbage_token(auth_client: TestClient) -> None:
    """A malformed bearer token is not 'any valid JWT' -> still 401."""
    response = auth_client.get("/v1/ipfs/stats", headers={"Authorization": "Bearer not-a-jwt"})
    assert response.status_code == 401
