"""Unit tests for agent spend policy (AGENT-SPEND-A-1)."""

from __future__ import annotations

from decimal import Decimal

import pytest

from coordinator_api.contexts.agent_identity.domain.spend_policy import (
    PERM_WALLET_EXECUTE,
    assert_wallet_permission,
    operation_from_tx_data,
)
from coordinator_api.contexts.agent_identity.services.spend_session_service import SpendSessionService


@pytest.mark.unit
def test_operation_from_tx_data_defaults():
    assert operation_from_tx_data(None) == PERM_WALLET_EXECUTE
    assert operation_from_tx_data({"op": "escrow.fund"}) == "escrow.fund"


@pytest.mark.unit
def test_assert_wallet_permission_empty_list_legacy():
    assert_wallet_permission([], PERM_WALLET_EXECUTE)


@pytest.mark.unit
def test_assert_wallet_permission_enforces_when_set():
    assert_wallet_permission(["wallet.execute"], "wallet.execute")
    with pytest.raises(ValueError, match="Insufficient permissions"):
        assert_wallet_permission(["escrow.fund"], "wallet.execute")


@pytest.mark.unit
def test_spend_session_consume_cap(db_session):
    from coordinator_api.contexts.agent_identity.domain.agent_identity import AgentIdentity

    db_session.add(AgentIdentity(agent_id="agent-spend-1", owner_address="0x" + "11" * 20))
    db_session.commit()
    svc = SpendSessionService(db_session)
    row = svc.create_session(
        "agent-spend-1",
        "0x" + "11" * 20,
        1000,
        Decimal("10"),
        ["wallet.execute"],
        None,
    )
    svc.consume(row.id, "agent-spend-1", 1000, Decimal("3"), "wallet.execute")
    svc.consume(row.id, "agent-spend-1", 1000, Decimal("7"), "wallet.execute")
    with pytest.raises(ValueError, match="cap exceeded"):
        svc.consume(row.id, "agent-spend-1", 1000, Decimal("0.01"), "wallet.execute")
