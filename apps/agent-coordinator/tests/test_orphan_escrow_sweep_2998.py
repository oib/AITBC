"""#2998 pins: an atask escrow whose on-chain ESCROW_LOCK landed while the
local row never reached LOCKED must be reconciled, not stranded.

``PaymentEscrow.lock`` records LOCKED only after the chain answers; an
ambiguous submit (502 after the lock was accepted, lost response, exhausted
425 retries) leaves the row PENDING with ``tx_hash_lock=None`` — invisible
to ``expire_stale`` (LOCKED-only) and to both existing sweepers. The orphan
reconciler point-reads ``GET /rpc/escrow/{task_id}`` and either adopts the
lock (task was distributed — heal bookkeeping) or refunds it (submit died
before distribution — nobody can claim the escrow).
"""

from __future__ import annotations

import os
import time
from unittest.mock import AsyncMock, MagicMock

import pytest

os.environ.setdefault("SECRET_KEY", "test-secret-key")
os.environ.setdefault("JWT_SECRET", "test-secret-for-agent-coordinator-tests" * 2)

pytest.importorskip("fastapi", reason="agent-coordinator app dependencies not installed")

import httpx  # noqa: E402
from fastapi import FastAPI  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from agent_app.config import settings  # noqa: E402
from agent_app.lifespan import _orphan_sweep_once  # noqa: E402
from agent_app.routers import tasks as tasks_router  # noqa: E402
from agent_app.services.chain_escrow import ChainEscrowClient, EscrowRPCError  # noqa: E402
from agent_app.services.orphan_escrow_sweeper import (  # noqa: E402
    META_ORPHAN_PROBE_AT,
    ORPHAN_REFUND_REASON,
    OrphanedTaskEscrowSweeper,
    escrow_record_is_stranded,
)

from aitbc.crypto import EscrowStatus, PaymentEscrow  # noqa: E402

CHAIN_ID = "ait-test-chain"
TASK_ID = "atask_20261126101608_c9252014"
SETTLEMENT_KEY = "test-settlement-key"


def _pending_entry(escrow: PaymentEscrow, task_id: str = TASK_ID, age: float = 10_000.0):
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


def _rejected_entry(escrow: PaymentEscrow, task_id: str = TASK_ID):
    entry = _pending_entry(escrow, task_id)
    entry.status = EscrowStatus.REJECTED
    return entry


def _locked_entry(escrow: PaymentEscrow, task_id: str = "task-healthy"):
    entry = escrow.create_escrow(
        task_id=task_id,
        chain_id=CHAIN_ID,
        requester="0xBuyer",
        agent="0xAgent",
        amount=100,
    )
    entry.created_at = time.time() - 10_000.0
    escrow.lock(entry.escrow_id, submitter=lambda *_a: "0x" + "ab" * 32)
    return entry


def _live_record(task_id: str = TASK_ID) -> dict:
    """The chain's escrow record for a funded, unsettled lock."""
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
    """MockTransport handler recording calls; escrow GET/refund are scripted."""

    def __init__(self, records: dict[str, dict | None], refund_status: int = 200):
        self.records = records
        self.refund_status = refund_status
        self.gets: list[str] = []
        self.refunds: list[tuple[str, dict, dict]] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if request.method == "GET" and path.startswith("/rpc/escrow/"):
            job_id = path.rsplit("/", 1)[-1]
            self.gets.append(job_id)
            record = self.records.get(job_id)
            if record is None:
                return httpx.Response(404, json={"detail": "not found"}, request=request)
            return httpx.Response(200, json=record, request=request)
        if request.method == "POST" and path.endswith("/refund"):
            job_id = path.split("/")[-2]
            body = {}
            try:
                import json

                body = json.loads(request.content or b"{}")
            except ValueError:
                pass
            self.refunds.append((job_id, body, dict(request.headers)))
            if self.refund_status == 425:
                return httpx.Response(425, json={"detail": "lock not sealed"}, headers={"Retry-After": "1"}, request=request)
            if self.refund_status != 200:
                return httpx.Response(self.refund_status, json={"detail": "boom"}, request=request)
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


