"""Unit tests for aitbc.agent_economics rebalancing (v0.12.0 §A3)."""

from __future__ import annotations

from decimal import Decimal

import pytest

from aitbc.agent_economics import (
    ChainHoldings,
    RebalanceActionType,
    RebalanceConstraint,
    RebalanceError,
    Rebalancer,
    ReinvestmentPolicy,
)


def test_reinvestment_policy_target_validation() -> None:
    with pytest.raises(RebalanceError):
        ReinvestmentPolicy(
            policy_id="p1",
            agent_id="agent-a",
            target_allocations={
                "ait-hub": Decimal("60"),
                "island-2": Decimal("50"),
            },
        )


def test_chain_holdings_deviation() -> None:
    holdings = ChainHoldings(
        chain_id="ait-hub",
        token="AITBC",
        amount=Decimal("100"),
        target_percent=Decimal("40"),
        current_percent=Decimal("60"),
    )
    assert holdings.deviation == Decimal("20")


def test_rebalancer_no_action_when_within_threshold() -> None:
    policy = ReinvestmentPolicy(
        policy_id="p1",
        agent_id="agent-a",
        target_allocations={"ait-hub": Decimal("50"), "island-2": Decimal("50")},
        trigger_threshold=Decimal("10"),
    )
    rebalancer = Rebalancer(policy)
    holdings = [
        ChainHoldings(
            chain_id="ait-hub",
            token="AITBC",
            amount=Decimal("55"),
            target_percent=Decimal("50"),
            current_percent=Decimal("55"),
        ),
        ChainHoldings(
            chain_id="island-2",
            token="AITBC",
            amount=Decimal("45"),
            target_percent=Decimal("50"),
            current_percent=Decimal("45"),
        ),
    ]
    actions = rebalancer.plan(holdings)
    assert len(actions) == 0


def test_rebalancer_transfer_overweight_to_underweight() -> None:
    policy = ReinvestmentPolicy(
        policy_id="p1",
        agent_id="agent-a",
        target_allocations={"ait-hub": Decimal("50"), "island-2": Decimal("50")},
        trigger_threshold=Decimal("5"),
        min_reinvest_amount=Decimal("1"),
    )
    rebalancer = Rebalancer(policy)
    holdings = [
        ChainHoldings(
            chain_id="ait-hub",
            token="AITBC",
            amount=Decimal("70"),
            target_percent=Decimal("50"),
            current_percent=Decimal("70"),
        ),
        ChainHoldings(
            chain_id="island-2",
            token="AITBC",
            amount=Decimal("30"),
            target_percent=Decimal("50"),
            current_percent=Decimal("30"),
        ),
    ]
    actions = rebalancer.plan(holdings)
    assert len(actions) == 1
    assert actions[0].action_type == RebalanceActionType.TRANSFER
    assert actions[0].source_chain == "ait-hub"
    assert actions[0].target_chain == "island-2"
    assert actions[0].amount == Decimal("20")


def test_rebalancer_reinvest_underweight_with_available_funds() -> None:
    policy = ReinvestmentPolicy(
        policy_id="p1",
        agent_id="agent-a",
        target_allocations={"ait-hub": Decimal("50"), "island-2": Decimal("50")},
        trigger_threshold=Decimal("5"),
        min_reinvest_amount=Decimal("1"),
    )
    rebalancer = Rebalancer(policy)
    holdings = [
        ChainHoldings(
            chain_id="ait-hub",
            token="AITBC",
            amount=Decimal("30"),
            target_percent=Decimal("50"),
            current_percent=Decimal("30"),
        ),
        ChainHoldings(
            chain_id="island-2",
            token="AITBC",
            amount=Decimal("70"),
            target_percent=Decimal("50"),
            current_percent=Decimal("70"),
        ),
    ]
    available = {"ait-hub": Decimal("20")}
    actions = rebalancer.plan(holdings, available_tokens=available)
    assert len(actions) == 1
    assert actions[0].action_type == RebalanceActionType.REINVEST
    assert actions[0].target_chain == "ait-hub"
    assert actions[0].amount == Decimal("20")


def test_rebalance_constraint_validation() -> None:
    with pytest.raises(ValueError):
        RebalanceConstraint(
            constraint_type="max_exposure",
            limit=Decimal("-1"),
        )


def test_reinvestment_policy_max_exposure_bounds() -> None:
    with pytest.raises(ValueError):
        ReinvestmentPolicy(
            policy_id="p1",
            agent_id="agent-a",
            max_exposure_per_chain=Decimal("101"),
        )
