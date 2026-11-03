"""Pin for COIN-REQUEST-EXEC-AMBIGUOUS-RETRY-1 (#851).

The execute endpoint used to release its claim after ANY submit failure —
including a timeout after the node had already accepted the transaction —
so a retry paid the same request twice. Now the claim folds in the signed
transaction's nonce before the POST, an ambiguous exit keeps the claim,
and a retry checks the chain for that (sender, nonce) pair: found → the
first tx's hash is returned and the row is finalized; not found → the
claim is released and the next call executes fresh.
"""

from __future__ import annotations

import pytest

from aitbc.models import CoinRequestStatus
from agent_app.routers import coin_requests

from .conftest import (
    API_KEY,
    FakeTransactionService,
    PAYOUT,
    TX_HASH,
    signed_transactions,
    store_request,
    stored_request,
)

APPROVED = {"id": "req-amb", "amount": PAYOUT, "wallet_address": "0xf3290d4F0D96a2Dd231C44362c57d5ad0AF0A281"}
GENESIS = "0xF5A930bBC90c15dB0bbf28f8485D18eEf24c3F43"  # FakeTransactionService.genesis_address
NONCE = 7


class _AmbiguousHttpClient:
    """post() always dies mid-flight — the node may or may not have accepted."""

    mempool: list[dict] = []
    sealed: list[dict] = []

    def __init__(self, *_args, **_kwargs) -> None:
        pass

    def post(self, _path, json):  # noqa: A002
        raise ConnectionError("response lost after the node accepted")

    def get_json(self, path, params=None):
        if path == "/rpc/mempool":
            return {"success": True, "transactions": list(self.mempool)}
        if path == "/rpc/transactions":
            return list(self.sealed)
        return {}


def _sign_with_nonce(self, to_address, amount, fee):  # noqa: ANN001, ANN202
    payload = {"from": GENESIS, "to": to_address, "amount": amount, "fee": fee, "nonce": NONCE}
    self.signed.append(payload)
    return payload


@pytest.fixture
def client(bare_client, coin_request_env, monkeypatch):
    """A hub holding one approved request; the signer emits nonce-marked txs,
    the node POST always dies ambiguously."""
    _AmbiguousHttpClient.mempool.clear()
    _AmbiguousHttpClient.sealed.clear()
    monkeypatch.setattr(FakeTransactionService, "generate_signed_transaction", _sign_with_nonce)
    monkeypatch.setattr("aitbc.network.AITBCHTTPClient", _AmbiguousHttpClient, raising=False)

    from aitbc.db import agent_db

    with agent_db.get_db_session() as session:
        store_request(session, APPROVED, CoinRequestStatus.APPROVED)
    return bare_client


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


def _execute(client):
    return client.post("/api/v1/agent/coin-requests/execute", json=_body(), headers={"x-api-key": API_KEY})


def test_ambiguous_failure_keeps_the_nonce_marked_claim(client) -> None:
    """The POST dies after signing: the claim must stay — the tx may be in the
    mempool — and it must carry the attempt's nonce for the retry's check."""
    response = _execute(client)
    assert response.status_code == 502
    row = stored_request(APPROVED["id"])
    assert row is not None and row.transaction_hash is not None
    assert row.transaction_hash.startswith(coin_requests.EXECUTION_CLAIM_PREFIX)
    assert f"nonce={NONCE}" in row.transaction_hash


def test_retry_after_accept_recovers_the_first_tx(client) -> None:
    """done_when: post raises after the node accepted → retry returns the first tx."""
    _execute(client)

    # The first attempt's tx is sitting in the mempool under the claim's nonce.
    _AmbiguousHttpClient.mempool.append(
        {"from": GENESIS, "to": APPROVED["wallet_address"], "nonce": NONCE, "tx_hash": TX_HASH}
    )
    response = _execute(client)

    assert response.status_code == 200
    body = response.json()
    assert body["success"] is True and body["already_executed"] is True
    assert body["tx_hash"] == TX_HASH
    # The row is finalized to the real hash — no second signing ever happened.
    assert stored_request(APPROVED["id"]).transaction_hash == TX_HASH
    assert len(signed_transactions()) == 1


def test_retry_recovers_from_sealed_history_too(client) -> None:
    _execute(client)
    _AmbiguousHttpClient.sealed.append({"from": GENESIS, "to": APPROVED["wallet_address"], "nonce": NONCE, "tx_hash": TX_HASH})
    response = _execute(client)
    assert response.status_code == 200 and response.json()["tx_hash"] == TX_HASH


def test_clean_slate_after_a_truly_unlanded_attempt(client) -> None:
    """Chain check finds nothing → the claim is released and the next call
    executes fresh. This is the only case a new payment may be signed."""
    _execute(client)
    # mempool and sealed both empty → retry releases the claim and 409s once…
    assert _execute(client).status_code == 409
    assert stored_request(APPROVED["id"]).transaction_hash is None


def test_executed_row_replay_is_unchanged(client) -> None:
    """A real tx_hash on the row still short-circuits before any chain work."""
    _execute(client)
    _AmbiguousHttpClient.mempool.append(
        {"from": GENESIS, "to": APPROVED["wallet_address"], "nonce": NONCE, "tx_hash": TX_HASH}
    )
    _execute(client)  # recovers and finalizes to TX_HASH
    response = _execute(client)
    assert response.status_code == 200 and response.json()["tx_hash"] == TX_HASH
    assert len(signed_transactions()) == 1
