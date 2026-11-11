"""Pins example aitbc_ai job executor (#1651)."""

from __future__ import annotations

import asyncio
import os
import sys
import tempfile
from pathlib import Path

import pytest

_DB_DIR = Path(tempfile.mkdtemp(prefix="aitbc_ai_exec_test_"))
os.environ.setdefault("AI_SERVICE_DATABASE_URL", f"sqlite+aiosqlite:///{_DB_DIR / 'ai_exec.db'}")
os.environ["AITBC_AI_CLIENT_KEYS"] = "test-key-a:tenant-a"
os.environ["AITBC_AI_EXECUTE_JOBS"] = "true"
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "examples" / "src"))

from sqlmodel import SQLModel  # noqa: E402

from aitbc_ai.executor import receipt_signature  # noqa: E402
from aitbc_ai.main import app  # noqa: E402
from aitbc_ai.storage import engine  # noqa: E402


@pytest.fixture(autouse=True)
async def _reset_executor_env():
    yield
    os.environ["AITBC_AI_EXECUTE_JOBS"] = "false"
    await asyncio.sleep(0.05)


@pytest.fixture
async def client():
    from httpx import ASGITransport, AsyncClient

    os.environ["AITBC_AI_EXECUTE_JOBS"] = "true"

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


async def _wait_terminal(client, job_id: str, *, timeout: float = 2.0) -> dict:
    deadline = asyncio.get_event_loop().time() + timeout
    while asyncio.get_event_loop().time() < deadline:
        resp = await client.get(f"/jobs/{job_id}")
        assert resp.status_code == 200
        body = resp.json()
        if body["state"] in ("completed", "failed", "expired", "canceled"):
            return body
        await asyncio.sleep(0.05)
    raise AssertionError(f"job {job_id} did not reach terminal state")


@pytest.mark.asyncio
async def test_submitted_job_reaches_completed_with_receipt(client) -> None:
    resp = await client.post(
        "/jobs",
        json={"task_type": "inference", "task_data": {"prompt": "hello"}},
    )
    assert resp.status_code == 201
    job_id = resp.json()["id"]

    final = await _wait_terminal(client, job_id)
    assert final["state"] == "completed"
    assert final["result"]["simulated"] is True
    assert final["result"]["output"] == "hello"

    result = await client.get(f"/jobs/{job_id}/result")
    assert result.status_code == 200
    payload = result.json()
    assert payload["receipt"]["simulated"] is True
    assert payload["receipt"]["signature"]
    expected_sig = receipt_signature(job_id, payload["receipt"]["miner_id"], final["result"])
    assert payload["receipt"]["signature"] == expected_sig


@pytest.mark.asyncio
async def test_task_data_fail_marks_job_failed(client) -> None:
    resp = await client.post(
        "/jobs",
        json={"task_type": "inference", "task_data": {"fail": True, "error": "boom"}},
    )
    job_id = resp.json()["id"]
    final = await _wait_terminal(client, job_id)
    assert final["state"] == "failed"
    assert final["error"] == "boom"
