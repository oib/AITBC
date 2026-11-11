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
    """Matrix pin: aggregate-read + signature-gated /v1/ipfs routes stay AuthLevel.ANY.

    IPFS-API-AUTHZ-1 (#1686) moved the mutating memory/pin routes to
    ADMIN_OR_CLIENT; IPFS-AUTHZ-RESIDUAL-1 (#1766) moved the CID-disclosing
    reads (``retrieve``, ``list/{agent_id}``) there too — both asserted
    separately below. What remains at ANY is operational (``stats``,
    ``health``) plus the island swarm-key routes, which carry their own
    signature/subscription checks.
    """
    for path in (
        "/v1/ipfs/stats",
        "/v1/ipfs/health",
        "/v1/ipfs/island/swarm-key",
        "/v1/ipfs/island/swarm-key/nonce",
    ):
        assert get_auth_level(path) is AuthLevel.ANY, f"{path} resolved to {get_auth_level(path)}"


def test_ipfs_cid_disclosing_reads_require_admin_or_client() -> None:
    """IPFS-AUTHZ-RESIDUAL-1 (#1766): retrieve + per-agent list are not ANY-role.

    ``retrieve`` pulls arbitrary CIDs through the shared Kubo node and
    ``list/{agent_id}`` enumerates another agent's memory CIDs — under ANY
    every authenticated role (incl. miner) could do both.
    """
    for path in (
        "/v1/ipfs/upload",
        "/v1/ipfs/batch-upload",
        "/v1/ipfs/create-deal",
        "/v1/ipfs/delete",
        "/v1/ipfs/retrieve",
        "/v1/ipfs/list/some-agent",
    ):
        assert get_auth_level(path) is AuthLevel.ADMIN_OR_CLIENT, f"{path} resolved to {get_auth_level(path)}"
        assert get_auth_level(path, "POST") is AuthLevel.ADMIN_OR_CLIENT


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


def test_ipfs_cid_reads_reject_miner_role(auth_client: TestClient) -> None:
    """#1766: a valid miner-role token must not reach retrieve/list.

    Before the gate these resolved to AuthLevel.ANY — any role passed. The
    client-role request below proves the gate admits the intended roles
    (it fails later on request validation, not authorization).
    """
    from aitbc.auth.jwt import create_access_token

    miner_headers = {"Authorization": f"Bearer {create_access_token('miner-1', 'miner')}"}
    assert auth_client.post("/v1/ipfs/retrieve", json={"cid": "bafy"}, headers=miner_headers).status_code == 403
    assert auth_client.get("/v1/ipfs/list/some-agent", headers=miner_headers).status_code == 403

    client_headers = {"Authorization": f"Bearer {create_access_token('client-1', 'client')}"}
    # cid is intentionally invalid/absent downstream — we only assert the
    # request cleared authorization (not 401/403).
    assert auth_client.post("/v1/ipfs/retrieve", json={}, headers=client_headers).status_code == 422
