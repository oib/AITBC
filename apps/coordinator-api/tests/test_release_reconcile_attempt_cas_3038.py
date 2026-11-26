"""#3038 pins: stale release-audit evidence must not overwrite or stamp a newer attempt.

``_audit_one_release_hash`` snapshots ``transaction_hash`` before the chain
awaits; ``_readopt_release_hash`` historically checked only
``status == "released"`` — the identical snapshot-then-write shape #3033
fixed for refunds. The bare ``_mark_audited`` stamps (hash_ok / unbacked /
ambiguous on release, ok / ambiguous on refund) had the same hole: a stale
audit's stamp lands on whatever attempt the row carries now, deferring the
*newer* attempt's audit by ~20h. The fix CAS-guards the readopt on the
probed hash and scopes every stamp to the probed attempt.
"""

from __future__ import annotations

from contextlib import nullcontext
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from unittest.mock import AsyncMock, patch

import pytest
from sqlmodel import Session

from aitbc_shared import JobPayment

from coordinator_api.contexts.payments.services.settlement_reconciler import SettlementReconciler

OLD_HASH = "0xold-release-attempt"
NEW_HASH = "0xnewer-release-attempt"
SEALED_OTHER = "0xsealed-release-replacement"
REFUND_OLD = "0xold-refund-attempt"
REFUND_NEW = "0xnewer-refund-attempt"


def _release_payment() -> JobPayment:
    return JobPayment(
        job_id="job-cas-3038",
        amount=Decimal("1.0"),
        status="released",
        transaction_hash=OLD_HASH,
        released_at=datetime.now(UTC) - timedelta(hours=2),
        meta_data={},
    )


def _refund_payment() -> JobPayment:
    return JobPayment(
        job_id="job-cas-3038",
        amount=Decimal("1.0"),
        status="refunded",
        refund_transaction_hash=REFUND_OLD,
        refunded_at=datetime.now(UTC) - timedelta(hours=2),
        meta_data={},
    )


def _persist_release_attempt(db_engine, payment_id: str, new_hash: str = NEW_HASH) -> None:
    """The 'other worker': a separate transaction persists a newer release
    attempt — new hash on the still-released row."""
    with Session(db_engine) as other:
        payment = other.get(JobPayment, payment_id)
        assert payment is not None
        payment.transaction_hash = new_hash
        payment.released_at = datetime.now(UTC)
        other.add(payment)
        other.commit()


def _persist_refund_attempt(db_engine, payment_id: str, new_hash: str = REFUND_NEW) -> None:
    with Session(db_engine) as other:
        payment = other.get(JobPayment, payment_id)
        assert payment is not None
        payment.refund_transaction_hash = new_hash
        payment.refunded_at = datetime.now(UTC)
        other.add(payment)
        other.commit()


def _reconciler(db_session) -> SettlementReconciler:
    return SettlementReconciler(session_factory=lambda: nullcontext(db_session), batch_size=2, min_age_seconds=60)


# --- readopt CAS -------------------------------------------------------------


@pytest.mark.asyncio
async def test_stale_release_readopt_cannot_overwrite_a_newer_attempt(db_session, db_engine):
    """Recorded release hash dead + exactly one other sealed release →
    readopt. A newer attempt lands mid-probe: the adoption must NOT fire —
    the row keeps the newer hash instead of the audit's stale replacement."""
    payment = _release_payment()
    db_session.add(payment)
    db_session.commit()

    async def _sealed_after_newer_attempt(_self, client, rpc, job_id, tx_type):
        _persist_release_attempt(db_engine, payment.id)
        return {SEALED_OTHER}

    reconciler = _reconciler(db_session)
    with (
        patch.object(SettlementReconciler, "_recorded_hash_state", new=AsyncMock(return_value=False)),
        patch.object(SettlementReconciler, "_sealed_settlement_hashes", new=_sealed_after_newer_attempt),
    ):
        counts = await reconciler._audit_release_hashes()

    assert counts["hash_readopted"] == 0
    db_session.expire_all()
    fresh = db_session.get(JobPayment, payment.id)
    assert fresh.status == "released"
    assert fresh.transaction_hash == NEW_HASH
    assert "release_tx_hash_corrected" not in (fresh.meta_data or {})


@pytest.mark.asyncio
async def test_uncontended_release_readopt_still_fires(db_session):
    """Control: with no concurrent write the sealed replacement is adopted
    exactly as before — the CAS only blocks *changed* attempts."""
    payment = _release_payment()
    db_session.add(payment)
    db_session.commit()

    reconciler = _reconciler(db_session)
    with (
        patch.object(SettlementReconciler, "_recorded_hash_state", new=AsyncMock(return_value=False)),
        patch.object(SettlementReconciler, "_sealed_settlement_hashes", new=AsyncMock(return_value={SEALED_OTHER})),
    ):
        counts = await reconciler._audit_release_hashes()

    assert counts["hash_readopted"] == 1
    db_session.expire_all()
    fresh = db_session.get(JobPayment, payment.id)
    assert fresh.transaction_hash == SEALED_OTHER
    assert fresh.meta_data["release_tx_hash_corrected"]["to"] == SEALED_OTHER


# --- attempt-scoped audit stamps ----------------------------------------------


