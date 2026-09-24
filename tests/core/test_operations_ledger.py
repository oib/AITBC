"""State-machine tests for the shared operation ledger (aitbc.operations).

The ledger is the server half of Idempotency-Key support: one durable row per
key, leased begin/complete/fail transitions, lease-expiry recovery, and an
``uncertain`` state for outcomes that must not be retried blindly.
"""

import sqlite3
import time

import pytest

from aitbc.operations import BeginStatus, OperationLedger, request_hash


@pytest.fixture
def db(tmp_path):
    return tmp_path / "operations.db"


@pytest.fixture
def ledger(db):
    return OperationLedger(db, service="svc", lease_seconds=60)


def _force_expired(db, key: str) -> None:
    """Push a row's lease into the past without touching its state."""
    conn = sqlite3.connect(db)
    conn.execute(
        "UPDATE operations SET lease_expires_at=? WHERE idempotency_key=?",
        (time.time() - 10, key),
    )
    conn.commit()
    conn.close()


class TestRequestHash:
    def test_stable_and_key_order_independent(self):
        assert request_hash({"b": 2, "a": 1}) == request_hash({"a": 1, "b": 2})

    def test_different_payloads_differ(self):
        assert request_hash({"a": 1}) != request_hash({"a": 2})


class TestBegin:
    def test_new_key_executes(self, ledger):
        r = ledger.begin("k1", "place_order", "h1")
        assert r.status is BeginStatus.EXECUTE
        assert r.attempt == 1

    def test_second_live_begin_is_in_progress(self, ledger):
        ledger.begin("k1", "op", "h1")
        r = ledger.begin("k1", "op", "h1")
        assert r.status is BeginStatus.IN_PROGRESS

    def test_completed_replays_stored_result(self, ledger):
        b = ledger.begin("k1", "op", "h1")
        assert ledger.complete("k1", b.attempt, {"id": 7}, response_status=201)
        r = ledger.begin("k1", "op", "h1")
        assert r.status is BeginStatus.REPLAY
        assert r.result == {"id": 7}
        assert r.response_status == 201

    def test_completed_different_hash_conflicts(self, ledger):
        b = ledger.begin("k1", "op", "h1")
        ledger.complete("k1", b.attempt, {"ok": True})
        assert ledger.begin("k1", "op", "h2").status is BeginStatus.CONFLICT

    def test_failed_different_hash_conflicts(self, ledger):
        b = ledger.begin("k1", "op", "h1")
        ledger.fail("k1", b.attempt, "boom")
        assert ledger.begin("k1", "op", "h2").status is BeginStatus.CONFLICT

    def test_failed_retries_same_hash(self, ledger):
        b = ledger.begin("k1", "op", "h1")
        ledger.fail("k1", b.attempt, "boom")
        r = ledger.begin("k1", "op", "h1")
        assert r.status is BeginStatus.EXECUTE
        assert r.attempt == 2

    def test_expired_pending_adopted_when_allowed(self, ledger, db):
        ledger.begin("k1", "op", "h1")
        _force_expired(db, "k1")
        r = ledger.begin("k1", "op", "h1")
        assert r.status is BeginStatus.EXECUTE
        assert r.attempt == 2

    def test_expired_pending_quarantined_when_not_allowed(self, ledger, db):
        ledger.begin("k1", "op", "h1", allow_adopt=False)
        _force_expired(db, "k1")
        r = ledger.begin("k1", "op", "h1")
        assert r.status is BeginStatus.UNCERTAIN
        # and stays uncertain until resolved
        assert ledger.begin("k1", "op", "h1").status is BeginStatus.UNCERTAIN
        assert ledger.get("k1").state == "uncertain"

    def test_attempt_guard_blocks_stale_completion(self, ledger, db):
        ledger.begin("k1", "op", "h1")
        _force_expired(db, "k1")
        r2 = ledger.begin("k1", "op", "h1")
        assert r2.attempt == 2
        # The preempted attempt can no longer write.
        assert ledger.complete("k1", 1, {"stale": True}) is False
        assert ledger.complete("k1", 2, {"fresh": True}) is True


