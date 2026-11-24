"""#2876: POST /v1/governance/profiles must not mass-assign server fields.

``GovernanceProfile(**profile_data)`` accepted ``role`` (incl. 'admin'),
``voting_power``/``delegated_power``, vote counters, ``delegate_to``,
``joined_at`` and a caller-chosen ``profile_id`` (PK squat → 500, or
pre-claiming another user's profile id). Only ``user_id`` — bound to the
signing address by the route — is caller-settable now.
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

PRIVKEY = "0x" + "77" * 32


def _address(privkey: str) -> str:
    return keys.PrivateKey(bytes.fromhex(privkey.removeprefix("0x"))).public_key.to_checksum_address()


def _sign_body(private_key: str, payload: dict[str, Any]) -> str:
    msg = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    pk = keys.PrivateKey(bytes.fromhex(private_key.removeprefix("0x")))
    return pk.sign_msg_hash(keccak(msg)).to_hex()


def _signed(body: dict[str, Any]) -> dict[str, Any]:
    out = dict(body)
    addr = _address(PRIVKEY)
    out["caller_address"] = addr
    out["timestamp"] = time.time()
    out["signature"] = _sign_body(PRIVKEY, {k: v for k, v in out.items() if k != "signature"})
    return out


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


def test_profile_drops_forged_server_fields(client: TestClient) -> None:
    body = _signed(
        {
            "role": "admin",
            "voting_power": "999999999",
            "delegated_power": "999999999",
            "total_votes_cast": 9999,
            "proposals_created": 9999,
            "proposals_passed": 9999,
            "delegate_to": "0xattacker",
            "profile_id": "gov_squat",
            "joined_at": "2020-01-01T00:00:00+00:00",
            "last_voted_at": "2020-01-01T00:00:00+00:00",
        }
    )
    r = client.post("/v1/governance/profiles", json=body)
    assert r.status_code == 200, r.text
    prof = r.json()
    assert prof["profile_id"] != "gov_squat"
    assert str(prof.get("role", "")).lower() != "admin"
    for f in ("voting_power", "delegated_power"):
        assert str(prof[f]) in ("0", "0.0", "0E-8", "0.00000000"), (f, prof[f])
    assert prof.get("delegate_to") in (None, "")
    assert prof["user_id"] == _address(PRIVKEY)


def test_profile_legit_user_id_lands(client: TestClient) -> None:
    other = "0x" + "88" * 32
    out = {"caller_address": _address(other), "timestamp": time.time()}
    out["signature"] = _sign_body(other, out)
    r = client.post("/v1/governance/profiles", json=out)
    assert r.status_code == 200, r.text
    assert r.json()["user_id"] == _address(other)
