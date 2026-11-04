"""Pin for #1091: governance write routes refuse unsigned or wrongly-signed calls.

Every write route used to take any body: a caller could stake tokens it did
not hold, send its own voting_power, vote repeatedly, and close the proposal
as succeeded. Writes now need a secp256k1 signature from the acting address,
client-supplied power fields are ignored, and a voter can vote once.
"""

from __future__ import annotations

import json

import pytest
from eth_keys import keys
from eth_utils import keccak
from fastapi.testclient import TestClient

from governance_service.main import StakeRequest, app


def _sign(pk: keys.PrivateKey, payload: dict) -> str:
    return pk.sign_msg_hash(keccak(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode())).to_hex()


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


@pytest.fixture
def proposal_id(client: TestClient) -> str:
    proposer = keys.PrivateKey(b"\x0a" * 32)
    from datetime import UTC, datetime, timedelta

    now = datetime.now(UTC)
    body = {
        "proposer_address": proposer.public_key.to_checksum_address(),
        "proposer_id": "pin-proposer",
        "title": "test",
        "description": "pin",
        "category": "other",
        "voting_starts": now.isoformat(),
        "voting_ends": (now + timedelta(hours=4)).isoformat(),
    }
    body["signature"] = _sign(proposer, body.copy())
    r = client.post("/v1/governance/proposals", json=body)
    assert r.status_code == 200, r.text
    return r.json()["proposal_id"]


def test_stake_unsigned_refused(client: TestClient) -> None:
    r = client.post("/v1/governance/stake", json={"staker_address": "0x" + "11" * 20, "amount": 1000, "lock_period_days": 30})
    assert r.status_code == 403


def test_stake_wrong_signer_refused(client: TestClient) -> None:
    real = keys.PrivateKey(b"\x01" * 32)
    forger = keys.PrivateKey(b"\x02" * 32)
    body = {"staker_address": real.public_key.to_checksum_address(), "amount": 1000, "lock_period_days": 30}
    signed = dict(body)
    signed["signature"] = _sign(forger, body)
    r = client.post("/v1/governance/stake", json=signed)
    assert r.status_code == 403


def test_stake_signed_accepted(client: TestClient) -> None:
    staker = keys.PrivateKey(b"\x01" * 32)
    body = {"staker_address": staker.public_key.to_checksum_address(), "amount": 1000, "lock_period_days": 30}
    unsigned = {k: v for k, v in StakeRequest(**body).model_dump(mode="json").items() if k != "signature"}
    signed = dict(body)
    signed["signature"] = _sign(staker, unsigned)
    r = client.post("/v1/governance/stake", json=signed)
    assert r.status_code == 200, r.text


def test_delegate_unsigned_refused(client: TestClient) -> None:
    r = client.post(
        "/v1/governance/delegate",
        json={"delegator_address": "0x" + "11" * 20, "delegate_address": "0x" + "22" * 20, "amount": 1},
    )
    assert r.status_code == 403


def test_vote_unsigned_refused(client: TestClient, proposal_id: str) -> None:
    r = client.post(
        "/v1/governance/votes", json={"proposal_id": proposal_id, "voter_id": "0x" + "33" * 20, "vote_type": "for"}
    )
    assert r.status_code == 403


def test_vote_client_supplied_power_ignored(client: TestClient, proposal_id: str) -> None:
    """The repro: a self-reported million-vote weight must not survive."""
    voter = keys.PrivateKey(b"\x03" * 32)
    body = {
        "proposal_id": proposal_id,
        "voter_id": "0x" + "33" * 20,
        "voter_address": voter.public_key.to_checksum_address(),
        "vote_type": "for",
        "voting_power": 1000000,
    }
    body["signature"] = _sign(voter, body)
    r = client.post("/v1/governance/votes", json=body)
    assert r.status_code == 200, r.text
    power = r.json().get("voting_power") or r.json().get("voting_power_used")
    assert float(power or 0) < 1000, f"client power survived: {power}"


def test_double_vote_rejected(client: TestClient, proposal_id: str) -> None:
    voter = keys.PrivateKey(b"\x04" * 32)
    body = {
        "proposal_id": proposal_id,
        "voter_id": "0x" + "44" * 20,
        "voter_address": voter.public_key.to_checksum_address(),
        "vote_type": "for",
    }
    body["signature"] = _sign(voter, body)
    assert client.post("/v1/governance/votes", json=body).status_code == 200
    again = client.post("/v1/governance/votes", json=body)
    assert again.status_code in (400, 409, 500), again.status_code
    assert "already voted" in again.text or "not active" in again.text


def test_close_unsigned_refused(client: TestClient, proposal_id: str) -> None:
    r = client.post(f"/v1/governance/proposals/{proposal_id}/close", json={})
    assert r.status_code == 403


def test_execute_unsigned_refused(client: TestClient, proposal_id: str) -> None:
    r = client.post(f"/v1/governance/proposals/{proposal_id}/execute", json={})
    assert r.status_code == 403
