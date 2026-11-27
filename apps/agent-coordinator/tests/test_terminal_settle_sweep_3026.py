"""#3026 pins: a RELEASED/REFUNDED escrow row is recorded at mempool admission,
not at seal. A settle tx evicted before sealing leaves no durable chain row —
``transaction_status`` answers ``None`` and the #2926 reconcile never fires,
so the local row stays terminal forever while the on-chain escrow stays
locked. The terminal-settle sweeper probes the settle hash past a grace
horizon and demotes proven-dead rows back to LOCKED.
"""

from __future__ import annotations

import inspect
import os
import time

import pytest

os.environ.setdefault("SECRET_KEY", "test-secret-key")
os.environ.setdefault("JWT_SECRET", "test-secret-for-agent-coordinator-tests" * 2)

pytest.importorskip("fastapi", reason="agent-coordinator app dependencies not installed")

import httpx  # noqa: E402

from agent_app.config import settings  # noqa: E402
from agent_app.lifespan import _terminal_sweep_once  # noqa: E402
from agent_app.services.chain_escrow import ChainEscrowClient  # noqa: E402
from agent_app.services.terminal_settle_sweeper import (  # noqa: E402
    META_SETTLE_CONFIRMED_AT,
    META_SETTLE_PROBE_AT,
    TerminalSettleSweeper,
    _classify_probe,
)

from aitbc.crypto import EscrowStatus, PaymentEscrow  # noqa: E402

CHAIN_ID = "ait-test-chain"
TASK_ID = "atask_20261127000000_deadbeef"
RELEASE_TX = "0x" + "aa" * 32
REFUND_TX = "0x" + "bb" * 32
LOCK_TX = "0x" + "cc" * 32
AGE = 10_000.0  # well past the 900s grace


def _released_entry(escrow: PaymentEscrow, task_id: str = TASK_ID, age: float = AGE):
    entry = escrow.create_escrow(
        task_id=task_id,
        chain_id=CHAIN_ID,
        requester="0xBuyer",
        agent="0xAgent",
        amount=100,
        fee=1,
    )
    escrow.lock(entry.escrow_id, submitter=lambda *_a: LOCK_TX)
    escrow.release(entry.escrow_id, submitter=lambda *_a: RELEASE_TX)
    entry = escrow.get_escrow(entry.escrow_id)
    entry.created_at = time.time() - age
    entry.released_at = time.time() - age
    return entry


def _refunded_entry(escrow: PaymentEscrow, task_id: str = TASK_ID, age: float = AGE):
    entry = escrow.create_escrow(
        task_id=task_id,
        chain_id=CHAIN_ID,
        requester="0xBuyer",
        agent="0xAgent",
        amount=100,
        fee=1,
    )
    escrow.lock(entry.escrow_id, submitter=lambda *_a: LOCK_TX)
    escrow.refund(entry.escrow_id, submitter=lambda *_a: REFUND_TX)
    entry = escrow.get_escrow(entry.escrow_id)
    entry.created_at = time.time() - age
    entry.metadata["refunded_at"] = time.time() - age
    return entry


def _terminal_no_hash_entry(escrow: PaymentEscrow, status: EscrowStatus, task_id: str = TASK_ID, age: float = AGE):
    """A terminal row whose settle submitter recorded no tx hash."""
    entry = escrow.create_escrow(
        task_id=task_id,
        chain_id=CHAIN_ID,
        requester="0xBuyer",
        agent="0xAgent",
        amount=100,
    )
    escrow.lock(entry.escrow_id, submitter=lambda *_a: LOCK_TX)
    # No submitter → terminal status with tx_hash_* = None (bookkeeping path).
    if status == EscrowStatus.RELEASED:
        escrow.release(entry.escrow_id)
    else:
        escrow.refund(entry.escrow_id)
    entry = escrow.get_escrow(entry.escrow_id)
    entry.created_at = time.time() - age
    entry.released_at = time.time() - age if status == EscrowStatus.RELEASED else None
    entry.metadata["refunded_at"] = time.time() - age if status == EscrowStatus.REFUNDED else entry.metadata.get("refunded_at")
    return entry


