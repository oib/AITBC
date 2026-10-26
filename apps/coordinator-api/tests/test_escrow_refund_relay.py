"""Tests for POST /v1/escrow/refund (ESCROW-REFUND-1).

The relay forwards ``{job_id, reason?}`` to the settlement node's
``/rpc/escrow/{job_id}/refund`` — a route the node signs itself and that
carries no caller auth — so these tests pin the JWT-side ruling from
#471: the on-chain escrow's ``buyer`` must equal the wallet bound to the
JWT subject (admin exempt), the coordinator ``job`` row must exist and be
terminal-unpaid (FAILED/CANCELED/EXPIRED, or past ``expires_at``),
COMPLETED is never refundable, a sealed on-chain ``software_job``
completion record fails closed, replays return the stored tx_hash without
a second chain call, and chain failures map 4xx → same code / else →
502. The chain client is stubbed — no live calls.

Each test uses a unique JWT ``sub``: the per-client rate limiter keys on
the credential, and a shared sub could share a bucket across tests.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from unittest.mock import AsyncMock, patch

import httpx
from sqlmodel import Session, select

from aitbc.auth import create_access_token
from aitbc.exceptions import NetworkError
from aitbc_shared import JobPayment

from coordinator_api.contexts.infrastructure.domain.job import Job
from coordinator_api.contexts.infrastructure.domain.user import User, Wallet
from coordinator_api.contexts.payments.domain.escrow_refund_relay import EscrowRefundRelay

BUYER = "0x08aB801150eF3496344cFA78fe025c3B48Caf435"
OTHER_BUYER = "0x11cD222222eF3496344cFA78fe025c3B48Caf435"
PROVIDER = "0xF4924759508E420eeD947BD33326731B11c4B7Df"

PATCH_TARGET = "coordinator_api.contexts.payments.services.escrow_refund_relay.AsyncAITBCHTTPClient"

PAST = datetime.now(UTC) - timedelta(hours=1)
FUTURE = datetime.now(UTC) + timedelta(hours=1)


def _payload(job_id: str = "job_1", reason: str | None = None) -> dict:
    body: dict = {"job_id": job_id}
    if reason is not None:
        body["reason"] = reason
    return body


def _escrow_state(
    buyer: str = BUYER,
    state: str = "funded",
    **extra,
) -> dict:
    escrow = {
        "job_id": "job_1",
        "contract_id": "0xc1",
        "state": state,
        "buyer": buyer,
        "provider": PROVIDER,
        "amount": "2.0",
        "released_at": None,
        "refunded_at": None,
        "release_tx_hash": None,
        "refund_tx_hash": None,
    }
    escrow.update(extra)
    return escrow


def _actor(db_session: Session, sub: str, buyer: str = BUYER) -> dict[str, str]:
    """Bind *buyer* to *sub* and return its JWT headers.

    ``wallets.address`` is unique — when several actors share a buyer in one
    test DB the wallet row is re-pointed at the latest sub.
    """
    if db_session.get(User, sub) is None:
        db_session.add(User(id=sub, email=f"{sub}@example.com", username=sub))
    existing = db_session.execute(select(Wallet).where(Wallet.address == buyer.lower())).scalars().first()
    if existing is not None:
        existing.user_id = sub
    else:
        db_session.add(Wallet(user_id=sub, address=buyer.lower()))
    db_session.commit()
    return {"Authorization": f"Bearer {create_access_token(sub, 'client')}"}


def _token(sub: str, role: str = "client") -> dict[str, str]:
    return {"Authorization": f"Bearer {create_access_token(sub, role)}"}


def _add_job(
    db_session: Session,
    job_id: str = "job_1",
    client_id: str = "client-1",
    state: str = "FAILED",
    expires_at: datetime = FUTURE,
) -> Job:
    job = Job(
        id=job_id,
        client_id=client_id,
        state=state,
        payload={},
        constraints={},
        expires_at=expires_at,
    )
    db_session.add(job)
    db_session.commit()
    return job


def _add_payment(db_session: Session, job_id: str = "job_1", status: str = "escrowed", **extra) -> JobPayment:
    payment = JobPayment(job_id=job_id, amount=Decimal("2.0"), status=status, **extra)
    db_session.add(payment)
    db_session.commit()
    return payment


def _chain_client_mock(
    escrow: dict | None = None,
    refund: dict | None = None,
    transactions: list | None = None,
    side_effect: Exception | None = None,
    get_side_effect: Exception | None = None,
    get_json_side_effect: Exception | None = None,
):
    client = AsyncMock()
    if get_side_effect is not None:
        client.get.side_effect = get_side_effect
    else:
        client.get.return_value = escrow if escrow is not None else _escrow_state()
    if get_json_side_effect is not None:
        client.get_json.side_effect = get_json_side_effect
    else:
        client.get_json.return_value = transactions if transactions is not None else []
    if side_effect is not None:
        client.post.side_effect = side_effect
    else:
        client.post.return_value = refund or {"success": True, "refund_tx_hash": "0xref1", "contract_id": "0xc1"}
    return client


def _network_error(status_code: int, detail: str | None = None, method: str = "POST") -> NetworkError:
    request = httpx.Request(method, "http://node.invalid/rpc/escrow/x")
    response = httpx.Response(status_code, json={"detail": detail} if detail else {}, request=request)
    http_error = httpx.HTTPStatusError(f"status {status_code}", request=request, response=response)
    error = NetworkError(f"{method} request failed")
    error.__cause__ = http_error
    return error


def _completed_job_tx(job_id: str = "job_1") -> dict:
    return {
        "transaction_id": 7,
        "tx_hash": "0xjobdone",
        "block_height": 42,
        "sender": BUYER,
        "payload": {"action": "software_job", "job_id": job_id, "status": "completed"},
        "type": "GPU_MARKET",
    }


class TestEscrowRefundRelay:
    def test_refund_happy_path_failed_job(self, client, db_session):
        headers = _actor(db_session, "c-happy")
        _add_job(db_session, client_id="c-happy", state="FAILED")
        mock_client = _chain_client_mock()
        with patch(PATCH_TARGET, return_value=mock_client):
            resp = client.post("/v1/escrow/refund", json=_payload(), headers=headers)
        assert resp.status_code == 200, resp.text
        assert resp.json()["refund_tx_hash"] == "0xref1"
        # Escrow read for the buyer binding, job-record conflict check, then refund posted.
        assert "/rpc/escrow/job_1" in mock_client.get.call_args.args[0]
        assert "/rpc/transactions" in mock_client.get_json.call_args.args[0]
        assert mock_client.get_json.call_args.kwargs["params"]["job_id"] == "job_1"
        assert "/rpc/escrow/job_1/refund" in mock_client.post.call_args.args[0]
        sent = mock_client.post.call_args.kwargs["json"]
        # No caller-chosen amount — only the reason is forwarded.
        assert sent == {"reason": "buyer_requested"}
        assert "amount" not in sent

    def test_refund_forwards_reason(self, client, db_session):
        headers = _actor(db_session, "c-reason")
        _add_job(db_session, client_id="c-reason", state="FAILED")
        mock_client = _chain_client_mock()
        with patch(PATCH_TARGET, return_value=mock_client):
            resp = client.post("/v1/escrow/refund", json=_payload(reason="job_failed"), headers=headers)
        assert resp.status_code == 200
        assert mock_client.post.call_args.kwargs["json"] == {"reason": "job_failed"}

    def test_refund_reason_allowlist(self, client, db_session):
        headers = _actor(db_session, "c-badreason")
        _add_job(db_session, client_id="c-badreason", state="FAILED")
        mock_client = _chain_client_mock()
        with patch(PATCH_TARGET, return_value=mock_client):
            resp = client.post("/v1/escrow/refund", json=_payload(reason="spite"), headers=headers)
        assert resp.status_code in (400, 422)
        mock_client.post.assert_not_called()

    def test_refund_terminal_states_pass(self, client, db_session):
        for i, state in enumerate(("CANCELED", "EXPIRED", "FAILED")):
            sub = f"c-term{i}"
            headers = _actor(db_session, sub)
            job_id = f"job_term_{i}"
            _add_job(db_session, job_id=job_id, client_id=sub, state=state)
            mock_client = _chain_client_mock(refund={"refund_tx_hash": f"0x{i}"})
            with patch(PATCH_TARGET, return_value=mock_client):
                resp = client.post("/v1/escrow/refund", json=_payload(job_id), headers=headers)
            assert resp.status_code == 200, f"{state}: {resp.text}"

    def test_refund_running_past_expiry_passes(self, client, db_session):
        """A QUEUED/RUNNING job becomes refundable once its own expires_at
        has passed — the same bound the sweeper refunds on."""
        headers = _actor(db_session, "c-oldrun")
        _add_job(db_session, job_id="job_old", client_id="c-oldrun", state="RUNNING", expires_at=PAST)
        mock_client = _chain_client_mock()
        with patch(PATCH_TARGET, return_value=mock_client):
            resp = client.post("/v1/escrow/refund", json=_payload("job_old"), headers=headers)
        assert resp.status_code == 200, resp.text

    def test_refund_running_before_expiry_conflict(self, client, db_session):
        headers = _actor(db_session, "c-running")
        _add_job(db_session, client_id="c-running", state="RUNNING", expires_at=FUTURE)
        mock_client = _chain_client_mock()
        with patch(PATCH_TARGET, return_value=mock_client):
            resp = client.post("/v1/escrow/refund", json=_payload(), headers=headers)
        assert resp.status_code == 409
        mock_client.post.assert_not_called()

    def test_refund_completed_job_never_refundable(self, client, db_session):
        """COMPLETED → 409 even with an unreleased lock — release is the
        path for it. Mutation check: deleting this rule must fail here."""
        headers = _actor(db_session, "c-completed")
        _add_job(db_session, client_id="c-completed", state="COMPLETED")
        mock_client = _chain_client_mock()
        with patch(PATCH_TARGET, return_value=mock_client):
            resp = client.post("/v1/escrow/refund", json=_payload(), headers=headers)
        assert resp.status_code == 409
        assert "COMPLETED" in resp.json()["detail"]
        mock_client.post.assert_not_called()

    def test_refund_completed_past_expiry_still_409(self, client, db_session):
        """Director ruling: expiry does NOT make a COMPLETED job refundable."""
        headers = _actor(db_session, "c-completed-old")
        _add_job(db_session, client_id="c-completed-old", state="COMPLETED", expires_at=PAST)
        mock_client = _chain_client_mock()
        with patch(PATCH_TARGET, return_value=mock_client):
            resp = client.post("/v1/escrow/refund", json=_payload(), headers=headers)
        assert resp.status_code == 409
        mock_client.post.assert_not_called()

    def test_refund_no_job_row_refused(self, client, db_session):
        """No coordinator job row = market-minted escrow → refused. Mutation
        check: skipping the row-existence check must fail here."""
        headers = _actor(db_session, "c-minted")
        mock_client = _chain_client_mock()
        with patch(PATCH_TARGET, return_value=mock_client):
            resp = client.post("/v1/escrow/refund", json=_payload("mkt_job_9"), headers=headers)
        assert resp.status_code == 404
        mock_client.post.assert_not_called()

    def test_refund_job_owned_by_other_client_forbidden(self, client, db_session):
        headers = _actor(db_session, "c-notowner")
        db_session.add(User(id="other-owner", email="o@example.com", username="other-owner"))
        _add_job(db_session, client_id="other-owner", state="FAILED")
        mock_client = _chain_client_mock()
        with patch(PATCH_TARGET, return_value=mock_client):
            resp = client.post("/v1/escrow/refund", json=_payload(), headers=headers)
        assert resp.status_code == 403
        mock_client.post.assert_not_called()

    def test_refund_buyer_mismatch_forbidden(self, client, db_session):
        """Mutation check: dropping the buyer binding must fail here."""
        headers = _actor(db_session, "c-wrongbuyer", buyer=OTHER_BUYER)
        _add_job(db_session, client_id="c-wrongbuyer", state="FAILED")
        mock_client = _chain_client_mock()
        with patch(PATCH_TARGET, return_value=mock_client):
            resp = client.post("/v1/escrow/refund", json=_payload(), headers=headers)
        assert resp.status_code == 403
        mock_client.post.assert_not_called()

    def test_refund_admin_any_buyer_and_owner(self, client, db_session):
        db_session.add(User(id="someone-else", email="s@example.com", username="someone-else"))
        _add_job(db_session, client_id="someone-else", state="FAILED")
        mock_client = _chain_client_mock(refund={"success": True, "refund_tx_hash": "0xadm", "contract_id": "0xc1"})
        with patch(PATCH_TARGET, return_value=mock_client):
            resp = client.post("/v1/escrow/refund", json=_payload(), headers=_token("operator", role="admin"))
        assert resp.status_code == 200, resp.text
        assert resp.json()["refund_tx_hash"] == "0xadm"

    def test_refund_replay_returns_stored_tx(self, client, db_session):
        headers = _actor(db_session, "c-replay")
        _add_job(db_session, client_id="c-replay", state="FAILED")
        mock_client = _chain_client_mock(refund={"success": True, "refund_tx_hash": "0xref9", "contract_id": "0xc1"})
        with patch(PATCH_TARGET, return_value=mock_client):
            first = client.post("/v1/escrow/refund", json=_payload(), headers=headers)
            second = client.post("/v1/escrow/refund", json=_payload(), headers=headers)
        assert first.status_code == second.status_code == 200
        assert second.json()["refund_tx_hash"] == "0xref9"
        assert second.json()["duplicate"] is True
        assert mock_client.post.call_count == 1

    def test_refund_already_refunded_on_chain(self, client, db_session):
        """An escrow the chain already refunded returns its tx without a
        refund POST — cross-caller dedup after a lost reply."""
        headers = _actor(db_session, "c-orefunded")
        _add_job(db_session, client_id="c-orefunded", state="FAILED")
        mock_client = _chain_client_mock(
            escrow=_escrow_state(state="refunded", refunded_at="2026-10-27T00:00:00", refund_tx_hash="0xoldref")
        )
        with patch(PATCH_TARGET, return_value=mock_client):
            resp = client.post("/v1/escrow/refund", json=_payload(), headers=headers)
        assert resp.status_code == 200
        assert resp.json()["refund_tx_hash"] == "0xoldref"
        assert resp.json()["duplicate"] is True
        mock_client.post.assert_not_called()
        row = db_session.execute(select(EscrowRefundRelay).where(EscrowRefundRelay.job_id == "job_1")).scalars().first()
        assert row is not None and row.tx_hash == "0xoldref"

    def test_refund_released_escrow_conflict(self, client, db_session):
        headers = _actor(db_session, "c-released")
        _add_job(db_session, client_id="c-released", state="FAILED")
        mock_client = _chain_client_mock(escrow=_escrow_state(state="released", released_at="2026-10-27T00:00:00"))
        with patch(PATCH_TARGET, return_value=mock_client):
            resp = client.post("/v1/escrow/refund", json=_payload(), headers=headers)
        assert resp.status_code == 409
        mock_client.post.assert_not_called()

    def test_refund_job_payment_released_conflict(self, client, db_session):
        """Secondary evidence: a released job_payments row refuses before the
        chain call even when the escrow row still reads funded."""
        headers = _actor(db_session, "c-prel")
        _add_job(db_session, client_id="c-prel", state="FAILED")
        _add_payment(db_session, status="released", released_at=datetime.now(UTC))
        mock_client = _chain_client_mock()
        with patch(PATCH_TARGET, return_value=mock_client):
            resp = client.post("/v1/escrow/refund", json=_payload(), headers=headers)
        assert resp.status_code == 409
        mock_client.post.assert_not_called()

    def test_refund_job_payment_refunded_returns_stored(self, client, db_session):
        headers = _actor(db_session, "c-pref")
        _add_job(db_session, client_id="c-pref", state="FAILED")
        _add_payment(db_session, status="refunded", refunded_at=datetime.now(UTC), refund_transaction_hash="0xpayref")
        mock_client = _chain_client_mock()
        with patch(PATCH_TARGET, return_value=mock_client):
            resp = client.post("/v1/escrow/refund", json=_payload(), headers=headers)
        assert resp.status_code == 200
        assert resp.json()["refund_tx_hash"] == "0xpayref"
        assert resp.json()["duplicate"] is True
        mock_client.post.assert_not_called()

    def test_refund_software_job_completed_fails_closed(self, client, db_session):
        """A sealed on-chain software_job=completed record contradicting a
        terminal-unpaid coordinator row → 409. Mutation check: skipping
        the conflict check must fail here."""
        headers = _actor(db_session, "c-conflict")
        _add_job(db_session, client_id="c-conflict", state="FAILED")
        mock_client = _chain_client_mock(transactions=[_completed_job_tx()])
        with patch(PATCH_TARGET, return_value=mock_client):
            resp = client.post("/v1/escrow/refund", json=_payload(), headers=headers)
        assert resp.status_code == 409
        mock_client.post.assert_not_called()

    def test_refund_job_record_lookup_failure_fails_closed(self, client, db_session):
        """A failed on-chain record lookup refuses — the check cannot be
        skipped by knocking out the query."""
        headers = _actor(db_session, "c-lookupfail")
        _add_job(db_session, client_id="c-lookupfail", state="FAILED")
        mock_client = _chain_client_mock(get_json_side_effect=NetworkError("GET request failed: timeout"))
        with patch(PATCH_TARGET, return_value=mock_client):
            resp = client.post("/v1/escrow/refund", json=_payload(), headers=headers)
        assert resp.status_code == 502
        mock_client.post.assert_not_called()

    def test_refund_unsealed_completed_record_ignored(self, client, db_session):
        """A mempool (unsealed) software_job record is not evidence."""
        headers = _actor(db_session, "c-unsealed")
        _add_job(db_session, client_id="c-unsealed", state="FAILED")
        tx = _completed_job_tx()
        tx["block_height"] = None
        mock_client = _chain_client_mock(transactions=[tx])
        with patch(PATCH_TARGET, return_value=mock_client):
            resp = client.post("/v1/escrow/refund", json=_payload(), headers=headers)
        assert resp.status_code == 200, resp.text

    def test_refund_chain_4xx_passthrough(self, client, db_session):
        headers = _actor(db_session, "c-4xx")
        _add_job(db_session, client_id="c-4xx", state="FAILED")
        mock_client = _chain_client_mock(side_effect=_network_error(400, "Escrow already in final state: refunded"))
        with patch(PATCH_TARGET, return_value=mock_client):
            resp = client.post("/v1/escrow/refund", json=_payload(), headers=headers)
        assert resp.status_code == 400
        assert resp.json()["detail"] == "Escrow already in final state: refunded"

    def test_refund_chain_425_unsealed_passthrough(self, client, db_session):
        """The chain's 425 'lock not yet sealed' is a retryable refusal —
        its own message passes through at the same status."""
        headers = _actor(db_session, "c-425")
        _add_job(db_session, client_id="c-425", state="FAILED")
        mock_client = _chain_client_mock(
            side_effect=_network_error(425, "lock tx 0xl for job_id=job_1 is neither sealed nor present in the hub mempool")
        )
        with patch(PATCH_TARGET, return_value=mock_client):
            resp = client.post("/v1/escrow/refund", json=_payload(), headers=headers)
        assert resp.status_code == 425
        assert "neither sealed" in resp.json()["detail"]

    def test_refund_chain_5xx_is_502(self, client, db_session):
        headers = _actor(db_session, "c-5xx")
        _add_job(db_session, client_id="c-5xx", state="FAILED")
        mock_client = _chain_client_mock(side_effect=_network_error(503, "EscrowManager not initialised"))
        with patch(PATCH_TARGET, return_value=mock_client):
            resp = client.post("/v1/escrow/refund", json=_payload(), headers=headers)
        assert resp.status_code == 502

    def test_refund_chain_timeout_is_502(self, client, db_session):
        headers = _actor(db_session, "c-timeout")
        _add_job(db_session, client_id="c-timeout", state="FAILED")
        mock_client = _chain_client_mock(side_effect=NetworkError("POST request failed: timeout"))
        with patch(PATCH_TARGET, return_value=mock_client):
            resp = client.post("/v1/escrow/refund", json=_payload(), headers=headers)
        assert resp.status_code == 502

    def test_refund_escrow_lookup_5xx_is_502(self, client, db_session):
        """A failed escrow read must fail closed — the buyer binding cannot
        be checked, so the refund must not be attempted."""
        headers = _actor(db_session, "c-getdown")
        _add_job(db_session, client_id="c-getdown", state="FAILED")
        mock_client = _chain_client_mock(get_side_effect=NetworkError("GET request failed: timeout"))
        with patch(PATCH_TARGET, return_value=mock_client):
            resp = client.post("/v1/escrow/refund", json=_payload(), headers=headers)
        assert resp.status_code == 502
        mock_client.post.assert_not_called()

    def test_refund_escrow_not_found_passthrough(self, client, db_session):
        headers = _actor(db_session, "c-404")
        _add_job(db_session, job_id="nope", client_id="c-404", state="FAILED")
        mock_client = _chain_client_mock(get_side_effect=_network_error(404, "No escrow found for job_id=nope", method="GET"))
        with patch(PATCH_TARGET, return_value=mock_client):
            resp = client.post("/v1/escrow/refund", json=_payload("nope"), headers=headers)
        assert resp.status_code == 404
        mock_client.post.assert_not_called()

    def test_refund_row_persisted(self, client, db_session):
        headers = _actor(db_session, "c-row")
        _add_job(db_session, job_id="job_row", client_id="c-row", state="FAILED")
        mock_client = _chain_client_mock(refund={"success": True, "refund_tx_hash": "0xrow", "contract_id": "0xc9"})
        with patch(PATCH_TARGET, return_value=mock_client):
            resp = client.post("/v1/escrow/refund", json=_payload("job_row"), headers=headers)
        assert resp.status_code == 200
        row = db_session.execute(select(EscrowRefundRelay).where(EscrowRefundRelay.job_id == "job_row")).scalars().first()
        assert row is not None
        assert row.client_id == "c-row"
        assert row.tx_hash == "0xrow"
        assert row.contract_id == "0xc9"

    def test_dedup_result_requires_ownership(self, client, db_session):
        """A caller who knows the job_id but isn't the buyer must 403 —
        even when a relay row already exists (ownership runs before dedup).
        """
        db_session.add(
            EscrowRefundRelay(
                client_id="other-client",
                job_id="job_1",
                tx_hash="0xstored",
                contract_id="0xc1",
            )
        )
        db_session.commit()
        headers = _actor(db_session, "c-notbuyer", buyer=OTHER_BUYER)
        _add_job(db_session, client_id="c-notbuyer", state="FAILED")
        mock_client = _chain_client_mock()
        with patch(PATCH_TARGET, return_value=mock_client):
            resp = client.post("/v1/escrow/refund", json=_payload(), headers=headers)
        assert resp.status_code == 403

    def test_concurrent_duplicate_insert_returns_stored_not_500(self, client, db_session):
        """Loser of a same-job_id insert race gets the stored result, not a 500."""
        headers = _actor(db_session, "c-racy")
        _add_job(db_session, client_id="c-racy", state="FAILED")

        def racy_commit():
            engine = db_session.get_bind()
            with engine.begin() as conn:
                conn.execute(
                    EscrowRefundRelay.__table__.insert().values(
                        client_id="other-client", job_id="job_1", tx_hash="0xwinner", contract_id="0xc1"
                    )
                )
            from sqlalchemy.exc import IntegrityError

            raise IntegrityError("INSERT", {}, Exception("unique job_id"))

        mock_client = _chain_client_mock()
        with patch.object(db_session, "commit", side_effect=racy_commit), patch(PATCH_TARGET, return_value=mock_client):
            resp = client.post("/v1/escrow/refund", json=_payload(), headers=headers)
        assert resp.status_code == 200, resp.text
        assert resp.json()["refund_tx_hash"] == "0xwinner"
        assert resp.json()["duplicate"] is True

    def test_refund_per_client_hourly_cap(self, client, db_session):
        """Director ruling: a per-client hourly cap stops a stolen JWT from
        sweeping locks. Eleven requests on one credential → the last is 429."""
        mock_client = _chain_client_mock(get_side_effect=NetworkError("GET failed"))
        headers = _token("cap-user")
        with patch(PATCH_TARGET, return_value=mock_client):
            codes = [
                client.post("/v1/escrow/refund", json=_payload(f"job_cap_{i}"), headers=headers).status_code for i in range(11)
            ]
        assert 429 in codes
        assert codes[-1] == 429


def test_refund_route_registered_in_security_matrix():
    """/v1/escrow/refund must not fall to middleware deny-by-default (403 'Forbidden')."""
    from aitbc.auth.security_matrix import ROUTE_SECURITY_MATRIX, AuthLevel, get_auth_level

    assert get_auth_level("/v1/escrow/refund") == AuthLevel.ADMIN_OR_CLIENT
    assert ROUTE_SECURITY_MATRIX["/v1/escrow/refund"] == AuthLevel.ADMIN_OR_CLIENT
