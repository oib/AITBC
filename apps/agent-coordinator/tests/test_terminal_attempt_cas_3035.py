"""#3035 pins: the terminal-settle sweeper probes chain state OUTSIDE the
escrow manager lock, then demotes/stamps terminal rows. A status-only CAS
lets a stale probe result apply to a *newer* settlement attempt: the
reject/expiry worker can cycle a refund LOCKED -> REFUNDED with a
replacement tx between probe and write, landing back on the same terminal
status with a different ``tx_hash_*``. Every probe outcome — demote,
probe-time stamp, and the permanent ``settle_probe_confirmed_at`` marker —
must be scoped to the settle attempt it observed.
"""

from __future__ import annotations

import os
import time

import pytest

os.environ.setdefault("SECRET_KEY", "test-secret-key")
os.environ.setdefault("JWT_SECRET", "test-secret-for-agent-coordinator-tests" * 2)

pytest.importorskip("fastapi", reason="agent-coordinator app dependencies not installed")

import httpx  # noqa: E402

from agent_app.services.chain_escrow import ChainEscrowClient  # noqa: E402
from agent_app.services.terminal_settle_sweeper import (  # noqa: E402
    META_SETTLE_CONFIRMED_AT,
    META_SETTLE_PROBE_AT,
    TerminalSettleSweeper,
)

from aitbc.crypto import EscrowEntry, EscrowStatus, PaymentEscrow  # noqa: E402

CHAIN_ID = "ait-test-chain"
TASK_ID = "atask_20261128000000_cas3035"
RELEASE_TX = "0x" + "aa" * 32
REFUND_TX = "0x" + "bb" * 32
NEW_REFUND_TX = "0x" + "dd" * 32
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


def _no_hash_refunded_entry(escrow: PaymentEscrow, task_id: str = TASK_ID, age: float = AGE):
    """REFUNDED bookkeeping-only row: terminal, but no settle hash recorded."""
    entry = escrow.create_escrow(
        task_id=task_id,
        chain_id=CHAIN_ID,
        requester="0xBuyer",
        agent="0xAgent",
        amount=100,
    )
    escrow.lock(entry.escrow_id, submitter=lambda *_a: LOCK_TX)
    escrow.refund(entry.escrow_id)  # no submitter -> tx_hash_refund stays None
    entry = escrow.get_escrow(entry.escrow_id)
    entry.created_at = time.time() - age
    entry.metadata["refunded_at"] = time.time() - age
    return entry


class _ChainHandler:
    """MockTransport handler: scripted ``/rpc/transaction/{hash}`` answers."""

    def __init__(self, tx_answers: dict[str, tuple[int, dict] | None]):
        # hash -> (http_status, json_body); missing key -> 404 (absent everywhere)
        self.tx_answers = tx_answers
        self.tx_gets: list[str] = []

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


def _land_replacement_refund(escrow: PaymentEscrow, escrow_id: str, new_tx: str = NEW_REFUND_TX) -> None:
    """Replay the reject/expiry worker's cycle in a separate 'transaction':

    ``reconcile_rejected_refund`` flips REFUNDED -> LOCKED (the dead settle
    hash is kept for audit), then ``expire_stale``/``refund`` re-drives the
    row to REFUNDED with a REPLACEMENT settle tx — same terminal status,
    different attempt identity.
    """
    current = escrow.get_escrow(escrow_id)
    current.status = EscrowStatus.LOCKED
    current.metadata["refund_rejected_reason"] = "apply gate failed"
    escrow.persist_entry(current)
    escrow.refund(escrow_id, submitter=lambda *_a: new_tx)


