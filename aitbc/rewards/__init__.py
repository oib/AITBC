"""AITBC reward policy shared utilities (v0.6.7).

Provides:
- RewardPolicy: manages reward epochs and payout eligibility
- RewardEpoch: tracks miner contributions and payouts within an epoch
- MinerContribution: a single miner's contribution within an epoch
- calculate_block_reward: block reward at a given height (with halvings)
- calculate_epoch_number: reward epoch number from block height
- Reward policy constants (REWARD_PER_SHARE, HALVING_INTERVAL, etc.)
"""

from __future__ import annotations

from .policy import (
    BASE_BLOCK_REWARD,
    HALVING_INTERVAL,
    MAX_REWARD_PER_EPOCH,
    MINIMUM_PAYOUT,
    REWARD_EPOCH_LENGTH,
    REWARD_PER_SHARE,
    MinerContribution,
    RewardEpoch,
    RewardPolicy,
    calculate_block_reward,
    calculate_epoch_number,
)

__all__ = [
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
]