class TestSharedConnectionAtomicity:
    """With a caller-supplied connection the ledger row joins the domain txn."""

    def test_rollback_removes_pending_row(self, db):
        OperationLedger(db, service="svc")  # create schema
        ledger = OperationLedger(db, service="svc")
        conn = sqlite3.connect(db)
        conn.execute("BEGIN IMMEDIATE")
        b = ledger.begin("k1", "op", "h1", conn=conn)
        assert b.status is BeginStatus.EXECUTE
        conn.rollback()  # simulate crash before domain commit
        conn.close()
        assert ledger.get("k1") is None

    def test_commit_persists_completed_row(self, db):
        ledger = OperationLedger(db, service="svc")
        conn = sqlite3.connect(db)
        conn.execute("BEGIN IMMEDIATE")
        b = ledger.begin("k1", "op", "h1", conn=conn)
        ledger.complete("k1", b.attempt, {"id": 1}, conn=conn)
        conn.commit()
        conn.close()
        r = ledger.begin("k1", "op", "h1")
        assert r.status is BeginStatus.REPLAY and r.result == {"id": 1}


class TestReconcileAndPurge:
    def test_reconcile_expires_adoptable_to_failed(self, ledger, db):
        ledger.begin("k1", "op", "h1")
        _force_expired(db, "k1")
        report = ledger.reconcile()
        assert report == {"expired_to_failed": 1, "expired_to_uncertain": 0}
        assert ledger.get("k1").state == "failed"

    def test_reconcile_expired_nonadoptable_to_uncertain(self, ledger, db):
        ledger.begin("k1", "op", "h1", allow_adopt=False)
        _force_expired(db, "k1")
        report = ledger.reconcile()
        assert report == {"expired_to_failed": 0, "expired_to_uncertain": 1}
        assert ledger.get("k1").state == "uncertain"

    def test_reconcile_leaves_live_pending(self, ledger):
        ledger.begin("k1", "op", "h1")
        assert ledger.reconcile() == {"expired_to_failed": 0, "expired_to_uncertain": 0}
        assert ledger.get("k1").state == "pending"

    def test_purge_removes_old_terminal_but_keeps_uncertain(self, ledger, db):
        b = ledger.begin("old", "op", "h1")
        ledger.complete("old", b.attempt, {})
        b = ledger.begin("bad", "op", "h2", allow_adopt=False)
        ledger.fail("bad", b.attempt, "?", terminal=True)
        conn = sqlite3.connect(db)
        conn.execute("UPDATE operations SET updated_at=?", (time.time() - 90 * 86400,))
        conn.commit()
        conn.close()
        assert ledger.purge(retention_seconds=30 * 86400) == 1
        assert ledger.get("old") is None
        assert ledger.get("bad").state == "uncertain"


class TestResolve:
    def test_resolve_makes_uncertain_retryable(self, ledger):
        b = ledger.begin("k1", "op", "h1", allow_adopt=False)
        ledger.fail("k1", b.attempt, "ambiguous", terminal=True)
        assert ledger.begin("k1", "op", "h1").status is BeginStatus.UNCERTAIN
        assert ledger.resolve("k1") is True
        r = ledger.begin("k1", "op", "h1")
        assert r.status is BeginStatus.EXECUTE

    def test_resolve_rejects_non_uncertain(self, ledger):
        ledger.begin("k1", "op", "h1")
        assert ledger.resolve("k1") is False


class TestServiceIsolation:
    def test_same_key_different_services(self, db):
        a = OperationLedger(db, service="svc-a")
        b = OperationLedger(db, service="svc-b")
        ba = a.begin("k1", "op", "h1")
        a.complete("k1", ba.attempt, {"who": "a"})
        rb = b.begin("k1", "op", "h1")
        assert rb.status is BeginStatus.EXECUTE  # not a replay of svc-a's row
