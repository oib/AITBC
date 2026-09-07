"""Targeted branch-coverage tests for StakingManager.

Covers validation, state transitions, slashing, rewards, and query helpers
that are not exercised by the existing staking lock-period tests.
"""

from __future__ import annotations

import time
from decimal import Decimal

import pytest

from aitbc_chain.economics.staking import (
    StakingManager,
    StakingStatus,
)


VAL1 = "0x1111111111111111111111111111111111111111"
VAL2 = "0x2222222222222222222222222222222222222222"
DELEG = "0x3333333333333333333333333333333333333333"


@pytest.fixture
def mgr() -> StakingManager:
    m = StakingManager(min_stake_amount=Decimal("100"))
    return m


def _register(mgr: StakingManager, addr: str = VAL1, stake: float = 200) -> None:
    ok, msg = mgr.register_validator(addr, stake)
    assert ok, msg


# --- register_validator -----------------------------------------------------


class TestRegisterValidator:
    def test_self_stake_below_minimum(self, mgr: StakingManager):
        ok, msg = mgr.register_validator(VAL1, 50)
        assert not ok and "at least" in msg

    def test_commission_too_low(self, mgr: StakingManager):
        ok, msg = mgr.register_validator(VAL1, 200, commission_rate=0.001)
        assert not ok and "Commission" in msg

    def test_commission_too_high(self, mgr: StakingManager):
        ok, msg = mgr.register_validator(VAL1, 200, commission_rate=0.5)
        assert not ok and "Commission" in msg

    def test_already_registered(self, mgr: StakingManager):
        _register(mgr)
        ok, msg = mgr.register_validator(VAL1, 200)
        assert not ok and "already" in msg

    def test_success(self, mgr: StakingManager):
        _register(mgr)
        info = mgr.get_validator_stake_info(VAL1)
        assert info is not None
        assert info.is_active
        assert info.commission_rate == 0.05
        # Self-stake position created
        pos = mgr.get_stake_position(VAL1, VAL1)
        assert pos is not None
        assert pos.lock_period == 90  # validator self-stake


# --- stake ------------------------------------------------------------------


class TestStake:
    def test_stake_below_minimum(self, mgr: StakingManager):
        _register(mgr)
        ok, msg = mgr.stake(VAL1, DELEG, 50)
        assert not ok and "at least" in msg

    def test_stake_nonexistent_validator(self, mgr: StakingManager):
        ok, msg = mgr.stake(VAL1, DELEG, 200)
        assert not ok and "not found" in msg

    def test_stake_inactive_validator(self, mgr: StakingManager):
        _register(mgr)
        mgr.validator_info[VAL1].is_active = False
        ok, msg = mgr.stake(VAL1, DELEG, 200)
        assert not ok and "not active" in msg

    def test_stake_self_is_self_stake(self, mgr: StakingManager):
        _register(mgr)
        # Self-staking again overwrites the existing position
        ok, _ = mgr.stake(VAL1, VAL1, 300)
        assert ok
        pos = mgr.get_stake_position(VAL1, VAL1)
        assert pos.amount == Decimal("300")

    def test_stake_delegator_success(self, mgr: StakingManager):
        _register(mgr)
        ok, msg = mgr.stake(VAL1, DELEG, 200)
        assert ok
        info = mgr.get_validator_stake_info(VAL1)
        assert info.delegators_count == 1
        assert info.delegated_stake == Decimal("200")


# --- unstake / withdraw -----------------------------------------------------