class _ChainHandler:
    """MockTransport handler: scripted ``/rpc/transaction/{hash}`` answers plus
    ``/rpc/escrow/{job}`` record reads."""

    def __init__(self, tx_answers: dict[str, tuple[int, dict] | None], records: dict[str, dict | None] | None = None):
        # hash -> (http_status, json_body); missing key -> 404 (absent everywhere)
        self.tx_answers = tx_answers
        self.records = records or {}
        self.tx_gets: list[str] = []
        self.record_gets: list[str] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if request.method == "GET" and path.startswith("/rpc/transaction/"):
            tx_hash = path.rsplit("/", 1)[-1]
            self.tx_gets.append(tx_hash)
            answer = self.tx_answers.get(tx_hash)
            if answer is None:
                return httpx.Response(404, json={"detail": "not found"}, request=request)
            code, body = answer
            return httpx.Response(code, json=body, request=request)
        if request.method == "GET" and path.startswith("/rpc/escrow/"):
            job_id = path.rsplit("/", 1)[-1]
            self.record_gets.append(job_id)
            record = self.records.get(job_id)
            if record is None:
                return httpx.Response(404, json={"detail": "not found"}, request=request)
            return httpx.Response(200, json=record, request=request)
        return httpx.Response(404, json={"detail": "unrouted"}, request=request)


def _client(handler: _ChainHandler) -> ChainEscrowClient:
    return ChainEscrowClient("http://rpc.test", api_key="api-key", transport=httpx.MockTransport(handler))


def _sweeper(escrow: PaymentEscrow, client: ChainEscrowClient, **kwargs) -> TerminalSettleSweeper:
    return TerminalSettleSweeper(
        payment_escrow=escrow,
        escrow_rpc=client,
        grace_seconds=kwargs.pop("grace_seconds", 900.0),
        batch_size=kwargs.pop("batch_size", 25),
        **kwargs,
    )


def _confirmed_tx() -> tuple[int, dict]:
    return 200, {"tx_hash": RELEASE_TX, "status": "confirmed", "block_height": 1234, "type": "ESCROW_RELEASE"}


def _pending_tx() -> tuple[int, dict]:
    return 200, {"tx_hash": RELEASE_TX, "status": "pending", "state": "pending", "type": "ESCROW_RELEASE"}


def _rejected_tx() -> tuple[int, dict]:
    return 200, {
        "tx_hash": RELEASE_TX,
        "status": "rejected",
        "rejected_reason": "apply gate failed",
        "rejected_at_height": 1200,
    }