class TestOrphanRefund:
    def test_orphan_pending_with_live_lock_is_refunded(self):
        """The headline defect: chain locked, local row stuck PENDING, no
        assignment (submit died before distribution) → refund on-chain and
        mark the row REFUNDED."""
        escrow = PaymentEscrow()
        entry = _pending_entry(escrow)
        handler = _ChainHandler({TASK_ID: _live_record()})
        sweeper = _sweeper(escrow, _client(handler), lb=MagicMock(get_assignment=MagicMock(return_value=None)))

        counts = sweeper.run_once()

        assert counts["refunded"] == 1
        assert len(handler.refunds) == 1
        refunded_job, refund_body, refund_headers = handler.refunds[0]
        assert refunded_job == TASK_ID
        assert refund_body == {"reason": ORPHAN_REFUND_REASON}
        # The refund went out with the settlement credential (#1917).
        assert refund_headers.get("x-settlement-key") == SETTLEMENT_KEY
        refreshed = escrow.get_escrow(entry.escrow_id)
        assert refreshed.status == EscrowStatus.REFUNDED
        assert refreshed.tx_hash_refund == "0x" + "ef" * 32
        assert refreshed.metadata["orphan_refund"] is True

    def test_second_run_is_idempotent(self):
        escrow = PaymentEscrow()
        _pending_entry(escrow)
        handler = _ChainHandler({TASK_ID: _live_record()})
        sweeper = _sweeper(escrow, _client(handler), lb=MagicMock(get_assignment=MagicMock(return_value=None)))

        assert sweeper.run_once()["refunded"] == 1
        # The row is terminal now — and even if the chain record still read
        # live, no candidate remains and the chain refund dedups per job id.
        counts = sweeper.run_once()
        assert counts["candidates"] == 0
        assert len(handler.refunds) == 1

    def test_rejected_row_with_live_lock_is_refunded(self):
        """REJECTED is terminal for the *recorded* lock tx; a different sealed
        lock for the same job id can still hold funds — the chain read wins."""
        escrow = PaymentEscrow()
        entry = _rejected_entry(escrow)
        handler = _ChainHandler({TASK_ID: _live_record()})
        sweeper = _sweeper(escrow, _client(handler), lb=MagicMock(get_assignment=MagicMock(return_value=None)))

        counts = sweeper.run_once()

        assert counts["refunded"] == 1
        assert escrow.get_escrow(entry.escrow_id).status == EscrowStatus.REFUNDED

    def test_distributed_task_adopts_lock_instead_of_refunding(self):
        """A live assignment means the task was distributed — the escrow
        belongs to real work: heal the row to LOCKED, never refund it."""
        escrow = PaymentEscrow()
        entry = _pending_entry(escrow)
        handler = _ChainHandler({TASK_ID: _live_record()})
        assignment = MagicMock(status="pending")
        lb = MagicMock()
        lb.get_assignment = MagicMock(return_value=assignment)
        sweeper = _sweeper(escrow, _client(handler), lb=lb)

        counts = sweeper.run_once()

        assert counts["adopted"] == 1
        assert handler.refunds == []
        refreshed = escrow.get_escrow(entry.escrow_id)
        assert refreshed.status == EscrowStatus.LOCKED
        assert refreshed.tx_hash_lock == "0x" + "cd" * 32
        assert refreshed.contract_id == "contract-1"
        assert refreshed.metadata["contract_id"] == "contract-1"


