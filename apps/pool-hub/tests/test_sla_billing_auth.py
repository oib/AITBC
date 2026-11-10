"""Route-level auth pins for the pool-hub billing mutation routes.

``POST /v1/sla/billing/{sync,usage/record,invoice/generate}`` trigger
billing side-effects in coordinator-api. Each wires ``_governance_auth``
(``X-PoolHub-Key``) as a ``Depends`` — but until now nothing exercised that
wiring at route level, so dropping the dependency would silently open the
billing surface (the same gap #1400's Decimal validation closed on the
payload side). These tests mount the sla router and assert 401 without and
with a wrong key, mirroring test_parameters_apply.py's route pins.
"""

from __future__ import annotations

from typing import Any

from fastapi import FastAPI
from fastapi.testclient import TestClient

from poolhub.app.routers import sla as sla_module
from poolhub.app.routers.parameters import _governance_auth
from poolhub.database import get_session


class _FakeTx:
    async def __aenter__(self) -> _FakeTx:
        return self

    async def __aexit__(self, *args: Any) -> bool:
        return False

    async def execute(self, *args: Any, **kwargs: Any) -> Any:
        raise RuntimeError("no database in an auth-gate test")


class _FakeSession:
    """Enough AsyncSession surface for BillingIntegration to construct and
    for its first query to fail cleanly into the route's 500 handler."""

    def begin(self) -> _FakeTx:
        return _FakeTx()


def _sla_client() -> TestClient:
    """Mount just the sla router with a stub session so only auth is exercised."""
    app = FastAPI()
    app.include_router(sla_module.router, prefix="/v1")

    async def _db() -> Any:
        yield _FakeSession()

    app.dependency_overrides[get_session] = _db
    return TestClient(app)


_BILLING_MUTATIONS = [
    ("/v1/sla/billing/sync", {}),
    (
        "/v1/sla/billing/usage/record",
        {"tenant_id": "t-1", "resource_type": "api_calls", "quantity": "1"},
    ),
    (
        "/v1/sla/billing/invoice/generate",
        {
            "tenant_id": "t-1",
            "period_start": "2026-01-01T00:00:00Z",
            "period_end": "2026-01-31T00:00:00Z",
        },
    ),
]


def test_billing_mutations_reject_missing_key() -> None:
    client = _sla_client()
    for path, body in _BILLING_MUTATIONS:
        resp = client.post(path, json=body)
        assert resp.status_code == 401, f"POST {path} without key: {resp.status_code}"


def test_billing_mutations_reject_wrong_key() -> None:
    client = _sla_client()
    for path, body in _BILLING_MUTATIONS:
        resp = client.post(path, json=body, headers={"X-PoolHub-Key": "attacker-key"})
        assert resp.status_code == 401, f"POST {path} with wrong key: {resp.status_code}"


def test_billing_mutation_reaches_handler_with_governance_key() -> None:
    """Control: the configured key passes auth (handler then fails on the
    stub session's billing call — anything but 401 proves auth let it through)."""
    client = _sla_client()
    resp = client.post(
        "/v1/sla/billing/sync",
        json={},
        headers={"X-PoolHub-Key": _governance_auth.expected_key or ""},
    )
    assert resp.status_code != 401
