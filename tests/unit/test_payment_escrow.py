"""Unit tests for aitbc.crypto.payment_escrow (v0.6.5 §A2).

Covers the full escrow lifecycle (PENDING → LOCKED → RELEASED/REFUNDED),
callback wiring, expiry/refund, and lookup helpers. No blockchain node
required — callbacks are stubbed with deterministic fake tx hashes.
"""

from __future__ import annotations

import time
from collections.abc import Callable

import pytest

from aitbc.crypto.payment_escrow import (
    EscrowEntry,
    EscrowStatus,
    PaymentEscrow,
)

REQUESTER = "0x" + "11" * 20
AGENT = "0x" + "22" * 20
CHAIN_ID = "ait-hub"


def _make_lock_callback(calls: list[tuple[str, str, str, int]]) -> Callable[[str, str, str, int], str]:
    def _cb(chain_id: str, from_addr: str, to_addr: str, amount: int) -> str:
        calls.append((chain_id, from_addr, to_addr, amount))
        return "lock-tx-" + str(len(calls))

    return _cb


def _make_release_callback(calls: list[tuple[str, str, str, int]]) -> Callable[[str, str, str, int], str]:
    def _cb(chain_id: str, from_addr: str, to_addr: str, amount: int) -> str:
        calls.append((chain_id, from_addr, to_addr, amount))
        return "release-tx-" + str(len(calls))

    return _cb


def _make_refund_callback(calls: list[tuple[str, str, str, int]]) -> Callable[[str, str, str, int], str]:
    def _cb(chain_id: str, from_addr: str, to_addr: str, amount: int) -> str:
        calls.append((chain_id, from_addr, to_addr, amount))
        return "refund-tx-" + str(len(calls))

    return _cb


# ---------------------------------------------------------------------------
# create_escrow
# ---------------------------------------------------------------------------


def test_create_escrow() -> None:
    escrow = PaymentEscrow()
    entry = escrow.create_escrow(
        task_id="task-1",
        chain_id=CHAIN_ID,
        requester=REQUESTER,
        agent=AGENT,
        amount=1000,
        fee=10,
    )
    assert entry.task_id == "task-1"
    assert entry.chain_id == CHAIN_ID
    assert entry.requester == REQUESTER
    assert entry.agent == AGENT
    assert entry.amount == 1000
    assert entry.fee == 10
    assert entry.status == EscrowStatus.PENDING
    assert entry.escrow_id  # uuid populated
    assert entry.expires_at is not None
    assert entry.created_at <= time.time()
    assert entry.locked_at is None
    assert entry.tx_hash_lock is None


def test_create_escrow_zero_amount_raises() -> None:
    escrow = PaymentEscrow()
    with pytest.raises(ValueError, match="must be positive"):
        escrow.create_escrow("task-1", CHAIN_ID, REQUESTER, AGENT, amount=0)
    with pytest.raises(ValueError, match="must be positive"):
        escrow.create_escrow("task-1", CHAIN_ID, REQUESTER, AGENT, amount=-5)


def test_default_timeout() -> None:
    escrow = PaymentEscrow(default_timeout=60.0)
    entry = escrow.create_escrow("task-1", CHAIN_ID, REQUESTER, AGENT, amount=100)
    assert entry.expires_at is not None
    # expires ~60s in the future, not the 3600 default
    assert 55 <= (entry.expires_at - time.time()) <= 65


def test_create_escrow_custom_timeout() -> None:
    escrow = PaymentEscrow(default_timeout=3600.0)
    entry = escrow.create_escrow("task-1", CHAIN_ID, REQUESTER, AGENT, amount=100, timeout=10.0)
    assert entry.expires_at is not None
    assert 5 <= (entry.expires_at - time.time()) <= 15


# ---------------------------------------------------------------------------
# lock
# ---------------------------------------------------------------------------


def test_lock_pending_escrow() -> None:
    escrow = PaymentEscrow()
    entry = escrow.create_escrow("task-1", CHAIN_ID, REQUESTER, AGENT, amount=100)
    locked = escrow.lock(entry.escrow_id)
    assert locked.status == EscrowStatus.LOCKED
    assert locked.locked_at is not None
    assert locked is entry  # same object, mutated in place


