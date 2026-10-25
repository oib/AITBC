"""Tests for POST /v1/escrow/release (ESCROW-RELEASE-1).

The relay forwards ``{job_id, amount, job_tx_hash}`` to the settlement
node's ``/rpc/escrow/{job_id}/release`` — a route the node signs itself
and that carries no caller auth — so these tests pin the JWT-side ruling:
the on-chain escrow's ``buyer`` must equal the wallet bound to the JWT
subject (admin exempt), the amount is bounded by the escrow's locked
amount, replays return the stored tx_hash without a second chain call, and
chain failures map 4xx → same code / else → 502. The chain client is
stubbed — no live calls.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import httpx
from sqlmodel import Session, select

from aitbc.auth import create_access_token
from aitbc.exceptions import NetworkError

from coordinator_api.contexts.infrastructure.domain.user import User, Wallet
from coordinator_api.contexts.payments.domain.escrow_release_relay import EscrowReleaseRelay

BUYER = "0x08aB801150eF3496344cFA78fe025c3B48Caf435"
OTHER_BUYER = "0x11cD222222eF3496344cFA78fe025c3B48Caf435"
PROVIDER = "0xF4924759508E420eeD947BD33326731B11c4B7Df"

PATCH_TARGET = "coordinator_api.contexts.payments.services.escrow_release_relay.AsyncAITBCHTTPClient"


def _payload(job_id: str = "mkt_job_1", amount: str = "1.5") -> dict:
    return {"job_id": job_id, "amount": amount, "job_tx_hash": "0xjobtx"}


def _escrow_state(
    buyer: str = BUYER,
    state: str = "funded",
    amount: str = "2.0",
    **extra,
) -> dict:
    escrow = {
        "job_id": "mkt_job_1",
        "contract_id": "0xc1",
        "state": state,
        "buyer": buyer,
        "provider": PROVIDER,
        "amount": amount,
        "released_at": None,
        "refunded_at": None,
        "release_tx_hash": None,
    }
    escrow.update(extra)
    return escrow


def _bind_wallet(db_session: Session, user_id: str, address: str) -> None:
    if db_session.get(User, user_id) is None:
        db_session.add(User(id=user_id, email=f"{user_id}@example.com", username=user_id))
    db_session.add(Wallet(user_id=user_id, address=address.lower()))
    db_session.commit()


def _token(sub: str, role: str = "client") -> dict[str, str]:
    return {"Authorization": f"Bearer {create_access_token(sub, role)}"}


def _chain_client_mock(
    escrow: dict | None = None,
    release: dict | None = None,
    side_effect: Exception | None = None,
    get_side_effect: Exception | None = None,
):
    client = AsyncMock()
    if get_side_effect is not None:
        client.get.side_effect = get_side_effect
    else:
        client.get.return_value = escrow if escrow is not None else _escrow_state()
    if side_effect is not None:
        client.post.side_effect = side_effect
    else:
        client.post.return_value = release or {"success": True, "tx_hash": "0xrel1", "contract_id": "0xc1"}
    return client


def _network_error(status_code: int, detail: str | None = None, method: str = "POST") -> NetworkError:
    request = httpx.Request(method, "http://node.invalid/rpc/escrow/x")
    response = httpx.Response(status_code, json={"detail": detail} if detail else {}, request=request)
    http_error = httpx.HTTPStatusError(f"status {status_code}", request=request, response=response)
    error = NetworkError(f"{method} request failed")
    error.__cause__ = http_error
    return error


class TestEscrowReleaseRelay:
    def test_release_happy_path(self, client, db_session):
        _bind_wallet(db_session, "client-1", BUYER)
        mock_client = _chain_client_mock()
        with patch(PATCH_TARGET, return_value=mock_client):
            resp = client.post("/v1/escrow/release", json=_payload(), headers=_token("client-1"))
        assert resp.status_code == 200, resp.text
        assert resp.json()["tx_hash"] == "0xrel1"
        # Escrow row was read for the buyer binding, then the release posted.
        mock_client.get.assert_called_once()
        assert "/rpc/escrow/mkt_job_1" in mock_client.get.call_args.args[0]
        assert "/rpc/escrow/mkt_job_1/release" in mock_client.post.call_args.args[0]
        sent = mock_client.post.call_args.kwargs["json"]
        assert sent == {"amount": "1.5", "job_tx_hash": "0xjobtx"}

    def test_release_buyer_mismatch_forbidden(self, client, db_session):
        _bind_wallet(db_session, "client-1", OTHER_BUYER)
        mock_client = _chain_client_mock()
        with patch(PATCH_TARGET, return_value=mock_client):
            resp = client.post("/v1/escrow/release", json=_payload(), headers=_token("client-1"))
        assert resp.status_code == 403
        mock_client.post.assert_not_called()

    def test_release_no_bound_wallet_forbidden(self, client):
        mock_client = _chain_client_mock()
        with patch(PATCH_TARGET, return_value=mock_client):
            resp = client.post("/v1/escrow/release", json=_payload(), headers=_token("walletless-user"))
        assert resp.status_code == 403
        mock_client.post.assert_not_called()

    def test_release_amount_over_lock_rejected(self, client, db_session):
        _bind_wallet(db_session, "client-1", BUYER)
        mock_client = _chain_client_mock(escrow=_escrow_state(amount="1.0"))
        with patch(PATCH_TARGET, return_value=mock_client):
            resp = client.post("/v1/escrow/release", json=_payload(amount="1.5"), headers=_token("client-1"))
        assert resp.status_code == 400
        assert "locked amount" in resp.json()["detail"]
        mock_client.post.assert_not_called()

    def test_release_replay_returns_stored_tx(self, client, db_session):
        _bind_wallet(db_session, "client-1", BUYER)
        mock_client = _chain_client_mock(release={"success": True, "tx_hash": "0xrel9", "contract_id": "0xc1"})
        with patch(PATCH_TARGET, return_value=mock_client):
            first = client.post("/v1/escrow/release", json=_payload(), headers=_token("client-1"))
            second = client.post("/v1/escrow/release", json=_payload(), headers=_token("client-1"))
        assert first.status_code == second.status_code == 200
        assert second.json()["tx_hash"] == "0xrel9"
        assert second.json()["duplicate"] is True
        assert mock_client.post.call_count == 1
        # The replay re-reads the escrow for the ownership check (which runs
        # before dedup) but never re-posts the release.
        assert mock_client.get.call_count == 2

    def test_release_already_released_on_chain(self, client, db_session):
        """An escrow the chain already released returns its tx without a
        release POST — cross-caller dedup for a retry after a lost reply."""
        _bind_wallet(db_session, "client-1", BUYER)
        mock_client = _chain_client_mock(
            escrow=_escrow_state(state="released", released_at="2026-10-27T00:00:00", release_tx_hash="0xoldrel")
        )
        with patch(PATCH_TARGET, return_value=mock_client):
            resp = client.post("/v1/escrow/release", json=_payload(), headers=_token("client-1"))
        assert resp.status_code == 200
        assert resp.json()["tx_hash"] == "0xoldrel"
        assert resp.json()["duplicate"] is True
        mock_client.post.assert_not_called()
        # The dedup row was stored so the next replay needs no chain call.
        row = db_session.execute(select(EscrowReleaseRelay).where(EscrowReleaseRelay.job_id == "mkt_job_1")).scalars().first()
        assert row is not None and row.tx_hash == "0xoldrel"

    def test_release_refunded_escrow_conflict(self, client, db_session):
        _bind_wallet(db_session, "client-1", BUYER)
        mock_client = _chain_client_mock(escrow=_escrow_state(state="refunded", refunded_at="2026-10-27T00:00:00"))
        with patch(PATCH_TARGET, return_value=mock_client):
            resp = client.post("/v1/escrow/release", json=_payload(), headers=_token("client-1"))
        assert resp.status_code == 409
        mock_client.post.assert_not_called()

    def test_release_admin_any_buyer(self, client, db_session):
        mock_client = _chain_client_mock(release={"success": True, "tx_hash": "0xadmin", "contract_id": "0xc1"})
        with patch(PATCH_TARGET, return_value=mock_client):
            resp = client.post(
                "/v1/escrow/release",
                json=_payload(job_id="mkt_admin_1", amount="999"),
                headers=_token("operator", role="admin"),
            )
        assert resp.status_code == 200, resp.text
        assert resp.json()["tx_hash"] == "0xadmin"

    def test_release_escrow_not_found_passthrough(self, client, db_session):
        _bind_wallet(db_session, "client-1", BUYER)
        mock_client = _chain_client_mock(get_side_effect=_network_error(404, "No escrow found for job_id=nope", method="GET"))
        with patch(PATCH_TARGET, return_value=mock_client):
            resp = client.post("/v1/escrow/release", json=_payload(job_id="nope"), headers=_token("client-1"))
        assert resp.status_code == 404
        mock_client.post.assert_not_called()

    def test_release_chain_4xx_passthrough(self, client, db_session):
        _bind_wallet(db_session, "client-1", BUYER)
        mock_client = _chain_client_mock(side_effect=_network_error(409, "Escrow is not locked"))
        with patch(PATCH_TARGET, return_value=mock_client):
            resp = client.post("/v1/escrow/release", json=_payload(job_id="mkt_4xx"), headers=_token("client-1"))
        assert resp.status_code == 409
        assert resp.json()["detail"] == "Escrow is not locked"

    def test_release_chain_5xx_is_502(self, client, db_session):
        _bind_wallet(db_session, "client-1", BUYER)
        mock_client = _chain_client_mock(side_effect=_network_error(503, "EscrowManager not initialised"))
        with patch(PATCH_TARGET, return_value=mock_client):
            resp = client.post("/v1/escrow/release", json=_payload(job_id="mkt_5xx"), headers=_token("client-1"))
        assert resp.status_code == 502

    def test_release_chain_timeout_is_502(self, client, db_session):
        _bind_wallet(db_session, "client-1", BUYER)
        mock_client = _chain_client_mock(side_effect=NetworkError("POST request failed: timeout"))
        with patch(PATCH_TARGET, return_value=mock_client):
            resp = client.post("/v1/escrow/release", json=_payload(job_id="mkt_to"), headers=_token("client-1"))
        assert resp.status_code == 502

    def test_release_escrow_lookup_5xx_is_502(self, client, db_session):
        """A failed escrow read must fail closed — the buyer binding cannot
        be checked, so the release must not be attempted."""
        _bind_wallet(db_session, "client-1", BUYER)
        mock_client = _chain_client_mock(get_side_effect=NetworkError("GET request failed: timeout"))
        with patch(PATCH_TARGET, return_value=mock_client):
            resp = client.post("/v1/escrow/release", json=_payload(job_id="mkt_getdown"), headers=_token("client-1"))
        assert resp.status_code == 502
        mock_client.post.assert_not_called()

    def test_release_row_persisted(self, client, db_session):
        _bind_wallet(db_session, "client-1", BUYER)
        mock_client = _chain_client_mock(release={"success": True, "tx_hash": "0xrow", "contract_id": "0xc9"})
        with patch(PATCH_TARGET, return_value=mock_client):
            resp = client.post("/v1/escrow/release", json=_payload(job_id="mkt_row"), headers=_token("client-1"))
        assert resp.status_code == 200
        row = db_session.execute(select(EscrowReleaseRelay).where(EscrowReleaseRelay.job_id == "mkt_row")).scalars().first()
        assert row is not None
        assert row.client_id == "client-1"
        assert row.tx_hash == "0xrow"
        assert row.contract_id == "0xc9"

    def test_dedup_result_requires_ownership(self, client, db_session):
        """A caller who knows the job_id but isn't the buyer must 403 —
        even when a relay row already exists (ownership runs before dedup).
        """
        db_session.add(
            EscrowReleaseRelay(
                client_id="other-client",
                job_id="mkt_job_1",
                tx_hash="0xstored",
                contract_id="0xc1",
            )
        )
        db_session.commit()
        _bind_wallet(db_session, "client-1", OTHER_BUYER)
        mock_client = _chain_client_mock()
        with patch(PATCH_TARGET, return_value=mock_client):
            resp = client.post("/v1/escrow/release", json=_payload(), headers=_token("client-1"))
        assert resp.status_code == 403

    def test_concurrent_duplicate_insert_returns_stored_not_500(self, client, db_session):
        """Loser of a same-job_id insert race gets the stored result, not a 500.

        The winning row must NOT exist when the dedup select runs (or the
        test never reaches the insert path). It lands inside the patched
        commit() via an independent connection — simulating the concurrent
        insert — just before the unique-violation error is raised.
        """
        _bind_wallet(db_session, "client-1", BUYER)

        def racy_commit():
            # The other client lands first — committed on a SEPARATE
            # connection so the service session's rollback cannot remove it.
            engine = db_session.get_bind()
            with engine.begin() as conn:
                conn.execute(
                    EscrowReleaseRelay.__table__.insert().values(
                        client_id="other-client", job_id="mkt_job_1", tx_hash="0xwinner", contract_id="0xc1"
                    )
                )
            from sqlalchemy.exc import IntegrityError

            raise IntegrityError("INSERT", {}, Exception("unique job_id"))

        mock_client = _chain_client_mock()
        with patch.object(db_session, "commit", side_effect=racy_commit), patch(PATCH_TARGET, return_value=mock_client):
            resp = client.post("/v1/escrow/release", json=_payload(), headers=_token("client-1"))
        assert resp.status_code == 200, resp.text
        assert resp.json()["tx_hash"] == "0xwinner"
        assert resp.json()["duplicate"] is True


def test_release_route_registered_in_security_matrix():
    """/v1/escrow/release must not fall to middleware deny-by-default (403 'Forbidden')."""
    from aitbc.auth.security_matrix import ROUTE_SECURITY_MATRIX, AuthLevel, get_auth_level

    assert get_auth_level("/v1/escrow/release") == AuthLevel.ADMIN_OR_CLIENT
    assert ROUTE_SECURITY_MATRIX["/v1/escrow/release"] == AuthLevel.ADMIN_OR_CLIENT


class TestOmittedAmount:
    """Directors ruling on #469: an omitted amount releases the full lock
    — ownership and dedup still run before the amount is derived."""

    def test_omitted_amount_releases_full_lock(self, client, db_session):
        _bind_wallet(db_session, "client-1", BUYER)
        mock_client = _chain_client_mock()
        with patch(PATCH_TARGET, return_value=mock_client):
            resp = client.post("/v1/escrow/release", json={"job_id": "mkt_job_1"}, headers=_token("client-1"))
        assert resp.status_code == 200, resp.text
        # Forwarded body carries NO amount — the chain pays the whole lock.
        posted = mock_client.post.call_args.kwargs.get("json") or mock_client.post.call_args[1].get("json", {})
        assert "amount" not in posted

    def test_omitted_amount_still_requires_buyer(self, client, db_session):
        _bind_wallet(db_session, "client-1", BUYER)
        mock_client = _chain_client_mock(escrow=_escrow_state(buyer="0xSomebodyElse"))
        with patch(PATCH_TARGET, return_value=mock_client):
            resp = client.post("/v1/escrow/release", json={"job_id": "mkt_job_1"}, headers=_token("client-1"))
        assert resp.status_code == 403

    def test_omitted_amount_on_refunded_escrow_is_409(self, client, db_session):
        _bind_wallet(db_session, "client-1", BUYER)
        mock_client = _chain_client_mock(escrow=_escrow_state(state="refunded"))
        with patch(PATCH_TARGET, return_value=mock_client):
            resp = client.post("/v1/escrow/release", json={"job_id": "mkt_job_1"}, headers=_token("client-1"))
        assert resp.status_code == 409

    def test_omitted_amount_replay_returns_stored(self, client, db_session):
        _bind_wallet(db_session, "client-1", BUYER)
        db_session.add(EscrowReleaseRelay(client_id="client-1", job_id="mkt_job_1", tx_hash="0xearlier", contract_id="0xc1"))
        db_session.commit()
        mock_client = _chain_client_mock(escrow=_escrow_state(state="released"))
        with patch(PATCH_TARGET, return_value=mock_client):
            resp = client.post("/v1/escrow/release", json={"job_id": "mkt_job_1"}, headers=_token("client-1"))
        assert resp.status_code == 200
        assert resp.json()["tx_hash"] == "0xearlier"
        assert mock_client.post.call_count == 0
