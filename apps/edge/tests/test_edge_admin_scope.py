"""EDGE-PAY-1 (#1668): node-level mutating routes are admin-only.

The serve router scopes objects to the caller's ``sub``; the gpu,
database and islands routers manage node-level resources with no owner
column, so their mutating routes now require the admin role (``AdminDep``)
while reads stay open to any fleet JWT. Before this any fleet JWT could
delete GPU listings/databases, init databases, or join an island claiming
``is_hub=true``.
"""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from aitbc.auth import create_access_token
from aitbc_edge.routers import database as database_router
from aitbc_edge.routers import gpu as gpu_router
from aitbc_edge.routers import islands as islands_router


def _token(sub: str = "user-1", role: str = "client") -> str:
    return create_access_token(sub, role)


def _auth(token: str | None) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"} if token else {}


class _FakeGPUService:
    def __init__(self) -> None:
        self.mutated: list[str] = []

    async def list_gpus(self, **kwargs):
        return []

    async def get_gpu_listing(self, gpu_id):
        return {"id": gpu_id}

    async def remove_gpu_listing(self, gpu_id):
        self.mutated.append(f"delete:{gpu_id}")
        return True

    async def scan_gpus(self, miner_id):
        self.mutated.append(f"scan:{miner_id}")
        return {"success": True}

    async def get_gpu_metrics(self, gpu_id, limit=100):
        return []

    async def advertise_to_market(self):
        self.mutated.append("advertise")
        return {"status": "advertised"}


class _FakeDatabaseService:
    def __init__(self) -> None:
        self.mutated: list[str] = []

    async def init_database(self, database_id, island_id, capacity_gb):
        self.mutated.append(f"init:{database_id}")
        return {"success": True, "database": database_id}

    async def list_databases(self, island_id=None):
        return []

    async def get_database(self, database_id):
        return {"database_id": database_id}

    async def delete_database(self, database_id):
        self.mutated.append(f"delete:{database_id}")
        return True

    async def sync_database(self, database_id):
        self.mutated.append(f"sync:{database_id}")
        return {"success": True}


class _FakeIslandService:
    def __init__(self) -> None:
        self.mutated: list[str] = []

    async def join_island(self, **kwargs):
        self.mutated.append(f"join:{kwargs.get('island_id')}")
        return {"success": True}

    async def leave_island(self, island_id):
        self.mutated.append(f"leave:{island_id}")
        return {"success": True}

    async def list_islands(self):
        return []

    async def get_island(self, island_id):
        return {"island_id": island_id}

    async def list_memberships_by_region(self, region):
        return []

    async def request_bridge(self, target_island_id):
        self.mutated.append(f"bridge:{target_island_id}")
        return {"success": True}


@pytest.fixture
def env():
    app = FastAPI()
    app.include_router(gpu_router.router, prefix="/v1/gpu")
    app.include_router(database_router.router, prefix="/v1/database")
    app.include_router(islands_router.router, prefix="/v1/islands")
    gpu_svc = _FakeGPUService()
    db_svc = _FakeDatabaseService()
    island_svc = _FakeIslandService()
    app.dependency_overrides[gpu_router.get_gpu_service] = lambda: gpu_svc
    app.dependency_overrides[database_router.get_database_service] = lambda: db_svc
    app.dependency_overrides[islands_router.get_island_service] = lambda: island_svc
    yield TestClient(app), gpu_svc, db_svc, island_svc
    app.dependency_overrides.clear()


# (method, path, json body) for every node-level mutating route.
MUTATING_ROUTES = [
    ("delete", "/v1/gpu/gpu-1", None),
    ("post", "/v1/gpu/scan", {"miner_id": "m-1"}),
    ("post", "/v1/gpu/advertise", None),
    ("post", "/v1/database/init", {"database_id": "db-1", "island_id": "i-1", "capacity_gb": 10}),
    ("delete", "/v1/database/db-1", None),
    ("post", "/v1/database/db-1/sync", None),
    ("post", "/v1/islands/join", {"island_id": "i-1", "island_name": "n", "chain_id": "c", "is_hub": True}),
    ("post", "/v1/islands/leave", {"island_id": "i-1"}),
    ("post", "/v1/islands/bridge", {"target_island_id": "i-2"}),
]


def _call(client: TestClient, method: str, path: str, body, headers: dict[str, str]):
    kwargs = {"headers": headers}
    if method != "delete":
        kwargs["json"] = body
    return getattr(client, method)(path, **kwargs)


class TestMutatingRoutesRequireAdmin:
    @pytest.mark.parametrize("method,path,body", MUTATING_ROUTES)
    def test_client_role_gets_403(self, env, method, path, body):
        client, gpu_svc, db_svc, island_svc = env
        response = _call(client, method, path, body, _auth(_token("user-1", "client")))
        assert response.status_code == 403, f"{method.upper()} {path} -> {response.status_code}"
        assert not (gpu_svc.mutated or db_svc.mutated or island_svc.mutated)

    @pytest.mark.parametrize("method,path,body", MUTATING_ROUTES)
    def test_admin_role_reaches_service(self, env, method, path, body):
        client, *_ = env
        response = _call(client, method, path, body, _auth(_token("op-1", "admin")))
        assert response.status_code == 200, f"{method.upper()} {path} -> {response.status_code}: {response.text}"

    @pytest.mark.parametrize("method,path,body", MUTATING_ROUTES)
    def test_no_token_is_401(self, env, method, path, body):
        client, *_ = env
        response = _call(client, method, path, body, {})
        assert response.status_code == 401


class TestReadRoutesStayOpen:
    @pytest.mark.parametrize(
        "path",
        [
            "/v1/gpu/",
            "/v1/gpu/gpu-1",
            "/v1/gpu/gpu-1/metrics",
            "/v1/database/",
            "/v1/database/db-1",
            "/v1/islands/",
            "/v1/islands/i-1",
            "/v1/islands/by-region/eu",
        ],
    )
    def test_client_role_can_read(self, env, path):
        client, *_ = env
        response = client.get(path, headers=_auth(_token("user-1", "client")))
        assert response.status_code == 200, f"GET {path} -> {response.status_code}: {response.text}"
