"""#2872: POST /v1/governance/proposals must not mass-assign server fields.

Before the fix the signed body went verbatim into ``Proposal(**data)`` —
a caller could forge ``status='succeeded'``, vote tallies, quorum and the
on-chain anchors, then ``execute`` the proposal's parameter changes without
a real vote. The signature only proves key ownership; it cannot vouch for
field sanity. These pins assert forged server fields are dropped on both
the dedicated route and the ``/v1/transactions`` relay, while legitimate
caller fields still land.
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


def _address(privkey: str) -> str:
    return keys.PrivateKey(bytes.fromhex(privkey.removeprefix("0x"))).public_key.to_checksum_address()


def _sign_body(private_key: str, payload: dict[str, Any]) -> str:
    msg = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    pk = keys.PrivateKey(bytes.fromhex(private_key.removeprefix("0x")))
    return pk.sign_msg_hash(keccak(msg)).to_hex()


def _signed(body: dict[str, Any]) -> dict[str, Any]:
    out = dict(body)
    addr = _address(PRIVKEY)
    out["proposer_address"] = addr
    out["caller_address"] = addr
    out["timestamp"] = time.time()
    out["signature"] = _sign_body(PRIVKEY, {k: v for k, v in out.items() if k != "signature"})
    return out


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


_FORGED = {
    "status": "succeeded",
    "yes_votes": "999999999",
    "no_votes": "0",
    "votes_for": "999999999",
    "votes_against": "0",
    "votes_abstain": "0",
    "quorum_required": "0",
    "passing_threshold": "0",
    "block_height": 1,
    "voting_ends_block": 2,
    "tx_hash": "0xdead",
    "execution_tx_hash": "0xbeef",
    "executed_at": "2020-01-01T00:00:00+00:00",
    "snapshot_block": 1,
    "snapshot_timestamp": "2020-01-01T00:00:00+00:00",
}


def _base_body() -> dict[str, Any]:
    return {
        "title": "t",
        "description": "d",
        "proposal_type": "general",
        "category": "general",
        "proposal_value": {"k": "v"},
    }


def _assert_server_fields_clean(prop: dict[str, Any]) -> None:
    from decimal import Decimal

    assert prop["status"] != "succeeded"
    for tally in ("yes_votes", "no_votes", "votes_for", "votes_against", "votes_abstain"):
        assert Decimal(str(prop[tally])) == 0, (tally, prop[tally])
    assert Decimal(str(prop["quorum_required"])) != 0
    assert prop["executed_at"] is None
    assert prop["execution_tx_hash"] is None
    assert prop["tx_hash"] != "0xdead"


def test_route_drops_forged_server_fields(client: TestClient) -> None:
    body = _signed({**_base_body(), **_FORGED})
    r = client.post("/v1/governance/proposals", json=body)
    assert r.status_code == 200, r.text
    prop = r.json()
    _assert_server_fields_clean(prop)
    # Legitimate caller fields still land.
    assert prop["title"] == "t"
    assert prop["proposal_value"] == {"k": "v"}
    assert prop["proposer_id"] == _address(PRIVKEY)


def test_relay_drops_forged_server_fields(client: TestClient) -> None:
    body = _signed(
        {
            "type": "governance",
            "action": "propose",
            "proposer_id": _address(PRIVKEY),
            **_base_body(),
            **_FORGED,
        }
    )
    r = client.post("/v1/transactions", json=body)
    assert r.status_code == 200, r.text
    pid = r.json()["transaction_id"]
    got = client.get(f"/v1/governance/proposals/{pid}")
    assert got.status_code == 200, got.text
    _assert_server_fields_clean(got.json())
