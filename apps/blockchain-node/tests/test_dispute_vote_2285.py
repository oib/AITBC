"""DISPUTE-VOTE-STUB-1 (#2285): the vote RPC must reach the contract.

``submit_arbitration_vote`` used to authenticate and then return a
hardcoded success — votes were silently dropped while reporting
``{"status": "Submitted", "vote_id": 0}`` for nonexistent disputes and
non-arbitrators. It now calls ``dispute_resolution_service`` like its
sibling routes: unknown dispute -> 404, non-arbitrator -> 403, and a
recorded vote carries a real ``vote_id``.
"""

from __future__ import annotations

import pytest
from fastapi import HTTPException
from pydantic import ValidationError

import aitbc_chain.rpc.disputes as disputes
from aitbc_chain.contracts.dispute_resolution import dispute_resolution_contract
from aitbc_chain.models.dispute import SubmitArbitrationVoteRequest

ARBITRATOR = "0x1111111111111111111111111111111111111111"
PLAINTIFF = "0xaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
RESPONDENT = "0xbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"
NON_ARBITRATOR = "0xcccccccccccccccccccccccccccccccccccccccc"


@pytest.fixture
def as_arbitrator(monkeypatch):
    monkeypatch.setattr(disputes, "get_authenticated_address", lambda request, credentials=None: ARBITRATOR)


@pytest.fixture
def filed_dispute():
    result = dispute_resolution_contract.file_dispute(
        agreement_id=1,
        respondent=RESPONDENT,
        dispute_type="Payment",
        reason="test",
        evidence_hash="0x" + "00" * 32,
        sender_address=PLAINTIFF,
    )
    dispute_id = result["dispute_id"]
    yield dispute_id
    dispute_resolution_contract.disputes.pop(dispute_id, None)
    dispute_resolution_contract.evidence.pop(dispute_id, None)
    dispute_resolution_contract.votes.pop(dispute_id, None)


def _request(dispute_id: int, vote: str = "plaintiff", reasoning: str = "because") -> SubmitArbitrationVoteRequest:
    return SubmitArbitrationVoteRequest(dispute_id=dispute_id, vote=vote, reasoning=reasoning)


def test_vote_is_recorded(as_arbitrator, filed_dispute):
    resp = disputes.submit_arbitration_vote(_request(filed_dispute, "plaintiff"), None, None)
    assert resp.status == "Submitted"
    assert resp.vote_id == 0
    votes = dispute_resolution_contract.votes[filed_dispute]
    assert len(votes) == 1
    assert votes[0].arbitrator == ARBITRATOR
    assert votes[0].vote_in_favor_of_initiator is True

    resp2 = disputes.submit_arbitration_vote(_request(filed_dispute, "defendant", "rebuttal"), None, None)
    assert resp2.vote_id == 1
    assert dispute_resolution_contract.votes[filed_dispute][1].vote_in_favor_of_initiator is False


def test_unknown_dispute_is_404(as_arbitrator):
    with pytest.raises(HTTPException) as excinfo:
        disputes.submit_arbitration_vote(_request(999999), None, None)
    assert excinfo.value.status_code == 404


def test_non_arbitrator_is_403(monkeypatch, filed_dispute):
    monkeypatch.setattr(disputes, "get_authenticated_address", lambda request, credentials=None: NON_ARBITRATOR)
    with pytest.raises(HTTPException) as excinfo:
        disputes.submit_arbitration_vote(_request(filed_dispute), None, None)
    assert excinfo.value.status_code == 403


def test_zero_address_still_401(as_arbitrator, monkeypatch):
    monkeypatch.setattr(
        disputes,
        "get_authenticated_address",
        lambda request, credentials=None: "0x0000000000000000000000000000000000000000",
    )
    with pytest.raises(HTTPException) as excinfo:
        disputes.submit_arbitration_vote(_request(1), None, None)
    assert excinfo.value.status_code == 401


def test_invalid_vote_rejected_by_model():
    with pytest.raises(ValidationError):
        _request(1, vote="maybe")