class TestUnstakeWithdraw:
    def test_unstake_nonexistent(self, mgr: StakingManager):
        ok, msg = mgr.unstake(VAL1, DELEG)
        assert not ok and "not found" in msg

    def test_unstake_not_active(self, mgr: StakingManager):
        _register(mgr)
        pos = mgr.get_stake_position(VAL1, VAL1)
        pos.status = StakingStatus.WITHDRAWN
        ok, msg = mgr.unstake(VAL1, VAL1)
        assert not ok and "withdrawn" in msg

    def test_unstake_in_lock_period(self, mgr: StakingManager):
        _register(mgr)
        # Self-stake has 90-day lock; immediately unstaking should fail
        ok, msg = mgr.unstake(VAL1, VAL1)
        assert not ok and "lock period" in msg

    def test_unstake_success(self, mgr: StakingManager):
        _register(mgr)
        pos = mgr.get_stake_position(VAL1, VAL1)
        pos.staked_at = time.time() - 91 * 86400  # past lock
        ok, msg = mgr.unstake(VAL1, VAL1)
        assert ok
        assert pos.status == StakingStatus.UNSTAKING

    def test_withdraw_nonexistent(self, mgr: StakingManager):
        ok, msg, amt = mgr.withdraw(VAL1, DELEG)
        assert not ok and amt == Decimal("0")

    def test_withdraw_not_unstaking(self, mgr: StakingManager):
        _register(mgr)
        ok, msg, amt = mgr.withdraw(VAL1, VAL1)
        assert not ok and amt == Decimal("0")

    def test_withdraw_before_period_ends(self, mgr: StakingManager):
        _register(mgr)
        pos = mgr.get_stake_position(VAL1, VAL1)
        pos.staked_at = time.time() - 91 * 86400
        mgr.unstake(VAL1, VAL1)
        ok, msg, amt = mgr.withdraw(VAL1, VAL1)
        assert not ok and "remaining" in msg

    def test_withdraw_success(self, mgr: StakingManager):
        _register(mgr)
        pos = mgr.get_stake_position(VAL1, VAL1)
        pos.staked_at = time.time() - 91 * 86400
        mgr.unstake(VAL1, VAL1)
        # Fast-forward unstaking period
        key = f"{VAL1}:{VAL1}"
        mgr.unstaking_requests[key] = time.time() - 22 * 86400
        ok, msg, amt = mgr.withdraw(VAL1, VAL1)
        assert ok
        assert amt == Decimal("200")
        assert pos.status == StakingStatus.WITHDRAWN


# --- slash ------------------------------------------------------------------


class TestSlash:
    def test_slash_nonexistent(self, mgr: StakingManager):
        ok, msg = mgr.slash_validator(VAL1, 0.1, "bad")
        assert not ok and "not found" in msg

    def test_slash_no_active_stakes(self, mgr: StakingManager):
        _register(mgr)
        pos = mgr.get_stake_position(VAL1, VAL1)
        pos.status = StakingStatus.WITHDRAWN
        ok, msg = mgr.slash_validator(VAL1, 0.1, "bad")
        assert not ok and "No active" in msg

    def test_slash_success(self, mgr: StakingManager):
        _register(mgr)
        ok, msg = mgr.slash_validator(VAL1, 0.5, "misbehavior")
        assert ok
        pos = mgr.get_stake_position(VAL1, VAL1)
        assert pos.amount == Decimal("100")  # 200 - 50% = 100
        assert pos.slash_count == 1
        assert len(mgr.slashing_events) == 1
        info = mgr.get_validator_stake_info(VAL1)
        assert info.performance_score == 0.9  # 1.0 - 0.1

    def test_slash_below_minimum_marks_slashed(self, mgr: StakingManager):
        _register(mgr, stake=200)
        ok, _ = mgr.slash_validator(VAL1, 0.99, "severe")
        assert ok
        pos = mgr.get_stake_position(VAL1, VAL1)
        assert pos.status == StakingStatus.SLASHED


# --- rewards ----------------------------------------------------------------


class TestRewards:
    def test_calculate_epoch_rewards_empty(self, mgr: StakingManager):
        rewards = mgr.calculate_epoch_rewards()
        assert rewards == {}

    def test_calculate_epoch_rewards_proportional(self, mgr: StakingManager):
        _register(mgr, VAL1, 200)
        _register(mgr, VAL2, 300)
        rewards = mgr.calculate_epoch_rewards(Decimal("100"))
        # VAL1 has 200/500, VAL2 has 300/500
        assert rewards[VAL1] == Decimal("40")
        assert rewards[VAL2] == Decimal("60")

    def test_distribute_rewards_no_validators(self, mgr: StakingManager):
        ok, msg = mgr.distribute_rewards()
        assert not ok and "No rewards" in msg

    def test_distribute_rewards_success(self, mgr: StakingManager):
        _register(mgr, VAL1, 200)
        ok, msg = mgr.distribute_rewards(Decimal("100"))
        assert ok
        pos = mgr.get_stake_position(VAL1, VAL1)
        assert pos.rewards == Decimal("100")

    def test_get_validator_rewards(self, mgr: StakingManager):
        _register(mgr, VAL1, 200)
        mgr.distribute_rewards(Decimal("100"))
        rewards = mgr.get_validator_rewards(VAL1)
        assert rewards == Decimal("100")


