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


def _stake_body(staker: keys.PrivateKey, **over) -> dict:
    import time

    body = {
        "staker_address": staker.public_key.to_checksum_address(),
        "amount": 1000,
        "lock_period_days": 30,
        "timestamp": time.time(),
    }
    body.update(over)
    return body


def _signed_stake(staker: keys.PrivateKey, **over) -> dict:
    body = _stake_body(staker, **over)
    unsigned = {k: v for k, v in StakeRequest(**body).model_dump(mode="json").items() if k != "signature"}
    body["signature"] = _sign(staker, unsigned)
    return body


def test_stake_unsigned_refused(client: TestClient) -> None:
    r = client.post("/v1/governance/stake", json=_stake_body(keys.PrivateKey(b"\x11" * 32)))
    assert r.status_code == 403


def test_stake_wrong_signer_refused(client: TestClient) -> None:
    real = keys.PrivateKey(b"\x01" * 32)
    forger = keys.PrivateKey(b"\x02" * 32)
    body = _stake_body(real)
    unsigned = {k: v for k, v in StakeRequest(**body).model_dump(mode="json").items() if k != "signature"}
    body["signature"] = _sign(forger, unsigned)
    r = client.post("/v1/governance/stake", json=body)
    assert r.status_code == 403


def test_stake_signed_accepted(client: TestClient) -> None:
    body = _signed_stake(keys.PrivateKey(b"\x01" * 32))
    r = client.post("/v1/governance/stake", json=body)
    assert r.status_code == 200, r.text


def test_replayed_stake_body_refused(client: TestClient) -> None:
    """A captured signed body may not run twice."""
    staker = keys.PrivateKey(b"\x05" * 32)
    body = _signed_stake(staker)
    assert client.post("/v1/governance/stake", json=body).status_code == 200
    replay = client.post("/v1/governance/stake", json=body)
    assert replay.status_code == 403, replay.text


def test_stale_stake_timestamp_refused(client: TestClient) -> None:
    staker = keys.PrivateKey(b"\x06" * 32)
    body = _signed_stake(staker, timestamp=1.0)
    r = client.post("/v1/governance/stake", json=body)
    assert r.status_code == 403


def test_delegate_unsigned_refused(client: TestClient) -> None:
    import time

    r = client.post(
        "/v1/governance/delegate",
        json={
            "delegator_address": "0x" + "11" * 20,
            "delegate_address": "0x" + "22" * 20,
            "amount": 1,
            "timestamp": time.time(),
        },
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


def test_signer_who_is_not_the_voter_refused(client: TestClient, proposal_id: str) -> None:
    """voter_id naming a different address than the signer is refused."""
    signer = keys.PrivateKey(b"\x07" * 32)
    victim = keys.PrivateKey(b"\x08" * 32)
    body = {
        "proposal_id": proposal_id,
        "voter_address": signer.public_key.to_checksum_address(),
        "voter_id": victim.public_key.to_checksum_address(),
        "vote_type": "for",
    }
    body["signature"] = _sign(signer, body)
    r = client.post("/v1/governance/votes", json=body)
    assert r.status_code == 403


def test_one_signer_cannot_vote_twice_via_voter_id(client: TestClient, proposal_id: str) -> None:
    """First vote goes through; a second attempt is refused either by binding
    (voter_id != signer) or by the bound-actor dedup."""
    voter = keys.PrivateKey(b"\x09" * 32)
    body = {
        "proposal_id": proposal_id,
        "voter_address": voter.public_key.to_checksum_address(),
        "vote_type": "for",
    }
    body["signature"] = _sign(voter, body)
    assert client.post("/v1/governance/votes", json=body).status_code == 200

    sneaky = dict(body)
    sneaky["voter_id"] = "0x" + "ee" * 20
    sneaky["signature"] = _sign(voter, sneaky)
    assert client.post("/v1/governance/votes", json=sneaky).status_code == 403

    again = client.post("/v1/governance/votes", json=body)
    assert again.status_code == 400 and "already voted" in again.text


def test_proposer_id_not_the_signer_refused(client: TestClient) -> None:
    from datetime import UTC, datetime, timedelta

    signer = keys.PrivateKey(b"\x0b" * 32)
    now = datetime.now(UTC)
    body = {
        "proposer_address": signer.public_key.to_checksum_address(),
        "proposer_id": "0x" + "cc" * 20,
        "title": "t",
        "description": "d",
        "voting_starts": now.isoformat(),
        "voting_ends": (now + timedelta(hours=4)).isoformat(),
    }
    body["signature"] = _sign(signer, body)
    r = client.post("/v1/governance/proposals", json=body)
    assert r.status_code == 403