class TestSettleTxAbsentDemotes:
    """The headline defect: settle hash known to neither the sealed table
    nor the mempool past the grace horizon → the terminal row is a lie."""

    def test_released_with_absent_settle_tx_demotes_to_locked(self):
        escrow = PaymentEscrow()
        entry = _released_entry(escrow)
        handler = _ChainHandler({})  # every tx hash 404s
        sweeper = _sweeper(escrow, _client(handler))

        counts = sweeper.run_once()

        assert counts["demoted"] == 1
        assert handler.tx_gets == [RELEASE_TX]
        refreshed = escrow.get_escrow(entry.escrow_id)
        assert refreshed.status == EscrowStatus.LOCKED
        # released_at cleared (mirrors reconcile_rejected_release); the dead
        # hash stays for audit and a retry overwrites it.
        assert refreshed.released_at is None
        assert refreshed.tx_hash_release == RELEASE_TX
        assert refreshed.tx_hash_lock == LOCK_TX
        assert refreshed.metadata["settle_demoted_reason"] == "settle_tx_absent_from_chain"
        assert refreshed.metadata["settle_demote_evidence"]["tx_hash"] == RELEASE_TX
        assert refreshed.metadata["settle_demoted_at"] > 0

    def test_refunded_with_absent_settle_tx_demotes_to_locked(self):
        escrow = PaymentEscrow()
        entry = _refunded_entry(escrow)
        handler = _ChainHandler({REFUND_TX: None})  # explicit 404
        sweeper = _sweeper(escrow, _client(handler))

        counts = sweeper.run_once()

        assert counts["demoted"] == 1
        assert handler.tx_gets == [REFUND_TX]
        refreshed = escrow.get_escrow(entry.escrow_id)
        assert refreshed.status == EscrowStatus.LOCKED
        assert refreshed.tx_hash_refund == REFUND_TX
        assert refreshed.metadata["settle_demoted_reason"] == "settle_tx_absent_from_chain"

    def test_demoted_row_is_re_driven_by_normal_paths(self):
        """A RELEASED->LOCKED demote must leave a row the release path can
        re-submit: release() only needs LOCKED and overwrites the dead hash."""
        escrow = PaymentEscrow()
        entry = _released_entry(escrow)
        handler = _ChainHandler({})
        sweeper = _sweeper(escrow, _client(handler))
        assert sweeper.run_once()["demoted"] == 1

        # The provider retries complete → release() re-submits a fresh settle.
        new_tx = "0x" + "dd" * 32
        escrow.release(entry.escrow_id, submitter=lambda *_a: new_tx)
        refreshed = escrow.get_escrow(entry.escrow_id)
        assert refreshed.status == EscrowStatus.RELEASED
        assert refreshed.tx_hash_release == new_tx
        assert refreshed.released_at is not None

    def test_rejected_settle_tx_also_demotes(self):
        """A durable rejected row is proven dead just like an absent hash —
        same stranding, same demote (the #2926 reconcile covers hot rows;
        this covers store-only ones too)."""
        escrow = PaymentEscrow()
        entry = _released_entry(escrow)
        handler = _ChainHandler({RELEASE_TX: _rejected_tx()})
        sweeper = _sweeper(escrow, _client(handler))

        counts = sweeper.run_once()

        assert counts["demoted"] == 1
        refreshed = escrow.get_escrow(entry.escrow_id)
        assert refreshed.status == EscrowStatus.LOCKED
        assert refreshed.metadata["settle_demoted_reason"] == "settle_tx_rejected_on_chain"

    def test_second_run_after_demote_finds_no_terminal_candidate(self):
        escrow = PaymentEscrow()
        _released_entry(escrow)
        sweeper = _sweeper(escrow, _client(_ChainHandler({})))

        assert sweeper.run_once()["demoted"] == 1
        counts = sweeper.run_once()
        assert counts["candidates"] == 0