@pytest.mark.asyncio
async def test_stale_hash_ok_stamp_cannot_land_on_a_newer_release_attempt(db_session, db_engine):
    """hash_ok path: recorded hash confirms, but a newer attempt lands during
    the probe — the 20h stamp must NOT be written onto the new attempt."""
    payment = _release_payment()
    db_session.add(payment)
    db_session.commit()

    async def _state_after_newer_attempt(_self, client, rpc, tx_hash, tx_type="ESCROW_RELEASE"):
        _persist_release_attempt(db_engine, payment.id)
        return True

    reconciler = _reconciler(db_session)
    with patch.object(SettlementReconciler, "_recorded_hash_state", new=_state_after_newer_attempt):
        counts = await reconciler._audit_release_hashes()

    assert counts["hash_ok"] == 1
    db_session.expire_all()
    fresh = db_session.get(JobPayment, payment.id)
    assert fresh.transaction_hash == NEW_HASH
    assert "release_hash_audit_at" not in (fresh.meta_data or {})


@pytest.mark.asyncio
async def test_stale_unbacked_stamp_cannot_land_on_a_newer_release_attempt(db_session, db_engine):
    """unbacked path: dead recorded hash + authoritative empty sealed set →
    critical stamp. Newer attempt mid-probe → no stamp on the new attempt."""
    payment = _release_payment()
    db_session.add(payment)
    db_session.commit()

    async def _sealed_after_newer_attempt(_self, client, rpc, job_id, tx_type):
        _persist_release_attempt(db_engine, payment.id)
        return set()

    reconciler = _reconciler(db_session)
    with (
        patch.object(SettlementReconciler, "_recorded_hash_state", new=AsyncMock(return_value=False)),
        patch.object(SettlementReconciler, "_sealed_settlement_hashes", new=_sealed_after_newer_attempt),
    ):
        counts = await reconciler._audit_release_hashes()

    assert counts["hash_unbacked"] == 1
    db_session.expire_all()
    fresh = db_session.get(JobPayment, payment.id)
    assert fresh.transaction_hash == NEW_HASH
    assert "release_hash_audit_at" not in (fresh.meta_data or {})


@pytest.mark.asyncio
async def test_stale_ambiguous_stamp_cannot_land_on_a_newer_release_attempt(db_session, db_engine):
    """ambiguous path: dead recorded hash + multiple sealed releases →
    leave-recorded stamp. Newer attempt mid-probe → no stamp on it."""
    payment = _release_payment()
    db_session.add(payment)
    db_session.commit()

    async def _sealed_after_newer_attempt(_self, client, rpc, job_id, tx_type):
        _persist_release_attempt(db_engine, payment.id)
        return {"0xaaa", "0xbbb"}

    reconciler = _reconciler(db_session)
    with (
        patch.object(SettlementReconciler, "_recorded_hash_state", new=AsyncMock(return_value=False)),
        patch.object(SettlementReconciler, "_sealed_settlement_hashes", new=_sealed_after_newer_attempt),
    ):
        counts = await reconciler._audit_release_hashes()

    assert counts["hash_ambiguous"] == 1
    db_session.expire_all()
    fresh = db_session.get(JobPayment, payment.id)
    assert fresh.transaction_hash == NEW_HASH
    assert "release_hash_audit_at" not in (fresh.meta_data or {})


@pytest.mark.asyncio
async def test_stale_refund_ok_stamp_cannot_land_on_a_newer_attempt(db_session, db_engine):
    """Refund ok path — same class on the sibling audit: a newer refund
    attempt landing mid-probe must not receive the stale 20h stamp."""
    payment = _refund_payment()
    db_session.add(payment)
    db_session.commit()

    async def _state_after_newer_attempt(_self, client, rpc, tx_hash, tx_type="ESCROW_REFUND"):
        _persist_refund_attempt(db_engine, payment.id)
        return True

    reconciler = _reconciler(db_session)
    with patch.object(SettlementReconciler, "_recorded_hash_state", new=_state_after_newer_attempt):
        counts = await reconciler._audit_refund_hashes()

    assert counts["refund_hash_ok"] == 1
    db_session.expire_all()
    fresh = db_session.get(JobPayment, payment.id)
    assert fresh.refund_transaction_hash == REFUND_NEW
    assert "refund_hash_audit_at" not in (fresh.meta_data or {})


@pytest.mark.asyncio
async def test_stale_refund_ambiguous_stamp_cannot_land_on_a_newer_attempt(db_session, db_engine):
    """Refund ambiguous path — same class: no stale stamp on the newer
    refund attempt."""
    payment = _refund_payment()
    db_session.add(payment)
    db_session.commit()

    async def _sealed_after_newer_attempt(_self, client, rpc, job_id, tx_type):
        _persist_refund_attempt(db_engine, payment.id)
        return {"0xaaa", "0xbbb"}

    reconciler = _reconciler(db_session)
    with (
        patch.object(SettlementReconciler, "_recorded_hash_state", new=AsyncMock(return_value=False)),
        patch.object(SettlementReconciler, "_sealed_settlement_hashes", new=_sealed_after_newer_attempt),
    ):
        counts = await reconciler._audit_refund_hashes()

    assert counts["refund_hash_ambiguous"] == 1
    db_session.expire_all()
    fresh = db_session.get(JobPayment, payment.id)
    assert fresh.refund_transaction_hash == REFUND_NEW
    assert "refund_hash_audit_at" not in (fresh.meta_data or {})


@pytest.mark.asyncio
async def test_uncontended_audit_stamp_still_fires(db_session):
    """Control: no concurrent write → the hash_ok stamp lands normally."""
    payment = _release_payment()
    db_session.add(payment)
    db_session.commit()

    reconciler = _reconciler(db_session)
    with patch.object(SettlementReconciler, "_recorded_hash_state", new=AsyncMock(return_value=True)):
        counts = await reconciler._audit_release_hashes()

    assert counts["hash_ok"] == 1
    db_session.expire_all()
    fresh = db_session.get(JobPayment, payment.id)
    assert "release_hash_audit_at" in (fresh.meta_data or {})