class TestStaleProbeCannotDemoteReplacementAttempt:
    """Gap 1+2: probe observes attempt A; attempt B lands mid-probe; the
    stale 'A is dead' verdict must not demote the row recording B."""

    def test_absent_probe_does_not_demote_replacement_refund(self):
        escrow = PaymentEscrow()
        entry = _refunded_entry(escrow)

        class _ReplacingHandler(_ChainHandler):
            def __call__(self, request: httpx.Request) -> httpx.Response:
                # The concurrent worker lands the replacement attempt while
                # the probe for the OLD hash is in flight; the probe then
                # answers 404 (absent) for that old hash.
                _land_replacement_refund(escrow, entry.escrow_id)
                return super().__call__(request)

        handler = _ReplacingHandler({})
        sweeper = _sweeper(escrow, _client(handler))

        counts = sweeper.run_once()

        assert counts["demoted"] == 0
        assert counts["skipped"] == 1
        refreshed = escrow.get_escrow(entry.escrow_id)
        # The newer attempt survives untouched — no demote metadata.
        assert refreshed.status == EscrowStatus.REFUNDED
        assert refreshed.tx_hash_refund == NEW_REFUND_TX
        assert "settle_demoted_reason" not in refreshed.metadata
        assert "settle_demoted_at" not in refreshed.metadata

    def test_rejected_probe_does_not_demote_replacement_release(self):
        """Same race on the RELEASED leg: a retried release() records a
        new tx_hash_release under the same RELEASED status."""
        escrow = PaymentEscrow()
        entry = _released_entry(escrow)
        new_release = "0x" + "ee" * 32

        class _ReplacingHandler(_ChainHandler):
            def __call__(self, request: httpx.Request) -> httpx.Response:
                current = escrow.get_escrow(entry.escrow_id)
                current.status = EscrowStatus.LOCKED
                current.released_at = None
                current.metadata["release_rejected_reason"] = "apply gate failed"
                escrow.persist_entry(current)
                escrow.release(entry.escrow_id, submitter=lambda *_a: new_release)
                return super().__call__(request)

        handler = _ReplacingHandler({RELEASE_TX: (200, {"status": "rejected", "rejected_reason": "dead"})})
        sweeper = _sweeper(escrow, _client(handler))

        counts = sweeper.run_once()

        assert counts["demoted"] == 0
        assert counts["skipped"] == 1
        refreshed = escrow.get_escrow(entry.escrow_id)
        assert refreshed.status == EscrowStatus.RELEASED
        assert refreshed.tx_hash_release == new_release
        assert "settle_demoted_reason" not in refreshed.metadata


class TestStaleProbeCannotStampOverReplacementAttempt:
    """Gap 3: the probe-stamp/confirmed writes must be conditional on the
    entry still being current — no whole-entry overwrite, no stale
    permanent-confirmation marker."""

    def test_sealed_probe_does_not_confirm_replacement_attempt(self):
        """The OLD settle hash sealed — but the row now records a NEW
        attempt. Stamping settle_probe_confirmed_at would resolve the new
        attempt forever without ever probing it."""
        escrow = PaymentEscrow()
        entry = _refunded_entry(escrow)

        class _ReplacingHandler(_ChainHandler):
            def __call__(self, request: httpx.Request) -> httpx.Response:
                _land_replacement_refund(escrow, entry.escrow_id)
                return httpx.Response(
                    200,
                    json={"tx_hash": REFUND_TX, "status": "confirmed", "block_height": 42},
                    request=request,
                )

        sweeper = _sweeper(escrow, _client(_ReplacingHandler({})))

        counts = sweeper.run_once()

        assert counts["confirmed"] == 0
        assert counts["skipped"] == 1
        refreshed = escrow.get_escrow(entry.escrow_id)
        assert refreshed.status == EscrowStatus.REFUNDED
        assert refreshed.tx_hash_refund == NEW_REFUND_TX
        assert META_SETTLE_CONFIRMED_AT not in refreshed.metadata

    def test_pending_probe_does_not_stamp_replacement_attempt(self):
        """Even the benign settle_probe_at cadence stamp is attempt-scoped:
        it must not land on a row whose attempt changed mid-probe."""
        escrow = PaymentEscrow()
        entry = _refunded_entry(escrow)

        class _ReplacingHandler(_ChainHandler):
            def __call__(self, request: httpx.Request) -> httpx.Response:
                _land_replacement_refund(escrow, entry.escrow_id)
                return httpx.Response(
                    200,
                    json={"tx_hash": REFUND_TX, "status": "pending", "state": "pending"},
                    request=request,
                )

        sweeper = _sweeper(escrow, _client(_ReplacingHandler({})))

        counts = sweeper.run_once()

        assert counts["skipped"] == 1
        refreshed = escrow.get_escrow(entry.escrow_id)
        assert refreshed.tx_hash_refund == NEW_REFUND_TX
        assert META_SETTLE_PROBE_AT not in refreshed.metadata
        assert META_SETTLE_CONFIRMED_AT not in refreshed.metadata


