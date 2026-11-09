"""#1389: POST /v1/transactions offer path must validate status and price.

Before the fix, the gpu_market/offer branch wrote GPURegistry rows using
caller-controlled `status` (bypassing the OfferFSM validation PUT
/v1/gpu/{id} applies — arbitrary strings and unreserved 'booked'/'in_use'
states could be persisted) and an unvalidated `price_per_hour` (negative,
non-finite, or wider than the Numeric(20,8) column). Invalid offers are now
refused with 400 before any chain submission or local write.
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

import gpu_service.main as main  # noqa: E402
from gpu_service.main import app  # noqa: E402

CHAIN = "bc-2"


def _signed_tx(gpu_id: str, **payload_overrides: Any) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "gpu_id": gpu_id,
        "miner_id": "miner-1",
        "model": "A100",
        "memory_gb": 80,
        "price_per_hour": "1.5",
        "region": "eu-central",
        "capabilities": ["fp16"],
    }
    payload.update(payload_overrides)
    return {
        "from": "0xProviderWallet",
        "to": "0xProviderWallet",
        "amount": 0,
        "fee": 360000,
        "nonce": 7,
        "type": "GPU_REGISTER",
        "chain_id": CHAIN,
        "payload": payload,
        "signature": "ab" * 65,
    }


def _registry_row(gpu_id: str) -> dict[str, Any] | None:
    async def _run() -> dict[str, Any] | None:
        from sqlalchemy import select

        from gpu_service.domain.gpu_market import GPURegistry
        from gpu_service.storage import get_session

        async with get_session() as session:
            row = (await session.execute(select(GPURegistry).where(GPURegistry.id == gpu_id))).scalars().first()
            return None if row is None else {"status": row.status, "price_per_hour": str(row.price_per_hour)}

    return asyncio.run(_run())


@pytest.fixture
def client(monkeypatch):
    calls: list[dict] = []

    async def fake_submit(tx: dict[str, Any]) -> dict[str, Any]:
        calls.append(tx)
        return {"transaction_hash": "0xdeadbeef123"}

    monkeypatch.setattr(main._rpc_client, "submit_transaction", fake_submit)
    app.dependency_overrides[main.require_gpu_api_key] = lambda: {"role": "gpu_admin"}
    with TestClient(app) as c:
        c.calls = calls  # type: ignore[attr-defined]
        yield c
    app.dependency_overrides.clear()


def _post(client, gpu_id: str, tx: dict[str, Any] | None = None, **extra: Any):
    body: dict[str, Any] = {"type": "gpu_market", "action": "offer", "tx": tx if tx is not None else _signed_tx(gpu_id)}
    body.update(extra)
    return client.post("/v1/transactions", json=body)


def test_valid_offer_still_accepted(client):
    gpu_id = "gpu_offer_ok"
    resp = _post(client, gpu_id)
    assert resp.status_code == 200, resp.text
    row = _registry_row(gpu_id)
    assert row is not None
    assert row["status"] == "available"
    from decimal import Decimal

    assert Decimal(row["price_per_hour"]) == Decimal("1.5")
    assert client.calls == [_signed_tx(gpu_id)]


def test_explicit_available_status_accepted(client):
    gpu_id = "gpu_offer_avail"
    resp = _post(client, gpu_id, status="available")
    assert resp.status_code == 200, resp.text
    assert _registry_row(gpu_id)["status"] == "available"  # type: ignore[index]


@pytest.mark.parametrize("bad_status", ["booked", "in_use", "bogus", "offline"])
def test_non_available_status_rejected(client, bad_status):
    gpu_id = f"gpu_offer_st_{bad_status}"
    resp = _post(client, gpu_id, status=bad_status)
    assert resp.status_code == 400, resp.text
    assert _registry_row(gpu_id) is None
    assert client.calls == [], "invalid offer must be refused before chain submission"


def test_signed_payload_status_is_authoritative(client):
    """A signed payload claiming 'booked' is refused even if outer fields agree."""
    gpu_id = "gpu_offer_signed_booked"
    tx = _signed_tx(gpu_id, status="booked")
    resp = _post(client, gpu_id, tx=tx, status="booked")
    assert resp.status_code == 400, resp.text
    assert _registry_row(gpu_id) is None
    assert client.calls == []


@pytest.mark.parametrize("bad_price", ["-5", "-0.00000001", "abc", "NaN", "Infinity", "1e30"])
def test_invalid_price_rejected(client, bad_price):
    gpu_id = f"gpu_offer_p_{abs(hash(bad_price)) % 100000}"
    tx = _signed_tx(gpu_id, price_per_hour=bad_price)
    resp = _post(client, gpu_id, tx=tx)
    assert resp.status_code == 400, resp.text
    assert _registry_row(gpu_id) is None
    assert client.calls == []


def test_zero_and_boundary_prices_accepted(client):
    for i, price in enumerate(["0", "0.00000001", "999999999999.99999999"]):
        gpu_id = f"gpu_offer_p_ok_{i}"
        resp = _post(client, gpu_id, tx=_signed_tx(gpu_id, price_per_hour=price))
        assert resp.status_code == 200, resp.text
        assert _registry_row(gpu_id) is not None
