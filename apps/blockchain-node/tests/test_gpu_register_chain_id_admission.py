"""GPU_REGISTER market branch: a request chain_id outside supported_chains must not reach mempool.add.

The GPU_REGISTER arm of submit_market_transaction skipped _validate_transaction_admission entirely — its
supported-chain check included — so a signed GPU_REGISTER naming an arbitrary chain_id entered the mempool under
that chain and minted blockchain_mempool_pending_*{chain_id=...} series for chains the node does not produce.
The supported-chain check now runs inside that branch too (C18); the rest of the branch is unchanged.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock, patch

import pytest
from fastapi import HTTPException

from aitbc.crypto.crypto import derive_ethereum_address
from aitbc.utils import DEFAULT_TX_FEE_UNITS
from aitbc_chain.mempool import InMemoryMempool
from aitbc_chain.metrics import mempool_pending_count
from aitbc_chain.rpc import transactions as tx_mod
from aitbc_chain.rpc.utils import sign_transaction_data

CHAIN = "ait-test"
FOREIGN = "ait-foreign-c18"
KEY = "0x" + "33" * 32
SENDER = derive_ethereum_address(KEY)


def _register_tx(chain_id: str = CHAIN) -> dict[str, Any]:
    tx: dict[str, Any] = {
        "from": SENDER,
        "to": SENDER,
        "amount": 0,
        "fee": DEFAULT_TX_FEE_UNITS,
        "nonce": 0,
        "type": "GPU_REGISTER",
        "chain_id": chain_id,
        "payload": {"gpu_id": "gpu-c18-1", "miner_id": "miner-1", "model": "RTX 4090", "memory_gb": 24},
    }
    tx["signature"] = sign_transaction_data(tx, KEY)
    return tx


@pytest.fixture
def supported(monkeypatch):
    monkeypatch.setattr("aitbc_chain.rpc.utils.get_supported_chains", lambda: [CHAIN])


def _pending_series_chains() -> set[str]:
    return {sample.labels["chain_id"] for metric in mempool_pending_count.collect() for sample in metric.samples}


@pytest.mark.asyncio
class TestMarketRouteChainAdmission:
    async def _submit(self, tx: dict[str, Any], mempool: Any) -> tuple[Any, Any]:
        with patch("aitbc_chain.mempool.get_mempool", return_value=mempool), patch.object(tx_mod, "_queue_peer_fanout"):
            try:
                return await tx_mod.submit_market_transaction(MagicMock(), tx), mempool
            except HTTPException as exc:
                return exc, mempool

    def _mock_pool(self) -> MagicMock:
        pool = MagicMock()
        pool.add = MagicMock(return_value="0xtxhash")
        return pool

    async def test_refuses_an_unsupported_chain_id_and_queues_nothing(self, supported):
        result, mempool = await self._submit(_register_tx(FOREIGN), self._mock_pool())
        assert isinstance(result, HTTPException) and result.status_code == 400
        assert "unsupported chain_id" in result.detail and FOREIGN in result.detail
        mempool.add.assert_not_called()

    async def test_admits_a_supported_chain_id(self, supported):
        result, mempool = await self._submit(_register_tx(CHAIN), self._mock_pool())
        assert isinstance(result, dict) and result["success"] is True
        mempool.add.assert_called_once()
        assert mempool.add.call_args.kwargs["chain_id"] == CHAIN

    async def test_a_refused_chain_id_mints_no_mempool_gauge_series(self, supported):
        pool = InMemoryMempool(chain_id=CHAIN)
        result, _ = await self._submit(_register_tx(FOREIGN), pool)
        assert isinstance(result, HTTPException) and result.status_code == 400
        assert FOREIGN not in _pending_series_chains()

        # belt: prove the wiring really mints on admission, so the absence above is refusal, not a dead gauge
        ok, _ = await self._submit(_register_tx(CHAIN), pool)
        assert isinstance(ok, dict) and ok["success"] is True
        assert CHAIN in _pending_series_chains()