def test_lock_non_pending_raises() -> None:
    escrow = PaymentEscrow()
    entry = escrow.create_escrow("task-1", CHAIN_ID, REQUESTER, AGENT, amount=100)
    escrow.lock(entry.escrow_id)
    with pytest.raises(ValueError, match="not pending"):
        escrow.lock(entry.escrow_id)


def test_lock_unknown_raises() -> None:
    escrow = PaymentEscrow()
    with pytest.raises(ValueError, match="not found"):
        escrow.lock("does-not-exist")


def test_lock_callback_called() -> None:
    calls: list[tuple[str, str, str, int]] = []
    escrow = PaymentEscrow(lock_callback=_make_lock_callback(calls))
    entry = escrow.create_escrow("task-1", CHAIN_ID, REQUESTER, AGENT, amount=500)
    escrow.lock(entry.escrow_id)
    assert calls == [(CHAIN_ID, REQUESTER, AGENT, 500)]
    assert entry.tx_hash_lock == "lock-tx-1"


def test_no_callback_still_works() -> None:
    escrow = PaymentEscrow()  # no callbacks
    entry = escrow.create_escrow("task-1", CHAIN_ID, REQUESTER, AGENT, amount=100)
    escrow.lock(entry.escrow_id)
    assert entry.status == EscrowStatus.LOCKED
    assert entry.tx_hash_lock is None  # no callback → no tx hash
    escrow.release(entry.escrow_id)
    assert entry.status == EscrowStatus.RELEASED
    assert entry.tx_hash_release is None


# ---------------------------------------------------------------------------
# release
# ---------------------------------------------------------------------------


def test_release_locked_escrow() -> None:
    escrow = PaymentEscrow()
    entry = escrow.create_escrow("task-1", CHAIN_ID, REQUESTER, AGENT, amount=100)
    escrow.lock(entry.escrow_id)
    released = escrow.release(entry.escrow_id)
    assert released.status == EscrowStatus.RELEASED
    assert released.released_at is not None


def test_release_non_locked_raises() -> None:
    escrow = PaymentEscrow()
    entry = escrow.create_escrow("task-1", CHAIN_ID, REQUESTER, AGENT, amount=100)
    with pytest.raises(ValueError, match="not locked"):
        escrow.release(entry.escrow_id)


def test_release_callback_called() -> None:
    calls: list[tuple[str, str, str, int]] = []
    escrow = PaymentEscrow(release_callback=_make_release_callback(calls))
    entry = escrow.create_escrow("task-1", CHAIN_ID, REQUESTER, AGENT, amount=500)
    escrow.lock(entry.escrow_id)
    escrow.release(entry.escrow_id)
    # release sends from requester -> agent
    assert calls == [(CHAIN_ID, REQUESTER, AGENT, 500)]
    assert entry.tx_hash_release == "release-tx-1"


# ---------------------------------------------------------------------------
# refund
# ---------------------------------------------------------------------------


def test_refund_locked_escrow() -> None:
    escrow = PaymentEscrow()
    entry = escrow.create_escrow("task-1", CHAIN_ID, REQUESTER, AGENT, amount=100)
    escrow.lock(entry.escrow_id)
    refunded = escrow.refund(entry.escrow_id)
    assert refunded.status == EscrowStatus.REFUNDED


def test_refund_non_locked_raises() -> None:
    escrow = PaymentEscrow()
    entry = escrow.create_escrow("task-1", CHAIN_ID, REQUESTER, AGENT, amount=100)
    with pytest.raises(ValueError, match="not locked"):
        escrow.refund(entry.escrow_id)
    escrow.lock(entry.escrow_id)
    escrow.release(entry.escrow_id)
    with pytest.raises(ValueError, match="not locked"):
        escrow.refund(entry.escrow_id)


