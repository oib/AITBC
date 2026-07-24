"""Unit tests for aitbc.agent_economics staking (v0.13.0 §A1)."""

from __future__ import annotations

from decimal import Decimal

import pytest

from aitbc.agent_economics import (
    Delegation,
    DelegationStatus,
    StakingError,
    StakingStrategy,
    YieldPosition,
)


def test_delegation_lifecycle() -> None:
    delegation = Delegation(
        delegation_id="d1",
        agent_id="agent-a",
        validator="val-1",
        amount=Decimal("100"),
        token="AITBC",
    )
    delegation.activate()
    assert delegation.status == DelegationStatus.ACTIVE

    delegation.unbond()
    assert delegation.status == DelegationStatus.UNBONDING
    assert delegation.unbonded_at is not None

    delegation.withdraw()
    assert delegation.status == DelegationStatus.WITHDRAWN


def test_delegation_claim_rewards() -> None:
    delegation = Delegation(
        delegation_id="d1",
        agent_id="agent-a",
        validator="val-1",
        amount=Decimal("100"),
        token="AITBC",
        rewards=Decimal("5"),
    )
    assert delegation.claim_rewards() == Decimal("5")
    assert delegation.rewards == Decimal("0")


def test_staking_strategy_validation() -> None:
    with pytest.raises(ValueError):
        StakingStrategy(
            strategy_id="s1",
            agent_id="agent-a",
            rebalance_threshold=Decimal("101"),
        )


def test_staking_strategy_allowed_validator() -> None:
    strategy = StakingStrategy(
        strategy_id="s1",
        agent_id="agent-a",
        target_validators=["val-1", "val-2"],
    )
    assert strategy.allowed_validator("val-1") is True
    assert strategy.allowed_validator("val-3") is False


def test_staking_strategy_validate_delegation() -> None:
    strategy = StakingStrategy(
        strategy_id="s1",
        agent_id="agent-a",
        target_validators=["val-1"],
    )
    delegation = Delegation(
        delegation_id="d1",
        agent_id="agent-a",
        validator="val-2",
        amount=Decimal("100"),
        token="AITBC",
    )
    with pytest.raises(StakingError):
        strategy.validate_delegation(delegation)


def test_yield_position_harvest() -> None:
    position = YieldPosition(
        agent_id="agent-a",
        chain_id="ait-hub",
        token="AITBC",
    )
    position.harvest(Decimal("10"))
    assert position.total_rewards == Decimal("10")


def test_delegation_cannot_activate_twice() -> None:
    delegation = Delegation(
        delegation_id="d1",
        agent_id="agent-a",
        validator="val-1",
        amount=Decimal("100"),
        token="AITBC",
    )
    delegation.activate()
    with pytest.raises(StakingError):
        delegation.activate()
