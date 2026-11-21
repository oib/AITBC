"""Tests for #2387: shared dispute state across processes/workers.

``aitbc-blockchain-rpc`` runs ``uvicorn --workers 2``; the dispute store
must live in a file beside chain.db (flock-serialized) so both workers —
and restarts — see the same disputes. ``AITBC_DISPUTE_STATE_FILE=memory``
(or an explicit ``state_path="memory"``) keeps the legacy per-process
behaviour for tests/dev.
"""

from __future__ import annotations

import json

import pytest

from aitbc_chain.contracts.dispute_resolution import DisputeResolutionContract, DisputeStatus

ARB = "0x1111111111111111111111111111111111111111"  # placeholder arbitrator (env unset in tests)
PARTY_A = "0xF1C83cd90e4d33F35BE73Dd57CaBa21Ea52D4584"
PARTY_B = "0x4A5b3bf95aa06072c568Cfcb7392b4e86608B5D2"


@pytest.fixture()
def state_file(tmp_path):
    return tmp_path / "disputes.json"


def _file_dispute(contract: DisputeResolutionContract) -> int:
    result = contract.file_dispute(
        agreement_id=0,
        respondent=PARTY_B,
        dispute_type="Payment",
        reason="test",
        evidence_hash="0xabc",
        sender_address=PARTY_A,
    )
    assert result["success"] is True
    return int(result["dispute_id"])


def test_second_instance_sees_filed_dispute(state_file):
    """Simulates the second uvicorn worker: same state file, fresh object."""
    worker_a = DisputeResolutionContract(state_path=state_file)
    dispute_id = _file_dispute(worker_a)

    worker_b = DisputeResolutionContract(state_path=state_file)
    got = worker_b.get_dispute(dispute_id)
    assert got["success"] is True
    assert got["dispute"]["agreement_id"] == 0
    assert got["dispute"]["initiator"] == PARTY_A


def test_evidence_and_votes_shared_across_instances(state_file):
    worker_a = DisputeResolutionContract(state_path=state_file)
    dispute_id = _file_dispute(worker_a)

    worker_b = DisputeResolutionContract(state_path=state_file)
    ev = worker_b.submit_evidence(
        dispute_id=dispute_id,
        evidence_type="transcript",
        evidence_data="log",
        submitter_address=PARTY_A,
        evidence_hash="0xfeedface",
    )
    assert ev["success"] is True

    # worker A sees worker B's evidence
    listed = worker_a.get_dispute_evidence(dispute_id)
    assert listed["count"] == 1
    assert listed["evidence"][0]["evidence_hash"] == "0xfeedface"

    vote = worker_a.submit_arbitration_vote(
        dispute_id=dispute_id,
        vote_in_favor_of_initiator=True,
        confidence=90,
        reasoning="conclusive",
        arbitrator_address=ARB,
    )
    assert vote["success"] is True

    # worker B sees the vote and the arbitration_in_progress status
    votes = worker_b.get_arbitration_votes(dispute_id)
    assert votes["count"] == 1
    status = worker_b.get_dispute(dispute_id)["dispute"]["status"]
    assert status == DisputeStatus.ARBITRATION_IN_PROGRESS.value or status == DisputeStatus.ARBITRATION_IN_PROGRESS


def test_dispute_ids_unique_across_instances(state_file):
    """Counters persist — two workers can't mint the same dispute_id."""
    worker_a = DisputeResolutionContract(state_path=state_file)
    first = _file_dispute(worker_a)
    worker_b = DisputeResolutionContract(state_path=state_file)
    second = _file_dispute(worker_b)
    assert second == first + 1
    assert worker_a.get_dispute(second)["success"] is True


def test_state_survives_new_process_equivalent(state_file):
    """A fresh instance (post-restart) loads persisted disputes."""
    worker_a = DisputeResolutionContract(state_path=state_file)
    dispute_id = _file_dispute(worker_a)
    reloaded = DisputeResolutionContract(state_path=state_file)
    assert reloaded.get_dispute(dispute_id)["success"] is True


def test_memory_mode_isolated(tmp_path, monkeypatch):
    monkeypatch.setenv("AITBC_DISPUTE_STATE_FILE", "memory")
    a = DisputeResolutionContract()
    b = DisputeResolutionContract()
    dispute_id = _file_dispute(a)
    assert b.get_dispute(dispute_id)["success"] is False


def test_explicit_memory_state_path_isolated(state_file):
    a = DisputeResolutionContract(state_path="memory")
    b = DisputeResolutionContract(state_path=state_file)
    dispute_id = _file_dispute(a)
    assert b.get_dispute(dispute_id)["success"] is False
    assert not state_file.exists()


def test_env_state_file_path_used(tmp_path, monkeypatch):
    target = tmp_path / "env-disputes.json"
    monkeypatch.setenv("AITBC_DISPUTE_STATE_FILE", str(target))
    a = DisputeResolutionContract()
    dispute_id = _file_dispute(a)
    b = DisputeResolutionContract()
    assert b.get_dispute(dispute_id)["success"] is True


def test_corrupt_state_file_falls_back_to_memory(state_file, caplog):
    state_file.write_text("{not json")
    contract = DisputeResolutionContract(state_path=state_file)
    dispute_id = _file_dispute(contract)
    # mutation still works and rewrites a valid file
    assert contract.get_dispute(dispute_id)["success"] is True
    data = json.loads(state_file.read_text())
    assert str(dispute_id) in data["disputes"]


def test_vote_dedup_rejects_second_vote(state_file):
    contract = DisputeResolutionContract(state_path=state_file)
    dispute_id = _file_dispute(contract)
    kwargs = {
        "dispute_id": dispute_id,
        "vote_in_favor_of_initiator": True,
        "confidence": 90,
        "reasoning": "first",
        "arbitrator_address": ARB,
    }
    assert contract.submit_arbitration_vote(**kwargs)["success"] is True
    second = contract.submit_arbitration_vote(**kwargs)
    assert second["success"] is False
    assert "Duplicate" in second["error"]
    # a changed verdict is still allowed (vote revision)
    changed = contract.submit_arbitration_vote(**{**kwargs, "vote_in_favor_of_initiator": False})
    assert changed["success"] is True
    assert contract.get_arbitration_votes(dispute_id)["count"] == 2


def test_evidence_hash_preserved(state_file):
    contract = DisputeResolutionContract(state_path=state_file)
    dispute_id = _file_dispute(contract)
    contract.submit_evidence(
        dispute_id=dispute_id,
        evidence_type="receipt",
        evidence_data="data",
        submitter_address=PARTY_B,
        evidence_hash="0xdeadbeef",
    )
    evidence = contract.get_dispute_evidence(dispute_id)["evidence"]
    assert evidence[0]["evidence_hash"] == "0xdeadbeef"
