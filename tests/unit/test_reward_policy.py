"""Unit tests for aitbc.rewards.policy (v0.6.7 §A1/A3).

Covers reward constants, block reward halving, epoch tracking,
contribution accumulation, proportional payout calculation, payout
caps, minimum payout threshold, duplicate payout prevention, and
package re-exports. No blockchain node required.
"""

from __future__ import annotations

import pytest

from aitbc.rewards import (
    BASE_BLOCK_REWARD,
    HALVING_INTERVAL,
    MAX_REWARD_PER_EPOCH,
    MINIMUM_PAYOUT,
    REWARD_EPOCH_LENGTH,
    REWARD_PER_SHARE,
    RewardEpoch,
    RewardPolicy,
    calculate_block_reward,
    calculate_epoch_number,
)
from aitbc.rewards import policy as policy_module


# --- calculate_block_reward ---


def test_calculate_block_reward_genesis() -> None:
    assert calculate_block_reward(0) == BASE_BLOCK_REWARD


def test_calculate_block_reward_after_first_halving() -> None:
    assert calculate_block_reward(HALVING_INTERVAL) == BASE_BLOCK_REWARD // 2


def test_calculate_block_reward_after_second_halving() -> None:
    assert calculate_block_reward(HALVING_INTERVAL * 2) == BASE_BLOCK_REWARD // 4


def test_calculate_block_reward_just_before_halving() -> None:
    assert calculate_block_reward(HALVING_INTERVAL - 1) == BASE_BLOCK_REWARD


def test_calculate_block_reward_many_halvings() -> None:
    # 64+ halvings → overflow protection → 0 reward
    assert calculate_block_reward(HALVING_INTERVAL * 64) == 0
    assert calculate_block_reward(HALVING_INTERVAL * 100) == 0


# --- calculate_epoch_number ---


def test_calculate_epoch_number_genesis() -> None:
    assert calculate_epoch_number(0) == 0


def test_calculate_epoch_number_mid_epoch() -> None:
    assert calculate_epoch_number(500) == 0


def test_calculate_epoch_number_next_epoch() -> None:
    assert calculate_epoch_number(REWARD_EPOCH_LENGTH) == 1


def test_calculate_epoch_number_later_epoch() -> None:
    assert calculate_epoch_number(REWARD_EPOCH_LENGTH * 5 + 250) == 5


# --- RewardEpoch.add_contribution ---


def test_reward_epoch_add_contribution_new_miner() -> None:
    epoch = RewardEpoch(epoch_number=0, block_start=0, block_end=999, total_reward_pool=1000)
    epoch.add_contribution("miner-1", score=80.0, shares=100)
    assert "miner-1" in epoch.contributions
    assert epoch.contributions["miner-1"].shares == 100
    assert epoch.contributions["miner-1"].score == 80.0
    assert epoch.contributions["miner-1"].jobs_completed == 1
    assert epoch.total_shares == 100


def test_reward_epoch_add_contribution_existing_miner() -> None:
    epoch = RewardEpoch(epoch_number=0, block_start=0, block_end=999, total_reward_pool=1000)
    epoch.add_contribution("miner-1", score=80.0, shares=100)
    epoch.add_contribution("miner-1", score=90.0, shares=50, jobs_completed=2)
    contrib = epoch.contributions["miner-1"]
    assert contrib.shares == 150  # accumulated
    assert contrib.score == 90.0  # latest score
    assert contrib.jobs_completed == 3  # accumulated
    assert epoch.total_shares == 150


# --- RewardEpoch.calculate_payouts ---


def test_reward_epoch_calculate_payouts_proportional() -> None:
    epoch = RewardEpoch(epoch_number=0, block_start=0, block_end=999, total_reward_pool=10_000)
    epoch.add_contribution("miner-1", score=80.0, shares=300)
    epoch.add_contribution("miner-2", score=70.0, shares=700)
    epoch.calculate_payouts()
    # miner-1: 10000 * 300/1000 = 3000
    assert epoch.contributions["miner-1"].reward_amount == 3000
    # miner-2: 10000 * 700/1000 = 7000
    assert epoch.contributions["miner-2"].reward_amount == 7000


def test_reward_epoch_calculate_payouts_capped() -> None:
    # miner-1 has 99% of shares → would get 198000, capped at MAX_REWARD_PER_EPOCH
    epoch = RewardEpoch(epoch_number=0, block_start=0, block_end=999, total_reward_pool=200_000)
    epoch.add_contribution("miner-1", score=99.0, shares=9900)
    epoch.add_contribution("miner-2", score=1.0, shares=100)
    epoch.calculate_payouts()
    # miner-1: 200000 * 9900/10000 = 198000 → capped at MAX_REWARD_PER_EPOCH
    assert epoch.contributions["miner-1"].reward_amount == MAX_REWARD_PER_EPOCH
    # miner-2: 200000 * 100/10000 = 2000 → not capped
    assert epoch.contributions["miner-2"].reward_amount == 2000


