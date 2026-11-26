"""#3016 AUDIT-ESCROW-LOCK-CONFIRM-PROOF-1 pins — sealed-only tx proof.

``_lookup_chain_lock``/``_lookup_chain_refund`` returned the first tx whose
payload named the job — ``/rpc/transactions`` also serves stored rejected
and pending results, so a dead envelope satisfied the funding proof. Both
lookups now require ``status="confirmed"`` plus a non-null
``block_height`` — the same bar ``SettlementReconciler`` applies.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock

import pytest

from coordinator_api.contexts.payments.services.payments_helpers import (
    _lookup_chain_lock,
    _lookup_chain_refund,
    _sealed_tx_hash,
)

JOB = "job-3016"
RPC = "http://node"


def _tx(tx_hash: str, *, status: str, block_height: int | None, job_id: str = JOB) -> dict[str, Any]:
    return {
        "tx_hash": tx_hash,
        "status": status,
        "block_height": block_height,
        "payload": {"job_id": job_id},
    }


class _Client:
    def __init__(self, payload: Any) -> None:
        self._payload = payload
        self.get_json = AsyncMock(return_value=payload)


class TestSealedTxHash:
    def test_confirmed_with_height_satisfies(self) -> None:
        txs = [_tx("0xdead", status="rejected", block_height=None), _tx("0xlive", status="confirmed", block_height=42)]
        assert _sealed_tx_hash(txs, JOB) == "0xlive"

    def test_rejected_only_returns_none(self) -> None:
        assert _sealed_tx_hash([_tx("0xdead", status="rejected", block_height=None)], JOB) is None

    def test_pending_only_returns_none(self) -> None:
        assert _sealed_tx_hash([_tx("0xp", status="pending", block_height=None)], JOB) is None

    def test_confirmed_without_height_returns_none(self) -> None:
        """Malformed: confirmed status but no block height is not sealed."""
        assert _sealed_tx_hash([_tx("0xm", status="confirmed", block_height=None)], JOB) is None

    def test_missing_status_returns_none(self) -> None:
        tx = _tx("0xn", status="confirmed", block_height=7)
        del tx["status"]
        assert _sealed_tx_hash([tx], JOB) is None

    def test_foreign_job_id_ignored(self) -> None:
        txs = [_tx("0xother", status="confirmed", block_height=3, job_id="other-job")]
        assert _sealed_tx_hash(txs, JOB) is None

    def test_non_dict_rows_ignored(self) -> None:
        assert _sealed_tx_hash(["garbage", None, 42], JOB) is None


class TestLookupChainLock:
    @pytest.mark.asyncio
    async def test_rejected_lock_does_not_satisfy(self) -> None:
        client = _Client([_tx("0xrej", status="rejected", block_height=None)])
        assert await _lookup_chain_lock(RPC, client, JOB) is None

    @pytest.mark.asyncio
    async def test_confirmed_lock_accepted_despite_newer_rejected(self) -> None:
        client = _Client(
            [
                _tx("0xold-good", status="confirmed", block_height=10),
                _tx("0xnew-dead", status="rejected", block_height=None),
            ]
        )
        assert await _lookup_chain_lock(RPC, client, JOB) == "0xold-good"

    @pytest.mark.asyncio
    async def test_sealed_lock_still_returned(self) -> None:
        client = _Client([_tx("0xlive", status="confirmed", block_height=99)])
        assert await _lookup_chain_lock(RPC, client, JOB) == "0xlive"


class TestLookupChainRefund:
    @pytest.mark.asyncio
    async def test_rejected_refund_does_not_satisfy(self) -> None:
        client = _Client([_tx("0xrej", status="rejected", block_height=None)])
        assert await _lookup_chain_refund(RPC, client, JOB) is None

    @pytest.mark.asyncio
    async def test_confirmed_refund_returned(self) -> None:
        client = _Client([_tx("0xref", status="confirmed", block_height=55)])
        assert await _lookup_chain_refund(RPC, client, JOB) == "0xref"
