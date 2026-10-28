"""FORK-OOB-1/#382 caller-side relays.

The GPU register/allocate RPC routes accept only a signed ``{"tx": …}``
envelope. These tests pin the relay contract of each caller that forwards
one: the market RPC client, pool-hub's ``register_miner_on_chain``, and the
``aitbc gpu onchain allocate`` builder (which must carry ``allocation_id``
in the payload so the caller knows which row is theirs).
"""

from __future__ import annotations

import re
from decimal import Decimal
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, MagicMock
import pytest


def _envelope(tx_type: str = "GPU_REGISTER") -> dict[str, Any]:
    return {
        "type": tx_type,
        "from": "0x" + "aa" * 20,
        "signature": "0x" + "ee" * 65,
        "chain_id": "bc-2",
        "payload": {"gpu_id": "gpu-1"},
    }


class _FakeAsyncClient:
    """Stand-in for httpx.AsyncClient returned by ``client._client()``."""

    def __init__(self) -> None:
        self.posts: list[tuple[str, dict[str, Any]]] = []
        self._resp = MagicMock()
        self._resp.json.return_value = {"status": "submitted", "tx_hash": "0x" + "ab" * 32}
        self._resp.raise_for_status = MagicMock()

    async def __aenter__(self) -> _FakeAsyncClient:
        return self

    async def __aexit__(self, *exc: object) -> None:
        return None

    async def post(self, url: str, json: dict[str, Any]) -> MagicMock:
        self.posts.append((url, json))
        return self._resp


@pytest.mark.asyncio
async def test_market_client_register_gpu_forwards_envelope() -> None:
    from aitbc.market.blockchain_rpc import BlockchainRPCClient

    client = BlockchainRPCClient(rpc_url="http://node.test:8202")
    fake = _FakeAsyncClient()
    client._client = lambda: fake  # type: ignore[method-assign]

    envelope = _envelope()
    result = await client.register_gpu(envelope)

    assert fake.posts == [("http://node.test:8202/rpc/gpu/register", {"tx": envelope})]
    assert result["tx_hash"] == "0x" + "ab" * 32


@pytest.mark.asyncio
async def test_market_client_allocate_gpu_forwards_envelope() -> None:
    from aitbc.market.blockchain_rpc import BlockchainRPCClient

    client = BlockchainRPCClient(rpc_url="http://node.test:8202")
    fake = _FakeAsyncClient()
    client._client = lambda: fake  # type: ignore[method-assign]

    envelope = _envelope("GPU_ALLOCATE")
    envelope["payload"]["allocation_id"] = "alloc_0123456789ab"
    await client.allocate_gpu(envelope)

    assert fake.posts == [("http://node.test:8202/rpc/gpu/allocate", {"tx": envelope})]


@pytest.mark.asyncio
async def test_poolhub_register_miner_on_chain_relays_envelope() -> None:
    """Pool-hub holds no miner key — it must forward the miner-signed
    envelope untouched rather than build an unsigned body."""
    from poolhub.clients.blockchain import PoolHubBlockchainClient

    client = PoolHubBlockchainClient()
    register = AsyncMock(return_value={"status": "submitted", "tx_hash": "0x1"})
    client._rpc = SimpleNamespace(register_gpu=register)  # type: ignore[assignment]

    envelope = _envelope()
    result = await client.register_miner_on_chain(envelope)

    register.assert_awaited_once_with(envelope)
    assert result["tx_hash"] == "0x1"


def test_submit_gpu_allocate_carries_allocation_id(monkeypatch) -> None:
    """The payload must name the allocation_id up front — the apply path can
    mint a random one the caller could never learn."""
    from aitbc_cli.utils import gpu_onchain

    captured: dict[str, Any] = {}

    def fake_build(ctx, rpc_url, chain_id, wallet, password, tx_type, payload, **kw):
        captured["payload"] = payload
        return {"type": tx_type, "payload": payload}, "deadbeef" * 8

    def fake_submit(rpc_url, tx):
        captured["tx"] = tx
        return {"transaction_hash": "0x" + "cd" * 32}

    monkeypatch.setattr(gpu_onchain, "_build_gpu_tx", fake_build)
    monkeypatch.setattr(gpu_onchain, "_sign_tx", lambda tx, key: "0x" + "ee" * 65)
    monkeypatch.setattr(gpu_onchain, "_submit_signed_tx", fake_submit)

    result = gpu_onchain.submit_gpu_allocate(
        ctx=None,
        rpc_url="http://node.test:8202",
        chain_id="bc-2",
        wallet="miner",
        password=None,
        gpu_id="gpu-1",
        client_id="0x" + "bb" * 20,
        duration_hours=2.0,
        total_cost=Decimal("10"),
    )

    allocation_id = captured["payload"]["allocation_id"]
    assert re.fullmatch(r"alloc_[0-9a-f]{12}", allocation_id)
    assert result["allocation_id"] == allocation_id
