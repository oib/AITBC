"""#3049 pins: the escrow idempotency finders must only adopt
confirmed+sealed rows. ``sync_block_import`` stores apply-failed txs as
``status='failed'`` WITH a ``block_height`` — the old no-status-filter
lookup returned them as "the settled lock/release", so every retry
reported the job settled and the provider was never paid.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from aitbc_chain.rpc import escrow_routes


def _reload_routes():
    import importlib

    return importlib.reload(escrow_routes)


def _resp(rows: list[dict]):
    r = MagicMock()
    r.status_code = 200
    r.json.return_value = rows
    return r


def _row(tx_hash: str, job_id: str, status: str, height: int | None) -> dict:
    return {
        "tx_hash": tx_hash,
        "type": "ESCROW_RELEASE",
        "payload": {"job_id": job_id},
        "status": status,
        "block_height": height,
    }


@pytest.fixture
def routes(monkeypatch):
    monkeypatch.setenv("HUB_RPC_URL", "http://localhost:8202")
    return _reload_routes()


class TestFailedSealedNeverDedupes:
    """An apply-failed leg moved no value — the finder must answer 'absent'
    so the retry re-drives it, never 'already settled'."""

    @pytest.mark.asyncio
    async def test_release_failed_sealed_is_invisible(self, routes):
        rows = [_row("0xdead", "job-1", "failed", 4321)]
        with patch.object(routes.SharedHttpClient, "get", new_callable=AsyncMock, return_value=_resp(rows)):
            assert await routes._find_existing_release("job-1") is None

    @pytest.mark.asyncio
    async def test_refund_failed_sealed_is_invisible(self, routes):
        rows = [_row("0xdead", "job-1", "failed", 4321)]
        with patch.object(routes.SharedHttpClient, "get", new_callable=AsyncMock, return_value=_resp(rows)):
            assert await routes._find_existing_refund("job-1") is None

    @pytest.mark.asyncio
    async def test_lock_failed_sealed_is_invisible(self, routes):
        rows = [_row("0xdead", "job-1", "failed", 4321)]
        with patch.object(routes.SharedHttpClient, "get", new_callable=AsyncMock, return_value=_resp(rows)):
            row, probe_ok = await routes._find_existing_lock_tx_status("job-1")
            assert row is None
            assert probe_ok is True

    @pytest.mark.asyncio
    async def test_fee_sweep_and_receipt_claim_failed_sealed_invisible(self, routes):
        rows = [_row("0xdead", "job-1", "failed", 4321)]
        with patch.object(routes.SharedHttpClient, "get", new_callable=AsyncMock, return_value=_resp(rows)):
            assert await routes._find_existing_fee_sweep("job-1") is None
            assert await routes._find_existing_receipt_claim("job-1") is None

    @pytest.mark.asyncio
    async def test_rejected_row_is_invisible(self, routes):
        rows = [_row("0xdead", "job-1", "rejected", None)]
        with patch.object(routes.SharedHttpClient, "get", new_callable=AsyncMock, return_value=_resp(rows)):
            assert await routes._find_existing_release("job-1") is None


class TestConfirmedStillDedupes:
    @pytest.mark.asyncio
    async def test_release_skips_failed_and_finds_confirmed(self, routes):
        """Newest-first: a failed retry attempt above the original
        confirmed settle must not hide it — the confirmed row still
        dedupes (money DID move via the first attempt)."""
        rows = [
            _row("0xfailed-retry", "job-1", "failed", 5000),
            _row("0xpaid", "job-1", "confirmed", 4000),
        ]
        with patch.object(routes.SharedHttpClient, "get", new_callable=AsyncMock, return_value=_resp(rows)):
            assert await routes._find_existing_release("job-1") == "0xpaid"

    @pytest.mark.asyncio
    async def test_all_finders_return_confirmed_hash(self, routes):
        rows = [_row("0xok", "job-1", "confirmed", 4321)]
        with patch.object(routes.SharedHttpClient, "get", new_callable=AsyncMock, return_value=_resp(rows)):
            assert await routes._find_existing_release("job-1") == "0xok"
            assert await routes._find_existing_refund("job-1") == "0xok"
            assert await routes._find_existing_fee_sweep("job-1") == "0xok"
            assert await routes._find_existing_receipt_claim("job-1") == "0xok"
            row, _ = await routes._find_existing_lock_tx_status("job-1")
            assert row is not None and row["tx_hash"] == "0xok"

    @pytest.mark.asyncio
    async def test_height_without_confirmed_status_is_invisible(self, routes):
        """A durable row with a height but no 'confirmed' status is not
        proven-applied — same strict rule as the wallet predicate."""
        rows = [{"tx_hash": "0xodd", "payload": {"job_id": "job-1"}, "block_height": 9}]
        with patch.object(routes.SharedHttpClient, "get", new_callable=AsyncMock, return_value=_resp(rows)):
            assert await routes._find_existing_release("job-1") is None
