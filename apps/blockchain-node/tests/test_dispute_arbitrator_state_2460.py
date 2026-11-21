"""Tests for #2460: arbitrator state separation — env rotation must revoke.

Pre-fix, ``_save_state`` serialized the whole effective ``self.arbitrators``
set, so env-seeded and placeholder entries became indistinguishable from
owner grants: removing an address from ``AITBC_DISPUTE_ARBITRATORS`` never
revoked it, and a mutation with env unset persisted the placeholder trio,
leaving a later real arbitrator unable to reach quorum.

Now only owner-granted entries persist under ``granted_arbitrators``; the
effective set is recomputed at every load (env ∪ granted, else granted,
else placeholders) and ``revoke_arbitrator`` gives the owner a signed
removal path.
"""

from __future__ import annotations

import json

import pytest
from eth_keys import keys
from eth_utils import keccak, to_checksum_address

from aitbc_chain.contracts.dispute_resolution import DisputeResolutionContract, DisputeStatus

# Canonical (EIP-55) forms — the contract stores arbitrators checksummed.
ARB_A = to_checksum_address("0x" + "aa" * 20)
ARB_B = to_checksum_address("0x" + "bb" * 20)
ARB_C = to_checksum_address("0x" + "cc" * 20)
OWNER_KEY = keys.PrivateKey(b"\x07" * 32)
OWNER_ADDR = OWNER_KEY.public_key.to_checksum_address()
OTHER_KEY = keys.PrivateKey(b"\x09" * 32)
OTHER_ADDR = OTHER_KEY.public_key.to_checksum_address()


def _sign(priv_key, message_data: dict) -> str:
    message = json.dumps(message_data, sort_keys=True, separators=(",", ":")).encode()
    return priv_key.sign_msg_hash(keccak(message)).to_hex()


def _auth_sig(priv_key, arbitrator_address: str, reputation_score: int = 90) -> str:
    return _sign(
        priv_key,
        {
            "action": "authorize_arbitrator",
            "arbitrator_address": arbitrator_address,
            "reputation_score": reputation_score,
        },
    )


def _revoke_sig(priv_key, arbitrator_address: str) -> str:
    return _sign(priv_key, {"action": "revoke_arbitrator", "arbitrator_address": arbitrator_address})


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch):
    monkeypatch.delenv("AITBC_DISPUTE_ARBITRATORS", raising=False)
    monkeypatch.delenv("AITBC_DISPUTE_STATE_FILE", raising=False)


def _contract(tmp_path, name="disputes.json"):
    return DisputeResolutionContract(state_path=tmp_path / name)


def _file(contract):
    result = contract.file_dispute(
        agreement_id=0,
        respondent="0x" + "dd" * 20,
        dispute_type="Payment",
        reason="r",
        evidence_hash="0xabc",
        sender_address="0x" + "ee" * 20,
    )
    assert result["success"] is True
    return result


def _file_state(tmp_path, name="disputes.json"):
    return json.loads((tmp_path / name).read_text())


# --- env rotation revokes ---


def test_env_rotation_revokes_removed_arbitrator(tmp_path, monkeypatch):
    monkeypatch.setenv("AITBC_DISPUTE_ARBITRATORS", f"{ARB_A}:90, {ARB_B}:85")
    c1 = _contract(tmp_path)
    assert set(c1.arbitrators) == {ARB_A, ARB_B}
    _file(c1)  # persist state

    # Rotate env down to A only — B must lose authorization on reload.
    monkeypatch.setenv("AITBC_DISPUTE_ARBITRATORS", f"{ARB_A}:90")
    c2 = _contract(tmp_path)
    assert ARB_B not in c2.arbitrators
    assert c2.arbitrators == {ARB_A: 90}


def test_env_unset_after_rotation_falls_back_to_granted_or_placeholders(tmp_path, monkeypatch):
    monkeypatch.setenv("AITBC_DISPUTE_ARBITRATORS", f"{ARB_A}:90")
    c1 = _contract(tmp_path)
    _file(c1)

    monkeypatch.delenv("AITBC_DISPUTE_ARBITRATORS")
    c2 = _contract(tmp_path)
    # No grants, no env → historical placeholders; the env-seeded A is gone.
    assert ARB_A not in c2.arbitrators
    assert c2.arbitrators == DisputeResolutionContract._PLACEHOLDER_ARBITRATORS