class TestSettleTxSealedOrPending:
    def test_sealed_settle_tx_stamps_confirmed_and_stays_terminal(self):
        escrow = PaymentEscrow()
        entry = _released_entry(escrow)
        handler = _ChainHandler({RELEASE_TX: _confirmed_tx()})
        sweeper = _sweeper(escrow, _client(handler))

        counts = sweeper.run_once()

        assert counts["confirmed"] == 1
        assert counts["demoted"] == 0
        refreshed = escrow.get_escrow(entry.escrow_id)
        assert refreshed.status == EscrowStatus.RELEASED
        assert META_SETTLE_CONFIRMED_AT in refreshed.metadata
        # Resolved forever — the next pass does not even probe.
        counts2 = sweeper.run_once()
        assert counts2["candidates"] == 0
        assert handler.tx_gets == [RELEASE_TX]

    def test_pending_settle_tx_skips_without_demote(self):
        """Still in the mempool — it may yet seal. Skip, stamp, re-probe later."""
        escrow = PaymentEscrow()
        entry = _released_entry(escrow)
        handler = _ChainHandler({RELEASE_TX: _pending_tx()})
        sweeper = _sweeper(escrow, _client(handler))

        counts = sweeper.run_once()

        assert counts["skipped"] == 1
        assert counts["demoted"] == 0
        refreshed = escrow.get_escrow(entry.escrow_id)
        assert refreshed.status == EscrowStatus.RELEASED
        assert META_SETTLE_PROBE_AT in refreshed.metadata
        assert META_SETTLE_CONFIRMED_AT not in refreshed.metadata

    def test_recently_pending_row_reprobes_only_after_cadence(self):
        escrow = PaymentEscrow()
        _released_entry(escrow)
        handler = _ChainHandler({RELEASE_TX: _pending_tx()})
        sweeper = _sweeper(escrow, _client(handler))

        sweeper.run_once()
        # Second pass inside the grace cadence: no new chain read.
        counts = sweeper.run_once()
        assert counts["candidates"] == 0
        assert handler.tx_gets == [RELEASE_TX]

    def test_probe_failure_never_demotes(self):
        """5xx / transport failure → unknown, never death."""
        escrow = PaymentEscrow()
        entry = _released_entry(escrow)

        def boom(request: httpx.Request) -> httpx.Response:
            return httpx.Response(500, json={"detail": "down"}, request=request)

        client = ChainEscrowClient("http://rpc.test", transport=httpx.MockTransport(boom))
        sweeper = _sweeper(escrow, client)

        counts = sweeper.run_once()

        assert counts["failed"] == 1
        assert counts["demoted"] == 0
        assert escrow.get_escrow(entry.escrow_id).status == EscrowStatus.RELEASED

    def test_unclassifiable_durable_row_skips(self):
        """A durable row with an unexpected status is unknown, not absent."""
        escrow = PaymentEscrow()
        _released_entry(escrow)
        handler = _ChainHandler({RELEASE_TX: (200, {"tx_hash": RELEASE_TX, "status": "weird"})})
        sweeper = _sweeper(escrow, _client(handler))

        counts = sweeper.run_once()

        assert counts["failed"] == 1
        assert counts["demoted"] == 0


class TestGraceAndEligibility:
    def test_within_grace_is_skipped_without_chain_call(self):
        escrow = PaymentEscrow()
        _released_entry(escrow, age=10.0)
        handler = _ChainHandler({})
        sweeper = _sweeper(escrow, _client(handler))

        counts = sweeper.run_once()

        assert counts["candidates"] == 0
        assert handler.tx_gets == []

    def test_locked_and_pending_rows_are_not_candidates(self):
        """Mutation guard: the candidate predicate must stay terminal-only —
        widening it to LOCKED/PENDING would double-drive the other sweepers."""
        escrow = PaymentEscrow()
        locked = escrow.create_escrow(task_id="t-locked", chain_id=CHAIN_ID, requester="0xB", agent="0xA", amount=1)
        escrow.lock(locked.escrow_id, submitter=lambda *_a: LOCK_TX)
        locked.created_at = time.time() - AGE
        pending = escrow.create_escrow(task_id="t-pending", chain_id=CHAIN_ID, requester="0xB", agent="0xA", amount=1)
        pending.created_at = time.time() - AGE
        handler = _ChainHandler({})
        sweeper = _sweeper(escrow, _client(handler))

        counts = sweeper.run_once()

        assert counts["candidates"] == 0
        assert handler.tx_gets == []

    def test_batch_is_bounded(self):
        escrow = PaymentEscrow()
        for i in range(5):
            _released_entry(escrow, task_id=f"atask_{i}")
        handler = _ChainHandler({})
        sweeper = _sweeper(escrow, _client(handler), batch_size=2)

        counts = sweeper.run_once()

        assert counts["candidates"] == 2
        assert len(handler.tx_gets) == 2

    def test_dry_run_counts_but_mutates_nothing(self):
        escrow = PaymentEscrow()
        entry = _released_entry(escrow)
        handler = _ChainHandler({})
        sweeper = _sweeper(escrow, _client(handler), dry_run=True)

        counts = sweeper.run_once()

        assert counts["demoted"] == 1
        assert escrow.get_escrow(entry.escrow_id).status == EscrowStatus.RELEASED
        assert META_SETTLE_PROBE_AT not in escrow.get_escrow(entry.escrow_id).metadata
        assert META_SETTLE_CONFIRMED_AT not in escrow.get_escrow(entry.escrow_id).metadata