def test_refund_callback_called() -> None:
    calls: list[tuple[str, str, str, int]] = []
    escrow = PaymentEscrow(refund_callback=_make_refund_callback(calls))
    entry = escrow.create_escrow("task-1", CHAIN_ID, REQUESTER, AGENT, amount=500)
    escrow.lock(entry.escrow_id)
    escrow.refund(entry.escrow_id)
    # refund sends from agent -> requester (funds return to payer)
    assert calls == [(CHAIN_ID, AGENT, REQUESTER, 500)]
    assert entry.tx_hash_refund == "refund-tx-1"


# ---------------------------------------------------------------------------
# expire_stale
# ---------------------------------------------------------------------------


def test_expire_stale_refunds() -> None:
    refund_calls: list[tuple[str, str, str, int]] = []
    escrow = PaymentEscrow(refund_callback=_make_refund_callback(refund_calls))
    # timeout=0 → already expired at creation time
    entry = escrow.create_escrow("task-1", CHAIN_ID, REQUESTER, AGENT, amount=100, timeout=0.0)
    escrow.lock(entry.escrow_id)
    # Sleep a hair so now > expires_at deterministically.
    time.sleep(0.01)
    expired = escrow.expire_stale()
    assert len(expired) == 1
    assert expired[0].status == EscrowStatus.REFUNDED
    assert refund_calls == [(CHAIN_ID, AGENT, REQUESTER, 100)]


def test_expire_stale_no_locked() -> None:
    escrow = PaymentEscrow()
    # Pending escrow, not locked → not expired
    escrow.create_escrow("task-1", CHAIN_ID, REQUESTER, AGENT, amount=100, timeout=0.0)
    assert escrow.expire_stale() == []


def test_expire_stale_skips_non_expired() -> None:
    escrow = PaymentEscrow()
    entry = escrow.create_escrow("task-1", CHAIN_ID, REQUESTER, AGENT, amount=100, timeout=3600.0)
    escrow.lock(entry.escrow_id)
    assert escrow.expire_stale() == []
    assert entry.status == EscrowStatus.LOCKED


# ---------------------------------------------------------------------------
# lookup helpers
# ---------------------------------------------------------------------------


def test_get_escrow() -> None:
    escrow = PaymentEscrow()
    entry = escrow.create_escrow("task-1", CHAIN_ID, REQUESTER, AGENT, amount=100)
    assert escrow.get_escrow(entry.escrow_id) is entry
    assert escrow.get_escrow("missing") is None


def test_get_escrow_for_task() -> None:
    escrow = PaymentEscrow()
    entry = escrow.create_escrow("task-42", CHAIN_ID, REQUESTER, AGENT, amount=100)
    assert escrow.get_escrow_for_task("task-42") is entry
    assert escrow.get_escrow_for_task("missing") is None


def test_get_escrows_by_status() -> None:
    escrow = PaymentEscrow()
    e1 = escrow.create_escrow("t1", CHAIN_ID, REQUESTER, AGENT, amount=100)
    e2 = escrow.create_escrow("t2", CHAIN_ID, REQUESTER, AGENT, amount=200)
    escrow.lock(e2.escrow_id)
    pending = escrow.get_escrows_by_status(EscrowStatus.PENDING)
    locked = escrow.get_escrows_by_status(EscrowStatus.LOCKED)
    assert pending == [e1]
    assert locked == [e2]
    assert escrow.get_escrows_by_status(EscrowStatus.RELEASED) == []


def test_get_all_escrows() -> None:
    escrow = PaymentEscrow()
    e1 = escrow.create_escrow("t1", CHAIN_ID, REQUESTER, AGENT, amount=100)
    e2 = escrow.create_escrow("t2", CHAIN_ID, REQUESTER, AGENT, amount=200)
    all_entries = escrow.get_all_escrows()
    assert len(all_entries) == 2
    assert e1 in all_entries
    assert e2 in all_entries


# ---------------------------------------------------------------------------
# package re-export
# ---------------------------------------------------------------------------


def test_package_reexport() -> None:
    from aitbc.crypto import EscrowEntry as ExportedEntry, EscrowStatus as ExportedStatus, PaymentEscrow as ExportedEscrow

    assert ExportedEntry is EscrowEntry
    assert ExportedStatus is EscrowStatus
    assert ExportedEscrow is PaymentEscrow
