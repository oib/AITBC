"""Tests for the miner reinvestment engine."""

from decimal import Decimal

import pytest

from aitbc.agent_economics import Budget

from miner_app.reinvestment import ReinvestmentEngine, ReinvestmentPolicy, build_revenue_route


@pytest.fixture
def budget():
    return Budget(budget_id="b1", agent_id="agent-1", chain_id="ait-hub", token="AIT", total=Decimal("100"))


@pytest.fixture
def policy():
    return ReinvestmentPolicy(
        reinvest_pct=Decimal("50"),
        staking_pct=Decimal("60"),
        capacity_reserve_pct=Decimal("40"),
        min_reinvest_amount=Decimal("0.01"),
        chain_id="ait-hub",
        staking_contract="0x staking",
        reserve_address="0x reserve",
    )


def test_policy_validation():
    with pytest.raises(ValueError, match="between 0 and 100"):
        ReinvestmentPolicy(reinvest_pct=Decimal("101"))


def test_policy_staking_plus_reserve_must_equal_100():
    with pytest.raises(ValueError, match="must equal 100"):
        ReinvestmentPolicy(staking_pct=Decimal("50"), capacity_reserve_pct=Decimal("30"))


def test_plan_reinvestment_returns_stake_and_reserve_actions(budget, policy):
    engine = ReinvestmentEngine(budget, policy)
    actions = engine.plan_reinvestment(Decimal("10"), "agent-1")

    assert len(actions) == 2
    assert sum(a.amount for a in actions) == Decimal("5")

    stake = [a for a in actions if a.action_type == "stake"][0]
    reserve = [a for a in actions if a.action_type == "transfer"][0]
    assert stake.amount == Decimal("3")
    assert reserve.amount == Decimal("2")


def test_plan_reinvestment_below_min_returns_empty(budget, policy):
    engine = ReinvestmentEngine(budget, policy)
    actions = engine.plan_reinvestment(Decimal("0.001"), "agent-1")
    assert actions == []


def test_plan_reinvestment_no_contracts_returns_empty(budget, policy):
    policy.staking_contract = ""
    policy.reserve_address = ""
    engine = ReinvestmentEngine(budget, policy)
    actions = engine.plan_reinvestment(Decimal("10"), "agent-1")
    assert actions == []


def test_plan_reinvestment_exceeds_budget_raises(budget, policy):
    engine = ReinvestmentEngine(budget, policy)
    with pytest.raises(ValueError, match="exceeds available budget"):
        engine.plan_reinvestment(Decimal("1000"), "agent-1")


def test_apply_reduces_budget(budget, policy):
    engine = ReinvestmentEngine(budget, policy)
    actions = engine.apply(Decimal("10"), "agent-1")
    assert budget.allocated == Decimal("5")
    assert budget.available == Decimal("95")
    assert len(actions) == 2


def test_build_revenue_route():
    route = build_revenue_route("agent-1", "0x recipient", Decimal("25"))
    assert route.recipient == "0x recipient"
    assert route.percentage == Decimal("25")
    assert route.route_type == "provider"