# --- placeholders never persist ---


def test_env_unset_mutation_does_not_persist_placeholders(tmp_path):
    c1 = _contract(tmp_path)
    assert set(c1.arbitrators) == set(DisputeResolutionContract._PLACEHOLDER_ARBITRATORS)
    _file(c1)

    data = _file_state(tmp_path)
    assert data["granted_arbitrators"] == {}
    # Legacy key must not smuggle the effective set back in either.
    assert "arbitrators" not in data


def test_placeholders_do_not_block_quorum_after_env_configured(tmp_path, monkeypatch):
    # Mutation with env unset used to serialize the placeholder trio; a
    # later env config then left 4 effective arbitrators and quorum could
    # never complete. Now the file stays clean.
    c1 = _contract(tmp_path)
    _file(c1)

    monkeypatch.setenv("AITBC_DISPUTE_ARBITRATORS", f"{ARB_A}:90")
    c2 = _contract(tmp_path)
    assert c2.arbitrators == {ARB_A: 90}

    did = _file(c2)["dispute_id"]
    vote = c2.submit_arbitration_vote(did, True, 80, "ok", ARB_A)
    assert vote["success"], vote
    assert vote["resolved"] is True
    status = c2.get_dispute(did)["dispute"]["status"]
    assert status in (DisputeStatus.RESOLVED, "resolved")


# --- owner-granted set persists and merges with env ---


def test_granted_arbitrator_persists_and_survives_env_unset(tmp_path):
    c1 = _contract(tmp_path)
    c1.set_owner(OWNER_ADDR)
    auth = c1.authorize_arbitrator(ARB_A, 90, OWNER_ADDR, _auth_sig(OWNER_KEY, ARB_A))
    assert auth["success"], auth
    _file(c1)

    data = _file_state(tmp_path)
    assert data["granted_arbitrators"] == {ARB_A: 90}

    # Env unset + grant present → effective set is the grant, not placeholders.
    c2 = _contract(tmp_path)
    assert c2.arbitrators == {ARB_A: 90}
    assert c2._owner == OWNER_ADDR.lower()


def test_env_and_granted_merge_with_env_winning(tmp_path, monkeypatch):
    c1 = _contract(tmp_path)
    c1.set_owner(OWNER_ADDR)
    c1.authorize_arbitrator(ARB_A, 90, OWNER_ADDR, _auth_sig(OWNER_KEY, ARB_A))
    _file(c1)

    # Env adds B and overrides A's score.
    monkeypatch.setenv("AITBC_DISPUTE_ARBITRATORS", f"{ARB_A}:50, {ARB_B}:70")
    c2 = _contract(tmp_path)
    assert c2.arbitrators == {ARB_A: 50, ARB_B: 70}


# --- revoke_arbitrator ---


def test_revoke_removes_grant_and_blocks_quorum(tmp_path):
    c = _contract(tmp_path)
    c.set_owner(OWNER_ADDR)
    c.authorize_arbitrator(ARB_A, 90, OWNER_ADDR, _auth_sig(OWNER_KEY, ARB_A))
    c.authorize_arbitrator(ARB_B, 85, OWNER_ADDR, _auth_sig(OWNER_KEY, ARB_B, 85))
    did = _file(c)["dispute_id"]

    rev = c.revoke_arbitrator(ARB_B, OWNER_ADDR, _revoke_sig(OWNER_KEY, ARB_B))
    assert rev["success"], rev
    assert rev["was_granted"] is True
    assert ARB_B not in c.arbitrators
    assert ARB_B not in c._granted_arbitrators

    # Persisted state no longer carries the grant.
    data = _file_state(tmp_path)
    assert data["granted_arbitrators"] == {ARB_A: 90}

    # A fresh instance agrees, and a stray vote from the revoked arb fails.
    c2 = _contract(tmp_path)
    assert ARB_B not in c2.arbitrators
    vote = c2.submit_arbitration_vote(did, True, 80, "sneaky", ARB_B)
    assert vote["success"] is False


