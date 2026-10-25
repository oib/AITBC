"""Tests for POST /v1/escrow/relay (ESCROW-ROUTE-1).

The relay forwards a buyer-signed ``/rpc/escrow/create`` payload to the
settlement-capable chain RPC from inside the nginx allowlist. These tests pin
the ruling semantics: the JWT subject's bound wallet must equal ``buyer``
(admin exempt), non-admin amounts are capped at ESCROW_RELAY_MAX_UNITS,
replays of the same lock return the stored contract_id without a second chain
call, and chain failures map 4xx → same code / else → 502. The chain client
is stubbed — no live calls.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import httpx
from sqlmodel import Session

from aitbc.auth import create_access_token
from aitbc.exceptions import NetworkError

from coordinator_api.contexts.infrastructure.domain.user import User, Wallet
from coordinator_api.contexts.payments.domain.escrow_relay import EscrowRelay

BUYER = "0x08aB801150eF3496344cFA78fe025c3B48Caf435"
OTHER_BUYER = "0x11cD222222eF3496344cFA78fe025c3B48Caf435"
PROVIDER = "0xF4924759508E420eeD947BD33326731B11c4B7Df"

PATCH_TARGET = "coordinator_api.contexts.payments.services.escrow_relay.AsyncAITBCHTTPClient"


def _payload(job_id: str = "mkt_job_1", buyer: str = BUYER, amount: str = "1.5") -> dict:
    return {
        "job_id": job_id,
        "buyer": buyer,
        "provider": PROVIDER,
        "amount": amount,
        "lock_tx": {
            "type": "ESCROW_LOCK",
            "from": buyer,
            "to": "0x02B8cC0D4f4d84e5D0a4a4c9a9D04A9C7Dd3Ef01",
            "amount": 54_000_000,
            "nonce": 7,
            "signature": "0xdeadbeef",
            "payload": {"job_id": job_id, "provider": PROVIDER},
        },
        "lock_signature": "0xdeadbeef",
    }


def _bind_wallet(db_session: Session, user_id: str, address: str) -> None:
    if db_session.get(User, user_id) is None:
        db_session.add(User(id=user_id, email=f"{user_id}@example.com", username=user_id))
    db_session.add(Wallet(user_id=user_id, address=address.lower()))
    db_session.commit()


def _token(sub: str, role: str = "client") -> dict[str, str]:
    return {"Authorization": f"Bearer {create_access_token(sub, role)}"}


def _chain_client_mock(result: dict | None = None, side_effect: Exception | None = None):
    client = AsyncMock()
    if side_effect is not None:
        client.post.side_effect = side_effect
    else:
        client.post.return_value = result or {"contract_id": "0xcontract1", "success": True}
    return client


def _network_error(status_code: int, detail: str | None = None) -> NetworkError:
    request = httpx.Request("POST", "http://node.invalid/rpc/escrow/create")
    response = httpx.Response(status_code, json={"detail": detail} if detail else {}, request=request)
    http_error = httpx.HTTPStatusError(f"status {status_code}", request=request, response=response)
    error = NetworkError("POST request failed")
    error.__cause__ = http_error
    return error


class TestEscrowRelay:
    def test_relay_happy_path(self, client, db_session):
        _bind_wallet(db_session, "client-1", BUYER)
        mock_client = _chain_client_mock({"contract_id": "0xc1"})
        with patch(PATCH_TARGET, return_value=mock_client):
            resp = client.post("/v1/escrow/relay", json=_payload(), headers=_token("client-1"))
        assert resp.status_code == 200, resp.text
        assert resp.json()["contract_id"] == "0xc1"
        # Payload forwarded verbatim — lock_signature passthrough included.
        sent = mock_client.post.call_args.kwargs["json"]
        assert sent["lock_signature"] == "0xdeadbeef"
        assert sent["lock_tx"]["signature"] == "0xdeadbeef"

    def test_relay_buyer_mismatch_forbidden(self, client, db_session):
        _bind_wallet(db_session, "client-1", OTHER_BUYER)
        mock_client = _chain_client_mock()
        with patch(PATCH_TARGET, return_value=mock_client):
            resp = client.post("/v1/escrow/relay", json=_payload(), headers=_token("client-1"))
        assert resp.status_code == 403
        mock_client.post.assert_not_called()

    def test_relay_no_bound_wallet_forbidden(self, client):
        mock_client = _chain_client_mock()
        with patch(PATCH_TARGET, return_value=mock_client):
            resp = client.post("/v1/escrow/relay", json=_payload(), headers=_token("walletless-user"))
        assert resp.status_code == 403
        mock_client.post.assert_not_called()

    def test_relay_amount_over_cap_rejected(self, client, db_session, monkeypatch):
        monkeypatch.setenv("ESCROW_RELAY_MAX_UNITS", str(360_000_000))  # 10 AIT
        _bind_wallet(db_session, "client-1", BUYER)
        mock_client = _chain_client_mock()
        with patch(PATCH_TARGET, return_value=mock_client):
            resp = client.post("/v1/escrow/relay", json=_payload(amount="10.1"), headers=_token("client-1"))
        assert resp.status_code == 400
        assert "cap" in resp.json()["detail"]
        mock_client.post.assert_not_called()

    def test_relay_replay_returns_stored_contract(self, client, db_session):
        _bind_wallet(db_session, "client-1", BUYER)
        mock_client = _chain_client_mock({"contract_id": "0xc9"})
        with patch(PATCH_TARGET, return_value=mock_client):
            first = client.post("/v1/escrow/relay", json=_payload(), headers=_token("client-1"))
            second = client.post("/v1/escrow/relay", json=_payload(), headers=_token("client-1"))
        assert first.status_code == second.status_code == 200
        assert second.json()["contract_id"] == "0xc9"
        assert second.json()["duplicate"] is True
        assert mock_client.post.call_count == 1

    def test_relay_admin_any_buyer_over_cap(self, client, db_session):
        mock_client = _chain_client_mock({"contract_id": "0xadmin"})
        with patch(PATCH_TARGET, return_value=mock_client):
            resp = client.post(
                "/v1/escrow/relay",
                json=_payload(job_id="mkt_admin_1", buyer=BUYER, amount="999"),
                headers=_token("operator", role="admin"),
            )
        assert resp.status_code == 200, resp.text
        assert resp.json()["contract_id"] == "0xadmin"

    def test_relay_chain_4xx_passthrough(self, client, db_session):
        _bind_wallet(db_session, "client-1", BUYER)
        mock_client = _chain_client_mock(side_effect=_network_error(400, "lock signature invalid"))
        with patch(PATCH_TARGET, return_value=mock_client):
            resp = client.post("/v1/escrow/relay", json=_payload(job_id="mkt_4xx"), headers=_token("client-1"))
        assert resp.status_code == 400
        assert resp.json()["detail"] == "lock signature invalid"

    def test_relay_chain_5xx_is_502(self, client, db_session):
        _bind_wallet(db_session, "client-1", BUYER)
        mock_client = _chain_client_mock(side_effect=_network_error(503, "EscrowManager not initialised"))
        with patch(PATCH_TARGET, return_value=mock_client):
            resp = client.post("/v1/escrow/relay", json=_payload(job_id="mkt_5xx"), headers=_token("client-1"))
        assert resp.status_code == 502

    def test_relay_chain_timeout_is_502(self, client, db_session):
        _bind_wallet(db_session, "client-1", BUYER)
        mock_client = _chain_client_mock(side_effect=NetworkError("POST request failed: timeout"))
        with patch(PATCH_TARGET, return_value=mock_client):
            resp = client.post("/v1/escrow/relay", json=_payload(job_id="mkt_to"), headers=_token("client-1"))
        assert resp.status_code == 502

    def test_relay_job_id_conflict_on_different_lock(self, client, db_session):
        _bind_wallet(db_session, "client-1", BUYER)
        mock_client = _chain_client_mock({"contract_id": "0xc1"})
        with patch(PATCH_TARGET, return_value=mock_client):
            first = client.post("/v1/escrow/relay", json=_payload(job_id="mkt_dup"), headers=_token("client-1"))
            changed = _payload(job_id="mkt_dup")
            changed["lock_tx"]["nonce"] = 8  # different signed lock, same job
            second = client.post("/v1/escrow/relay", json=changed, headers=_token("client-1"))
        assert first.status_code == 200
        assert second.status_code == 409
        assert mock_client.post.call_count == 1

    def test_relay_energy_quote_passthrough(self, client, db_session):
        _bind_wallet(db_session, "client-1", BUYER)
        mock_client = _chain_client_mock({"contract_id": "0xeq"})
        payload = _payload(job_id="mkt_eq")
        payload["energy_quote"] = {"kwh": 1.25, "rate": "0.5"}
        payload["energy_quote_digest"] = "0xfeed"
        with patch(PATCH_TARGET, return_value=mock_client):
            resp = client.post("/v1/escrow/relay", json=payload, headers=_token("client-1"))
        assert resp.status_code == 200
        sent = mock_client.post.call_args.kwargs["json"]
        assert sent["energy_quote"] == {"kwh": 1.25, "rate": "0.5"}
        assert sent["energy_quote_digest"] == "0xfeed"

    def test_relay_row_persisted(self, client, db_session):
        _bind_wallet(db_session, "client-1", BUYER)
        mock_client = _chain_client_mock({"contract_id": "0xrow"})
        with patch(PATCH_TARGET, return_value=mock_client):
            resp = client.post("/v1/escrow/relay", json=_payload(job_id="mkt_row"), headers=_token("client-1"))
        assert resp.status_code == 200
        from sqlmodel import select

        row = db_session.execute(select(EscrowRelay).where(EscrowRelay.job_id == "mkt_row")).scalars().first()
        assert row is not None
        assert row.client_id == "client-1"
        assert row.contract_id == "0xrow"
        assert len(row.lock_hash) == 64


def test_relay_route_registered_in_security_matrix():
    """/v1/escrow/relay must not fall to middleware deny-by-default (403 'Forbidden')."""
    from aitbc.auth.security_matrix import ROUTE_SECURITY_MATRIX, get_auth_level, AuthLevel

    assert get_auth_level("/v1/escrow/relay") == AuthLevel.ADMIN_OR_CLIENT
    assert ROUTE_SECURITY_MATRIX["/v1/escrow/relay"] == AuthLevel.ADMIN_OR_CLIENT
