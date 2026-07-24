"""Unit tests for aitbc.agent_economics shared types (v0.11.0 §A2).

Covers budget allocation/release/spend, revenue route validation,
pricing strategy calculations, and on-chain action validation.
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from aitbc.agent_economics import (
    Budget,
    OnChainAction,
    OnChainActionType,
    PricingStrategy,
    PricingStrategyType,
    RevenueRoute,
    RevenueRouteType,
)


def test_budget_available_default_zero() -> None:
    budget = Budget(
        budget_id="b1",
        agent_id="agent-a",
        chain_id="ait-hub",
        token="AITBC",
    )
    assert budget.total == Decimal("0")
    assert budget.allocated == Decimal("0")
    assert budget.available == Decimal("0")


def test_budget_allocate_and_spend() -> None:
    budget = Budget(
        budget_id="b1",
        agent_id="agent-a",
        chain_id="ait-hub",
        token="AITBC",
        total=Decimal("100"),
    )
    budget.allocate(Decimal("40"))
    assert budget.available == Decimal("60")
    assert budget.allocated == Decimal("40")

    budget.spend(Decimal("30"))
    assert budget.total == Decimal("70")
    assert budget.allocated == Decimal("10")
    assert budget.available == Decimal("60")


def test_budget_release() -> None:
    budget = Budget(
        budget_id="b1",
        agent_id="agent-a",
        chain_id="ait-hub",
        token="AITBC",
        total=Decimal("100"),
    )
    budget.allocate(Decimal("25"))
    budget.release(Decimal("10"))
    assert budget.allocated == Decimal("15")
    assert budget.available == Decimal("85")


def test_budget_allocate_exceeds_available() -> None:
    budget = Budget(
        budget_id="b1",
        agent_id="agent-a",
        chain_id="ait-hub",
        token="AITBC",
        total=Decimal("100"),
    )
    with pytest.raises(ValueError):
        budget.allocate(Decimal("101"))


def test_budget_allocate_negative() -> None:
    budget = Budget(
        budget_id="b1",
        agent_id="agent-a",
        chain_id="ait-hub",
        token="AITBC",
        total=Decimal("100"),
    )
    with pytest.raises(ValueError):
        budget.allocate(Decimal("-1"))


def test_revenue_route_percentage_validation() -> None:
    with pytest.raises(ValueError):
        RevenueRoute(
            route_id="r1",
            route_type=RevenueRouteType.TREASURY,
            recipient="treasury",
            percentage=Decimal("101"),
        )


def test_revenue_route_string_enum() -> None:
    route = RevenueRoute(
        route_id="r1",
        route_type="provider",
        recipient="provider-1",
        percentage=Decimal("25"),
    )
    assert route.route_type == RevenueRouteType.PROVIDER


def test_pricing_strategy_dynamic_price() -> None:
    strategy = PricingStrategy(
        strategy_id="p1",
        agent_id="agent-a",
        strategy_type=PricingStrategyType.DYNAMIC,
        base_price=Decimal("10"),
        demand_factor=Decimal("1.5"),
        surge_multiplier=Decimal("2"),
    )
    assert strategy.price() == Decimal("30")


def test_pricing_strategy_min_max_bounds() -> None:
    strategy = PricingStrategy(
        strategy_id="p1",
        agent_id="agent-a",
        strategy_type=PricingStrategyType.SURGE,
        base_price=Decimal("10"),
        demand_factor=Decimal("10"),
        surge_multiplier=Decimal("1"),
        min_price=Decimal("5"),
        max_price=Decimal("50"),
    )
    assert strategy.price() == Decimal("50")

    strategy.demand_factor = Decimal("0.1")
    assert strategy.price() == Decimal("5")


def test_pricing_strategy_min_exceeds_max() -> None:
    with pytest.raises(ValueError):
        PricingStrategy(
            strategy_id="p1",
            agent_id="agent-a",
            strategy_type="fixed",
            base_price=Decimal("10"),
            min_price=Decimal("20"),
            max_price=Decimal("5"),
        )


def test_on_chain_action_validation() -> None:
    action = OnChainAction(
        action_id="a1",
        agent_id="agent-a",
        action_type=OnChainActionType.STAKE,
        chain_id="ait-hub",
        contract_address="0x1234",
        amount=Decimal("50"),
    )
    assert action.action_type == OnChainActionType.STAKE
    assert action.amount == Decimal("50")


def test_on_chain_action_string_enum() -> None:
    action = OnChainAction(
        action_id="a1",
        agent_id="agent-a",
        action_type="bond_lock",
        chain_id="ait-hub",
        contract_address="0x1234",
    )
    assert action.action_type == OnChainActionType.BOND_LOCK


def test_on_chain_action_missing_agent_id() -> None:
    with pytest.raises(ValueError):
        OnChainAction(
            action_id="a1",
            agent_id="",
            action_type=OnChainActionType.TRANSFER,
            chain_id="ait-hub",
            contract_address="0x1234",
        )


def test_on_chain_action_negative_amount() -> None:
    with pytest.raises(ValueError):
        OnChainAction(
            action_id="a1",
            agent_id="agent-a",
            action_type=OnChainActionType.TRANSFER,
            chain_id="ait-hub",
            contract_address="0x1234",
            amount=Decimal("-1"),
        )
