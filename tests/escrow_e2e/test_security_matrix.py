"""ESCROW-E2E-TEST-1 group 3: the security matrix guards the escrow routes.

The D2/CORE-03 regression was a relay route that had no matrix entry: the
middleware denied it by default with a bare ``{"detail": "Forbidden"}`` 403
to every caller, including valid clients. The coordinator unit suite runs
with ``TEST_MODE=true`` and never loads ``AuthMiddleware`` — this suite
runs the real app with the real middleware, so the checks here go through
the actual gate, not a static table lookup.
"""

from __future__ import annotations

import pytest

from aitbc.auth.security_matrix import ROUTE_SECURITY_MATRIX, AuthLevel, get_auth_level
from coordinator_api.main import app

from conftest import auth_header


def _escrow_routes() -> list[tuple[str, str]]:
    routes: list[tuple[str, str]] = []
    for route in app.routes:
        path = getattr(route, "path", "")
        if not path.startswith("/v1/escrow"):
            continue
        for method in (getattr(route, "methods", set()) or set()) - {"HEAD", "OPTIONS"}:
            routes.append((method, path))
    return sorted(routes)


class TestEscrowRoutesHaveMatrixEntries:
    def test_every_escrow_route_resolves_to_a_non_deny_level(self):
        """Static leg: no /v1/escrow/* route may resolve to DENY."""
        assert _escrow_routes(), "no /v1/escrow routes registered on the app"
        for method, path in _escrow_routes():
            level = get_auth_level(path, method)
            assert level is not AuthLevel.DENY, f"{method} {path} falls to deny-by-default"

    @pytest.mark.parametrize(("method", "path"), _escrow_routes())
    def test_escrow_route_passes_the_middleware_with_a_valid_token(self, wired, method, path):
        """Live leg: a valid client JWT gets past AuthMiddleware on every
        registered escrow route — a missing matrix entry would 403 here.

        The request body is deliberately empty: the middleware must let the
        call through to the route, which then answers with its own
        validation error (4xx/422) — anything but the bare middleware 403.
        """
        resp = wired.client.request(method, path, json={}, headers=auth_header("client-1"))
        assert not (resp.status_code == 403 and resp.json().get("detail") == "Forbidden"), (
            f"{method} {path} was denied by the middleware — missing ROUTE_SECURITY_MATRIX entry"
        )


class TestUnregisteredPathsAreDenied:
    def test_unregistered_escrow_path_gets_the_middleware_403(self, wired):
        """An escrow path with no matrix entry must 403 even with a valid JWT."""
        assert get_auth_level("/v1/escrow/definitely-not-a-route", "POST") is AuthLevel.DENY
        resp = wired.client.post("/v1/escrow/definitely-not-a-route", json={}, headers=auth_header("client-1"))
        assert resp.status_code == 403
        assert resp.json() == {"detail": "Forbidden"}

    def test_unauthenticated_request_to_a_gated_route_is_401(self, wired):
        """A registered route with no token is refused by the middleware itself."""
        resp = wired.client.post("/v1/escrow/relay", json={})
        assert resp.status_code == 401
        assert resp.json() == {"detail": "Authentication required"}

    def test_wrong_role_on_an_escrow_route_is_middleware_403(self, wired):
        """A miner token is authenticated but role-mismatched → bare 403."""
        resp = wired.client.post("/v1/escrow/relay", json={}, headers=auth_header("miner-1", role="miner"))
        assert resp.status_code == 403
        assert resp.json() == {"detail": "Forbidden"}

    def test_escrow_routes_registered_in_the_committed_matrix(self):
        """The two relay routes must exist as exact entries, not luck."""
        assert ROUTE_SECURITY_MATRIX.get("/v1/escrow/relay") is AuthLevel.ADMIN_OR_CLIENT
        assert ROUTE_SECURITY_MATRIX.get("/v1/escrow/release") is AuthLevel.ADMIN_OR_CLIENT
