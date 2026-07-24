"""Unit tests for aitbc.agent_economics bonds and slashing (v0.12.0 §A2)."""

from __future__ import annotations

from datetime import datetime, timedelta
from decimal import Decimal

import pytest

from aitbc.agent_economics import (
    BondStatus,
    BondError,
    PerformanceBond,
    SlashError,
    SlashEvent,
    SlashReason,
    SlashingCondition,
    StakeAccount,
    StakeStatus,
    compute_slash_amount,
    slash_bond,
    slash_stake,
    validate_slash_event,
)


def test_performance_bond_activate() -> None:
    bond = PerformanceBond(
        bond_id="b1",
        agent_id="agent-a",
        amount=Decimal("100"),
        token="AITBC",
    )
    bond.activate()
    assert bond.status == BondStatus.ACTIVE


def test_performance_bond_lock_and_release() -> None:
    now = datetime.utcnow()
    bond = PerformanceBond(
        bond_id="b1",
        agent_id="agent-a",
        amount=Decimal("100"),
        token="AITBC",
    )
    bond.lock(now + timedelta(days=1), now=now)
    assert bond.status == BondStatus.LOCKED
    assert bond.locked_until is not None

    bond.release(now=now + timedelta(days=2))
    assert bond.status == BondStatus.RELEASED


def test_performance_bond_cannot_release_while_locked() -> None:
    now = datetime.utcnow()
    future = now + timedelta(days=1)
    bond = PerformanceBond(
        bond_id="b1",
        agent_id="agent-a",
        amount=Decimal("100"),
        token="AITBC",
    )
    bond.lock(future, now=now)
    with pytest.raises(BondError):
        bond.release(now=now)


def test_performance_bond_slash() -> None:
    bond = PerformanceBond(
        bond_id="b1",
        agent_id="agent-a",
        amount=Decimal("100"),
        token="AITBC",
    )
    bond.activate()
    bond.slash()
    assert bond.status == BondStatus.SLASHED


def test_performance_bond_liquidate() -> None:
    bond = PerformanceBond(
        bond_id="b1",
        agent_id="agent-a",
        amount=Decimal("100"),
        token="AITBC",
    )
    bond.activate()
    bond.liquidate()
    assert bond.status == BondStatus.LIQUIDATED


def test_stake_account_lifecycle() -> None:
    stake = StakeAccount(
        stake_id="s1",
        agent_id="agent-a",
        validator="val-1",
        amount=Decimal("500"),
        token="AITBC",
    )
    stake.activate()
    assert stake.status == StakeStatus.ACTIVE

    stake.start_unstaking()
    assert stake.status == StakeStatus.UNSTAKING

    stake.finalize_unstake()
    assert stake.status == StakeStatus.UNSTAKED
    assert stake.unstaked_at is not None


def test_compute_slash_amount() -> None:
    assert compute_slash_amount(Decimal("100"), Decimal("10")) == Decimal("10")
    assert compute_slash_amount(Decimal("100"), Decimal("100")) == Decimal("100")


def test_validate_slash_event_wrong_bond() -> None:
    bond = PerformanceBond(
        bond_id="b1",
        agent_id="agent-a",
        amount=Decimal("100"),
        token="AITBC",
    )
    bond.activate()
    event = SlashEvent(
        event_id="e1",
        bond_id="b2",
        reason=SlashReason.DOWNTIME,
        penalty_percent=Decimal("5"),
    )
    with pytest.raises(SlashError):
        validate_slash_event(bond, event)


def test_slash_bond_with_conditions() -> None:
    bond = PerformanceBond(
        bond_id="b1",
        agent_id="agent-a",
        amount=Decimal("100"),
        token="AITBC",
    )
    bond.activate()
    conditions = [
        SlashingCondition(
            condition_id="c1",
            reason=SlashReason.DOWNTIME,
            penalty_percent=Decimal("5"),
        )
    ]
    event = SlashEvent(
        event_id="e1",
        bond_id="b1",
        reason=SlashReason.DOWNTIME,
        penalty_percent=Decimal("5"),
    )
    slashed = slash_bond(bond, event, conditions)
    assert slashed == Decimal("5")
    assert bond.status == BondStatus.SLASHED


def test_slash_bond_exceeds_max_penalty() -> None:
    bond = PerformanceBond(
        bond_id="b1",
        agent_id="agent-a",
        amount=Decimal("100"),
        token="AITBC",
    )
    bond.activate()
    conditions = [
        SlashingCondition(
            condition_id="c1",
            reason=SlashReason.DOWNTIME,
            penalty_percent=Decimal("5"),
        )
    ]
    event = SlashEvent(
        event_id="e1",
        bond_id="b1",
        reason=SlashReason.DOWNTIME,
        penalty_percent=Decimal("10"),
    )
    with pytest.raises(SlashError):
        slash_bond(bond, event, conditions)


def test_slash_stake() -> None:
    stake = StakeAccount(
        stake_id="s1",
        agent_id="agent-a",
        validator="val-1",
        amount=Decimal("200"),
        token="AITBC",
    )
    stake.activate()
    event = SlashEvent(
        event_id="e1",
        bond_id="s1",
        reason=SlashReason.DOUBLE_SIGN,
        penalty_percent=Decimal("20"),
    )
    slashed = slash_stake(stake, event)
    assert slashed == Decimal("40")
    assert stake.amount == Decimal("160")


def test_slash_stake_not_active() -> None:
    stake = StakeAccount(
        stake_id="s1",
        agent_id="agent-a",
        validator="val-1",
        amount=Decimal("200"),
        token="AITBC",
    )
    event = SlashEvent(
        event_id="e1",
        bond_id="s1",
        reason=SlashReason.DOWNTIME,
        penalty_percent=Decimal("10"),
    )
    with pytest.raises(SlashError):
        slash_stake(stake, event)
