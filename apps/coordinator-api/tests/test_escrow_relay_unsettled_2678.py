"""Unsettled chain answers must not become dedup rows (#2678).

The release/refund relays used to insert an ``EscrowReleaseRelay`` /
``EscrowRefundRelay`` row for *any* chain answer — including the chain's
``{"success": false, "settlement_status": "unsettled"}`` rollback. Every
retry then replayed ``_stored_result`` = ``success: true`` with a null
tx_hash while the escrow stayed locked. These tests pin that an unsettled
answer records no row and a retry re-attempts the chain call, and that a
later settled answer dedups normally.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from unittest.mock import AsyncMock, patch

from sqlmodel import Session, select

from aitbc.auth import create_access_token
from aitbc_shared import JobPayment

from coordinator_api.contexts.infrastructure.domain.job import Job
from coordinator_api.contexts.infrastructure.domain.user import User, Wallet
from coordinator_api.contexts.payments.domain.escrow_refund_relay import EscrowRefundRelay
from coordinator_api.contexts.payments.domain.escrow_release_relay import EscrowReleaseRelay

BUYER = "0x08aB801150eF3496344cFA78fe025c3B48Caf435"
PROVIDER = "0xF4924759508E420eeD947BD33326731B11c4B7Df"
FUTURE = datetime.now(UTC) + timedelta(hours=1)

UNSETTLED_RELEASE = {
    "success": False,
    "contract_id": "0xc1",
    "job_id": "job_u1",
    "message": "Escrow release could not be settled on-chain; the provider was not paid",
    "released_amount": "2.0",
    "refunded_amount": "0",
    "refund_tx_hash": None,
    "tx_hash": None,
    "settlement_status": "unsettled",
    "released_at": None,
}

UNSETTLED_REFUND = {
    "success": False,
    "contract_id": "0xc1",
    "job_id": "job_u2",
    "message": "Escrow refund could not be settled on-chain; the buyer was not refunded",
    "refund_tx_hash": None,
}


def _escrow(job_id: str) -> dict:
    return {
        "job_id": job_id,
        "contract_id": "0xc1",
        "state": "funded",
        "buyer": BUYER,
        "provider": PROVIDER,
        "amount": "2.0",
        "released_at": None,
        "refunded_at": None,
        "release_tx_hash": None,
        "refund_tx_hash": None,
    }


def _actor(db_session: Session, sub: str) -> dict[str, str]:
    """Bind BUYER to *sub* and return its JWT headers."""
    if db_session.get(User, sub) is None:
        db_session.add(User(id=sub, email=f"{sub}@example.com", username=sub))
    existing = db_session.execute(select(Wallet).where(Wallet.address == BUYER.lower())).scalars().first()
    if existing is not None:
        existing.user_id = sub
    else:
        db_session.add(Wallet(user_id=sub, address=BUYER.lower()))
    db_session.commit()
    return {"Authorization": f"Bearer {create_access_token(sub, 'client')}"}


def _chain_client(escrow: dict, post_returns: list) -> AsyncMock:
    """Chain stub: GET escrow, GET transactions (refund path), POST pops *post_returns*."""
    client = AsyncMock()
    client.get.return_value = escrow
    client.get_json.return_value = []
    client.post.side_effect = post_returns
    return client


def _release_patch():
    return patch("coordinator_api.contexts.payments.services.escrow_release_relay.AsyncAITBCHTTPClient")


def _refund_patch():
    return patch("coordinator_api.contexts.payments.services.escrow_refund_relay.AsyncAITBCHTTPClient")


class TestReleaseUnsettled:
    def test_unsettled_records_no_row_and_retry_reattempts(self, client, db_session):
        headers = _actor(db_session, "u-rel-1")
        mock_client = _chain_client(
            _escrow("job_u1"),
            [
                dict(UNSETTLED_RELEASE),
                {"success": True, "tx_hash": "0xrel_ok", "contract_id": "0xc1"},
                {"success": True, "tx_hash": "0xrel_dup", "contract_id": "0xc1"},
            ],
        )
        with _release_patch() as cls:
            cls.return_value = mock_client
            first = client.post("/v1/escrow/release", json={"job_id": "job_u1"}, headers=headers)
            assert first.status_code == 200, first.text
            assert first.json()["success"] is False
            # No dedup row: the escrow is not wedged.
            assert db_session.execute(select(EscrowReleaseRelay)).scalars().all() == []

            second = client.post("/v1/escrow/release", json={"job_id": "job_u1"}, headers=headers)
            assert second.status_code == 200, second.text
            assert second.json()["success"] is True
            assert second.json()["tx_hash"] == "0xrel_ok"
            rows = db_session.execute(select(EscrowReleaseRelay)).scalars().all()
            assert len(rows) == 1 and rows[0].tx_hash == "0xrel_ok"

            # Third call replays the stored row — no third chain POST.
            third = client.post("/v1/escrow/release", json={"job_id": "job_u1"}, headers=headers)
            assert third.status_code == 200, third.text
            assert third.json()["duplicate"] is True
            assert mock_client.post.await_count == 2


class TestRefundUnsettled:
    def _job(self, db_session: Session, job_id: str, client_id: str) -> None:
        db_session.add(
            Job(
                id=job_id,
                client_id=client_id,
                state="FAILED",
                payload={},
                constraints={},
                expires_at=FUTURE,
            )
        )
        db_session.add(JobPayment(job_id=job_id, amount=Decimal("2.0"), status="escrowed"))
        db_session.commit()

    def test_unsettled_records_no_row_and_retry_reattempts(self, client, db_session):
        headers = _actor(db_session, "u-ref-1")
        self._job(db_session, "job_u2", "u-ref-1")
        mock_client = _chain_client(
            _escrow("job_u2"),
            [
                dict(UNSETTLED_REFUND),
                {"success": True, "refund_tx_hash": "0xref_ok", "contract_id": "0xc1"},
                {"success": True, "refund_tx_hash": "0xref_dup", "contract_id": "0xc1"},
            ],
        )
        with _refund_patch() as cls:
            cls.return_value = mock_client
            first = client.post("/v1/escrow/refund", json={"job_id": "job_u2"}, headers=headers)
            assert first.status_code == 200, first.text
            assert first.json()["success"] is False
            assert db_session.execute(select(EscrowRefundRelay)).scalars().all() == []

            second = client.post("/v1/escrow/refund", json={"job_id": "job_u2"}, headers=headers)
            assert second.status_code == 200, second.text
            assert second.json()["success"] is True
            assert second.json()["refund_tx_hash"] == "0xref_ok"
            rows = db_session.execute(select(EscrowRefundRelay)).scalars().all()
            assert len(rows) == 1 and rows[0].tx_hash == "0xref_ok"

            third = client.post("/v1/escrow/refund", json={"job_id": "job_u2"}, headers=headers)
            assert third.status_code == 200, third.text
            assert third.json()["duplicate"] is True
            assert mock_client.post.await_count == 2


class TestReleaseAmbiguousAnswer:
    """#2813: only a verified settle (success:true + tx_hash) may become a
    dedup row. Absent/malformed success re-checks the escrow on-chain and
    stays retryable; a landed release is recorded from chain state."""

    def test_absent_success_records_no_row_and_retry_reattempts(self, client, db_session):
        headers = _actor(db_session, "u-amb-1")
        mock_client = _chain_client(
            _escrow("job_a1"),
            [
                {"detail": "upstream hiccup"},
                {"success": True, "tx_hash": "0xrel_ok", "contract_id": "0xc1"},
            ],
        )
        with _release_patch() as cls:
            cls.return_value = mock_client
            first = client.post("/v1/escrow/release", json={"job_id": "job_a1"}, headers=headers)
            assert first.status_code == 200, first.text
            assert first.json()["success"] is False
            assert db_session.execute(select(EscrowReleaseRelay)).scalars().all() == []

            second = client.post("/v1/escrow/release", json={"job_id": "job_a1"}, headers=headers)
            assert second.status_code == 200, second.text
            assert second.json()["success"] is True
            assert second.json()["tx_hash"] == "0xrel_ok"
            rows = db_session.execute(select(EscrowReleaseRelay)).scalars().all()
            assert len(rows) == 1 and rows[0].tx_hash == "0xrel_ok"

    def test_success_true_without_tx_hash_is_retryable(self, client, db_session):
        headers = _actor(db_session, "u-amb-2")
        mock_client = _chain_client(
            _escrow("job_a2"),
            [
                {"success": True, "contract_id": "0xc1"},
                {"success": True, "tx_hash": "0xrel_ok", "contract_id": "0xc1"},
            ],
        )
        with _release_patch() as cls:
            cls.return_value = mock_client
            first = client.post("/v1/escrow/release", json={"job_id": "job_a2"}, headers=headers)
            assert first.status_code == 200, first.text
            assert first.json()["success"] is False
            assert db_session.execute(select(EscrowReleaseRelay)).scalars().all() == []

    def test_ambiguous_answer_but_escrow_released_records_from_chain(self, client, db_session):
        headers = _actor(db_session, "u-amb-3")
        released = _escrow("job_a3")
        released.update({"state": "released", "released_at": "2026-11-24T00:00:00+00:00", "release_tx_hash": "0xchain_rel"})
        mock_client = AsyncMock()
        mock_client.get.side_effect = [_escrow("job_a3"), released]
        mock_client.post.return_value = {"detail": "ambiguous"}
        with _release_patch() as cls:
            cls.return_value = mock_client
            resp = client.post("/v1/escrow/release", json={"job_id": "job_a3"}, headers=headers)
            assert resp.status_code == 200, resp.text
            body = resp.json()
            assert body["success"] is True
            assert body["tx_hash"] == "0xchain_rel"
            rows = db_session.execute(select(EscrowReleaseRelay)).scalars().all()
            assert len(rows) == 1 and rows[0].tx_hash == "0xchain_rel"


class TestHashlessDedupRow:
    """#2813: a dedup row recorded without tx_hash (pre-fix wedge) must not
    replay success forever — it re-drives the release and heals."""

    def _hashless_row(self, db_session: Session, job_id: str) -> None:
        db_session.add(EscrowReleaseRelay(client_id="u-wedge", job_id=job_id, tx_hash=None))
        db_session.commit()

    def test_hashless_row_redrives_and_heals(self, client, db_session):
        headers = _actor(db_session, "u-wedge-1")
        self._hashless_row(db_session, "job_w1")
        mock_client = _chain_client(
            _escrow("job_w1"),
            [{"success": True, "tx_hash": "0xnew_rel", "contract_id": "0xc1"}],
        )
        with _release_patch() as cls:
            cls.return_value = mock_client
            resp = client.post("/v1/escrow/release", json={"job_id": "job_w1"}, headers=headers)
            assert resp.status_code == 200, resp.text
            body = resp.json()
            assert body["success"] is True
            assert body["tx_hash"] == "0xnew_rel"
            assert body["duplicate"] is False
            row = db_session.execute(select(EscrowReleaseRelay).where(EscrowReleaseRelay.job_id == "job_w1")).scalars().one()
            assert row.tx_hash == "0xnew_rel"
            # Next replay returns the healed stored row without a chain POST.
            again = client.post("/v1/escrow/release", json={"job_id": "job_w1"}, headers=headers)
            assert again.json()["duplicate"] is True
            assert again.json()["tx_hash"] == "0xnew_rel"
            assert mock_client.post.await_count == 1

    def test_hashless_row_on_released_escrow_heals_from_chain(self, client, db_session):
        headers = _actor(db_session, "u-wedge-2")
        self._hashless_row(db_session, "job_w2")
        released = _escrow("job_w2")
        released.update({"state": "released", "released_at": "2026-11-24T00:00:00+00:00", "release_tx_hash": "0xchain_rel"})
        mock_client = _chain_client(released, [])
        with _release_patch() as cls:
            cls.return_value = mock_client
            resp = client.post("/v1/escrow/release", json={"job_id": "job_w2"}, headers=headers)
            assert resp.status_code == 200, resp.text
            assert resp.json()["tx_hash"] == "0xchain_rel"
            row = db_session.execute(select(EscrowReleaseRelay).where(EscrowReleaseRelay.job_id == "job_w2")).scalars().one()
            assert row.tx_hash == "0xchain_rel"
            assert mock_client.post.await_count == 0


class _RefundFixture:
    """Shared setup for the refund-relay pins: a FAILED coordinator job
    with an escrowed payment, plus a bound actor."""

    @staticmethod
    def job(db_session: Session, job_id: str, client_id: str) -> None:
        db_session.add(
            Job(
                id=job_id,
                client_id=client_id,
                state="FAILED",
                payload={},
                constraints={},
                expires_at=FUTURE,
            )
        )
        db_session.add(JobPayment(job_id=job_id, amount=Decimal("2.0"), status="escrowed"))
        db_session.commit()


class TestRefundAmbiguousAnswer:
    """#2814: only a verified settle (success:true + refund_tx_hash) may
    become a dedup row — the same wedge the release relay had."""

    def test_absent_success_records_no_row_and_retry_reattempts(self, client, db_session):
        headers = _actor(db_session, "u-ra-1")
        _RefundFixture.job(db_session, "job_ra1", "u-ra-1")
        mock_client = _chain_client(
            _escrow("job_ra1"),
            [
                {"detail": "upstream hiccup"},
                {"success": True, "refund_tx_hash": "0xref_ok", "contract_id": "0xc1"},
            ],
        )
        with _refund_patch() as cls:
            cls.return_value = mock_client
            first = client.post("/v1/escrow/refund", json={"job_id": "job_ra1"}, headers=headers)
            assert first.status_code == 200, first.text
            assert first.json()["success"] is False
            assert db_session.execute(select(EscrowRefundRelay)).scalars().all() == []

            second = client.post("/v1/escrow/refund", json={"job_id": "job_ra1"}, headers=headers)
            assert second.status_code == 200, second.text
            assert second.json()["success"] is True
            assert second.json()["refund_tx_hash"] == "0xref_ok"
            rows = db_session.execute(select(EscrowRefundRelay)).scalars().all()
            assert len(rows) == 1 and rows[0].tx_hash == "0xref_ok"

    def test_success_true_without_refund_tx_hash_is_retryable(self, client, db_session):
        headers = _actor(db_session, "u-ra-2")
        _RefundFixture.job(db_session, "job_ra2", "u-ra-2")
        mock_client = _chain_client(
            _escrow("job_ra2"),
            [
                {"success": True, "contract_id": "0xc1"},
                {"success": True, "refund_tx_hash": "0xref_ok", "contract_id": "0xc1"},
            ],
        )
        with _refund_patch() as cls:
            cls.return_value = mock_client
            first = client.post("/v1/escrow/refund", json={"job_id": "job_ra2"}, headers=headers)
            assert first.status_code == 200, first.text
            assert first.json()["success"] is False
            assert db_session.execute(select(EscrowRefundRelay)).scalars().all() == []

    def test_ambiguous_answer_but_escrow_refunded_records_from_chain(self, client, db_session):
        headers = _actor(db_session, "u-ra-3")
        _RefundFixture.job(db_session, "job_ra3", "u-ra-3")
        refunded = _escrow("job_ra3")
        refunded.update({"state": "refunded", "refunded_at": "2026-11-24T00:00:00+00:00", "refund_tx_hash": "0xchain_ref"})
        mock_client = AsyncMock()
        mock_client.get.side_effect = [_escrow("job_ra3"), refunded]
        mock_client.get_json.return_value = []
        mock_client.post.return_value = {"detail": "ambiguous"}
        with _refund_patch() as cls:
            cls.return_value = mock_client
            resp = client.post("/v1/escrow/refund", json={"job_id": "job_ra3"}, headers=headers)
            assert resp.status_code == 200, resp.text
            body = resp.json()
            assert body["success"] is True
            assert body["refund_tx_hash"] == "0xchain_ref"
            rows = db_session.execute(select(EscrowRefundRelay)).scalars().all()
            assert len(rows) == 1 and rows[0].tx_hash == "0xchain_ref"


class TestRefundHashlessDedupRow:
    """#2814: a dedup row recorded without tx_hash (pre-fix wedge) must not
    replay success forever — it re-drives the refund and heals."""

    def _hashless_row(self, db_session: Session, job_id: str) -> None:
        db_session.add(EscrowRefundRelay(client_id="u-rwedge", job_id=job_id, tx_hash=None))
        db_session.commit()

    def test_hashless_row_redrives_and_heals(self, client, db_session):
        headers = _actor(db_session, "u-rw-1")
        _RefundFixture.job(db_session, "job_rw1", "u-rw-1")
        self._hashless_row(db_session, "job_rw1")
        mock_client = _chain_client(
            _escrow("job_rw1"),
            [{"success": True, "refund_tx_hash": "0xref_new", "contract_id": "0xc1"}],
        )
        with _refund_patch() as cls:
            cls.return_value = mock_client
            resp = client.post("/v1/escrow/refund", json={"job_id": "job_rw1"}, headers=headers)
            assert resp.status_code == 200, resp.text
            body = resp.json()
            assert body["success"] is True
            assert body["refund_tx_hash"] == "0xref_new"
            assert body["duplicate"] is False
            row = db_session.execute(select(EscrowRefundRelay).where(EscrowRefundRelay.job_id == "job_rw1")).scalars().one()
            assert row.tx_hash == "0xref_new"
            again = client.post("/v1/escrow/refund", json={"job_id": "job_rw1"}, headers=headers)
            assert again.json()["duplicate"] is True
            assert again.json()["refund_tx_hash"] == "0xref_new"
            assert mock_client.post.await_count == 1

    def test_hashless_row_on_refunded_escrow_heals_from_chain(self, client, db_session):
        headers = _actor(db_session, "u-rw-2")
        _RefundFixture.job(db_session, "job_rw2", "u-rw-2")
        self._hashless_row(db_session, "job_rw2")
        refunded = _escrow("job_rw2")
        refunded.update({"state": "refunded", "refunded_at": "2026-11-24T00:00:00+00:00", "refund_tx_hash": "0xchain_ref"})
        mock_client = _chain_client(refunded, [])
        with _refund_patch() as cls:
            cls.return_value = mock_client
            resp = client.post("/v1/escrow/refund", json={"job_id": "job_rw2"}, headers=headers)
            assert resp.status_code == 200, resp.text
            assert resp.json()["refund_tx_hash"] == "0xchain_ref"
            row = db_session.execute(select(EscrowRefundRelay).where(EscrowRefundRelay.job_id == "job_rw2")).scalars().one()
            assert row.tx_hash == "0xchain_ref"
            assert mock_client.post.await_count == 0


class TestRefundClientIdNormalization:
    """#2814: the ownership checks compare canonical users.id — a JWT sub
    that is a username (or wallet ref) resolving to the job owner must not
    403."""

    def test_username_sub_resolves_to_canonical_job_owner(self, client, db_session):
        db_session.add(User(id="u-canon", email="canon@example.com", username="alice-ref"))
        db_session.add(Wallet(user_id="u-canon", address=BUYER.lower()))
        db_session.commit()
        _RefundFixture.job(db_session, "job_cn1", "u-canon")
        headers = {"Authorization": f"Bearer {create_access_token('alice-ref', 'client')}"}
        mock_client = _chain_client(
            _escrow("job_cn1"),
            [{"success": True, "refund_tx_hash": "0xref_c", "contract_id": "0xc1"}],
        )
        with _refund_patch() as cls:
            cls.return_value = mock_client
            resp = client.post("/v1/escrow/refund", json={"job_id": "job_cn1"}, headers=headers)
        assert resp.status_code == 200, resp.text
        assert resp.json()["refund_tx_hash"] == "0xref_c"
