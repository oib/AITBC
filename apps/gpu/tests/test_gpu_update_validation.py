"""#1389: PUT /v1/gpu/{gpu_id} must apply the same price bounds as the offer path.

Before the fix the update path wrote ``Decimal(str(price_per_hour))`` with no
validation — negative, non-finite, non-numeric, or wider-than-Numeric(20,8)
values were persisted (or surfaced as a 500). Invalid prices are now refused
with 400 and the row is left unchanged. Illegal OfferFSM status transitions
on the same endpoint are likewise client errors and now return 400 instead of
500.
"""

from __future__ import annotations

import asyncio
import sys
import uuid
from decimal import Decimal
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

import gpu_service.main as main  # noqa: E402
from gpu_service.domain.gpu_market import GPURegistry  # noqa: E402
from gpu_service.main import app  # noqa: E402
from gpu_service.storage import get_session  # noqa: E402


async def _seed_gpu(status: str = "available", price: str = "1.5") -> str:
    gpu_id = f"gpu_put_{uuid.uuid4().hex[:8]}"
    async with get_session() as session:
        session.add(
            GPURegistry(
                id=gpu_id,
                miner_id="miner_put",
                model="TestGPU",
                status=status,
                price_per_hour=Decimal(price),
            )
        )
        await session.commit()
    return gpu_id


async def _row(gpu_id: str) -> dict[str, str]:
    async with get_session() as session:
        result = await session.execute(select(GPURegistry).where(GPURegistry.id == gpu_id))
        gpu = result.scalar_one()
        return {"status": gpu.status, "price_per_hour": str(gpu.price_per_hour)}


@pytest.fixture
def client():
    app.dependency_overrides[main.require_gpu_api_key] = lambda: {"role": "gpu_admin"}
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


def test_valid_price_update_accepted(client) -> None:
    gpu_id = asyncio.run(_seed_gpu())
    resp = client.put(f"/v1/gpu/{gpu_id}", json={"price_per_hour": "2.75"})
    assert resp.status_code == 200, resp.text
    row = asyncio.run(_row(gpu_id))
    assert Decimal(row["price_per_hour"]) == Decimal("2.75")


@pytest.mark.parametrize("bad_price", ["-5", "-0.00000001", "abc", "NaN", "Infinity", "1e30"])
def test_invalid_price_rejected(client, bad_price) -> None:
    gpu_id = asyncio.run(_seed_gpu())
    resp = client.put(f"/v1/gpu/{gpu_id}", json={"price_per_hour": bad_price})
    assert resp.status_code == 400, resp.text
    row = asyncio.run(_row(gpu_id))
    assert Decimal(row["price_per_hour"]) == Decimal("1.5"), "rejected price must not be persisted"


def test_boundary_prices_accepted(client) -> None:
    for price in ["0", "0.00000001", "999999999999.99999999"]:
        gpu_id = asyncio.run(_seed_gpu())
        resp = client.put(f"/v1/gpu/{gpu_id}", json={"price_per_hour": price})
        assert resp.status_code == 200, resp.text
        stored = Decimal(asyncio.run(_row(gpu_id))["price_per_hour"])
        # sqlite NUMERIC storage rounds the widest boundary value; the bound
        # itself (accepted, not 400) is what this test pins.
        assert abs(stored - Decimal(price)) <= Decimal("0.00000001")


def test_invalid_status_transition_returns_400(client) -> None:
    """available -> in_use is not a legal OfferFSM transition; it is a client
    error and must not surface as a 500."""
    gpu_id = asyncio.run(_seed_gpu(status="available"))
    resp = client.put(f"/v1/gpu/{gpu_id}", json={"status": "in_use"})
    assert resp.status_code == 400, resp.text
    assert asyncio.run(_row(gpu_id))["status"] == "available"


def test_valid_status_transition_still_accepted(client) -> None:
    gpu_id = asyncio.run(_seed_gpu(status="available"))
    resp = client.put(f"/v1/gpu/{gpu_id}", json={"status": "booked"})
    assert resp.status_code == 200, resp.text
    assert asyncio.run(_row(gpu_id))["status"] == "booked"