class TestOrphanSkips:
    def test_healthy_locked_row_untouched(self):
        """A normal LOCKED escrow is the expire sweeper's job, not ours."""
        escrow = PaymentEscrow()
        _locked_entry(escrow)
        handler = _ChainHandler({})
        sweeper = _sweeper(escrow, _client(handler))

        counts = sweeper.run_once()

        assert counts["candidates"] == 0
        assert handler.gets == [] and handler.refunds == []

    def test_settled_chain_record_untouched(self):
        escrow = PaymentEscrow()
        entry = _pending_entry(escrow)
        record = _live_record()
        record["refunded_at"] = "2026-11-26T11:00:00+00:00"
        record["state"] = "refunded"
        handler = _ChainHandler({TASK_ID: record})
        sweeper = _sweeper(escrow, _client(handler), lb=MagicMock(get_assignment=MagicMock(return_value=None)))

        counts = sweeper.run_once()

        assert counts["skipped"] == 1
        assert handler.refunds == []
        assert escrow.get_escrow(entry.escrow_id).status == EscrowStatus.PENDING
        # The definitive probe is stamped so the row re-checks on the grace
        # cadence, not every sweep.
        assert META_ORPHAN_PROBE_AT in entry.metadata

    def test_missing_chain_record_untouched(self):
        """404 = nothing was ever locked (bookkeeping-only PENDING escrow)."""
        escrow = PaymentEscrow()
        entry = _pending_entry(escrow)
        handler = _ChainHandler({})
        sweeper = _sweeper(escrow, _client(handler), lb=MagicMock(get_assignment=MagicMock(return_value=None)))

        counts = sweeper.run_once()

        assert counts["skipped"] == 1
        assert handler.refunds == []
        assert escrow.get_escrow(entry.escrow_id).status == EscrowStatus.PENDING

    def test_within_grace_is_skipped_without_chain_call(self):
        escrow = PaymentEscrow()
        _pending_entry(escrow, age=10.0)  # created 10s ago, grace is 900s
        handler = _ChainHandler({TASK_ID: _live_record()})
        sweeper = _sweeper(escrow, _client(handler), lb=MagicMock(get_assignment=MagicMock(return_value=None)))

        counts = sweeper.run_once()

        assert counts["candidates"] == 0
        assert handler.gets == []

    def test_425_refund_defers_without_mutating(self):
        escrow = PaymentEscrow()
        entry = _pending_entry(escrow)
        handler = _ChainHandler({TASK_ID: _live_record()}, refund_status=425)
        sweeper = _sweeper(escrow, _client(handler), lb=MagicMock(get_assignment=MagicMock(return_value=None)))

        counts = sweeper.run_once()

        assert counts["deferred"] == 1
        assert escrow.get_escrow(entry.escrow_id).status == EscrowStatus.PENDING

    def test_rpc_failure_counts_failed_and_retries_next_pass(self):
        escrow = PaymentEscrow()
        entry = _pending_entry(escrow)

        def boom(request: httpx.Request) -> httpx.Response:
            return httpx.Response(500, json={"detail": "down"}, request=request)

        client = ChainEscrowClient("http://rpc.test", transport=httpx.MockTransport(boom))
        sweeper = _sweeper(escrow, client, lb=MagicMock(get_assignment=MagicMock(return_value=None)))

        counts = sweeper.run_once()

        assert counts["failed"] == 1
        assert escrow.get_escrow(entry.escrow_id).status == EscrowStatus.PENDING

    def test_batch_is_bounded(self):
        escrow = PaymentEscrow()
        for i in range(5):
            _pending_entry(escrow, task_id=f"atask_{i}", age=10_000.0 + i)
        handler = _ChainHandler({f"atask_{i}": _live_record(f"atask_{i}") for i in range(5)})
        sweeper = _sweeper(
            escrow,
            _client(handler),
            lb=MagicMock(get_assignment=MagicMock(return_value=None)),
            batch_size=2,
        )

        counts = sweeper.run_once()

        assert counts["candidates"] == 2
        assert len(handler.gets) == 2

    def test_dry_run_mutates_nothing(self):
        escrow = PaymentEscrow()
        entry = _pending_entry(escrow)
        handler = _ChainHandler({TASK_ID: _live_record()})
        sweeper = _sweeper(
            escrow,
            _client(handler),
            lb=MagicMock(get_assignment=MagicMock(return_value=None)),
            dry_run=True,
        )

        counts = sweeper.run_once()

        assert counts["refunded"] == 1
        assert handler.refunds == []
        assert escrow.get_escrow(entry.escrow_id).status == EscrowStatus.PENDING


