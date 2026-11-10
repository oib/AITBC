"""Pin: route auth dependencies resolve BEFORE the ``@rate_limit`` wrapper.

``aitbc.rate_limiting.rate_limit`` wraps the endpoint *function*; FastAPI
solves the route's dependencies (``AdminDep`` → ``get_token`` → 401) before
the wrapped endpoint is ever invoked, so an unauthenticated request can
never consume rate-limit budget — the limiter only sees authenticated
callers. This is the coordinator-api half of the ordering contract the
api-gateway pins from the other side (``pre_auth_ip_limit`` counts a coarse
per-IP bucket *before* ``verify_auth`` by design, #1211; the identity-keyed
post-auth bucket is unchanged — ``apps/api-gateway/tests/
test_preauth_rate_limit.py``).

The sweep: ``GET /v1/agents/workflows/{id}`` carries ``AdminDep`` +
``@rate_limit(rate=200, per=60)``. With rate limiting force-enabled, 205
credentialess requests must ALL answer 401 — if the limiter ran first, the
201st+ would be 429.

Coder: C
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from coordinator_api.main import app

# One past the route's 200/minute budget.
_REQUESTS = 205


@pytest.fixture
def rl_client(monkeypatch) -> TestClient:
    """TestClient with rate limiting enabled (conftest disables it suite-wide)."""
    monkeypatch.setenv("AITBC_ENABLE_RATE_LIMITING", "true")
    return TestClient(app)


def test_unauthenticated_never_consumes_rate_limit_budget(rl_client: TestClient) -> None:
    codes = [rl_client.get("/v1/agents/workflows/0").status_code for _ in range(_REQUESTS)]

    assert 429 not in codes, f"unauthenticated requests hit the rate limiter — auth did not run first: {codes[-5:]}"
    assert set(codes) == {401}, f"expected uniform 401s, got {sorted(set(codes))}"


def test_route_really_is_rate_limited_and_authed() -> None:
    """Guard against a silent no-op pin: the chosen route must carry an auth
    dependency AND be decorator-wrapped (``@rate_limit`` sits between the
    router decorator and the function, so the registered endpoint is the
    ``functools.wraps`` wrapper with ``__wrapped__`` pointing at the raw
    handler)."""
    route = next(
        r
        for r in app.routes
        if getattr(r, "path", "") == "/v1/agents/workflows/{workflow_id}" and "GET" in getattr(r, "methods", set())
    )
    dependant = route.dependant
    dep_names = {d.call.__module__ + "." + d.call.__qualname__ for d in dependant.dependencies}
    # require_admin/get_token live in aitbc.auth.dependencies (re-exported).
    assert any("get_token" in name or "require_admin" in name for name in dep_names), dep_names
    endpoint = route.endpoint
    assert hasattr(endpoint, "__wrapped__"), "endpoint is not decorator-wrapped — @rate_limit may be gone"
    assert endpoint.__wrapped__.__name__ == "get_workflow"
