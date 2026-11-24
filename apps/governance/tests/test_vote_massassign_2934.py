"""#2934: POST /v1/governance/votes must not mass-assign server fields.

``Vote(**vote_data)`` received the signed body minus a hand-maintained pop
list (#1091 covered the weight fields only). Remaining caller-settable
columns — ``vote_id`` (PK squat), ``block_height``, ``tx_hash``,
``signature``, ``delegated_from``, ``created_at`` — are now dropped by an
allowlist; weight snapshots stay server-computed.
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


def _signed(body: dict[str, Any], privkey: str = PRIVKEY) -> dict[str, Any]:
    out = dict(body)
    addr = _address(privkey)
    out["voter_address"] = addr
    out["caller_address"] = addr
    out["timestamp"] = time.time()
    out["signature"] = _sign_body(privkey, {k: v for k, v in out.items() if k != "signature"})
    return out


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


def _active_proposal(client: TestClient) -> str:
    from datetime import UTC, datetime, timedelta

    now = datetime.now(UTC)
    body = _signed(
        {
            "proposer_address": _address(PRIVKEY),
            "title": "t",
            "description": "d",
            "category": "general",
            "voting_starts": now.isoformat(),
            "voting_ends": (now + timedelta(hours=4)).isoformat(),
        }
    )
    r = client.post("/v1/governance/proposals", json=body)
    assert r.status_code == 200, r.text
    return r.json()["proposal_id"]


def test_vote_drops_forged_server_fields(client: TestClient) -> None:
    pid = _active_proposal(client)
    body = _signed(
        {
            "proposal_id": pid,
            "voter_id": _address(PRIVKEY),
            "vote_type": "for",
            "reason": "ok",
            # forged server fields — none may land on the Vote row
            "vote_id": "vote_squat",
            "voting_power": "999999999",
            "voting_power_used": "999999999",
            "vote_weight": "999999999",
            "power_at_snapshot": "999999999",
            "delegated_power_at_snapshot": "999999999",
            "delegated_from": "0xattacker",
            "block_height": 1,
            "tx_hash": "0xdead",
            "signature": "0xforged",
            "created_at": "2020-01-01T00:00:00+00:00",
        }
    )
    r = client.post("/v1/governance/votes", json=body)
    assert r.status_code == 200, r.text
    vote = r.json()
    assert vote["vote_id"] != "vote_squat"
    assert vote["tx_hash"] in (None, "")
    assert vote["block_height"] in (None, 0)
    assert vote["delegated_from"] in (None, "")
    assert str(vote.get("signature") or "") != "0xforged"
    for w in ("voting_power", "voting_power_used", "vote_weight", "power_at_snapshot"):
        assert str(vote[w]) in ("0", "0.0", "0E-8", "0.00000000"), (w, vote[w])
    # Legitimate caller fields still land.
    assert vote["proposal_id"] == pid
    assert vote["vote_type"] in ("for", "VoteType.FOR", "FOR")
    assert vote["reason"] == "ok"


def test_relay_vote_drops_forged_server_fields(client: TestClient) -> None:
    pid = _active_proposal(client)
    keys.PrivateKey(b"\x22" * 32)
    body = _signed(
        {
            "type": "governance",
            "action": "vote",
            "proposal_id": pid,
            "voter_id": _address(OTHER_PRIVKEY),
            "voter_address": _address(OTHER_PRIVKEY),
            "vote_type": "against",
            "voting_power": "999999999",
            "tx_hash": "0xdead",
        },
        privkey=OTHER_PRIVKEY,
    )
    r = client.post("/v1/transactions", json=body)
    assert r.status_code == 200, r.text
    votes = client.get("/v1/governance/votes", params={"proposal_id": pid})
    assert votes.status_code == 200, votes.text
    rows = votes.json()
    rows = rows if isinstance(rows, list) else rows.get("votes", rows.get("items", []))
    mine = [v for v in rows if str(v.get("voter_id", "")).lower() == _address(OTHER_PRIVKEY).lower()]
    assert mine, rows
    v = mine[0]
    assert v["tx_hash"] in (None, "")
    assert str(v["voting_power"]) in ("0", "0.0", "0E-8", "0.00000000")
