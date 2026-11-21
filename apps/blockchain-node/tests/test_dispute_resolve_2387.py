"""Tests for #2387 resolve leg: auto-resolve at quorum, escalate on deadline.

- Once every authorized arbitrator has voted, the dispute resolves by
  plurality (latest vote per arbitrator); ties escalate.
- Disputes past ``arbitration_deadline`` escalate on the next state access.
- Closed disputes (resolved/escalated) reject further evidence and votes.
- Record-only: ``winner``/``resolution_reason`` are stored; no funds move.
"""

from __future__ import annotations

import time

import pytest

from aitbc_chain.contracts.dispute_resolution import DisputeResolutionContract, DisputeStatus

ARB1 = "0x1111111111111111111111111111111111111111"
ARB2 = "0x2222222222222222222222222222222222222222"
ARB3 = "0x3333333333333333333333333333333333333333"
PLAINTIFF = "0xaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
RESPONDENT = "0xbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"


@pytest.fixture()
def contract(monkeypatch):
    monkeypatch.delenv("AITBC_DISPUTE_ARBITRATORS", raising=False)
    return DisputeResolutionContract(state_path="memory")


def _file(contract: DisputeResolutionContract) -> int:
    result = contract.file_dispute(
        agreement_id=0,
        respondent=RESPONDENT,
        dispute_type="Payment",
        reason="test",
        evidence_hash="0xabc",
        sender_address=PLAINTIFF,
    )
    assert result["success"] is True
    return int(result["dispute_id"])


def _vote(contract, dispute_id, arbitrator, favor, reasoning="r"):
    return contract.submit_arbitration_vote(
        dispute_id=dispute_id,
        vote_in_favor_of_initiator=favor,
        confidence=80,
        reasoning=reasoning,
        arbitrator_address=arbitrator,
    )


def test_plurality_resolves_for_initiator(contract):
    did = _file(contract)
    assert _vote(contract, did, ARB1, True)["success"] is True
    assert _vote(contract, did, ARB2, True)["success"] is True
    last = _vote(contract, did, ARB3, False)
    assert last["success"] is True
    assert last["resolved"] is True

    dispute = contract.get_dispute(did)["dispute"]
    assert dispute["status"] == DisputeStatus.RESOLVED.value or dispute["status"] == DisputeStatus.RESOLVED
    assert dispute["winner"] == PLAINTIFF
    assert "2-1" in dispute["resolution_reason"]


def test_plurality_resolves_for_respondent(contract):
    did = _file(contract)
    _vote(contract, did, ARB1, False)
    _vote(contract, did, ARB2, False)
    _vote(contract, did, ARB3, True)
    dispute = contract.get_dispute(did)["dispute"]
    assert dispute["winner"] == RESPONDENT


def test_no_resolution_before_quorum(contract):
    did = _file(contract)
    _vote(contract, did, ARB1, True)
    _vote(contract, did, ARB2, True)
    dispute = contract.get_dispute(did)["dispute"]
    assert dispute["status"] in (DisputeStatus.ARBITRATION_IN_PROGRESS, "arbitration_in_progress")
    assert dispute["winner"] is None


def test_tie_escalates(contract, monkeypatch):
    monkeypatch.setenv("AITBC_DISPUTE_ARBITRATORS", f"{ARB1}:90, {ARB2}:85")
    c = DisputeResolutionContract(state_path="memory")
    did = _file(c)
    _vote(c, did, ARB1, True)
    _vote(c, did, ARB2, False)
    dispute = c.get_dispute(did)["dispute"]
    status = dispute["status"]
    assert status in (DisputeStatus.ESCALATED, "escalated")
    assert dispute["is_escalated"] is True


def test_revision_counts_latest_vote(contract):
    did = _file(contract)
    _vote(contract, did, ARB1, True, reasoning="first")
    _vote(contract, did, ARB2, False)
    # ARB1 revises to defendant before quorum completes
    rev = _vote(contract, did, ARB1, False, reasoning="revised")
    assert rev["success"] is True
    _vote(contract, did, ARB3, False)
    dispute = contract.get_dispute(did)["dispute"]
    assert dispute["winner"] == RESPONDENT


def test_deadline_escalates_on_read(contract):
    did = _file(contract)
    _vote(contract, did, ARB1, True)
    contract.disputes[did].arbitration_deadline = int(time.time()) - 1
    dispute = contract.get_dispute(did)["dispute"]
    status = dispute["status"]
    assert status in (DisputeStatus.ESCALATED, "escalated")
    assert dispute["is_escalated"] is True


def test_closed_dispute_rejects_evidence_and_votes(contract):
    did = _file(contract)
    _vote(contract, did, ARB1, True)
    _vote(contract, did, ARB2, True)
    _vote(contract, did, ARB3, True)
    assert contract.get_dispute(did)["dispute"]["status"] in (
        DisputeStatus.RESOLVED,
        "resolved",
    )
    ev = contract.submit_evidence(dispute_id=did, evidence_type="late", evidence_data="x", submitter_address=PLAINTIFF)
    assert ev["success"] is False
    vote = _vote(contract, did, ARB1, False, reasoning="too late")
    assert vote["success"] is False


def test_vote_after_arbitration_deadline_rejected(contract):
    did = _file(contract)
    contract.disputes[did].arbitration_deadline = int(time.time()) - 1
    result = _vote(contract, did, ARB1, True)
    assert result["success"] is False
    assert "deadline" in result["error"].lower()


def test_evidence_after_evidence_deadline_rejected(contract):
    did = _file(contract)
    contract.disputes[did].evidence_deadline = int(time.time()) - 1
    result = contract.submit_evidence(dispute_id=did, evidence_type="late", evidence_data="x", submitter_address=PLAINTIFF)
    assert result["success"] is False
