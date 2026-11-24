"""AUDIT-EDGE pins: #2913 — ai-engine examples bounds and stub auth.

The eight /multimodal/* and /optimization/* stub routes had no
get_client_id dependency (unauthenticated even with
AITBC_AI_REQUIRE_AUTH=true), request bodies were unbounded (no body-size
middleware anywhere in the app), task_data had no serialized-size cap,
and there was no per-client active-job quota.
"""

from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

import pytest

_DB_DIR = Path(tempfile.mkdtemp(prefix="aitbc_ai_bounds_test_"))
os.environ.setdefault("AI_SERVICE_DATABASE_URL", f"sqlite+aiosqlite:///{_DB_DIR / 'ai_bounds.db'}")
os.environ["AITBC_AI_CLIENT_KEYS"] = "test-key-a:tenant-a,test-key-b:tenant-b"
os.environ["AITBC_AI_EXECUTE_JOBS"] = "false"
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "examples" / "src"))

from sqlmodel import SQLModel  # noqa: E402

from aitbc_ai import main as ai_main  # noqa: E402
from aitbc_ai.main import MAX_BODY_BYTES, TASK_DATA_MAX_BYTES, app  # noqa: E402
from aitbc_ai.storage import engine  # noqa: E402


@pytest.fixture
async def client():
    from httpx import ASGITransport, AsyncClient

    async with engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.drop_all)
        await conn.run_sync(SQLModel.metadata.create_all)
    transport = ASGITransport(app=app)
    async with AsyncClient(
        transport=transport,
        base_url="http://test",
        headers={"Authorization": "Bearer test-key-a"},
    ) as c:
        yield c


@pytest.fixture
async def anon_client():
    from httpx import ASGITransport, AsyncClient

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


@pytest.mark.asyncio
async def test_stub_routes_require_auth(anon_client, client) -> None:
    for method, path, payload in (
        ("get", "/multimodal/health", None),
        ("get", "/multimodal/agents", None),
        ("get", "/multimodal/health/deep", None),
        ("get", "/optimization/health", None),
        ("get", "/optimization/agents", None),
        ("post", "/multimodal/process", {"modality": "text"}),
        ("post", "/multimodal/benchmark", {"modality": "text"}),
        ("post", "/optimization/tune", {"model": "m"}),
        ("post", "/optimization/predict", {"model": "m"}),
    ):
        kwargs = {"json": payload} if payload is not None else {}
        resp = await getattr(anon_client, method)(path, **kwargs)
        assert resp.status_code == 401, f"{method.upper()} {path} returned {resp.status_code} unauthenticated"
        ok = await getattr(client, method)(path, **kwargs)
        assert ok.status_code == 200, f"{method.upper()} {path} returned {ok.status_code} authenticated"


@pytest.mark.asyncio
async def test_oversized_body_rejected(anon_client, client) -> None:
    big = b'{"modality": "' + b"x" * (MAX_BODY_BYTES + 1) + b'"}'
    resp = await client.post(
        "/multimodal/process",
        content=big,
        headers={"Content-Type": "application/json"},
    )
    assert resp.status_code == 413
    # An anonymous oversized request is still capped, not routed.
    resp = await anon_client.post(
        "/multimodal/process",
        content=big,
        headers={"Content-Type": "application/json"},
    )
    assert resp.status_code == 413


@pytest.mark.asyncio
async def test_task_data_serialized_size_capped(client) -> None:
    resp = await client.post(
        "/jobs",
        json={"task_type": "inference", "task_data": {"blob": "x" * (TASK_DATA_MAX_BYTES + 1)}},
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_active_jobs_per_client_capped(client, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(ai_main, "MAX_ACTIVE_JOBS_PER_CLIENT", 1)
    first = await client.post("/jobs", json={"task_type": "inference", "task_data": {"prompt": "a"}})
    assert first.status_code == 201
    second = await client.post("/jobs", json={"task_type": "inference", "task_data": {"prompt": "b"}})
    assert second.status_code == 429
