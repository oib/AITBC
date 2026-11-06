"""PI-API-002 (#1178): governance parallel write surface must require the
caller signature the dedicated routes enforce (#1091).

Pins:
- ``POST /v1/transactions`` (propose/vote/execute relay) rejects unsigned
  and wrongly-signed bodies, and accepts a correctly-signed body past the
  auth gate.
- ``propagate`` / ``aggregate-votes`` / ``execute-cross-chain`` reject
  unsigned calls; ``aggregate-votes`` (auth runs before any proposal
  lookup) gives a clean 403 pin.
"""

from __future__ import annotations

import json
import time
from typing import Any

import pytest
from eth_keys import keys
from eth_utils import keccak
from fastapi.testclient import TestClient

from governance_service.main import app

PRIVKEY = "0x" + "11" * 32
OTHER_PRIVKEY = "0x" + "22" * 32


def _address(privkey: str) -> str:
    return keys.PrivateKey(bytes.fromhex(privkey.removeprefix("0x"))).public_key.to_checksum_address()


def _sign_body(private_key: str, payload: dict[str, Any]) -> str:
    msg = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    pk = keys.PrivateKey(bytes.fromhex(private_key.removeprefix("0x")))
    return pk.sign_msg_hash(keccak(msg)).to_hex()


def _signed(body: dict[str, Any], privkey: str = PRIVKEY, caller: str | None = None) -> dict[str, Any]:
    out = dict(body)
    out["caller_address"] = caller if caller is not None else _address(privkey)
    out["timestamp"] = time.time()
    out["signature"] = _sign_body(privkey, {k: v for k, v in out.items() if k != "signature"})
    return out


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


# ── /v1/transactions ────────────────────────────────────────────────


def test_transactions_rejects_unsigned(client: TestClient) -> None:
    r = client.post(
        "/v1/transactions",
        json={"type": "governance", "action": "propose", "title": "x"},
    )
    assert r.status_code == 403


def test_transactions_rejects_wrong_signer(client: TestClient) -> None:
    body = _signed(
        {"type": "governance", "action": "propose", "title": "x"},
        privkey=OTHER_PRIVKEY,
        caller=_address(PRIVKEY),  # claims A, signed by B
    )
    r = client.post("/v1/transactions", json=body)
    assert r.status_code == 403


def test_transactions_rejects_missing_timestamp(client: TestClient) -> None:
    body = {"type": "governance", "action": "propose", "caller_address": _address(PRIVKEY)}
    body["signature"] = _sign_body(PRIVKEY, body)
    r = client.post("/v1/transactions", json=body)
    assert r.status_code == 403


def test_transactions_accepts_valid_signature_past_auth(client: TestClient) -> None:
    # Unknown action -> deterministic 400 *after* the auth gate, proving the
    # signature verified (pre-fix this route had no gate at all).
    body = _signed({"type": "governance", "action": "bogus-action"})
    r = client.post("/v1/transactions", json=body)
    assert r.status_code == 400
    assert "Invalid action" in r.json()["error"]


def test_transactions_binds_actor_alias(client: TestClient) -> None:
    # Signed by A but claims proposer_id=B -> 403 via _bind_actor.
    body = _signed(
        {
            "type": "governance",
            "action": "propose",
            "proposer_id": _address(OTHER_PRIVKEY),
        }
    )
    r = client.post("/v1/transactions", json=body)
    assert r.status_code == 403


# ── cross-chain routes ──────────────────────────────────────────────


def test_aggregate_votes_rejects_unsigned(client: TestClient) -> None:
    r = client.post("/v1/governance/proposals/prop-x/aggregate-votes")
    assert r.status_code == 403


def test_aggregate_votes_rejects_empty_body(client: TestClient) -> None:
    r = client.post("/v1/governance/proposals/prop-x/aggregate-votes", json={})
    assert r.status_code == 403


def test_aggregate_votes_accepts_valid_signature(client: TestClient) -> None:
    # Auth passes; the tally itself runs against whatever votes exist
    # (none for a bogus proposal id) — any non-403 proves the gate opened.
    r = client.post(
        "/v1/governance/proposals/prop-x/aggregate-votes",
        json=_signed({}),
    )
    assert r.status_code == 200


def _create_proposal(client: TestClient, privkey: str = PRIVKEY) -> str:
    """Seed a real proposal via the dedicated signed route; return its id."""
    addr = _address(privkey)
    body = {
        "title": "t",
        "description": "d",
        "proposal_type": "parameter_change",
        "category": "general",
        "proposer_address": addr,
        "caller_address": addr,
        "timestamp": time.time(),
    }
    body["signature"] = _sign_body(privkey, {k: v for k, v in body.items() if k != "signature"})
    r = client.post("/v1/governance/proposals", json=body)
    assert r.status_code == 200, r.text
    return r.json()["proposal_id"]


def test_propagate_rejects_unsigned(client: TestClient) -> None:
    pid = _create_proposal(client)
    r = client.post(
        f"/v1/governance/proposals/{pid}/propagate",
        json={"target_chains": ["ait-side-1"]},
    )
    assert r.status_code == 403


def test_propagate_rejects_non_proposer_signer(client: TestClient) -> None:
    pid = _create_proposal(client)
    body = _signed({"target_chains": ["ait-side-1"]}, privkey=OTHER_PRIVKEY)
    r = client.post(f"/v1/governance/proposals/{pid}/propagate", json=body)
    assert r.status_code == 403


def test_propagate_accepts_proposer_signature(client: TestClient) -> None:
    pid = _create_proposal(client)
    body = _signed({"target_chains": ["ait-side-1"]})
    r = client.post(f"/v1/governance/proposals/{pid}/propagate", json=body)
    # Auth passed — downstream chain submission may fail per-chain, but the
    # route answers 200 with propagated_to/failed lists, never 403.
    assert r.status_code == 200, r.text
    assert "failed" in r.json() or "propagated_to" in r.json()


def test_execute_cross_chain_rejects_unsigned(client: TestClient) -> None:
    pid = _create_proposal(client)
    r = client.post(f"/v1/governance/proposals/{pid}/execute-cross-chain")
    assert r.status_code == 403


def test_execute_cross_chain_signed_non_proposer_403(client: TestClient) -> None:
    pid = _create_proposal(client)
    r = client.post(
        f"/v1/governance/proposals/{pid}/execute-cross-chain",
        json=_signed({}, privkey=OTHER_PRIVKEY),
    )
    assert r.status_code == 403


def test_execute_cross_chain_signed_proposer_reaches_status_check(client: TestClient) -> None:
    pid = _create_proposal(client)
    r = client.post(
        f"/v1/governance/proposals/{pid}/execute-cross-chain",
        json=_signed({}),
    )
    # Proposal is 'active', not 'passed' — auth passed, status gate answers 400.
    assert r.status_code == 400
