"""#3049 pins (market): a settle tx that sealed into a block but FAILED to
apply (``status='failed'`` + ``block_height``) moved no value. Both market
sweepers must treat it as NOT sealed-for-money and keep deferring — the
old ``block_height is not None`` check adopted it as settled.
"""

from __future__ import annotations

import sys
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from market_service.services.ipfs_rental_sweeper import IpfsRentalSweeper
from market_service.services.market_job_sweeper import MarketJobSweeper


class _StubRPC:
    """verify_escrow reports a settled verdict; get_transaction answers
    with a scripted row — the failed-sealed shape under test."""

    def __init__(self, tx: dict[str, Any] | None) -> None:
        self._tx = tx
        self.get_tx_calls: list[str] = []

    async def verify_escrow(self, job_id: str) -> dict[str, Any] | None:
        return {"state": "released", "release_tx_hash": "0xsettle"}

    async def get_transaction(self, tx_hash: str) -> dict[str, Any] | None:
        self.get_tx_calls.append(tx_hash)
        return self._tx


_FAILED_SEALED = {"tx_hash": "0xsettle", "status": "failed", "block_height": 4321}
_CONFIRMED_SEALED = {"tx_hash": "0xsettle", "status": "confirmed", "block_height": 4321}


@pytest.mark.asyncio
class TestIpfsRentalAdoption:
    async def test_failed_sealed_verdict_is_not_adopted(self):
        rpc = _StubRPC(dict(_FAILED_SEALED))
        sweeper = IpfsRentalSweeper(batch_size=1, refund_grace_seconds=0, rpc_client=rpc)  # type: ignore[arg-type]

        adopted = await sweeper._adopt_sealed_verdict("job-1")

        assert adopted is None
        assert rpc.get_tx_calls == ["0xsettle"]

    async def test_confirmed_sealed_verdict_still_adopted(self):
        rpc = _StubRPC(dict(_CONFIRMED_SEALED))
        sweeper = IpfsRentalSweeper(batch_size=1, refund_grace_seconds=0, rpc_client=rpc)  # type: ignore[arg-type]

        adopted = await sweeper._adopt_sealed_verdict("job-1")

        assert adopted == ("0xsettle", "released")


@pytest.mark.asyncio
class TestJobSweeperVerdict:
    async def _verdict(self, tx: dict[str, Any] | None) -> bool:
        rpc = _StubRPC(tx)
        sweeper = MarketJobSweeper(batch_size=1, rpc_client=rpc)  # type: ignore[arg-type]
        job = SimpleNamespace(id="job-1")
        payment = SimpleNamespace(id="pay-1")
        escrow = {"state": "released", "release_tx_hash": "0xsettle"}
        return await sweeper._settlement_verdict(
            AsyncMock(),  # session — untouched on the unsealed early return
            job,  # type: ignore[arg-type]
            payment,  # type: ignore[arg-type]
            {},
            escrow,
            "released",
            "released",
            datetime.now(UTC),
            10_000.0,
        )

    async def test_failed_sealed_keeps_deferring(self):
        assert await self._verdict(dict(_FAILED_SEALED)) is False

    async def test_confirmed_sealed_reaches_adoption(self):
        # Control: confirmed+height opens the seal gate and reaches
        # _adopt_escrow_verdict (the adoption itself is #2860's covered
        # behavior — here we only prove the gate no longer returns early).
        rpc = _StubRPC(dict(_CONFIRMED_SEALED))
        sweeper = MarketJobSweeper(batch_size=1, rpc_client=rpc)  # type: ignore[arg-type]
        adopt = AsyncMock(return_value=True)
        sweeper._adopt_escrow_verdict = adopt  # type: ignore[method-assign]
        job = SimpleNamespace(id="job-1")
        payment = SimpleNamespace(id="pay-1")
        escrow = {"state": "released", "release_tx_hash": "0xsettle"}

        result = await sweeper._settlement_verdict(
            AsyncMock(),  # type: ignore[arg-type]
            job,  # type: ignore[arg-type]
            payment,  # type: ignore[arg-type]
            {},
            escrow,
            "released",
            "released",
            datetime.now(UTC),
            10_000.0,
        )

        assert result is True
        adopt.assert_awaited_once()
