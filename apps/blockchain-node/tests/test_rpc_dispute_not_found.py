"""Unknown dispute id must answer 404 on the evidence and votes routes (RPC-DISPUTE-EVIDENCE-1).

The service layer returns ``{"success": False, "error": "Dispute N not
found"}`` for an unknown id. ``get_dispute`` already maps that to 404; the
evidence and votes readers raised a blanket 500, so an unknown dispute id
answered 500. The shared ``_raise_for_failed_dispute_call`` helper now maps
"not found" to 404 and keeps any other failure at 500.
"""

from __future__ import annotations

import asyncio
import inspect

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

import aitbc_chain.rpc.dispute_resolution_service as dispute_resolution_service_module
import aitbc_chain.rpc.disputes as disputes
import aitbc_chain.rpc.routers.disputes as disputes_router_module
from aitbc_chain.contracts.dispute_resolution import DisputeResolutionContract, DisputeStatus


def _run(coro):
    return asyncio.run(coro) if inspect.iscoroutine(coro) else coro


@pytest.fixture
def unknown_dispute(monkeypatch):
    def _fake(method):
        def _result(dispute_id: int):
            return {"success": False, "error": f"Dispute {dispute_id} not found"}

        monkeypatch.setattr(disputes.dispute_resolution_service, method, _result)

    return _fake


def test_evidence_unknown_id_is_404(unknown_dispute):
    unknown_dispute("get_dispute_evidence")
    with pytest.raises(HTTPException) as excinfo:
        _run(disputes.get_dispute_evidence(999999))
    assert excinfo.value.status_code == 404
    assert "not found" in str(excinfo.value.detail).lower()


def test_votes_unknown_id_is_404(unknown_dispute):
    unknown_dispute("get_arbitration_votes")
    with pytest.raises(HTTPException) as excinfo:
        _run(disputes.get_arbitration_votes(999999))
    assert excinfo.value.status_code == 404
    assert "not found" in str(excinfo.value.detail).lower()


def test_evidence_other_failure_stays_500(monkeypatch):
    def _boom(dispute_id: int):
        return {"success": False, "error": "contract backend unavailable"}

    monkeypatch.setattr(disputes.dispute_resolution_service, "get_dispute_evidence", _boom)
    with pytest.raises(HTTPException) as excinfo:
        _run(disputes.get_dispute_evidence(7))
    assert excinfo.value.status_code == 500


def test_evidence_known_id_returns_list(monkeypatch):
    def _ok(dispute_id: int):
        return {
            "success": True,
            "evidence": [
                {
                    "evidence_id": 1,
                    "dispute_id": dispute_id,
                    "evidence_hash": "0xabc",
                    "evidence_type": "log",
                    "evidence_data": "frame dump",
                    "submitter": "0x0000000000000000000000000000000000000001",
                    "is_valid": True,
                    "submission_time": 0,
                }
            ],
        }

    monkeypatch.setattr(disputes.dispute_resolution_service, "get_dispute_evidence", _ok)
    result = _run(disputes.get_dispute_evidence(7))
    assert len(result) == 1
    assert result[0].dispute_id == 7


def test_votes_route_exposes_persisted_ballots_after_auto_resolution(tmp_path, monkeypatch):
    """#2751: the votes route must surface each stored ballot, not ``votes: []``.

    The contract returns flat ``asdict`` vote rows; wrapping them with
    ``GetArbitrationVotesResponse(**vote)`` dropped every ballot field into
    the model's ignored extras and left ``votes`` empty. Drive the real
    contract (file-backed, tmp state) through the real router so the wire
    shape is pinned end to end.
    """
    arbitrators = [f"0x{n:040x}" for n in (1, 2, 3)]
    monkeypatch.setenv("AITBC_DISPUTE_ARBITRATORS", ",".join(f"{address}:90" for address in arbitrators))
    state_path = tmp_path / "disputes.json"
    writer = DisputeResolutionContract(state_path=state_path)
    filed = writer.file_dispute(
        agreement_id=0,
        respondent="0x" + "bb" * 20,
        dispute_type="Payment",
        reason="test",
        evidence_hash="0xabc",
        sender_address="0x" + "aa" * 20,
    )
    assert filed["success"] is True
    did = int(filed["dispute_id"])
    reader = DisputeResolutionContract(state_path=state_path)
    monkeypatch.setattr(dispute_resolution_service_module, "dispute_resolution_contract", reader)
    app = FastAPI()
    app.include_router(disputes_router_module.router, prefix="/rpc")
    with TestClient(app) as client:
        route = f"/rpc/disputes/{did}/votes"
        assert client.get(route).json() == []
        ballots = list(zip(arbitrators, (True, True, False), (90, 85, 70), ("first", "second", "third"), strict=False))
        for arbitrator, favor, confidence, reasoning in ballots:
            result = writer.submit_arbitration_vote(did, favor, confidence, reasoning, arbitrator)
            assert result["success"] is True
        assert result["resolved"] is True
        assert reader.get_dispute(did)["dispute"]["status"] == DisputeStatus.RESOLVED
        response = client.get(route)
    assert response.status_code == 200
    rows = response.json()
    assert len(rows) == 3
    for row, (arbitrator, favor, confidence, reasoning) in zip(rows, ballots, strict=True):
        assert row["dispute_id"] == did
        (vote,) = row["votes"]
        assert (vote["arbitrator"], vote["vote_in_favor_of_initiator"], vote["confidence"], vote["reasoning"]) == (
            arbitrator,
            favor,
            confidence,
            reasoning,
        )
        assert vote["dispute_id"] == did and vote["vote_time"] > 0 and vote["is_valid"] is True
