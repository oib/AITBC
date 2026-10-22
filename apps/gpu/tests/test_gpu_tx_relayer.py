"""GPU-RELAYER-1 (#385): the /v1/transactions relayer forwards the caller's
signed GPU_REGISTER envelope verbatim and only falls back to local storage on
transport failures — an admission refusal is relayed, never masked as success.

Signed fields are ("from","to","amount","fee","nonce","payload","type",
"chain_id"): any rebuild — the old code remapped payload keys, hardcoded `to`
to the zero address and re-fetched `nonce` — produces bytes the wallet never
signed, so the node refused every relayered tx and the broad except wrote a
local row anyway (zero GPU_REGISTER ever sealed on bc-2).
"""

import asyncio
import json
import sys
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

import gpu_service.main as main  # noqa: E402
from gpu_service.main import app  # noqa: E402

CHAIN = "bc-2"


def _signed_tx(gpu_id: str) -> dict[str, Any]:
    """A canonical GPU_REGISTER envelope as `aitbc gpu onchain register`
    produces it (gpu_onchain._build_gpu_tx + _sign_tx): `to` is the wallet's
    own address, `nonce` is the sign-time nonce, payload carries the
    consensus key set."""
    return {
        "from": "0xProviderWallet",
        "to": "0xProviderWallet",
        "amount": 0,
        "fee": 360000,
        "nonce": 7,
        "type": "GPU_REGISTER",
        "chain_id": CHAIN,
        "payload": {
            "gpu_id": gpu_id,
            "miner_id": "miner-1",
            "model": "A100",
            "memory_gb": 80,
            "cuda_version": "12.2",
            "region": "eu-central",
            "capabilities": ["fp16"],
            "price_per_hour": "1.5",
            "to": "0xProviderWallet",
            "amount": 0,
        },
        "signature": "ab" * 65,
    }


class _FakeResponse:
    """Duck-typed httpx.Response stand-in for _admission_refusal."""

    def __init__(self, status_code: int, body: Any):
        self.status_code = status_code
        self._body = body
        self.text = json.dumps(body)

    def json(self) -> Any:
        return self._body


class _HttpError(Exception):
    """Duck-typed httpx.HTTPStatusError stand-in (carries .response)."""

    def __init__(self, status_code: int, body: Any):
        super().__init__(f"HTTP {status_code}")
        self.response = _FakeResponse(status_code, body)


def _registry_row(gpu_id: str) -> dict[str, Any] | None:
    async def _run() -> dict[str, Any] | None:
        from sqlalchemy import select

        from gpu_service.domain.gpu_market import GPURegistry
        from gpu_service.storage import get_session

        async with get_session() as session:
            row = (await session.execute(select(GPURegistry).where(GPURegistry.id == gpu_id))).scalars().first()
            return (
                None if row is None else {"id": row.id, "miner_id": row.miner_id, "chain_id": row.chain_id, "model": row.model}
            )

    return asyncio.run(_run())


@pytest.fixture
def client():
    app.dependency_overrides[main.require_gpu_api_key] = lambda: {"role": "gpu_admin"}
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


def _stub_submit(monkeypatch, result: dict[str, Any] | None = None, exc: Exception | None = None) -> list[dict]:
    calls: list[dict] = []

    async def fake(tx: dict[str, Any]) -> dict[str, Any]:
        calls.append(tx)
        if exc is not None:
            raise exc
        return result or {"transaction_hash": "0xdeadbeef123"}

    monkeypatch.setattr(main._rpc_client, "submit_transaction", fake)
    return calls


def _body(gpu_id: str, **extra: Any) -> dict[str, Any]:
    return {"type": "gpu_market", "action": "offer", "tx": _signed_tx(gpu_id), **extra}


def test_relays_signed_envelope_verbatim(client, monkeypatch):
    """The node must receive the exact bytes the wallet signed — no rebuilt
    fields, no re-fetched nonce, no remapped payload keys."""
    calls = _stub_submit(monkeypatch)
    # Legacy flat fields are also sent by old callers; the relayer must prefer `tx`.
    resp = client.post("/v1/transactions", json=_body("gpu_relay_a", provider_address="0xOther", signature="ignored"))
    assert resp.status_code == 200, resp.text
    assert calls == [_signed_tx("gpu_relay_a")], "relayer must forward the signed envelope unchanged"
    data = resp.json()
    assert data["blockchain_registered"] is True
    assert data["blockchain_tx_hash"] == "0xdeadbeef123"
    row = _registry_row("gpu_relay_a")
    assert row is not None
    assert row["miner_id"] == "miner-1" and row["chain_id"] == CHAIN and row["model"] == "A100"


def test_admission_refusal_is_relayed_not_masked(client, monkeypatch):
    """A 4xx from the node is an admission refusal: relay the verdict to the
    caller and write nothing locally (the old code logged 'falling back to
    local storage' and returned success — that is how failures went silent)."""
    _stub_submit(monkeypatch, exc=_HttpError(400, {"error": "payload must include gpu_id"}))
    resp = client.post("/v1/transactions", json=_body("gpu_relay_b"))
    assert resp.status_code == 400, resp.text
    detail = resp.json()["detail"]
    assert "gpu_id" in json.dumps(detail)
    assert _registry_row("gpu_relay_b") is None, "refused transaction must not leave a local row"


def test_transport_failure_falls_back_to_local_row(client, monkeypatch):
    """Connect/timeout class failures (no HTTP response) may still fall back:
    nothing reached the chain, so a local record is honest."""
    _stub_submit(monkeypatch, exc=ConnectionError("rpc unreachable"))
    resp = client.post("/v1/transactions", json=_body("gpu_relay_c"))
    assert resp.status_code == 200, resp.text
    assert resp.json()["blockchain_registered"] is False
    row = _registry_row("gpu_relay_c")
    assert row is not None and row["model"] == "A100"


def test_node_5xx_falls_back_to_local_row(client, monkeypatch):
    """A 5xx means the node is up but errored — not a refusal of the tx."""
    _stub_submit(monkeypatch, exc=_HttpError(503, {"error": "upstream unavailable"}))
    resp = client.post("/v1/transactions", json=_body("gpu_relay_d"))
    assert resp.status_code == 200, resp.text
    assert resp.json()["blockchain_registered"] is False
    assert _registry_row("gpu_relay_d") is not None


def test_missing_signed_tx_refused(client, monkeypatch):
    """The legacy flat body (specs+signature, no `tx`) can never produce a
    valid tx — refuse it with a pointer instead of silently rebuilding."""
    calls = _stub_submit(monkeypatch)
    resp = client.post(
        "/v1/transactions",
        json={
            "type": "gpu_market",
            "action": "offer",
            "provider_address": "0xProviderWallet",
            "offer_id": "gpu_relay_e",
            "specs": {"model": "A100", "memory_gb": 80},
            "provider_node_id": "miner-1",
            "price_per_gpu": 1.5,
            "signature": "ab" * 65,
        },
    )
    assert resp.status_code == 400, resp.text
    assert "tx" in resp.json()["error"]
    assert calls == []
    assert _registry_row("gpu_relay_e") is None