class TestNoHashFallback:
    """Terminal rows with no recorded settle hash probe the chain escrow
    record instead — the bookkeeping-only vs live-lock distinction."""

    def test_no_hash_settled_record_confirms(self):
        escrow = PaymentEscrow()
        entry = _terminal_no_hash_entry(escrow, EscrowStatus.REFUNDED)
        record = {
            "job_id": TASK_ID,
            "state": "refunded",
            "status": "refunded",
            "refunded_at": "2026-11-27T00:00:00+00:00",
        }
        handler = _ChainHandler({}, records={TASK_ID: record})
        sweeper = _sweeper(escrow, _client(handler))

        counts = sweeper.run_once()

        assert counts["confirmed"] == 1
        assert handler.tx_gets == []
        assert META_SETTLE_CONFIRMED_AT in escrow.get_escrow(entry.escrow_id).metadata

    def test_no_hash_missing_record_confirms_bookkeeping_only(self):
        """404 on the escrow record = nothing was ever locked on-chain —
        the terminal row is final."""
        escrow = PaymentEscrow()
        _terminal_no_hash_entry(escrow, EscrowStatus.RELEASED)
        handler = _ChainHandler({}, records={})
        sweeper = _sweeper(escrow, _client(handler))

        counts = sweeper.run_once()

        assert counts["confirmed"] == 1
        assert counts["demoted"] == 0

    def test_no_hash_live_lock_demotes_with_backfill(self):
        """Terminal row + live unsettled chain lock + no recorded settle
        hash → demote and backfill the verified lock identity so the expire
        sweep can refund for real (#3006 contract)."""
        escrow = PaymentEscrow()
        entry = _terminal_no_hash_entry(escrow, EscrowStatus.REFUNDED)
        # Strip the lock hash too — the row must take the chain's identity.
        entry.tx_hash_lock = None
        entry.contract_id = None
        record = {
            "job_id": TASK_ID,
            "state": "funded",
            "status": "locked",
            "lock_tx_hash": "0x" + "ef" * 32,
            "contract_id": "contract-77",
            "released_amount": "0",
        }
        handler = _ChainHandler({}, records={TASK_ID: record})
        sweeper = _sweeper(escrow, _client(handler))

        counts = sweeper.run_once()

        assert counts["demoted"] == 1
        refreshed = escrow.get_escrow(entry.escrow_id)
        assert refreshed.status == EscrowStatus.LOCKED
        assert refreshed.tx_hash_lock == "0x" + "ef" * 32
        assert refreshed.contract_id == "contract-77"
        assert refreshed.metadata["settle_demoted_reason"] == "terminal_row_but_chain_lock_live"

    def test_no_hash_live_lock_without_identity_skips(self):
        """A live lock but no lock identity anywhere → demoting could only
        produce a bookkeeping refund that re-strands; skip + log instead."""
        escrow = PaymentEscrow()
        entry = _terminal_no_hash_entry(escrow, EscrowStatus.REFUNDED)
        entry.tx_hash_lock = None
        record = {"job_id": TASK_ID, "state": "funded", "status": "locked", "released_amount": "0"}
        handler = _ChainHandler({}, records={TASK_ID: record})
        sweeper = _sweeper(escrow, _client(handler))

        counts = sweeper.run_once()

        assert counts["skipped"] == 1
        assert counts["demoted"] == 0
        assert escrow.get_escrow(entry.escrow_id).status == EscrowStatus.REFUNDED


