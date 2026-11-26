"""#3012 pins: orphan-sweep starvation + dry-run purity.

``run_once`` selects the oldest-due ``batch_size`` entries every pass.
Before the fix, outcomes that leave a row eligible — failed chain reads,
deferred (425) and failed refunds, CAS-loss skips — never stamped
``orphan_probe_at``, so a full batch of persistent entry-specific failures
sat at the head of every oldest-first batch and later recoverable escrows
were never examined. The fix stamps the probe attempt on EVERY
still-eligible outcome, rotating failures onto the grace cadence while
leaving adopted/refunded rows terminal. ``dry_run`` must persist nothing —
including the skip-branch probe stamp and the distributed tombstone.
"""

from __future__ import annotations

import os
import time
from unittest.mock import MagicMock

import pytest

os.environ.setdefault("SECRET_KEY", "test-secret-key")
os.environ.setdefault("JWT_SECRET", "test-secret-for-agent-coordinator-tests" * 2)

pytest.importorskip("fastapi", reason="agent-coordinator app dependencies not installed")

import httpx  # noqa: E402

from agent_app.services.chain_escrow import ChainEscrowClient  # noqa: E402
from agent_app.services.orphan_escrow_sweeper import (  # noqa: E402
    META_ORPHAN_PROBE_AT,
    OrphanedTaskEscrowSweeper,
)

from aitbc.crypto import EscrowStatus, PaymentEscrow  # noqa: E402
from aitbc.crypto.payment_escrow import META_WAS_DISTRIBUTED_AT  # noqa: E402

CHAIN_ID = "ait-test-chain"
TASK_FAIL_A = "atask_fail_a"
TASK_FAIL_B = "atask_fail_b"
TASK_HEALTHY = "atask_healthy"
TASK_DEFER = "atask_defer"
SETTLEMENT_KEY = "test-settlement-key"


def _pending_entry(escrow: PaymentEscrow, task_id: str, age: float = 10_000.0):
    entry = escrow.create_escrow(
        task_id=task_id,
        chain_id=CHAIN_ID,
        requester="0xBuyer",
        agent="0xAgent",
        amount=100,
        fee=1,
    )
    entry.created_at = time.time() - age
    return entry


def _live_record(task_id: str) -> dict:
    return {
        "job_id": task_id,
        "contract_id": "contract-1",
        "state": "funded",
        "status": "locked",
        "buyer": "0xBuyer",
        "provider": "0xAgent",
        "amount": "0.05",
        "released_amount": "0",
        "lock_tx_hash": "0x" + "cd" * 32,
        "created_at": "2026-11-26T10:16:08+00:00",
    }


class _ChainHandler:
    """Per-task scripted handler: ``fail_ids`` get a 500, ``defer_ids`` a
    425 refund, everything else serves ``records`` / a successful refund."""

    def __init__(
        self,
        records: dict[str, dict | None],
        fail_ids: set[str] | None = None,
        defer_ids: set[str] | None = None,
    ):
        self.records = records
        self.fail_ids = fail_ids or set()
        self.defer_ids = defer_ids or set()
        self.gets: list[str] = []
        self.refunds: list[str] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if request.method == "GET" and path.startswith("/rpc/escrow/"):
            job_id = path.rsplit("/", 1)[-1]
            self.gets.append(job_id)
            if job_id in self.fail_ids:
                return httpx.Response(500, json={"detail": "down"}, request=request)
            record = self.records.get(job_id)
            if record is None:
                return httpx.Response(404, json={"detail": "not found"}, request=request)
            return httpx.Response(200, json=record, request=request)
        if request.method == "POST" and path.endswith("/refund"):
            job_id = path.split("/")[-2]
            self.refunds.append(job_id)
            if job_id in self.defer_ids:
                return httpx.Response(425, json={"detail": "lock not sealed"}, headers={"Retry-After": "1"}, request=request)
            return httpx.Response(200, json={"success": True, "refund_tx_hash": "0x" + "ef" * 32}, request=request)
        return httpx.Response(404, json={"detail": "unrouted"}, request=request)


def _client(handler: _ChainHandler) -> ChainEscrowClient:
    return ChainEscrowClient(
        "http://rpc.test",
        api_key="api-key",
        settlement_api_key=SETTLEMENT_KEY,
        transport=httpx.MockTransport(handler),
    )


def _sweeper(escrow: PaymentEscrow, client: ChainEscrowClient, lb=None, **kwargs) -> OrphanedTaskEscrowSweeper:
    return OrphanedTaskEscrowSweeper(
        payment_escrow=escrow,
        escrow_rpc=client,
        load_balancer=lb,
        grace_seconds=kwargs.pop("grace_seconds", 900.0),
        batch_size=kwargs.pop("batch_size", 25),
        **kwargs,
    )


def _no_assignment() -> MagicMock:
    lb = MagicMock()
    lb.get_assignment = MagicMock(return_value=None)
    return lb


