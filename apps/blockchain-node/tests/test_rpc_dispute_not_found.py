"""Unknown dispute id must answer 404 on the evidence and votes routes (RPC-DISPUTE-EVIDENCE-1).

The service layer returns ``{"success": False, "error": "Dispute N not
found"}`` for an unknown id. ``get_dispute`` already maps that to 404; the
evidence and votes readers raised a blanket 500, so an unknown dispute id
answered 500. The shared ``_raise_for_failed_dispute_call`` helper now maps
"not found" to 404 and keeps any other failure at 500.
"""

from __future__ import annotations

import asyncio

import pytest
from fastapi import HTTPException

import aitbc_chain.rpc.disputes as disputes


def _run(coro):
    return asyncio.run(coro)


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


def test_votes_known_id_returns_list(monkeypatch):
    def _ok(dispute_id: int):
        return {
            "success": True,
            "votes": [
                {
                    "dispute_id": dispute_id,
                    "votes": [{"arbitrator": "0x0000000000000000000000000000000000000002"}],
                }
            ],
        }

    monkeypatch.setattr(disputes.dispute_resolution_service, "get_arbitration_votes", _ok)
    result = _run(disputes.get_arbitration_votes(7))
    assert len(result) == 1