class TestPaymentEscrowOrphanTransitions:
    """The CAS guards inside adopt_chain_lock / refund_orphaned."""

    def test_refund_orphaned_rejects_non_eligible_status(self):
        escrow = PaymentEscrow()
        entry = _locked_entry(escrow)
        with pytest.raises(ValueError):
            escrow.refund_orphaned(entry, submitter=lambda *_a: "tx")
        # A normal LOCKED refund still works through refund().
        escrow.refund(entry.escrow_id, submitter=lambda *_a: "tx")
        assert escrow.get_escrow(entry.escrow_id).status == EscrowStatus.REFUNDED

    def test_adopt_chain_lock_rejects_locked_entry(self):
        escrow = PaymentEscrow()
        entry = _locked_entry(escrow)
        assert escrow.adopt_chain_lock(entry, tx_hash_lock="0xnew") is False
        assert escrow.get_escrow(entry.escrow_id).tx_hash_lock == "0x" + "ab" * 32

    def test_refund_orphaned_callback_arg_order_matches_refund(self):
        """refund() calls the callback (chain_id, agent, requester, amount);
        the orphan path must use the same order so submitters agree."""
        escrow = PaymentEscrow()
        entry = _pending_entry(escrow)
        seen = {}

        def submitter(chain_id, from_addr, to_addr, amount):
            seen.update(chain_id=chain_id, from_addr=from_addr, to_addr=to_addr, amount=amount)
            return "0xtx"

        escrow.refund_orphaned(entry, submitter=submitter)
        assert seen == {"chain_id": CHAIN_ID, "from_addr": "0xAgent", "to_addr": "0xBuyer", "amount": 100}


class TestGetEscrowRecord:
    def test_404_maps_to_none(self):
        handler = _ChainHandler({})
        client = _client(handler)
        assert client.get_escrow_record("missing") is None

    def test_record_returned(self):
        handler = _ChainHandler({TASK_ID: _live_record()})
        client = _client(handler)
        record = client.get_escrow_record(TASK_ID)
        assert record is not None and record["job_id"] == TASK_ID

    def test_non_404_error_raises(self):
        def boom(request: httpx.Request) -> httpx.Response:
            return httpx.Response(500, json={"detail": "down"}, request=request)

        client = ChainEscrowClient("http://rpc.test", transport=httpx.MockTransport(boom))
        with pytest.raises(EscrowRPCError):
            client.get_escrow_record(TASK_ID)


class TestStrandedPredicate:
    @pytest.mark.parametrize(
        "record",
        [
            None,
            {},
            {"state": "released", "status": "locked"},
            {"state": "funded", "status": "locked", "refunded_at": "2026-01-01T00:00:00Z"},
            {"state": "funded", "status": "locked", "released_amount": "0.05"},
            {"state": "disputed", "status": "locked"},
        ],
    )
    def test_not_stranded(self, record):
        assert escrow_record_is_stranded(record) is False

    @pytest.mark.parametrize(
        "record",
        [
            _live_record(),
            {"state": "locked", "status": "funded", "lock_tx_hash": "0x1"},
            {"state": "job_started", "status": "locked"},
        ],
    )
    def test_stranded(self, record):
        assert escrow_record_is_stranded(record) is True


class _FailingStore:
    """Store whose writes always fail — the #2998 no-row vector."""

    def save(self, entry) -> None:
        raise RuntimeError("db gone")

    def load_all(self) -> list:
        return []

    def load(self, escrow_id: str):
        return None

    def load_by_task(self, task_id: str):
        return None


