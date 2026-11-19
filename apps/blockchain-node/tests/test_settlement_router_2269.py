"""Refs #2269 SETTLEMENT-MISSING-CHAIN-500-1: /rpc/bridge/settlement/* must
fail closed with a clean 4xx when a source/dest chain has no local
chain.db — ChainDbMissingError is a client-input problem (unprovisioned
chain), not a server fault, and must not surface as a bare 500.
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


def test_create_escrow_missing_dest_chain_is_404(client, monkeypatch):
    """Unprovisioned dest chain.db -> 404 naming the chain, never 500."""
    from aitbc_chain.cross_chain import settlement as settlement_mod

    async def boom(self, **kwargs):
        raise ChainDbMissingError("chain db missing: /var/lib/aitbc/data/bc-2-island/chain.db")

    monkeypatch.setattr(settlement_mod.CrossChainSettlementService, "create_escrow", boom)
    resp = client.post("/bridge/settlement/create", json=_payload())
    assert resp.status_code == 404, resp.text
    assert "bc-2-island" in resp.json()["detail"]


def test_create_escrow_other_errors_still_500(client, monkeypatch):
    """Non-chain-db failures keep the generic 500 — the 404 mapping is
    scoped to ChainDbMissingError only."""
    from aitbc_chain.cross_chain import settlement as settlement_mod

    async def boom(self, **kwargs):
        raise RuntimeError("db exploded")

    monkeypatch.setattr(settlement_mod.CrossChainSettlementService, "create_escrow", boom)
    resp = client.post("/bridge/settlement/create", json=_payload())
    assert resp.status_code == 500
