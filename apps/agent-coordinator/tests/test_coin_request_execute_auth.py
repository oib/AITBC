"""The faucet's remote-execution endpoint signs treasury transfers (V23-62).

`POST /api/v1/agent/coin-requests/execute` exists so an island operator who holds no genesis
key can approve a payout and have the hub sign it. Past its one auth check it calls
`generate_signed_transaction` against the genesis wallet, so it is the only unauthenticated-
by-default path in the tree that moves money.

It had no tests. The CLI that drives it was covered by `tests/cli/test_commands_coin_requests.py`,
which was deleted in the `test(cleanup)` sweep, leaving the whole path uncovered on both sides
while the hub was publishing the key that opens it at
`https://hub.aitbc.bubuit.net/agent/blockchain-secrets.env` (V23-58).

The tests below split into two groups:

  - the API key gate, which is all the endpoint used to have;
  - the stored request as the authority for what gets paid, which is what it was missing.

The second group is the substance. `request_id` used to reach the handler and be used in exactly
one place: a log line. The hub never loaded the request, never checked it was approved, never
checked it existed, and never recorded that it paid out — so `amount` and `wallet_address` were
whatever the caller typed. That made the endpoint a general "send N from the treasury to X"
primitive wearing the name of a narrower operation, held shut by a shared secret that every
island operator holds and that was being served over plain HTTP.
"""

from __future__ import annotations

import os
from datetime import UTC, datetime, timedelta

import pytest

os.environ.setdefault("SECRET_KEY", "test-secret-key")

pytest.importorskip("fastapi", reason="agent-coordinator app dependencies not installed")

from fastapi import FastAPI  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from aitbc.db import agent_db  # noqa: E402
from aitbc.models import CoinRequest, CoinRequestStatus  # noqa: E402
from agent_app.routers import coin_requests  # noqa: E402

API_KEY = "test-coordinator-api-key"
TREASURY_BALANCE = 3_600_000_000_000
PAYOUT = 100
TX_HASH = "0x" + "cd" * 32

APPROVED = {"id": "req-0001", "amount": PAYOUT, "wallet_address": "ait1" + "ab" * 20}
PENDING = {"id": "req-0002", "amount": 250, "wallet_address": "ait1" + "ba" * 20}


class _FakeTransactionService:
    """Stands in for the real signer so no test can emit a transaction."""

    instances: list[_FakeTransactionService] = []

    def __init__(self) -> None:
        self.genesis_private_key = "0x" + "11" * 32
        self.genesis_address = "ait1" + "fe" * 20
        self.rpc_url = "http://localhost:8202"
        self.signed: list[dict] = []
        _FakeTransactionService.instances.append(self)

    def get_balance(self, _address: str) -> int:
        return TREASURY_BALANCE

    def generate_signed_transaction(self, to_address: str, amount: int, fee: int) -> dict:
        payload = {"to": to_address, "amount": amount, "fee": fee}
        self.signed.append(payload)
        return payload


class _FakeHttpClient:
    def __init__(self, *_args, **_kwargs) -> None:
        pass

    def post(self, _path: str, json: dict) -> dict:  # noqa: A002
        return {"transaction_hash": TX_HASH}


def _signed() -> list[dict]:
    """Every transaction any service instance signed during this test."""
    return [tx for service in _FakeTransactionService.instances for tx in service.signed]


def _row(request_id: str) -> CoinRequest | None:
    with agent_db.get_db_session() as session:
        found = session.query(CoinRequest).filter(CoinRequest.id == request_id).first()
        if found is not None:
            session.expunge(found)
        return found


def _store(session, spec: dict, status: CoinRequestStatus) -> None:
    now = datetime.now(UTC).replace(tzinfo=None)
    session.add(
        CoinRequest(
            id=spec["id"],
            sender="agent-under-test",
            recipient=spec["wallet_address"],
            amount=spec["amount"],
            wallet_address=spec["wallet_address"],
            status=status,
            approval_mode="manual",
            approved_by="cli" if status is CoinRequestStatus.APPROVED else None,
            created_at=now,
            expires_at=now + timedelta(days=1),
        )
    )


@pytest.fixture
def client(monkeypatch, tmp_path):
    _FakeTransactionService.instances.clear()
    monkeypatch.setenv("COORDINATOR_API_KEY", API_KEY)
    monkeypatch.delenv("SECRET_KEY", raising=False)
    monkeypatch.setattr(coin_requests, "TransactionService", _FakeTransactionService)
    monkeypatch.setattr("aitbc.network.AITBCHTTPClient", _FakeHttpClient, raising=False)

    # The engine is a module global cached on first use, so pointing AGENT_DB_PATH at a
    # fresh file is not enough on its own.
    monkeypatch.setenv("AGENT_DB_PATH", str(tmp_path / "coin_requests.db"))
    monkeypatch.setattr(agent_db, "_engine", None)
    monkeypatch.setattr(agent_db, "_SessionLocal", None)
    agent_db.init_db()

    with agent_db.get_db_session() as session:
        _store(session, APPROVED, CoinRequestStatus.APPROVED)
        _store(session, PENDING, CoinRequestStatus.PENDING)

    app = FastAPI()
    app.include_router(coin_requests.router)
    yield TestClient(app)

    agent_db._engine = None
    agent_db._SessionLocal = None


