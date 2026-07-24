"""Unit tests for aitbc.agent_economics liquidation (v0.13.0 §A2)."""

from __future__ import annotations

from decimal import Decimal

import pytest

from aitbc.agent_economics import (
    BondStatus,
    LiquidationError,
    LiquidationReason,
    LiquidationStatus,
    OffboardingStatus,
    PerformanceBond,
    ProviderOffboarding,
    liquidate_bond,
    offboard_provider,
)


def test_liquidate_bond() -> None:
    bond = PerformanceBond(
        bond_id="b1",
        agent_id="agent-a",
        amount=Decimal("100"),
        token="AITBC",
    )
    bond.activate()
    event = liquidate_bond(
        bond,
        event_id="l1",
        reason=LiquidationReason.SLA_VIOLATION,
        amount=Decimal("50"),
    )
    assert bond.status == BondStatus.LIQUIDATED
    assert event.status == LiquidationStatus.EXECUTED
    assert event.amount == Decimal("50")


def test_liquidate_bond_exceeds_amount() -> None:
    bond = PerformanceBond(
        bond_id="b1",
        agent_id="agent-a",
        amount=Decimal("100"),
        token="AITBC",
    )
    bond.activate()
    with pytest.raises(LiquidationError):
        liquidate_bond(
            bond,
            event_id="l1",
            reason=LiquidationReason.FRAUD,
            amount=Decimal("101"),
        )


def test_offboard_provider() -> None:
    bond = PerformanceBond(
        bond_id="b1",
        agent_id="agent-a",
        amount=Decimal("100"),
        token="AITBC",
    )
    bond.activate()
    event = liquidate_bond(
        bond,
        event_id="l1",
        reason=LiquidationReason.INSUFFICIENT_COLLATERAL,
    )
    offboarding = offboard_provider(event, "ob1")
    assert offboarding.status == OffboardingStatus.IN_PROGRESS
    assert offboarding.agent_id == "agent-a"


def test_provider_offboarding_complete() -> None:
    offboarding = ProviderOffboarding(
        offboarding_id="ob1",
        agent_id="agent-a",
    )
    offboarding.start()
    offboarding.complete()
    assert offboarding.status == OffboardingStatus.COMPLETED
    assert offboarding.resources_released is True


def test_liquidation_event_validation() -> None:
    with pytest.raises(ValueError):
        from aitbc.agent_economics import LiquidationEvent

        LiquidationEvent(
            event_id="l1",
            bond_id="b1",
            agent_id="agent-a",
            reason=LiquidationReason.FRAUD,
            amount=Decimal("-1"),
        )