class TestDemoteAttemptCas:
    """Unit pins for the extended demote CAS."""

    def test_demote_applies_when_attempt_matches(self):
        """Common case preserved: same status AND same probed hash -> demote."""
        escrow = PaymentEscrow()
        entry = _released_entry(escrow)

        assert (
            escrow.demote_unsealed_settle(
                entry,
                expected_status=EscrowStatus.RELEASED,
                expected_settle_tx_hash=RELEASE_TX,
                reason="settle_tx_absent_from_chain",
            )
            is True
        )
        refreshed = escrow.get_escrow(entry.escrow_id)
        assert refreshed.status == EscrowStatus.LOCKED
        assert refreshed.metadata["settle_demoted_reason"] == "settle_tx_absent_from_chain"

    def test_demote_rejects_mismatched_attempt_same_status(self):
        """The core #3035 unit pin: status alone is not the attempt."""
        escrow = PaymentEscrow()
        entry = _released_entry(escrow)

        assert (
            escrow.demote_unsealed_settle(
                entry,
                expected_status=EscrowStatus.RELEASED,
                expected_settle_tx_hash="0x" + "00" * 32,  # a different probed hash
                reason="x",
            )
            is False
        )
        refreshed = escrow.get_escrow(entry.escrow_id)
        assert refreshed.status == EscrowStatus.RELEASED
        assert refreshed.tx_hash_release == RELEASE_TX
        assert "settle_demoted_reason" not in refreshed.metadata

    def test_demote_no_hash_row_requires_still_no_hash(self):
        """Chain-record path (expected=None): a row that gained a settle
        hash mid-probe is a different attempt and must not demote."""
        escrow = PaymentEscrow()
        entry = _no_hash_refunded_entry(escrow)

        # Still no settle hash -> CAS passes.
        assert (
            escrow.demote_unsealed_settle(
                entry,
                expected_status=EscrowStatus.REFUNDED,
                expected_settle_tx_hash=None,
                reason="terminal_row_but_chain_lock_live",
            )
            is True
        )
        assert escrow.get_escrow(entry.escrow_id).status == EscrowStatus.LOCKED

    def test_demote_no_hash_expectation_rejects_recorded_hash(self):
        escrow = PaymentEscrow()
        entry = _refunded_entry(escrow)  # records REFUND_TX

        assert (
            escrow.demote_unsealed_settle(
                entry,
                expected_status=EscrowStatus.REFUNDED,
                expected_settle_tx_hash=None,  # probe observed "no hash" — stale now
                reason="x",
            )
            is False
        )
        assert escrow.get_escrow(entry.escrow_id).status == EscrowStatus.REFUNDED