def test_reward_epoch_calculate_payouts_zero_shares() -> None:
    epoch = RewardEpoch(epoch_number=0, block_start=0, block_end=999, total_reward_pool=1000)
    # No contributions → total_shares is 0
    epoch.calculate_payouts()
    # No crash, no payouts
    assert len(epoch.contributions) == 0


# --- RewardEpoch.mark_paid ---


def test_reward_epoch_mark_paid() -> None:
    epoch = RewardEpoch(epoch_number=0, block_start=0, block_end=999, total_reward_pool=1000)
    epoch.add_contribution("miner-1", score=80.0, shares=100)
    epoch.mark_paid("miner-1", "tx-abc123")
    contrib = epoch.contributions["miner-1"]
    assert contrib.paid is True
    assert contrib.tx_hash == "tx-abc123"
    assert contrib.paid_at is not None


def test_reward_epoch_mark_paid_unknown_miner_raises() -> None:
    epoch = RewardEpoch(epoch_number=0, block_start=0, block_end=999, total_reward_pool=1000)
    with pytest.raises(ValueError, match="no contribution"):
        epoch.mark_paid("unknown-miner", "tx-abc")


# --- RewardEpoch.get_unpaid ---


def test_reward_epoch_get_unpaid() -> None:
    epoch = RewardEpoch(epoch_number=0, block_start=0, block_end=999, total_reward_pool=100_000)
    epoch.add_contribution("miner-1", score=80.0, shares=500)
    epoch.add_contribution("miner-2", score=70.0, shares=500)
    epoch.calculate_payouts()
    unpaid = epoch.get_unpaid()
    assert len(unpaid) == 2
    miner_ids = {c.miner_id for c in unpaid}
    assert miner_ids == {"miner-1", "miner-2"}


def test_reward_epoch_get_unpaid_excludes_paid() -> None:
    epoch = RewardEpoch(epoch_number=0, block_start=0, block_end=999, total_reward_pool=100_000)
    epoch.add_contribution("miner-1", score=80.0, shares=500)
    epoch.add_contribution("miner-2", score=70.0, shares=500)
    epoch.calculate_payouts()
    epoch.mark_paid("miner-1", "tx-1")
    unpaid = epoch.get_unpaid()
    assert len(unpaid) == 1
    assert unpaid[0].miner_id == "miner-2"


def test_reward_epoch_get_unpaid_below_minimum() -> None:
    # Set up an epoch where a miner's reward is below MINIMUM_PAYOUT
    epoch = RewardEpoch(epoch_number=0, block_start=0, block_end=999, total_reward_pool=100_000)
    epoch.add_contribution("miner-1", score=99.0, shares=9990)
    epoch.add_contribution("miner-2", score=1.0, shares=10)
    epoch.calculate_payouts()
    # miner-1: 100000 * 9990/10000 = 99900 → above MINIMUM_PAYOUT
    # miner-2: 100000 * 10/10000 = 100 → below MINIMUM_PAYOUT
    assert epoch.contributions["miner-1"].reward_amount >= MINIMUM_PAYOUT
    assert epoch.contributions["miner-2"].reward_amount < MINIMUM_PAYOUT
    unpaid = epoch.get_unpaid()
    # miner-2 excluded because reward < MINIMUM_PAYOUT
    assert all(c.miner_id != "miner-2" for c in unpaid)
    assert any(c.miner_id == "miner-1" for c in unpaid)


# --- RewardPolicy ---


def test_reward_policy_current_epoch() -> None:
    policy = RewardPolicy(current_block_height=0)
    assert policy.current_epoch_number == 0


def test_reward_policy_current_epoch_nonzero_start() -> None:
    policy = RewardPolicy(current_block_height=2500)
    assert policy.current_epoch_number == 2


def test_reward_policy_update_block_height() -> None:
    policy = RewardPolicy(current_block_height=0)
    assert policy.update_block_height(500) == 0  # still epoch 0
    assert policy.update_block_height(REWARD_EPOCH_LENGTH) == 1  # advanced to epoch 1
    assert policy.update_block_height(REWARD_EPOCH_LENGTH * 3) == 3  # advanced to epoch 3


def test_reward_policy_record_contribution() -> None:
    policy = RewardPolicy(current_block_height=0)
    policy.record_contribution("miner-1", score=80.0, shares=100)
    contrib = policy.get_miner_contribution("miner-1")
    assert contrib is not None
    assert contrib.shares == 100
    assert contrib.score == 80.0


def test_reward_policy_is_eligible_for_payout_new() -> None:
    policy = RewardPolicy(current_block_height=0)
    assert policy.is_eligible_for_payout("miner-1") is True


