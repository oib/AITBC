"""DISPUTE-FILE-VALIDATE-1 (#2288): dispute file must reject bad input with 4xx.

``POST /rpc/disputes/file`` accepted any ``agreement_id`` (including
negatives) and let ``DisputeType(value)`` raise inside the contract,
surfacing as HTTP 500. The request model now validates ``dispute_type``
against the enum (422) and ``agreement_id >= 0``; the route maps any
contract-level "not a valid DisputeType" failure to 400 for callers that
bypass model validation.
"""

from __future__ import annotations

import pytest
from fastapi import HTTPException
from pydantic import ValidationError

import aitbc_chain.rpc.disputes as disputes
from aitbc_chain.models.dispute import FileDisputeRequest


def _request(**overrides) -> FileDisputeRequest:
    base = {
        "agreement_id": 1,
        "respondent": "0x" + "bb" * 20,
        "dispute_type": "Payment",
        "reason": "test",
        "evidence_hash": "0x" + "00" * 32,
    }
    base.update(overrides)
    return FileDisputeRequest(**base)


def test_invalid_dispute_type_rejected_at_model():
    with pytest.raises(ValidationError) as excinfo:
        _request(dispute_type="non_delivery")
    assert "dispute_type" in str(excinfo.value)
    assert "Performance" in str(excinfo.value)


def test_negative_agreement_id_rejected_at_model():
    with pytest.raises(ValidationError):
        _request(agreement_id=-1)


def test_zero_agreement_id_accepted():
    assert _request(agreement_id=0).agreement_id == 0


def test_all_valid_dispute_types_accepted():
    for t in ("Performance", "Payment", "ServiceQuality", "Availability", "Other"):
        assert _request(dispute_type=t).dispute_type == t


def test_route_maps_contract_enum_error_to_400(monkeypatch):
    """A service-level DisputeType ValueError (unvalidated caller) is a
    client error, not a 500."""
    monkeypatch.setattr(
        disputes,
        "get_authenticated_address",
        lambda request, credentials=None: "0x" + "aa" * 20,
    )

    def _boom(**kwargs):
        return {"success": False, "error": "'non_delivery' is not a valid DisputeType"}

    monkeypatch.setattr(disputes.dispute_resolution_service, "file_dispute", _boom)
    with pytest.raises(HTTPException) as excinfo:
        disputes.file_dispute(_request(), None, None)
    assert excinfo.value.status_code == 400


def test_route_other_failure_stays_500(monkeypatch):
    monkeypatch.setattr(
        disputes,
        "get_authenticated_address",
        lambda request, credentials=None: "0x" + "aa" * 20,
    )

    def _boom(**kwargs):
        return {"success": False, "error": "contract backend unavailable"}

    monkeypatch.setattr(disputes.dispute_resolution_service, "file_dispute", _boom)
    with pytest.raises(HTTPException) as excinfo:
        disputes.file_dispute(_request(), None, None)
    assert excinfo.value.status_code == 500