class TestCasAndStore:
    def test_cas_loses_to_concurrent_transition(self):
        """The demote is guarded by the expected terminal status: a row that
        moved between listing and demote is left alone."""
        escrow = PaymentEscrow()
        entry = _released_entry(escrow)

        class _FlippingHandler(_ChainHandler):
            def __call__(self, request: httpx.Request) -> httpx.Response:
                # Simulate a concurrent transition winning mid-probe.
                entry.status = EscrowStatus.LOCKED
                return super().__call__(request)

        handler = _FlippingHandler({})
        sweeper = _sweeper(escrow, _client(handler))

        counts = sweeper.run_once()

        assert counts["skipped"] == 1
        assert counts["demoted"] == 0
        # The concurrent LOCKED state wins — not flipped back or double-demoted.
        assert escrow.get_escrow(entry.escrow_id).status == EscrowStatus.LOCKED

    def test_demote_unsealed_settle_rejects_wrong_expected_status(self):
        escrow = PaymentEscrow()
        entry = _released_entry(escrow)
        assert (
            escrow.demote_unsealed_settle(
                entry,
                expected_status=EscrowStatus.REFUNDED,
                expected_settle_tx_hash=RELEASE_TX,
                reason="x",
            )
            is False
        )
        assert escrow.get_escrow(entry.escrow_id).status == EscrowStatus.RELEASED

    def test_store_only_terminal_row_is_swept_and_demoted(self):
        """#1515 split: terminal rows are not rehydrated at boot, so the sweep
        must enumerate them through the store's ``load_terminal`` hook — the
        restart-blindness case."""

        class _MemStore:
            def __init__(self):
                self.rows = {}

            def save(self, entry):
                self.rows[entry.escrow_id] = entry

            def load_all(self):
                return []  # terminal rows never rehydrate (#1515)

            def load(self, escrow_id):
                return self.rows.get(escrow_id)

            def load_by_task(self, task_id):
                return None

            def load_terminal(self, statuses, *, limit=500):
                return [e for e in self.rows.values() if e.status.name in statuses][:limit]

        store = _MemStore()
        writer = PaymentEscrow(store=store)
        entry = _released_entry(writer)

        # A "restarted" manager: load_all returns nothing, the terminal row
        # exists only in the store.
        reader = PaymentEscrow(store=store)
        assert reader.get_all_escrows() == []

        handler = _ChainHandler({})
        sweeper = _sweeper(reader, _client(handler))
        counts = sweeper.run_once()

        assert counts["demoted"] == 1
        # The demoted LOCKED row is active bookkeeping — it must land in the
        # store AND the hot cache so expire_stale sees it.
        stored = store.rows[entry.escrow_id]
        assert stored.status == EscrowStatus.LOCKED
        assert reader.get_escrow(entry.escrow_id).status == EscrowStatus.LOCKED

    def test_confirmed_store_only_row_is_not_recached(self):
        """persist_terminal must not pin resolved terminal rows in the hot
        cache — the #1515 memory split stays intact."""

        class _MemStore:
            def __init__(self):
                self.rows = {}
                self.saved = []

            def save(self, entry):
                self.rows[entry.escrow_id] = entry
                self.saved.append(entry)

            def load_all(self):
                return []

            def load(self, escrow_id):
                return self.rows.get(escrow_id)

            def load_by_task(self, task_id):
                return None

            def load_terminal(self, statuses, *, limit=500):
                # Mirror the SQL exclusion: confirmed rows never come back.
                return [
                    e for e in self.rows.values() if e.status.name in statuses and META_SETTLE_CONFIRMED_AT not in e.metadata
                ][:limit]

        store = _MemStore()
        writer = PaymentEscrow(store=store)
        _released_entry(writer)
        reader = PaymentEscrow(store=store)

        handler = _ChainHandler({RELEASE_TX: _confirmed_tx()})
        sweeper = _sweeper(reader, _client(handler))

        counts = sweeper.run_once()

        assert counts["confirmed"] == 1
        # The stamp persisted to the store but the row stayed out of memory.
        assert META_SETTLE_CONFIRMED_AT in store.rows[next(iter(store.rows))].metadata
        assert reader.get_all_escrows() == []
        counts2 = sweeper.run_once()
        assert counts2["candidates"] == 0