def test_reward_policy_is_eligible_after_payout() -> None:
    policy = RewardPolicy(current_block_height=0)
    policy.record_contribution("miner-1", score=80.0, shares=100)
    policy.mark_paid("miner-1", "tx-abc")
    assert policy.is_eligible_for_payout("miner-1") is False


def test_reward_policy_is_eligible_after_epoch_advance() -> None:
    policy = RewardPolicy(current_block_height=0)
    policy.record_contribution("miner-1", score=80.0, shares=100)
    policy.mark_paid("miner-1", "tx-abc")
    # Advance to next epoch
    policy.update_block_height(REWARD_EPOCH_LENGTH)
    assert policy.is_eligible_for_payout("miner-1") is True


def test_reward_policy_mark_paid() -> None:
    policy = RewardPolicy(current_block_height=0)
    policy.record_contribution("miner-1", score=80.0, shares=100)
    policy.mark_paid("miner-1", "tx-abc")
    contrib = policy.get_miner_contribution("miner-1")
    assert contrib is not None
    assert contrib.paid is True
    assert contrib.tx_hash == "tx-abc"


def test_reward_policy_get_unpaid_miners() -> None:
    policy = RewardPolicy(current_block_height=0)
    policy.record_contribution("miner-1", score=80.0, shares=500)
    policy.record_contribution("miner-2", score=70.0, shares=500)
    policy.calculate_payouts()
    unpaid = policy.get_unpaid_miners()
    assert len(unpaid) == 2


def test_reward_policy_get_unpaid_miners_excludes_paid() -> None:
    policy = RewardPolicy(current_block_height=0)
    policy.record_contribution("miner-1", score=80.0, shares=500)
    policy.record_contribution("miner-2", score=70.0, shares=500)
    policy.calculate_payouts()
    policy.mark_paid("miner-1", "tx-1")
    unpaid = policy.get_unpaid_miners()
    assert len(unpaid) == 1
    assert unpaid[0].miner_id == "miner-2"


def test_reward_policy_get_miner_contribution_none() -> None:
    policy = RewardPolicy(current_block_height=0)
    assert policy.get_miner_contribution("nonexistent") is None


def test_reward_policy_get_epoch() -> None:
    policy = RewardPolicy(current_block_height=0)
    # Trigger creation of epoch 0
    policy.record_contribution("miner-1", score=80.0, shares=100)
    epoch = policy.get_epoch(0)
    assert epoch is not None
    assert epoch.epoch_number == 0
    assert epoch.block_start == 0
    assert epoch.block_end == REWARD_EPOCH_LENGTH - 1


def test_reward_policy_get_epoch_none() -> None:
    policy = RewardPolicy(current_block_height=0)
    assert policy.get_epoch(999) is None


def test_reward_policy_calculate_payouts_returns_epoch() -> None:
    policy = RewardPolicy(current_block_height=0)
    policy.record_contribution("miner-1", score=80.0, shares=100)
    epoch = policy.calculate_payouts()
    assert isinstance(epoch, RewardEpoch)
    assert epoch.contributions["miner-1"].reward_amount > 0


def test_reward_policy_total_reward_pool_calculation() -> None:
    policy = RewardPolicy(current_block_height=0)
    epoch = policy.get_or_create_epoch(0)
    # epoch 0: block_start=0, block_reward=BASE_BLOCK_REWARD, pool = BASE_BLOCK_REWARD * REWARD_EPOCH_LENGTH
    assert epoch.total_reward_pool == BASE_BLOCK_REWARD * REWARD_EPOCH_LENGTH


# --- Package re-exports ---


def test_package_reexport() -> None:
    """All expected names are exported from aitbc.rewards."""
    import aitbc.rewards as rewards_pkg

    expected = {
        "BASE_BLOCK_REWARD",
        "HALVING_INTERVAL",
        "MAX_REWARD_PER_EPOCH",
        "MINIMUM_PAYOUT",
        "REWARD_EPOCH_LENGTH",
        "REWARD_PER_SHARE",
        "MinerContribution",
        "RewardEpoch",
        "RewardPolicy",
        "calculate_block_reward",
        "calculate_epoch_number",
    }
    for name in expected:
        assert hasattr(rewards_pkg, name), f"aitbc.rewards missing export: {name}"
    assert set(expected).issubset(set(rewards_pkg.__all__))


def test_policy_module_constants_match() -> None:
    """Constants in policy module match the re-exported ones."""
    assert policy_module.REWARD_PER_SHARE == REWARD_PER_SHARE
    assert policy_module.HALVING_INTERVAL == HALVING_INTERVAL
    assert policy_module.REWARD_EPOCH_LENGTH == REWARD_EPOCH_LENGTH
    assert policy_module.MAX_REWARD_PER_EPOCH == MAX_REWARD_PER_EPOCH
    assert policy_module.MINIMUM_PAYOUT == MINIMUM_PAYOUT
    assert policy_module.BASE_BLOCK_REWARD == BASE_BLOCK_REWARD