class TestStampTerminalCas:
    """Unit pins for the conditional stamp: merge-on-current, never a
    whole-entry overwrite of a newer state."""

    def test_stamp_merges_updates_onto_current_entry(self):
        escrow = PaymentEscrow()
        entry = _released_entry(escrow)
        live = escrow.get_escrow(entry.escrow_id)
        # A stale detached copy claiming different field values must NOT be
        # written back — only the metadata updates land, on the live row.
        stale = EscrowEntry(
            escrow_id=entry.escrow_id,
            task_id=entry.task_id,
            chain_id=entry.chain_id,
            requester=entry.requester,
            agent=entry.agent,
            amount=999_999,  # stale garbage the old persist_terminal would persist
            status=EscrowStatus.RELEASED,
            tx_hash_release=RELEASE_TX,
            metadata={"settle_probe_confirmed_at": 1.0},
        )

        assert (
            escrow.stamp_terminal(
                stale,
                {META_SETTLE_PROBE_AT: 123.0},
                expected_status=EscrowStatus.RELEASED,
                expected_settle_tx_hash=RELEASE_TX,
            )
            is True
        )
        refreshed = escrow.get_escrow(entry.escrow_id)
        assert refreshed is live or refreshed.amount == 100
        assert refreshed.amount == 100  # the stale copy's fields never landed
        assert refreshed.metadata[META_SETTLE_PROBE_AT] == 123.0
        assert META_SETTLE_CONFIRMED_AT not in refreshed.metadata

    def test_stamp_rejects_on_attempt_mismatch(self):
        escrow = PaymentEscrow()
        entry = _refunded_entry(escrow)

        assert (
            escrow.stamp_terminal(
                entry,
                {META_SETTLE_CONFIRMED_AT: time.time()},
                expected_status=EscrowStatus.REFUNDED,
                expected_settle_tx_hash="0x" + "00" * 32,
            )
            is False
        )
        refreshed = escrow.get_escrow(entry.escrow_id)
        assert META_SETTLE_CONFIRMED_AT not in refreshed.metadata
        assert META_SETTLE_PROBE_AT not in refreshed.metadata

    def test_stamp_rejects_on_status_mismatch(self):
        escrow = PaymentEscrow()
        entry = _released_entry(escrow)

        assert (
            escrow.stamp_terminal(
                entry,
                {META_SETTLE_PROBE_AT: time.time()},
                expected_status=EscrowStatus.REFUNDED,
                expected_settle_tx_hash=None,
            )
            is False
        )
        assert META_SETTLE_PROBE_AT not in escrow.get_escrow(entry.escrow_id).metadata


class TestStoreOnlyAttemptCas:
    """The detached store-only row path (#1515 split): the CAS resolves the
    stored row, not the caller's copy, and a store-only stamp stays out of
    the hot cache."""

    def _mem_store(self):
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

        return _MemStore()

    def test_store_only_demote_rejects_replaced_attempt(self):
        store = self._mem_store()
        writer = PaymentEscrow(store=store)
        entry = _released_entry(writer)
        # Simulate the replacement attempt persisted by the live process.
        live = writer.get_escrow(entry.escrow_id)
        live.status = EscrowStatus.LOCKED
        writer.persist_entry(live)
        writer.release(entry.escrow_id, submitter=lambda *_a: "0x" + "ee" * 32)

        # A "restarted" reader sweeps the detached row; the probe observed
        # the OLD hash (RELEASE_TX) — the store now records the new one.
        reader = PaymentEscrow(store=store)
        detached = store.rows[entry.escrow_id]
        assert detached.tx_hash_release != RELEASE_TX

        assert (
            reader.demote_unsealed_settle(
                detached,
                expected_status=EscrowStatus.RELEASED,
                expected_settle_tx_hash=RELEASE_TX,
                reason="settle_tx_absent_from_chain",
            )
            is False
        )
        assert store.rows[entry.escrow_id].status == EscrowStatus.RELEASED

    def test_store_only_stamp_does_not_recache_or_overwrite(self):
        store = self._mem_store()
        writer = PaymentEscrow(store=store)
        _released_entry(writer)
        reader = PaymentEscrow(store=store)
        detached = next(iter(store.rows.values()))

        assert (
            reader.stamp_terminal(
                detached,
                {META_SETTLE_PROBE_AT: 5.0},
                expected_status=EscrowStatus.RELEASED,
                expected_settle_tx_hash=RELEASE_TX,
            )
            is True
        )
        # Persisted to the store, still out of the hot cache (#1515).
        assert store.rows[detached.escrow_id].metadata[META_SETTLE_PROBE_AT] == 5.0
        assert reader.get_all_escrows() == []
