"""Tests for the route security matrix (D2).

``get_auth_level`` tries an exact match and then ``fnmatch``. ``fnmatch`` does not
treat ``/v1/payments/*`` as covering ``/v1/payments``, so a collection endpoint
whose only matrix entry is the wildcard falls through to the CORE-03
deny-by-default and answers 403 to every caller, correct role included.

That is what had happened to ``POST /v1/payments`` -- the one endpoint that
accepts a buyer-signed ESCROW_LOCK. With it unreachable no priced job on the
deployment could reach ``payment_status="escrowed"``, which left the provider
binding (G2) and the acceptance window (G3) downstream of a gate nothing could
pass.
"""

from __future__ import annotations

import fnmatch
import json
from pathlib import Path

from aitbc.auth.security_matrix import ROUTE_SECURITY_MATRIX, AuthLevel, check_role_match, get_auth_level

from coordinator_api.main import app


def test_a_wildcard_entry_does_not_cover_its_own_collection_path():
    """Pin the fnmatch behaviour the bug turned on, so the pairs are not 'simplified'."""
    assert not fnmatch.fnmatch("/v1/payments", "/v1/payments/*")
    assert fnmatch.fnmatch("/v1/payments/send", "/v1/payments/*")


def test_creating_a_payment_is_reachable_by_a_client():
    """POST /v1/payments is how a client supplies the escrow lock; it must not be denied."""
    level = get_auth_level("/v1/payments")

    assert level is AuthLevel.ADMIN_OR_CLIENT
    assert check_role_match(level, "client")
    assert check_role_match(level, "admin")


def test_every_registered_collection_path_is_registered_in_the_matrix():
    """A published route must not be reachable only through a wildcard sibling.

    This generalises the ``/v1/payments`` case: for every ``.../*`` pattern in the
    matrix, if the app also serves the bare prefix as a real, published route,
    that prefix needs its own entry or it is 403 to everyone.

    The check is scoped to routes that appear in the committed OpenAPI spec so
    that debug-only routes (which the spec deliberately omits) do not pollute
    the production matrix assertion when ``DEBUG=true`` is set by another suite.
    """
    spec = json.loads((Path(__file__).resolve().parents[3] / "docs" / "api" / "coordinator-api-openapi.json").read_text())
    published = set(spec.get("paths", {}))

    served = {
        route.path
        for route in app.routes
        if getattr(route, "path", "").startswith("/v1")
        and (getattr(route, "methods", set()) - {"HEAD", "OPTIONS"})
        and route.path in published
    }
    orphans = sorted(
        prefix
        for pattern in ROUTE_SECURITY_MATRIX
        if pattern.endswith("/*")
        for prefix in [pattern[: -len("/*")]]
        if prefix in served and get_auth_level(prefix) is AuthLevel.DENY
    )

    assert orphans == [], f"published routes reachable only via a wildcard sibling, so denied to everyone: {orphans}"


def test_every_published_route_resolves_to_a_callable_level():
    """No published route may resolve to AuthLevel.DENY (#1073).

    31 of the registered routes once answered 401/403 to every role because no
    matrix entry covered them. Walk every route in the committed OpenAPI spec
    (same scope rule as the collection-path test) and assert a caller exists.
    """
    published = {
        (path, method)
        for path, ops in json.loads(
            (Path(__file__).resolve().parents[3] / "docs" / "api" / "coordinator-api-openapi.json").read_text()
        )
        .get("paths", {})
        .items()
        for method in ops
    }

    denied = sorted(f"{method.upper()} {path}" for path, method in published if get_auth_level(path, method) is AuthLevel.DENY)
    assert denied == [], f"published routes resolving to DENY (no caller can ever reach them): {denied}"


