"""Unit tests for escrow agent_id binding helpers."""

from __future__ import annotations

import pytest
from fastapi import HTTPException

import aitbc_chain.rpc.escrow_routes as escrow_routes
from aitbc_chain.models import Escrow


@pytest.mark.unit
def test_optional_agent_binding_parses():
    buyer, provider = escrow_routes._optional_agent_binding({"buyer_agent_id": " agent-a ", "provider_agent_id": "agent-b"})
    assert buyer == "agent-a"
    assert provider == "agent-b"


@pytest.mark.unit
def test_optional_agent_binding_rejects_empty():
    with pytest.raises(HTTPException) as exc:
        escrow_routes._optional_agent_binding({"buyer_agent_id": "  "})
    assert exc.value.status_code == 400


@pytest.mark.unit
def test_stored_agent_binding_conflict():
    row = Escrow(
        job_id="j1",
        chain_id="c1",
        buyer="0x" + "1" * 40,
        provider="0x" + "2" * 40,
        amount=1,
        buyer_agent_id="bound-buyer",
    )
    with pytest.raises(HTTPException) as exc:
        escrow_routes._check_stored_agent_binding(row, "other-buyer", None)
    assert exc.value.status_code == 409
