from __future__ import annotations

import uuid

import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import async_sessionmaker

from poolhub.app import deps
from poolhub.app.main import create_app
from poolhub.app.prometheus import reset_metrics
from poolhub.repositories.miner_repository import MinerRepository


@pytest_asyncio.fixture()
async def async_client(db_engine, redis_client):  # noqa: F811
    async def _session_override():
        factory = async_sessionmaker(db_engine, expire_on_commit=False, autoflush=False)
        async with factory() as session:
            yield session

    async def _redis_override():
        yield redis_client

    app = create_app()
    app.dependency_overrides.clear()
    app.dependency_overrides[deps.db_session_dep] = _session_override
    app.dependency_overrides[deps.redis_dep] = _redis_override
    reset_metrics()

    async with AsyncClient(app=app, base_url="http://testserver") as client:
        yield client

    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_match_endpoint(async_client, db_session, redis_client):  # noqa: F811
    repo = MinerRepository(db_session, redis_client)
    await repo.register_miner(
        miner_id="miner-1",
        api_key_hash="hash",
        addr="127.0.0.1",
        proto="grpc",
        gpu_vram_gb=16,
        gpu_name="A100",
        cpu_cores=32,
        ram_gb=128,
        max_parallel=4,
        base_price=0.8,
        tags={"tier": "gold"},
        capabilities=["embedding"],
        region="eu",
    )
    await db_session.commit()

    response = await async_client.post(
        "/v1/match",
        json={
            "job_id": "job-123",
            "requirements": {"min_vram_gb": 8},
            "hints": {"region": "eu"},
            "top_k": 1,
        },
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["job_id"] == "job-123"
    assert len(payload["candidates"]) == 1


@pytest.mark.asyncio
async def test_match_endpoint_no_miners(async_client):
    response = await async_client.post(
        "/v1/match",
        json={"job_id": "empty", "requirements": {}, "hints": {}, "top_k": 2},
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["candidates"] == []


@pytest.mark.asyncio
async def test_health_endpoint(async_client):  # noqa: F811
    response = await async_client.get("/v1/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] in {"ok", "degraded"}
    assert "db_error" in data
    assert "redis_error" in data


@pytest.mark.asyncio
async def test_health_endpoint_degraded(db_engine, redis_client):  # noqa: F811
    async def _session_override():
        factory = async_sessionmaker(db_engine, expire_on_commit=False, autoflush=False)
        async with factory() as session:
            yield session

    class FailingRedis:
        async def ping(self) -> None:
            raise RuntimeError("redis down")

        def __getattr__(self, _: str) -> None:  # pragma: no cover - minimal stub
            raise RuntimeError("redis down")

    async def _redis_override():
        yield FailingRedis()

    app = create_app()
    app.dependency_overrides.clear()
    app.dependency_overrides[deps.db_session_dep] = _session_override
    app.dependency_overrides[deps.redis_dep] = _redis_override
    reset_metrics()

    async with AsyncClient(app=app, base_url="http://testserver") as client:
        response = await client.get("/v1/health")
        assert response.status_code == 200
        payload = response.json()
        assert payload["status"] == "degraded"
        assert payload["redis_error"]
        assert payload["db_error"] is None

    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_metrics_endpoint(async_client):
    baseline = await async_client.get("/metrics")
    before = _extract_counter(baseline.text, "poolhub_match_requests_total")

    for _ in range(2):
        await async_client.post(
            "/v1/match",
            json={"job_id": str(uuid.uuid4()), "requirements": {}, "hints": {}, "top_k": 1},
        )

    updated = await async_client.get("/metrics")
    after = _extract_counter(updated.text, "poolhub_match_requests_total")
    assert after >= before + 2


def _extract_counter(metrics_text: str, metric: str) -> float:
    for line in metrics_text.splitlines():
        if line.startswith(metric):
            parts = line.split()
            if len(parts) >= 2:
                try:
                    return float(parts[1])
                except ValueError:  # pragma: no cover
                    return 0.0
    return 0.0