def _body(**overrides) -> dict:
    body = {
        "request_id": APPROVED["id"],
        "sender": "agent-under-test",
        "amount": APPROVED["amount"],
        "wallet_address": APPROVED["wallet_address"],
        "approved_by": "cli",
    }
    body.update(overrides)
    return body


def _execute(client: TestClient, key: str | None = API_KEY, **overrides):
    headers = {"x-api-key": key} if key is not None else {}
    return client.post("/api/v1/agent/coin-requests/execute", json=_body(**overrides), headers=headers)


# --- The API key gate -------------------------------------------------------------------


def test_a_request_with_no_key_is_refused(client) -> None:
    assert _execute(client, key=None).status_code == 401
    assert _signed() == []


def test_a_request_with_the_wrong_key_is_refused(client) -> None:
    assert _execute(client, key="not-the-key").status_code == 401
    assert _signed() == []


def test_the_secret_key_is_accepted_interchangeably(client, monkeypatch) -> None:
    """`COORDINATOR_API_KEY or SECRET_KEY` — the two are one credential, not two.

    Worth pinning because it is the reason splitting the values buys less than it appears to:
    either one alone opens this endpoint.
    """
    monkeypatch.delenv("COORDINATOR_API_KEY", raising=False)
    monkeypatch.setenv("SECRET_KEY", "the-other-value")

    assert _execute(client, key="the-other-value").status_code == 200


def test_a_valid_key_signs_a_transfer_from_the_treasury(client) -> None:
    response = _execute(client)

    assert response.status_code == 200
    assert _signed() == [{"to": APPROVED["wallet_address"], "amount": PAYOUT, "fee": coin_requests.TRANSACTION_FEE}]


def test_a_payout_above_the_treasury_balance_is_refused(client, monkeypatch) -> None:
    monkeypatch.setattr(_FakeTransactionService, "get_balance", lambda _self, _address: PAYOUT - 1)

    response = _execute(client)

    assert response.status_code == 400
    assert _signed() == []


# --- The stored request is the authority ------------------------------------------------


def test_the_amount_comes_from_the_stored_request_not_the_request_body(client) -> None:
    """The whole defect in one assertion.

    A caller asking to execute `req-0001` — a request approved for 100 — could name any figure
    and the hub signed it. Nothing reconciled the body against what was approved, so the
    endpoint's authority was the treasury balance rather than the approval.
    """
    response = _execute(client, amount=TREASURY_BALANCE - 1)

    assert response.status_code == 200
    assert _signed()[0]["amount"] == PAYOUT
    assert response.json()["amount"] == PAYOUT


def test_the_destination_comes_from_the_stored_request_not_the_request_body(client) -> None:
    attacker = "ait1" + "ee" * 20

    response = _execute(client, wallet_address=attacker)

    assert response.status_code == 200
    assert _signed()[0]["to"] == APPROVED["wallet_address"]
    assert response.json()["recipient"] == APPROVED["wallet_address"]


def test_an_unknown_request_id_is_refused(client) -> None:
    response = _execute(client, request_id="req-does-not-exist")

    assert response.status_code == 404
    assert _signed() == []


def test_a_request_that_was_never_approved_is_refused(client) -> None:
    response = _execute(client, request_id=PENDING["id"], amount=PENDING["amount"])

    assert response.status_code == 409
    assert "not approved" in response.json()["detail"]
    assert _signed() == []


def test_the_same_request_cannot_be_executed_twice(client) -> None:
    """A replay must not pay again, and must still tell the caller what happened.

    Returning the original hash rather than an error matters for the case this endpoint
    actually meets: the CLI posts, the hub signs and submits, the response is lost. The
    retry then reconciles instead of leaving the operator unsure whether it paid.
    """
    first = _execute(client)
    assert first.status_code == 200
    assert first.json()["already_executed"] is False

    second = _execute(client)

    assert second.status_code == 200
    assert second.json()["already_executed"] is True
    assert second.json()["tx_hash"] == first.json()["tx_hash"]
    assert len(_signed()) == 1


def test_a_successful_execution_is_recorded_against_the_request(client) -> None:
    """Without this the replay guard has nothing to consult, and `list` never shows it paid."""
    _execute(client)

    stored = _row(APPROVED["id"])
    assert stored is not None
    assert stored.transaction_hash == TX_HASH
    assert TX_HASH in (stored.audit_log or "")


def test_a_failed_submission_leaves_the_request_executable(client, monkeypatch) -> None:
    """A claim that does not result in a payment must be released, or a blip strands the request."""

    class _RejectingHttpClient(_FakeHttpClient):
        def post(self, _path: str, json: dict) -> dict:  # noqa: A002
            raise RuntimeError("blockchain unreachable")

    monkeypatch.setattr("aitbc.network.AITBCHTTPClient", _RejectingHttpClient, raising=False)
    assert _execute(client).status_code == 502

    stored = _row(APPROVED["id"])
    assert stored is not None
    assert stored.transaction_hash is None

    monkeypatch.setattr("aitbc.network.AITBCHTTPClient", _FakeHttpClient, raising=False)
    assert _execute(client).status_code == 200
