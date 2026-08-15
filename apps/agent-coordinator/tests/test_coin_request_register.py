"""Registering a follower's coin request at the hub (V23-62).

`/execute` pays from the hub's own record of a request and refuses one it has never seen.
That is right, and it broke a real flow: a request raised on a follower island exists only in
that island's database, so the hub has nothing to consult. `/register` is how it gets a row.

The whole design question is what status that row may take. If registering could write an
approved row on the caller's word, then register-then-execute would hand back exactly what
`/execute` stopped giving away — an arbitrary treasury transfer for anyone holding the shared
API key, one call further along. So the hub decides, using the faucet policy it already
applied over the WebSocket: a first grant within the automatic ceiling goes through unattended,
anything else waits for an operator.

That is the trade this file pins. The key buys a *request*, subject to policy. It does not buy
a payment.
"""

from __future__ import annotations

import pytest

from agent_app.services import faucet_policy

from .conftest import API_KEY, PAYOUT, signed_transactions, stored_request

WALLET = "ait1" + "ab" * 20
ATTACKER_WALLET = "ait1" + "ee" * 20
TREASURY_DRAIN = 3_600_000_000_000


def _register(client, key: str | None = API_KEY, **overrides):
    body = {
        "request_id": "req-0001",
        "sender": "agent-alpha",
        "amount": PAYOUT,
        "wallet_address": WALLET,
    }
    body.update(overrides)
    headers = {"x-api-key": key} if key is not None else {}
    return client.post("/api/v1/agent/coin-requests/register", json=body, headers=headers)


def _execute(client, request_id: str = "req-0001", key: str | None = API_KEY, **overrides):
    body = {"request_id": request_id, "sender": "agent-alpha", "amount": PAYOUT, "wallet_address": WALLET}
    body.update(overrides)
    headers = {"x-api-key": key} if key is not None else {}
    return client.post("/api/v1/agent/coin-requests/execute", json=body, headers=headers)


# --- The gate ---------------------------------------------------------------------------


def test_registering_without_a_key_is_refused(bare_client) -> None:
    assert _register(bare_client, key=None).status_code == 401
    assert stored_request("req-0001") is None


def test_registering_with_the_wrong_key_is_refused(bare_client) -> None:
    assert _register(bare_client, key="not-the-key").status_code == 401
    assert stored_request("req-0001") is None


def test_a_non_positive_amount_is_refused(bare_client) -> None:
    assert _register(bare_client, amount=0).status_code == 422
    assert _register(bare_client, amount=-1).status_code == 422
    assert stored_request("req-0001") is None


# --- Who decides the status -------------------------------------------------------------


def test_a_first_request_within_the_ceiling_is_approved(bare_client) -> None:
    response = _register(bare_client)

    assert response.status_code == 200
    assert response.json()["status"] == "approved"
    assert response.json()["already_registered"] is False
    stored = stored_request("req-0001")
    assert stored is not None
    assert stored.approval_mode == "automatic"
    assert stored.approved_by == "faucet-policy"


def test_an_amount_above_the_ceiling_waits_for_an_operator(bare_client) -> None:
    """The one that matters: the shared key cannot register a treasury drain as approved."""
    response = _register(bare_client, amount=TREASURY_DRAIN)

    assert response.status_code == 200
    assert response.json()["status"] == "pending"
    assert "ceiling" in response.json()["reason"]
    stored = stored_request("req-0001")
    assert stored is not None
    assert stored.approved_by is None


def test_a_second_grant_to_the_same_agent_waits_for_an_operator(bare_client) -> None:
    assert _register(bare_client).json()["status"] == "approved"

    second = _register(bare_client, request_id="req-0002")

    assert second.json()["status"] == "pending"
    assert "already been granted" in second.json()["reason"]


