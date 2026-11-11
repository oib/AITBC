"""Contract: every mutating coordinator-api route rejects unauthenticated callers.

``AuthMiddleware`` (route security matrix) is only installed when
``auth_enabled and not test_mode`` — which is why the shared ``app`` fixture
never exercises it: conftest sets ``TEST_MODE=true``. This module builds a
second app with the middleware enabled and sweeps every POST/PUT/DELETE/PATCH
route with no credentials.

Two layers are pinned:

* every mutating route that is not on the documented public-write list must
  answer 401 to a credentialess request;
* the set of mutating routes the matrix resolves to ``AuthLevel.NONE`` must
  equal ``PUBLIC_WRITE_ROUTES`` exactly — a new accidental public write fails
  here instead of shipping silently.

Coder: B
"""

from __future__ import annotations

import re

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from coordinator_api.main import app

MUTATING_METHODS = frozenset({"POST", "PUT", "DELETE", "PATCH"})

# Mutating routes that are intentionally reachable without credentials.
# Each entry is a route *template* exactly as registered (path_format).
PUBLIC_WRITE_ROUTES: dict[str, str] = {
    "/v1/register": "account registration — the caller has no credential yet",
    "/v1/login": "credential exchange — the caller has no credential yet",
    "/v1/auth/nonce": "login nonce issuance, prerequisite for /v1/login",
}


def _mutating_routes(fastapi_app: FastAPI) -> list[tuple[str, list[str]]]:
    """(route template, mutating methods) for every mutating APIRoute."""
    routes: list[tuple[str, list[str]]] = []
    for route in fastapi_app.routes:
        methods = getattr(route, "methods", None)
        if not methods:
            continue
        mutating = sorted(methods & MUTATING_METHODS)
        if not mutating:
            continue
        path = getattr(route, "path_format", None) or getattr(route, "path", None)
        if path:
            routes.append((path, mutating))
    return routes


def _concrete(path_template: str) -> str:
    """Replace path params so the URL matches the route shape."""
    return re.sub(r"\{[^}]+\}", "0", path_template)


@pytest.fixture(scope="module")
def auth_client() -> TestClient:
    """TestClient on a coordinator-api app built with AuthMiddleware enabled.

    The shared ``app`` is constructed under ``TEST_MODE=true`` so the matrix
    middleware is never installed; this fixture flips the two settings flags
    for the duration of one ``create_app()`` call and restores them after.
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


_ALL_MUTATING = _mutating_routes(app)


def _cases() -> list[tuple[str, str]]:
    """(method, concrete path) pairs, public writes excluded."""
    cases: list[tuple[str, str]] = []
    for template, methods in _ALL_MUTATING:
        if template in PUBLIC_WRITE_ROUTES:
            continue
        for method in methods:
            cases.append((method, _concrete(template)))
    return cases


_MUTATING_CASES = _cases()


def test_route_enumeration_is_nonempty() -> None:
    """Guard against a silent empty sweep (e.g. route table refactor)."""
    assert len(_ALL_MUTATING) >= 100, f"only {len(_ALL_MUTATING)} mutating routes found"
    assert len(_MUTATING_CASES) >= 200


@pytest.mark.parametrize(("method", "path"), _MUTATING_CASES)
def test_gated_mutating_route_rejects_unauthenticated(auth_client: TestClient, method: str, path: str) -> None:
    """No credentials -> 401, for every mutating route off the public list."""
    response = auth_client.request(method, path, json={})
    assert response.status_code == 401, (
        f"{method} {path} answered {response.status_code} without credentials; "
        "either it needs a matrix entry/auth dep, or it belongs in PUBLIC_WRITE_ROUTES"
    )


@pytest.mark.parametrize("template", sorted(PUBLIC_WRITE_ROUTES), ids=lambda v: v)
def test_documented_public_write_is_reachable(auth_client: TestClient, template: str) -> None:
    """Intentional public writes must not be auth-gated (any non-401 proves it)."""
    methods = dict(_ALL_MUTATING).get(template)
    assert methods, f"{template} is whitelisted but no longer a registered route"
    for method in methods:
        if method not in MUTATING_METHODS:
            continue
        response = auth_client.request(method, _concrete(template), json={})
        assert response.status_code != 401, (
            f"{method} {template} is documented public but answered 401 — the matrix entry or a route dep is gating it"
        )


def test_public_write_set_matches_matrix_none() -> None:
    """The matrix-NONE mutating set must equal PUBLIC_WRITE_ROUTES exactly.

    A mutating route resolving to AuthLevel.NONE with no entry here is an
    accidental public write — fail loudly so it gets a deliberate decision
    (matrix entry, auth dep, or an added whitelist row with justification).
    """
    from aitbc.auth.security_matrix import AuthLevel, get_auth_level

    none_routes = {
        template
        for template, methods in _ALL_MUTATING
        if any(get_auth_level(_concrete(template), method) == AuthLevel.NONE for method in methods)
    }
    assert none_routes == set(PUBLIC_WRITE_ROUTES), (
        f"matrix-NONE mutating routes drifted: "
        f"unexpected={sorted(none_routes - set(PUBLIC_WRITE_ROUTES))} "
        f"stale={sorted(set(PUBLIC_WRITE_ROUTES) - none_routes)}"
    )