def test_revoke_rejects_wrong_owner_and_bad_signature(tmp_path):
    c = _contract(tmp_path)
    c.set_owner(OWNER_ADDR)
    c.authorize_arbitrator(ARB_A, 90, OWNER_ADDR, _auth_sig(OWNER_KEY, ARB_A))

    wrong_owner = c.revoke_arbitrator(ARB_A, OTHER_ADDR, _revoke_sig(OTHER_KEY, ARB_A))
    assert wrong_owner["success"] is False
    assert "owner" in wrong_owner["message"].lower()

    no_sig = c.revoke_arbitrator(ARB_A, OWNER_ADDR, None)
    assert no_sig["success"] is False
    assert "signature" in no_sig["message"].lower()

    bad_sig = c.revoke_arbitrator(ARB_A, OWNER_ADDR, "0x" + "cd" * 65)
    assert bad_sig["success"] is False
    assert "signature" in bad_sig["message"].lower()

    # An authorize-action signature must not replay as a revoke.
    replay = c.revoke_arbitrator(ARB_A, OWNER_ADDR, _auth_sig(OWNER_KEY, ARB_A))
    assert replay["success"] is False
    assert ARB_A in c.arbitrators


def test_revoke_without_owner_set_fails(tmp_path):
    c = _contract(tmp_path)
    result = c.revoke_arbitrator(ARB_A, OWNER_ADDR, _revoke_sig(OWNER_KEY, ARB_A))
    assert result["success"] is False
    assert "owner" in result["message"].lower()


def test_revoke_of_env_only_arbitrator_keeps_env_authority(tmp_path, monkeypatch):
    monkeypatch.setenv("AITBC_DISPUTE_ARBITRATORS", f"{ARB_A}:90")
    c = _contract(tmp_path)
    c.set_owner(OWNER_ADDR)
    # ARB_A was never granted — revoke is a no-op grant-wise but env still rules.
    rev = c.revoke_arbitrator(ARB_A, OWNER_ADDR, _revoke_sig(OWNER_KEY, ARB_A))
    assert rev["success"], rev
    assert rev["was_granted"] is False
    assert rev["note"]
    assert ARB_A in c.arbitrators


def test_revoke_signature_must_match_address(tmp_path):
    """Signing a different address must not authorize the revoke."""
    c = _contract(tmp_path)
    c.set_owner(OWNER_ADDR)
    c.authorize_arbitrator(ARB_A, 90, OWNER_ADDR, _auth_sig(OWNER_KEY, ARB_A))
    sig = _revoke_sig(OWNER_KEY, ARB_B)
    result = c.revoke_arbitrator(ARB_A, OWNER_ADDR, sig)
    assert result["success"] is False
    assert ARB_A in c.arbitrators


# --- state integrity round-trip ---


def test_disputes_evidence_votes_survive_reload(tmp_path):
    c1 = _contract(tmp_path)
    c1.set_owner(OWNER_ADDR)
    c1.authorize_arbitrator(ARB_A, 90, OWNER_ADDR, _auth_sig(OWNER_KEY, ARB_A))
    c1.authorize_arbitrator(ARB_B, 85, OWNER_ADDR, _auth_sig(OWNER_KEY, ARB_B, 85))
    c1.authorize_arbitrator(ARB_C, 88, OWNER_ADDR, _auth_sig(OWNER_KEY, ARB_C, 88))
    did = _file(c1)["dispute_id"]
    c1.submit_evidence(dispute_id=did, evidence_type="photo", evidence_data="hash-data", submitter_address="0x" + "ee" * 20)
    c1.submit_arbitration_vote(did, True, 80, "r", ARB_A)
    c1.submit_arbitration_vote(did, True, 80, "r", ARB_B)

    c2 = _contract(tmp_path)
    assert c2.dispute_counter == c1.dispute_counter
    assert c2.evidence_counter == c1.evidence_counter
    assert c2._owner == OWNER_ADDR.lower()
    assert c2._granted_arbitrators == {ARB_A: 90, ARB_B: 85, ARB_C: 88}
    assert c2.arbitrators == c2._granted_arbitrators
    assert len(c2.evidence[did]) == 1
    assert len(c2.votes[did]) == 2
    # Quorum still reachable after reload: one more vote resolves.
    last = c2.submit_arbitration_vote(did, False, 70, "r", ARB_C)
    assert last["success"] and last["resolved"]