def test_the_second_grant_check_does_not_wait_for_the_first_to_be_executed(bare_client) -> None:
    """An approved-but-unexecuted grant still counts.

    `agent_stream` counts only executed grants, which is safe there because it signs
    immediately. Here an operator may take hours to run `execute`, so counting only executed
    grants would let an agent register twice, collect two approvals and spend both.
    """
    assert _register(bare_client).json()["status"] == "approved"
    assert stored_request("req-0001").transaction_hash is None

    assert _register(bare_client, request_id="req-0002").json()["status"] == "pending"


def test_automatic_approval_can_be_turned_off_entirely(bare_client, monkeypatch) -> None:
    monkeypatch.setenv("FAUCET_AUTO_APPROVE_MAX", "0")

    response = _register(bare_client)

    assert response.json()["status"] == "pending"
    assert "disabled" in response.json()["reason"]


def test_the_ceiling_is_configurable(bare_client, monkeypatch) -> None:
    monkeypatch.setenv("FAUCET_AUTO_APPROVE_MAX", str(PAYOUT - 1))

    assert _register(bare_client).json()["status"] == "pending"


def test_a_nonsense_ceiling_falls_back_to_the_default(monkeypatch) -> None:
    monkeypatch.setenv("FAUCET_AUTO_APPROVE_MAX", "lots")

    assert faucet_policy.auto_approve_ceiling() == faucet_policy.DEFAULT_AUTO_APPROVE_MAX


# --- Registering twice ------------------------------------------------------------------


def test_registering_the_same_request_twice_is_idempotent(bare_client) -> None:
    """A retry after a lost response must not raise a second request or a second grant."""
    first = _register(bare_client)

    second = _register(bare_client)

    assert second.status_code == 200
    assert second.json()["already_registered"] is True
    assert second.json()["status"] == first.json()["status"] == "approved"


def test_re_registering_with_a_different_amount_is_refused(bare_client) -> None:
    """Otherwise the sequence register-100, get approved, re-register-3.6e12 walks the amount up."""
    _register(bare_client)

    response = _register(bare_client, amount=TREASURY_DRAIN)

    assert response.status_code == 409
    assert stored_request("req-0001").amount == PAYOUT


def test_re_registering_with_a_different_destination_is_refused(bare_client) -> None:
    _register(bare_client)

    response = _register(bare_client, wallet_address=ATTACKER_WALLET)

    assert response.status_code == 409
    assert stored_request("req-0001").wallet_address == WALLET


# --- End to end -------------------------------------------------------------------------


def test_a_registered_request_can_then_be_executed(bare_client) -> None:
    """The flow the fix broke and this restores."""
    assert _execute(bare_client).status_code == 404

    assert _register(bare_client).json()["status"] == "approved"
    response = _execute(bare_client)

    assert response.status_code == 200
    assert signed_transactions() == [{"to": WALLET, "amount": PAYOUT, "fee": 10}]


def test_a_pending_registration_cannot_be_executed(bare_client) -> None:
    """Register and execute together must not add up to more than either one allows."""
    assert _register(bare_client, amount=TREASURY_DRAIN).json()["status"] == "pending"

    response = _execute(bare_client, amount=TREASURY_DRAIN)

    assert response.status_code == 409
    assert signed_transactions() == []


def test_registering_does_not_let_the_body_pick_the_amount_at_execution(bare_client) -> None:
    """Both halves of the flow read the row, so tampering with either one changes nothing."""
    _register(bare_client)

    response = _execute(bare_client, amount=TREASURY_DRAIN, wallet_address=ATTACKER_WALLET)

    assert response.status_code == 200
    assert signed_transactions()[0] == {"to": WALLET, "amount": PAYOUT, "fee": 10}


@pytest.mark.parametrize("attempt", [1, 2, 3])
def test_re_registering_after_execution_does_not_pay_again(bare_client, attempt: int) -> None:
    _register(bare_client)
    _execute(bare_client)

    for _ in range(attempt):
        assert _register(bare_client).json()["already_registered"] is True
        assert _execute(bare_client).json()["already_executed"] is True

    assert len(signed_transactions()) == 1
