"""AUDIT-DISPUTE-REVOKE-FLAG-1 (#2524): the authorize route must refuse
``authorized=false`` instead of silently granting.

The CLI previously posted ``authorized=false`` to /arbitrators/authorize
on --revoke; the handler ignored the flag and granted anyway. The route
now answers 400 pointing at /arbitrators/revoke, after authentication.
"""

from __future__ import annotations

import pytest
from fastapi import HTTPException, Request
from pydantic import BaseModel

import aitbc_chain.rpc.disputes as disputes
from aitbc_chain.models.dispute import AuthorizeArbitratorRequest

OWNER = "0x" + "11" * 20
ARB = "0x" + "22" * 20


class _Req(BaseModel):
    arbitrator_address: str
    authorized: bool
    owner_signature: str | None = None


def _call(authorized: bool):
    request = AuthorizeArbitratorRequest(arbitrator_address=ARB, authorized=authorized, owner_signature="0xsig")
    http_request = Request({"type": "http", "headers": [], "method": "POST", "path": "/"})
    return disputes.authorize_arbitrator(request, http_request, None)


@pytest.fixture
def authed(monkeypatch):
    monkeypatch.setattr(disputes, "get_authenticated_address", lambda *a, **kw: OWNER)


def test_authorized_false_is_refused(authed, monkeypatch):
    called = []
    monkeypatch.setattr(
        disputes.dispute_resolution_service,
        "authorize_arbitrator",
        lambda **kw: called.append(kw) or {"success": True},
    )
    with pytest.raises(HTTPException) as excinfo:
        _call(False)
    assert excinfo.value.status_code == 400
    assert "revoke" in str(excinfo.value.detail)
    assert called == []


def test_authorized_true_reaches_service(authed, monkeypatch):
    seen = {}

    def _fake(**kw):
        seen.update(kw)
        return {"success": True, "status": "authorized", "message": "ok"}

    monkeypatch.setattr(disputes.dispute_resolution_service, "authorize_arbitrator", _fake)
    resp = _call(True)
    assert resp.status == "authorized"
    assert seen["arbitrator_address"] == ARB
    assert seen["owner_address"] == OWNER