# --- unregister / complete_exit ---------------------------------------------


class TestUnregisterExit:
    def test_unregister_nonexistent(self, mgr: StakingManager):
        ok, msg = mgr.unregister_validator(VAL1)
        assert not ok and "not found" in msg

    def test_unregister_with_delegators(self, mgr: StakingManager):
        _register(mgr)
        mgr.stake(VAL1, DELEG, 200)
        ok, msg = mgr.unregister_validator(VAL1)
        assert not ok and "delegators" in msg

    def test_unregister_self_stake_locked(self, mgr: StakingManager):
        _register(mgr)
        # Self-stake is locked for 90 days; unregister tries to unstake
        ok, msg = mgr.unregister_validator(VAL1)
        assert not ok and "Cannot unstake" in msg

    def test_unregister_success(self, mgr: StakingManager):
        _register(mgr)
        pos = mgr.get_stake_position(VAL1, VAL1)
        pos.staked_at = time.time() - 91 * 86400
        ok, msg = mgr.unregister_validator(VAL1)
        assert ok
        info = mgr.get_validator_stake_info(VAL1)
        assert not info.is_active

    def test_complete_exit_nonexistent(self, mgr: StakingManager):
        ok, msg = mgr.complete_validator_exit(VAL1)
        assert not ok and "not found" in msg

    def test_complete_exit_no_unstaking(self, mgr: StakingManager):
        _register(mgr)
        ok, msg = mgr.complete_validator_exit(VAL1)
        assert not ok and "No unstaking" in msg

    def test_complete_exit_before_period(self, mgr: StakingManager):
        _register(mgr)
        pos = mgr.get_stake_position(VAL1, VAL1)
        pos.staked_at = time.time() - 91 * 86400
        mgr.unstake(VAL1, VAL1)
        ok, msg = mgr.complete_validator_exit(VAL1)
        assert not ok and "not yet elapsed" in msg

    def test_complete_exit_success(self, mgr: StakingManager):
        _register(mgr)
        pos = mgr.get_stake_position(VAL1, VAL1)
        pos.staked_at = time.time() - 91 * 86400
        mgr.unstake(VAL1, VAL1)
        key = f"{VAL1}:{VAL1}"
        mgr.unstaking_requests[key] = time.time() - 22 * 86400
        ok, msg = mgr.complete_validator_exit(VAL1)
        assert ok
        assert pos.status == StakingStatus.WITHDRAWN
        assert not mgr.validator_info[VAL1].is_active


# --- query helpers ----------------------------------------------------------


class TestQueryHelpers:
    def test_get_all_validators(self, mgr: StakingManager):
        _register(mgr, VAL1)
        _register(mgr, VAL2)
        assert len(mgr.get_all_validators()) == 2

    def test_get_active_validators(self, mgr: StakingManager):
        _register(mgr, VAL1)
        _register(mgr, VAL2)
        mgr.validator_info[VAL2].is_active = False
        active = mgr.get_active_validators()
        assert len(active) == 1
        assert active[0].validator_address == VAL1

    def test_get_delegators(self, mgr: StakingManager):
        _register(mgr)
        mgr.stake(VAL1, DELEG, 200)
        delegators = mgr.get_delegators(VAL1)
        assert len(delegators) == 1
        assert delegators[0].delegator_address == DELEG

    def test_get_total_staked(self, mgr: StakingManager):
        _register(mgr, VAL1, 200)
        mgr.stake(VAL1, DELEG, 300)
        assert mgr.get_total_staked() == Decimal("500")

    def test_get_staking_statistics(self, mgr: StakingManager):
        _register(mgr, VAL1, 200)
        mgr.stake(VAL1, DELEG, 300)
        stats = mgr.get_staking_statistics()
        assert stats["total_validators"] == 1
        assert stats["total_staked"] == "500"
        assert stats["total_delegators"] == 1
        assert stats["total_slashing_events"] == 0
