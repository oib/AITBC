"""EDGE-AUTHZ-BEFORE-COMMISSIONING (#1205): every /v1 route requires a fleet
JWT, and serve-object access is scoped to the caller's ``sub`` (admin bypass).

Before this change every router was unauthenticated and serve
list/read/cancel had no ownership check — latent while the compute tier is
undeployed, armed the moment a shop node joins.
"""

from __future__ import annotations

from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from aitbc.auth import create_access_token
from aitbc_edge.routers import metrics as metrics_router
from aitbc_edge.routers import serve as serve_router


def _token(sub: str = "user-1", role: str = "client") -> str:
    return create_access_token(sub, role)


def _auth(token: str | None) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"} if token else {}


class FakeServeService:
    """Captures the owner scope the router resolves; returns canned rows."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, tuple[Any, ...]]] = []

    async def submit_compute_request(self, gpu_id, model_name, input_data, priority="normal", owner_id=None):
        self.calls.append(("submit", (gpu_id, model_name, input_data, priority, owner_id)))
        return {"success": True, "request_id": "req_test", "status": "queued"}

    async def list_compute_requests(self, gpu_id=None, status=None, owner_id=None):
        self.calls.append(("list", (gpu_id, status, owner_id)))
        return [{"request_id": "req_a"}]

    async def get_compute_request(self, request_id, owner_id=None):
        self.calls.append(("get", (request_id, owner_id)))
        return {"request_id": request_id, "owner_id": owner_id}

    async def cancel_compute_request(self, request_id, owner_id=None):
        self.calls.append(("cancel", (request_id, owner_id)))
        return True

    async def get_compute_result(self, request_id, owner_id=None):
        self.calls.append(("result", (request_id, owner_id)))
        return {"request_id": request_id, "output_data": {"ok": True}}


class FakeMetricsService:
    def __init__(self) -> None:
        self.calls: list[tuple[Any, ...]] = []

    async def record_metrics(self, gpu_id, metrics):
        self.calls.append((gpu_id, metrics))
        return {"success": True}

    async def list_metrics(self, gpu_id=None, limit=100):
        return {"metrics": [], "total": 0}

    async def get_metrics(self, metric_id):
        return {"metric_id": metric_id}

    async def delete_metrics(self, metric_id):
        return True


@pytest.fixture
def env(monkeypatch):
    # Payment verification would 402 before the service is reached; the
    # authz pins are about identity, not escrow.
    monkeypatch.setattr(serve_router.settings, "require_payment_verification", False)
    app = FastAPI()
    app.include_router(serve_router.router, prefix="/v1/serve")
    app.include_router(metrics_router.router, prefix="/v1/metrics")
    serve_svc = FakeServeService()
    metrics_svc = FakeMetricsService()
    app.dependency_overrides[serve_router.get_serve_service] = lambda: serve_svc
    app.dependency_overrides[metrics_router.get_metrics_service] = lambda: metrics_svc
    yield TestClient(app), serve_svc, metrics_svc
    app.dependency_overrides.clear()


class TestUnauthenticatedRejected:
    @pytest.mark.parametrize(
        "method,path",
        [
            ("get", "/v1/serve/requests"),
            ("post", "/v1/serve/requests"),
            ("get", "/v1/serve/requests/req_1"),
            ("post", "/v1/serve/requests/req_1/cancel"),
            ("get", "/v1/serve/requests/req_1/result"),
            ("get", "/v1/metrics/"),
            ("post", "/v1/metrics/"),
            ("delete", "/v1/metrics/m_1"),
        ],
    )
    def test_no_token_is_401(self, env, method, path):
        client, _, _ = env
        kwargs = {"json": {"gpu_id": "g", "model_name": "m", "input_data": {}, "metrics": {}}}
        response = getattr(client, method)(path, **({} if method in ("get", "delete") else kwargs))
        assert response.status_code == 401, f"{method.upper()} {path} -> {response.status_code}"


class TestServeOwnershipScope:
    def test_submit_records_owner_sub(self, env):
        client, svc, _ = env
        response = client.post(
            "/v1/serve/requests",
            json={"gpu_id": "g1", "model_name": "m", "input_data": {"x": 1}},
            headers=_auth(_token("user-42")),
        )
        assert response.status_code == 200
        assert svc.calls[-1] == ("submit", ("g1", "m", {"x": 1}, "normal", "user-42"))

    def test_list_scoped_to_client_sub(self, env):
        client, svc, _ = env
        client.get("/v1/serve/requests", headers=_auth(_token("user-7")))
        assert svc.calls[-1] == ("list", (None, None, "user-7"))

    def test_list_admin_is_unrestricted(self, env):
        client, svc, _ = env
        client.get("/v1/serve/requests", headers=_auth(_token("admin-1", "admin")))
        assert svc.calls[-1] == ("list", (None, None, None))

    def test_get_scoped_to_owner(self, env):
        client, svc, _ = env
        client.get("/v1/serve/requests/req_9", headers=_auth(_token("user-9")))
        assert svc.calls[-1] == ("get", ("req_9", "user-9"))

    def test_get_admin_unrestricted(self, env):
        client, svc, _ = env
        client.get("/v1/serve/requests/req_9", headers=_auth(_token("op", "admin")))
        assert svc.calls[-1] == ("get", ("req_9", None))

    def test_cancel_scoped_to_owner(self, env):
        client, svc, _ = env
        client.post("/v1/serve/requests/req_9/cancel", headers=_auth(_token("user-9")))
        assert svc.calls[-1] == ("cancel", ("req_9", "user-9"))

    def test_result_scoped_to_owner(self, env):
        client, svc, _ = env
        client.get("/v1/serve/requests/req_9/result", headers=_auth(_token("user-9")))
        assert svc.calls[-1] == ("result", ("req_9", "user-9"))

    def test_result_admin_unrestricted(self, env):
        client, svc, _ = env
        client.get("/v1/serve/requests/req_9/result", headers=_auth(_token("op", "admin")))
        assert svc.calls[-1] == ("result", ("req_9", None))


class TestMutatingRoutesRequireAuth:
    def test_metrics_record_needs_token(self, env):
        client, _, metrics_svc = env
        r = client.post("/v1/metrics/", json={"gpu_id": "g", "metrics": {}}, headers=_auth(_token()))
        assert r.status_code == 200
        assert metrics_svc.calls