class TestClassifyProbe:
    @pytest.mark.parametrize(
        "info,expected",
        [
            (None, "unknown"),
            ({"status": "absent", "state": "absent"}, "absent"),
            ({"status": "pending", "state": "pending"}, "pending"),
            ({"status": "pending", "state": "pending", "previously_rejected": True}, "pending"),
            ({"status": "rejected", "rejected_reason": "x"}, "rejected"),
            ({"status": "confirmed", "block_height": 5}, "sealed"),
            # #3049: sealed-for-money is confirmed AND height — a bare
            # confirmed status or a bare height proves nothing.
            ({"status": "confirmed"}, "unknown"),
            ({"block_height": 5}, "unknown"),
            ({"status": "failed", "block_height": 5}, "failed_sealed"),
            ({"status": "failed"}, "failed_sealed"),
            ({"status": "pending"}, "unknown"),  # durable pending row: not proven
            ({"status": "weird"}, "unknown"),
            ("not-a-dict", "unknown"),
        ],
    )
    def test_classification(self, info, expected):
        assert _classify_probe(info) == expected


class TestLifespanWiring:
    """#3026 wiring pin: the lifespan seam must build the real sweeper from
    live state — neutering the seal-check or dropping the registration
    fails these."""

    def test_terminal_sweep_once_runs_real_sweeper(self, monkeypatch):
        import agent_app.state as state_mod
        import agent_app.services.terminal_settle_sweeper as sweeper_mod

        captured = {}
        sentinel_counts = {"candidates": 0, "confirmed": 0, "demoted": 0, "failed": 0, "skipped": 0}

        class _SpySweeper:
            def __init__(self, **kwargs):
                captured.update(kwargs)

            def run_once(self):
                return sentinel_counts

        monkeypatch.setattr(sweeper_mod, "TerminalSettleSweeper", _SpySweeper)
        marker_escrow = object()
        marker_rpc = object()
        monkeypatch.setattr(state_mod, "payment_escrow", marker_escrow)
        monkeypatch.setattr(state_mod, "escrow_rpc", marker_rpc)

        counts = _terminal_sweep_once()

        assert counts == sentinel_counts
        assert captured["payment_escrow"] is marker_escrow
        assert captured["escrow_rpc"] is marker_rpc
        assert captured["grace_seconds"] == settings.task_payment_terminal_grace_seconds
        assert captured["batch_size"] == settings.task_payment_terminal_sweep_batch_size
        assert captured["dry_run"] == settings.task_payment_terminal_sweep_dry_run

    def test_end_to_end_demote_through_lifespan_seam(self, monkeypatch):
        """Drive ``_terminal_sweep_once`` against real state objects: a
        RELEASED row whose settle hash 404s must come out LOCKED."""
        import agent_app.state as state_mod

        escrow = PaymentEscrow()
        _released_entry(escrow)
        handler = _ChainHandler({})
        monkeypatch.setattr(state_mod, "payment_escrow", escrow)
        monkeypatch.setattr(state_mod, "escrow_rpc", _client(handler))

        counts = _terminal_sweep_once()

        assert counts["demoted"] == 1
        assert handler.tx_gets == [RELEASE_TX]

    def test_lifespan_registers_terminal_sweeper(self):
        """Source pin: the sweep loop must be registered under the escrow
        feature flag alongside the sibling sweepers."""
        import agent_app.lifespan as lifespan_mod

        source = inspect.getsource(lifespan_mod)
        assert "sweep_terminal_settles" in source
        assert "terminal_settle_sweeper" in source
        assert "task_payment_terminal_sweep_enabled" in source