class TestStarvation:
    def test_failed_reads_rotate_healthy_entry_into_batch(self):
        """Headline defect: a full batch of persistent read failures must
        not starve a later recoverable escrow. batch_size=2, two oldest
        entries 500 forever, a newer healthy orphan waits — pass 1 burns
        the failures (stamped), pass 2 reaches the healthy row and refunds."""
        escrow = PaymentEscrow()
        _pending_entry(escrow, TASK_FAIL_A, age=30_000.0)
        _pending_entry(escrow, TASK_FAIL_B, age=20_000.0)
        healthy = _pending_entry(escrow, TASK_HEALTHY, age=10_000.0)
        handler = _ChainHandler(
            {TASK_HEALTHY: _live_record(TASK_HEALTHY)},
            fail_ids={TASK_FAIL_A, TASK_FAIL_B},
        )
        sweeper = _sweeper(escrow, _client(handler), lb=_no_assignment(), batch_size=2)

        first = sweeper.run_once()
        assert first["candidates"] == 2
        assert first["failed"] == 2
        assert TASK_HEALTHY not in handler.gets

        second = sweeper.run_once()

        assert second["candidates"] == 1
        assert second["refunded"] == 1
        assert TASK_HEALTHY in handler.gets
        assert handler.refunds == [TASK_HEALTHY]
        assert escrow.get_escrow(healthy.escrow_id).status == EscrowStatus.REFUNDED

    def test_deferred_refunds_rotate_too(self):
        """425-deferred refunds are still-eligible — same starvation class."""
        escrow = PaymentEscrow()
        _pending_entry(escrow, TASK_FAIL_A, age=30_000.0)
        _pending_entry(escrow, TASK_FAIL_B, age=20_000.0)
        _pending_entry(escrow, TASK_DEFER, age=10_000.0)
        handler = _ChainHandler(
            {TASK_DEFER: _live_record(TASK_DEFER)},
            fail_ids={TASK_FAIL_A, TASK_FAIL_B},
            defer_ids={TASK_DEFER},
        )
        sweeper = _sweeper(escrow, _client(handler), lb=_no_assignment(), batch_size=2)

        sweeper.run_once()  # burns the two read failures
        second = sweeper.run_once()

        assert second["candidates"] == 1
        assert second["deferred"] == 1
        # The deferred row is stamped — a third pass must not re-pick it.
        third = sweeper.run_once()
        assert third["candidates"] == 0


class TestBoundedRetry:
    def test_failed_read_stamps_probe_and_retries_on_cadence(self):
        """A failed read stamps orphan_probe_at: no immediate re-probe, but
        the entry becomes due again once the stamp ages past grace."""
        escrow = PaymentEscrow()
        entry = _pending_entry(escrow, TASK_FAIL_A)
        handler = _ChainHandler({}, fail_ids={TASK_FAIL_A})
        sweeper = _sweeper(escrow, _client(handler), lb=_no_assignment())

        counts = sweeper.run_once()

        assert counts["failed"] == 1
        assert META_ORPHAN_PROBE_AT in entry.metadata
        assert len(handler.gets) == 1

        # Immediate second pass: stamped → not due → no chain call.
        assert sweeper.run_once()["candidates"] == 0
        assert len(handler.gets) == 1

        # Once the stamp ages past grace the entry retries — bounded, not lost.
        entry.metadata[META_ORPHAN_PROBE_AT] = time.time() - 10_000.0
        assert sweeper.run_once()["failed"] == 1
        assert len(handler.gets) == 2

    def test_cas_loss_skip_rotates(self):
        """A refund CAS loss (concurrent transition won) leaves the row
        eligible — it must stamp rather than pin the batch head."""
        escrow = PaymentEscrow()
        entry = _pending_entry(escrow, TASK_DEFER)

        def racing_refund(*_a, **_kw):
            raise ValueError("concurrent transition won")

        escrow.refund_orphaned = racing_refund  # type: ignore[method-assign]
        handler = _ChainHandler({TASK_DEFER: _live_record(TASK_DEFER)})
        sweeper = _sweeper(escrow, _client(handler), lb=_no_assignment())

        counts = sweeper.run_once()

        assert counts["skipped"] == 1
        assert META_ORPHAN_PROBE_AT in entry.metadata
        assert sweeper.run_once()["candidates"] == 0


class TestDryRunPurity:
    def test_dry_run_skip_branch_persists_no_probe_stamp(self):
        """Settled/missing record → skip branch: dry-run must not write
        orphan_probe_at (previously it did — a dry-run was not pure)."""
        escrow = PaymentEscrow()
        entry = _pending_entry(escrow, TASK_DEFER)
        settled = _live_record(TASK_DEFER)
        settled["state"] = "refunded"
        settled["refunded_at"] = "2026-11-26T11:00:00+00:00"
        handler = _ChainHandler({TASK_DEFER: settled})
        sweeper = _sweeper(
            escrow,
            _client(handler),
            lb=_no_assignment(),
            dry_run=True,
        )

        counts = sweeper.run_once()

        assert counts["skipped"] == 1
        assert META_ORPHAN_PROBE_AT not in entry.metadata
        # And the row stays due — a dry-run observes, it does not schedule.
        assert sweeper.run_once()["candidates"] == 1

    def test_dry_run_distributed_adopt_persists_no_tombstone(self):
        """Live assignment + stranded record in dry-run: the distributed
        tombstone is bookkeeping — dry-run must not write it."""
        escrow = PaymentEscrow()
        entry = _pending_entry(escrow, TASK_DEFER)
        handler = _ChainHandler({TASK_DEFER: _live_record(TASK_DEFER)})
        lb = MagicMock()
        lb.get_assignment = MagicMock(return_value=MagicMock(status="pending"))
        sweeper = _sweeper(escrow, _client(handler), lb=lb, dry_run=True)

        counts = sweeper.run_once()

        assert counts["adopted"] == 1
        assert META_WAS_DISTRIBUTED_AT not in entry.metadata
        assert escrow.get_escrow(entry.escrow_id).status == EscrowStatus.PENDING

    def test_dry_run_failed_read_persists_no_probe_stamp(self):
        escrow = PaymentEscrow()
        entry = _pending_entry(escrow, TASK_FAIL_A)
        handler = _ChainHandler({}, fail_ids={TASK_FAIL_A})
        sweeper = _sweeper(escrow, _client(handler), lb=_no_assignment(), dry_run=True)

        counts = sweeper.run_once()

        assert counts["failed"] == 1
        assert META_ORPHAN_PROBE_AT not in entry.metadata
