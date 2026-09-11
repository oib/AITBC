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
