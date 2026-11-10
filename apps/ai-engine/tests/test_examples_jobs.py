"""Tests for the examples job API: input validation, expiry, stub labels.

The examples app is not deployed, but it is the reference implementation —
these pin the fixes for #1475 (expires_at never enforced), #1476 (unvalidated
numerics / unbounded limit) and #1477 (fabricated stub success).

AI_SERVICE_DATABASE_URL must be set before aitbc_ai.storage is imported;
it is read into a module constant at import time. A per-run temp file keeps
:memory: connection-pool pitfalls out of the suite.
"""

from __future__ import annotations

import os
import sys
import tempfile
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

_DB_DIR = Path(tempfile.mkdtemp(prefix="aitbc_ai_test_"))
os.environ.setdefault("AI_SERVICE_DATABASE_URL", f"sqlite+aiosqlite:///{_DB_DIR / 'ai_test.db'}")
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "examples" / "src"))

from sqlmodel import SQLModel  # noqa: E402

from aitbc_ai.main import app  # noqa: E402
from aitbc_ai.storage import engine  # noqa: E402


@pytest.fixture
async def client():
    """Fresh schema per test; yields an httpx AsyncClient bound to the app."""
    from httpx import ASGITransport, AsyncClient

    async with engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.drop_all)
        await conn.run_sync(SQLModel.metadata.create_all)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


async def _submit(client, **overrides):
    body = {"task_type": "inference", "task_data": {"prompt": "hi"}}
    body.update(overrides)
    resp = await client.post("/jobs", json=body)
    assert resp.status_code == 201, resp.text
    return resp.json()


@pytest.mark.asyncio
async def test_negative_payment_amount_rejected(client) -> None:
    resp = await client.post("/jobs", json={"task_type": "x", "payment_amount": -1.0})
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_non_finite_payment_amount_rejected() -> None:
    """NaN/inf payment amounts fail model validation (JSON can't carry them,
    so this pins the validator at model level)."""
    from pydantic import ValidationError

    from aitbc_ai.main import JobCreate

    for bad in (float("nan"), float("inf"), float("-inf"), -0.5):
        with pytest.raises(ValidationError):
            JobCreate(task_type="x", payment_amount=bad)
    assert JobCreate(task_type="x", payment_amount=1.5).payment_amount == 1.5


@pytest.mark.asyncio
async def test_list_limit_is_bounded(client) -> None:
    assert (await client.get("/jobs?limit=0")).status_code == 422
    assert (await client.get("/jobs?limit=201")).status_code == 422
    assert (await client.get("/jobs?limit=200")).status_code == 200


@pytest.mark.asyncio
async def test_expired_job_transitions_on_read(client) -> None:
    past = (datetime.now(UTC) - timedelta(seconds=1)).isoformat()
    job = await _submit(client, expires_at=past)
    assert job["state"] == "pending"

    got = await client.get(f"/jobs/{job['id']}")
    assert got.status_code == 200
    assert got.json()["state"] == "expired"

    # EXPIRED is terminal: the result endpoint serves it instead of 425.
    result = await client.get(f"/jobs/{job['id']}/result")
    assert result.status_code == 200
    # And it can no longer be cancelled.
    assert (await client.post(f"/jobs/{job['id']}/cancel")).status_code == 400


@pytest.mark.asyncio
async def test_future_expiry_does_not_expire(client) -> None:
    future = (datetime.now(UTC) + timedelta(hours=1)).isoformat()
    job = await _submit(client, expires_at=future)
    got = await client.get(f"/jobs/{job['id']}")
    assert got.json()["state"] == "pending"


@pytest.mark.asyncio
async def test_stub_endpoints_are_labelled_simulated(client) -> None:
    health = await client.get("/multimodal/health")
    assert health.json()["simulated"] is True
    assert "notice" in health.json()

    proc = await client.post("/multimodal/process", json={"modality": "text"})
    assert proc.json()["simulated"] is True

    tune = await client.post("/optimization/tune", json={"model": "m"})
    assert tune.json()["simulated"] is True


@pytest.mark.asyncio
async def test_naive_expires_at_treated_as_utc(client) -> None:
    """A naive expires_at must not crash the comparison."""
    naive_past = (datetime.now(UTC) - timedelta(seconds=1)).replace(tzinfo=None).isoformat()
    job = await _submit(client, expires_at=naive_past)
    got = await client.get(f"/jobs/{job['id']}")
    assert got.json()["state"] == "expired"
