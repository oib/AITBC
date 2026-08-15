"""The faucet's remote-execution endpoint signs treasury transfers (V23-62).

`POST /api/v1/agent/coin-requests/execute` exists so an island operator who holds no genesis
key can approve a payout and have the hub sign it. Past its one auth check it calls
`generate_signed_transaction` against the genesis wallet, so it is the only unauthenticated-
by-default path in the tree that moves money.

It had no tests. The CLI that drives it was covered by `tests/cli/test_commands_coin_requests.py`,
which was deleted in the `test(cleanup)` sweep, leaving the whole path uncovered on both sides
while the hub was publishing the key that opens it at
`https://hub.aitbc.bubuit.net/agent/blockchain-secrets.env` (V23-58).

The tests below split into two groups deliberately:

  - what the endpoint gets right today, pinned so it cannot regress silently;
  - what it gets wrong, marked `xfail(strict=True)` so the suite stays green now and tells
    you the moment someone fixes it, rather than sitting as a comment nobody reads.

The second group is the substance. `request_id` reaches the handler and is used in exactly one
place: a log line. The hub never loads the request, never checks it was approved, never checks
it exists, and never records that it paid out — so `amount` and `wallet_address` are whatever
the caller typed. That makes the endpoint a general "send N from the treasury to X" primitive
wearing the name of a narrower operation.
"""

from __future__ import annotations

import os

import pytest

os.environ.setdefault("SECRET_KEY", "test-secret-key")

pytest.importorskip("fastapi", reason="agent-coordinator app dependencies not installed")

from fastapi import FastAPI  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from agent_app.routers import coin_requests  # noqa: E402

API_KEY = "test-coordinator-api-key"
TREASURY_BALANCE = 3_600_000_000_000
PAYOUT = 100

# A request the hub would consider approved, and the amount stored against it.
APPROVED_REQUEST = {"id": "req-0001", "amount": PAYOUT, "wallet_address": "ait1" + "ab" * 20}


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
        return {"transaction_hash": "0x" + "cd" * 32}


@pytest.fixture
def client(monkeypatch):
    _FakeTransactionService.instances.clear()
    monkeypatch.setenv("COORDINATOR_API_KEY", API_KEY)
    monkeypatch.delenv("SECRET_KEY", raising=False)
    monkeypatch.setattr(coin_requests, "TransactionService", _FakeTransactionService)
    monkeypatch.setattr("aitbc.network.AITBCHTTPClient", _FakeHttpClient, raising=False)

    app = FastAPI()
    app.include_router(coin_requests.router)
    return TestClient(app)


def _body(**overrides) -> dict:
    body = {
        "request_id": APPROVED_REQUEST["id"],
        "sender": "ait1" + "99" * 20,
        "amount": APPROVED_REQUEST["amount"],
        "wallet_address": APPROVED_REQUEST["wallet_address"],
        "approved_by": "cli",
    }
    body.update(overrides)
    return body


def _execute(client: TestClient, key: str | None = API_KEY, **overrides):
    headers = {"x-api-key": key} if key is not None else {}
    return client.post("/api/v1/agent/coin-requests/execute", json=_body(**overrides), headers=headers)


# --- What holds today -------------------------------------------------------------------


def test_a_request_with_no_key_is_refused(client) -> None:
    assert _execute(client, key=None).status_code == 401
    assert _FakeTransactionService.instances[-1].signed == [] if _FakeTransactionService.instances else True


def test_a_request_with_the_wrong_key_is_refused(client) -> None:
    assert _execute(client, key="not-the-key").status_code == 401


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
    signed = _FakeTransactionService.instances[-1].signed
    assert signed == [{"to": APPROVED_REQUEST["wallet_address"], "amount": PAYOUT, "fee": coin_requests.TRANSACTION_FEE}]


def test_a_payout_above_the_treasury_balance_is_refused(client) -> None:
    response = _execute(client, amount=TREASURY_BALANCE + 1)

    assert response.status_code == 400
    assert _FakeTransactionService.instances[-1].signed == []


# --- What does not hold, and should ----------------------------------------------------


@pytest.mark.xfail(strict=True, reason="V23-62: request_id is only logged; the stored amount is never consulted")
def test_the_amount_comes_from_the_stored_request_not_the_request_body(client) -> None:
    """The whole defect in one assertion.

    A caller asking to execute `req-0001` — a request approved for 100 — can name any figure
    and the hub signs it. Nothing reconciles the body against what was approved, so the
    endpoint's authority is the treasury balance rather than the approval.
    """
    _execute(client, amount=TREASURY_BALANCE - 1)

    assert _FakeTransactionService.instances[-1].signed[0]["amount"] == PAYOUT


@pytest.mark.xfail(strict=True, reason="V23-62: the destination is taken from the body, not the approved request")
def test_the_destination_comes_from_the_stored_request_not_the_request_body(client) -> None:
    attacker = "ait1" + "ee" * 20

    _execute(client, wallet_address=attacker)

    assert _FakeTransactionService.instances[-1].signed[0]["to"] == APPROVED_REQUEST["wallet_address"]


@pytest.mark.xfail(strict=True, reason="V23-62: no request lookup, so an id that was never approved still pays")
def test_an_unknown_request_id_is_refused(client) -> None:
    response = _execute(client, request_id="req-does-not-exist")

    assert response.status_code in (400, 404)


@pytest.mark.xfail(strict=True, reason="V23-62: no idempotency record, so a replayed call pays twice")
def test_the_same_request_cannot_be_executed_twice(client) -> None:
    """The CLI checks `transaction_hash` before forwarding; the hub does not check anything.

    A retried request — or a replayed one — pays again, and the second payout is
    indistinguishable from the first in the log.
    """
    assert _execute(client).status_code == 200
    second = _execute(client)

    assert second.status_code in (400, 409)
    assert len(_FakeTransactionService.instances[-1].signed) == 1
