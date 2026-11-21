"""Refs #2269 SETTLEMENT-MISSING-CHAIN-500-1 / #2385 settlement retirement.

The mutating endpoints on ``/rpc/bridge/settlement/*`` are retired (#2385):
they answer HTTP 410 before reaching ``CrossChainSettlementService``, so
the #2269 ChainDbMissingError→404 mapping is unreachable on the write
paths. The read endpoints still map an unprovisioned chain.db to a clean
404 — pinned below so the guard is not silently dropped.
"""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from aitbc_chain.config import settings
from aitbc_chain.database import ChainDbMissingError
from aitbc_chain.rpc.escrow_routes import verify_rpc_api_key
from aitbc_chain.rpc.routers.settlement import router as settlement_router


@pytest.fixture()
def client(monkeypatch):
    monkeypatch.setattr(settings, "escrow_enabled", True, raising=False)
    app = FastAPI()
    app.include_router(settlement_router)
    app.dependency_overrides[verify_rpc_api_key] = lambda: None
    return TestClient(app)


def _payload() -> dict:
    return {
        "trade_id": "trade_test",
        "source_chain": "bc-2",
        "dest_chain": "bc-2-island",
        "sender": "0x" + "11" * 20,
        "recipient": "0x" + "22" * 20,
        "amount": 1000,
    }


def test_create_escrow_retired_is_410(client, monkeypatch):
    """#2385: POST /create refuses with 410 before the service is even
    constructed — no ChainDbMissingError path remains on the write side."""
    from aitbc_chain.cross_chain import settlement as settlement_mod

    called = False

    async def boom(self, **kwargs):
        nonlocal called
        called = True
        raise ChainDbMissingError("chain db missing: /var/lib/aitbc/data/bc-2-island/chain.db")

    monkeypatch.setattr(settlement_mod.CrossChainSettlementService, "create_escrow", boom)
    resp = client.post("/bridge/settlement/create", json=_payload())
    assert resp.status_code == 410, resp.text
    assert "#2385" in resp.json()["detail"]
    assert called is False


def test_get_escrow_missing_chain_still_404(client, monkeypatch):
    """The read path keeps the #2269 mapping: an unprovisioned chain.db is
    a client-input problem — 404 naming the chain, never 500."""
    from aitbc_chain.cross_chain import settlement as settlement_mod

    async def boom(self, escrow_id):
        raise ChainDbMissingError("chain db missing: /var/lib/aitbc/data/bc-2-island/chain.db")

    monkeypatch.setattr(settlement_mod.CrossChainSettlementService, "get_escrow", boom)
    resp = client.get("/bridge/settlement/esc_x")
    assert resp.status_code == 404, resp.text
    assert "bc-2-island" in resp.json()["detail"]
