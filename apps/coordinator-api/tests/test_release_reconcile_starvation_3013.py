"""#3013 pins: released/refunded hash-audit starvation.

``_find_unsealed_release_hashes`` / ``_find_unsealed_refund_hashes`` applied
``LIMIT batch_size*10`` *before* the Python-side ``_audit_due`` check. A full
head of recently-audited rows (fresh ``*_hash_audit_at`` stamps stay eligible
for the query) meant zero due rows were examined and every older eligible
payment stayed hidden until the 30-day window excluded it. The fix pages
with OFFSET — the sibling sweepers' pattern — collecting audit-due rows up
to the same ``batch_size*10`` budget, so RPC work stays bounded and audited
rows leave the due set via their stamp.
"""

from __future__ import annotations

from contextlib import nullcontext
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from aitbc_shared import JobPayment

from coordinator_api.contexts.payments.services.settlement_reconciler import SettlementReconciler


def _released_payment(db_session, job_id: str, released_at: datetime, meta_data: dict | None = None, **extra) -> JobPayment:
    payment = JobPayment(
        job_id=job_id,
        amount=Decimal("1.0"),
        status="released",
        transaction_hash=f"0xhash-{job_id}",
        released_at=released_at,
        meta_data=meta_data,
        **extra,
    )
    db_session.add(payment)
    db_session.commit()
    return payment


def _stamped_meta(stamp_key: str = "release_hash_audit_at") -> dict:
    return {stamp_key: datetime.now(UTC).isoformat()}


class _FakeResp:
    def __init__(self, status_code, payload=None):
        self.status_code = status_code
        self._payload = payload if payload is not None else {}

    def json(self):
        return self._payload


class _RecordingClient:
    """Answers every ``/rpc/transaction/{hash}`` GET as a sealed tx and
    records which hashes were probed."""

    def __init__(self):
        self.calls: list[str] = []

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def get(self, url, params=None):
        self.calls.append(url)
        if "/rpc/transaction/" in url:
            url.rsplit("/", 1)[-1]
            return _FakeResp(200, {"status": "confirmed", "block_height": 123, "type": "ESCROW_RELEASE"})
        return _FakeResp(200, [])


def _reconciler(db_session, **kwargs) -> SettlementReconciler:
    return SettlementReconciler(session_factory=lambda: nullcontext(db_session), **kwargs)


def _patch_rpc():
    client = _RecordingClient()
    settings = SimpleNamespace(blockchain_rpc_url="http://rpc.test")
    return (
        patch("coordinator_api.contexts.payments.services.payments.settings", settings),
        patch("coordinator_api.contexts.payments.services.settlement_reconciler.httpx.AsyncClient", return_value=client),
        client,
    )


@pytest.mark.asyncio
async def test_older_due_release_payment_is_not_starved_by_audited_head(db_session):
    """Headline defect: >batch_size*10 freshly-audited newer rows must not
    hide an older unstamped payment — the audit pages past them."""
    now = datetime.now(UTC)
    # 25 newer rows, all audited seconds ago — they fill the old LIMIT=20
    # (batch_size=2 -> budget 20) with zero due rows.
    for i in range(25):
        _released_payment(
            db_session,
            f"job-new-{i}",
            released_at=now - timedelta(hours=2) + timedelta(minutes=i),
            meta_data=_stamped_meta(),
        )
    # The older eligible row: inside the 30-day window, past min_age, never audited.
    old = _released_payment(db_session, "job-old", released_at=now - timedelta(hours=5))

    reconciler = _reconciler(db_session, batch_size=2, min_age_seconds=60)
    p1, p2, client = _patch_rpc()
    with p1, p2:
        counts = await reconciler._audit_release_hashes()

    assert counts["hash_ok"] == 1
    assert any("0xhash-job-old" in url for url in client.calls)
    db_session.refresh(old)
    assert old.meta_data["release_hash_audit_at"]


@pytest.mark.asyncio
async def test_audit_budget_still_bounds_rpc_work(db_session):
    """Forward progress must not become unbounded: at most batch_size*10
    due rows are audited per pass even when more are eligible."""
    now = datetime.now(UTC)
    for i in range(30):
        _released_payment(db_session, f"job-due-{i}", released_at=now - timedelta(hours=3))

    reconciler = _reconciler(db_session, batch_size=2, min_age_seconds=60)
    p1, p2, client = _patch_rpc()
    with p1, p2:
        counts = await reconciler._audit_release_hashes()

    assert counts["hash_ok"] == 20  # batch_size * 10
    assert len(client.calls) == 20


@pytest.mark.asyncio
async def test_refund_audit_pages_past_audited_head_too(db_session):
    """The refund sibling finder had the identical LIMIT-before-filter bug."""
    now = datetime.now(UTC)
    for i in range(25):
        db_session.add(
            JobPayment(
                job_id=f"job-rnew-{i}",
                amount=Decimal("1.0"),
                status="refunded",
                refund_transaction_hash=f"0xrefund-{i}",
                refunded_at=now - timedelta(hours=2) + timedelta(minutes=i),
                meta_data=_stamped_meta("refund_hash_audit_at"),
            )
        )
    db_session.commit()
    old = JobPayment(
        job_id="job-rold",
        amount=Decimal("1.0"),
        status="refunded",
        refund_transaction_hash="0xrefund-old",
        refunded_at=now - timedelta(hours=5),
    )
    db_session.add(old)
    db_session.commit()

    reconciler = _reconciler(db_session, batch_size=2, min_age_seconds=60)

    class _RefundClient(_RecordingClient):
        async def get(self, url, params=None):
            self.calls.append(url)
            if "/rpc/transaction/" in url:
                return _FakeResp(200, {"status": "confirmed", "block_height": 123, "type": "ESCROW_REFUND"})
            if "/rpc/transactions" in url:
                return _FakeResp(200, [])
            return _FakeResp(200, [])

    client = _RefundClient()
    settings = SimpleNamespace(blockchain_rpc_url="http://rpc.test")
    with (
        patch("coordinator_api.contexts.payments.services.payments.settings", settings),
        patch("coordinator_api.contexts.payments.services.settlement_reconciler.httpx.AsyncClient", return_value=client),
    ):
        counts = await reconciler._audit_refund_hashes()

    assert counts["refund_hash_ok"] == 1
    assert any("0xrefund-old" in url for url in client.calls)