def test_matrix_patterns_match_at_least_one_published_route():
    """A matrix pattern that matches nothing is drift (#1073 gpu/*/delete).

    The old /v1/market/gpu/*/delete entry matched no real route while the real
    DELETE /v1/market/gpu/{gpu_id} went denied.
    """
    import fnmatch as _fnmatch
    import re as _re

    # FastAPI path templates "/v1/jobs/{job_id}" map to the matrix's "*".
    # The check runs against registered routes, not the published spec —
    # infra patterns (/docs, /prometheus) legitimately match routes the spec
    # deliberately omits.
    def wild(path: str) -> str:
        return _re.sub(r"\{[^}]+\}", "*", path)

    registered = {wild(route.path) for route in app.routes if getattr(route, "path", None)}
    # Mounted ASGI apps (/docs, /prometheus, /redoc) sit on Mount objects and
    # are reachable by construction — exclude their patterns from the check.
    {getattr(route, "path", "") for route in app.routes if not getattr(route, "methods", None)}

    infra = {
        "/docs",
        "/redoc",
        "/openapi.json",
        "/metrics",
        "/rate-limit-metrics",
        "/prometheus",
        "/prometheus/*",
        "/health",
        "/health/live",
        "/health/ready",
    }
    unmatched = sorted(
        pattern
        for pattern in ROUTE_SECURITY_MATRIX
        if pattern not in infra and not any(_fnmatch.fnmatch(p, pattern) for p in registered)
    )
    assert unmatched == [], f"matrix patterns matching no registered route: {unmatched}"


def test_sensitive_routes_have_their_exact_levels():
    """Each new entry's level is a security decision — pin it (#1073)."""
    cases = {
        # scrape targets, same as /prometheus
        "/metrics": AuthLevel.NONE,
        "/rate-limit-metrics": AuthLevel.NONE,
        # state dump leaks the whole chain table
        "/v1/state/dump": AuthLevel.ADMIN,
        # logout needs a valid token, nothing more
        "/v1/logout": AuthLevel.ANY,
        # handlers take AuthDep; ANY is the matrix floor for the path family
        "/v1/market/gpu/abc-123": AuthLevel.ANY,
        "/v1/market/gpu/abc-123/reviews": AuthLevel.ANY,
        # miner-owned write routes
        "/v1/market/sync-offers": AuthLevel.MINER,
        "/v1/market/providers/miner-1/capacity": AuthLevel.MINER,
        "/v1/tasks/ollama": AuthLevel.MINER,
        # families whose handlers carry their own auth deps
        "/v1/hipaa/consent": AuthLevel.ANY,
        "/v1/economic-proposals": AuthLevel.ANY,
        "/v1/economic-proposals/prop-1": AuthLevel.ANY,
        "/v1/agent-creativity/capabilities": AuthLevel.ANY,
        "/v1/oracle/price/BTC-USD": AuthLevel.ANY,
        "/v1/agents/security/trust-scores": AuthLevel.ANY,
    }
    wrong = [p for p, lvl in cases.items() if get_auth_level(p) is not lvl]
    assert wrong == [], f"routes resolving to the wrong auth level: {wrong}"


def test_dropped_patterns_match_no_registered_route():
    """The four entries removed in #1073 matched no real route — pin that."""
    dropped = ["/v1/market/gpu/*/delete", "/v1/market/gpu/bid", "/v1/blockchain*", "/v1/security*"]
    import re as _re

    def wild(path: str) -> str:
        return _re.sub(r"\{[^}]+\}", "*", path)

    import fnmatch as _fnmatch

    registered = {wild(r.path) for r in app.routes if getattr(r, "path", None)}
    hits = [f"{pat} -> {p}" for pat in dropped for p in registered if _fnmatch.fnmatch(p, pat)]
    assert hits == [], f"dropped patterns that DO match registered routes: {hits}"


def test_anonymous_deny_still_applies_to_unregistered_routes():
    """The deny-by-default floor must survive — a brand new path is denied."""
    assert get_auth_level("/v1/no-such-route-ever") is AuthLevel.DENY