class TestStrictPersistBeforeLock:
    """Ordering fix: the durable row must be proven BEFORE the chain submit.

    ``_persist`` swallows store failures by design (the chain op already
    happened), but on the create path the write IS the precondition — a
    swallowed failure there is how a funded escrow ends up with no row.
    """

    def test_store_failure_aborts_submit_before_chain_lock(self, monkeypatch):
        fake_state = MagicMock()
        fake_state.task_distributor = MagicMock()
        fake_state.task_distributor.submit_task = MagicMock()
        fake_state.payment_escrow = PaymentEscrow(store=_FailingStore())
        fake_state.escrow_rpc = MagicMock()
        fake_state.escrow_rpc.create = MagicMock(return_value={"lock_tx_hash": "0x" + "ab" * 32})
        app = FastAPI()
        app.include_router(tasks_router.router, prefix="/v1")
        monkeypatch.setattr(tasks_router, "state", fake_state)
        monkeypatch.setattr(settings, "agent_msg_signature_mode", "disabled")
        monkeypatch.setattr(settings, "task_payment_escrow_enabled", True)
        client = TestClient(app)

        resp = client.post(
            "/v1/tasks/submit",
            json={
                "task_data": {"task_id": "atask_storefail"},
                "payment": {
                    "requester": "0xBuyer",
                    "agent": "0xAgent",
                    "amount": 100,
                    "lock_tx": {"type": "ESCROW_LOCK"},
                    "lock_signature": "0xsig",
                },
            },
        )

        # The submit fails (502 via the generic escrow-error mapping) — and
        # critically the chain create was NEVER called: no orphan can form.
        assert resp.status_code == 502
        fake_state.escrow_rpc.create.assert_not_called()

    def test_healthy_store_still_locks(self, monkeypatch):
        fake_state = MagicMock()
        fake_state.task_distributor = MagicMock()
        fake_state.task_distributor.submit_task = AsyncMock(return_value=True)
        fake_state.payment_escrow = PaymentEscrow()
        fake_state.escrow_rpc = MagicMock()
        fake_state.escrow_rpc.create = MagicMock(return_value={"lock_tx_hash": "0x" + "ab" * 32, "contract_id": "contract-9"})
        app = FastAPI()
        app.include_router(tasks_router.router, prefix="/v1")
        monkeypatch.setattr(tasks_router, "state", fake_state)
        monkeypatch.setattr(settings, "agent_msg_signature_mode", "disabled")
        monkeypatch.setattr(settings, "task_payment_escrow_enabled", True)
        client = TestClient(app)

        resp = client.post(
            "/v1/tasks/submit",
            json={
                "task_data": {"task_id": "atask_ok"},
                "payment": {
                    "requester": "0xBuyer",
                    "agent": "0xAgent",
                    "amount": 100,
                    "lock_tx": {"type": "ESCROW_LOCK"},
                    "lock_signature": "0xsig",
                },
            },
        )

        assert resp.status_code == 200, resp.text
        fake_state.escrow_rpc.create.assert_called_once()


class TestLifespanWiring:
    """#2998 wiring pin: the lifespan seam must build the real sweeper from
    live state and run it — neutering the stranded-check or dropping the
    registration fails these."""

    def test_orphan_sweep_once_runs_real_sweeper(self, monkeypatch):
        import agent_app.state as state_mod
        import agent_app.services.orphan_escrow_sweeper as sweeper_mod

        captured = {}
        sentinel_counts = {"candidates": 0, "adopted": 0, "refunded": 0, "failed": 0, "deferred": 0, "skipped": 0}

        class _SpySweeper:
            def __init__(self, **kwargs):
                captured.update(kwargs)

            def run_once(self):
                return sentinel_counts

        monkeypatch.setattr(sweeper_mod, "OrphanedTaskEscrowSweeper", _SpySweeper)
        marker_escrow = object()
        marker_rpc = object()
        marker_lb = object()
        monkeypatch.setattr(state_mod, "payment_escrow", marker_escrow)
        monkeypatch.setattr(state_mod, "escrow_rpc", marker_rpc)
        monkeypatch.setattr(state_mod, "load_balancer", marker_lb)

        counts = _orphan_sweep_once()

        assert counts == sentinel_counts
        assert captured["payment_escrow"] is marker_escrow
        assert captured["escrow_rpc"] is marker_rpc
        assert captured["load_balancer"] is marker_lb
        # Settings feed the knobs — a neutered wiring drops these.
        assert captured["grace_seconds"] == settings.task_payment_orphan_grace_seconds
        assert captured["batch_size"] == settings.task_payment_orphan_sweep_batch_size
        assert captured["dry_run"] == settings.task_payment_orphan_sweep_dry_run

    def test_end_to_end_refund_through_lifespan_seam(self, monkeypatch):
        """The strongest wiring pin: drive ``_orphan_sweep_once`` against real
        state objects — a PENDING orphan + live chain record must come out
        REFUNDED. Gut ``escrow_record_is_stranded`` or the refund call and
        this fails."""
        import agent_app.state as state_mod

        escrow = PaymentEscrow()
        entry = _pending_entry(escrow)
        handler = _ChainHandler({TASK_ID: _live_record()})
        monkeypatch.setattr(state_mod, "payment_escrow", escrow)
        monkeypatch.setattr(state_mod, "escrow_rpc", _client(handler))
        monkeypatch.setattr(state_mod, "load_balancer", MagicMock(get_assignment=MagicMock(return_value=None)))

        counts = _orphan_sweep_once()

        assert counts["refunded"] == 1
        assert escrow.get_escrow(entry.escrow_id).status == EscrowStatus.REFUNDED
        assert len(handler.refunds) == 1
