"""Reward policy for compute mining pools (v0.6.7 §A1).

Defines reward constants, epoch tracking, and payout calculation
for the pool-hub service. Rewards are distributed proportional to
miner contribution score within each reward epoch.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)

# --- Reward policy constants ---

REWARD_PER_SHARE = 1000  # base reward per share (compute-seconds)
HALVING_INTERVAL = 210_000  # blocks between reward halvings
REWARD_EPOCH_LENGTH = 1_000  # blocks per reward epoch
MAX_REWARD_PER_EPOCH = 100_000  # cap per miner per epoch
MINIMUM_PAYOUT = 3_600  # 1 AIT in compute-seconds (smallest unit)
BASE_BLOCK_REWARD = 50_000  # base reward per block (before halving)


def calculate_block_reward(current_height: int) -> int:
    """Calculate the block reward at a given height, accounting for halvings.

    Args:
        current_height: Current block height.

    Returns:
        Block reward in compute-seconds (smallest unit).
    """
    halvings = current_height // HALVING_INTERVAL
    if halvings >= 64:  # prevent shift overflow (effectively zero reward)
        return 0
    return BASE_BLOCK_REWARD >> halvings


def calculate_epoch_number(block_height: int) -> int:
    """Calculate the current reward epoch number from block height."""
    return block_height // REWARD_EPOCH_LENGTH


@dataclass
class MinerContribution:
    """A miner's contribution within a reward epoch."""

    miner_id: str
    score: float  # contribution score (0-100)
    shares: int = 0  # compute-seconds contributed
    jobs_completed: int = 0
    reward_amount: int = 0  # calculated reward (in compute-seconds)
    paid: bool = False
    paid_at: float | None = None
    tx_hash: str | None = None


@dataclass
class RewardEpoch:
    """A single reward epoch tracking miner contributions and payouts."""

    epoch_number: int
    block_start: int
    block_end: int
    total_shares: int = 0
    total_reward_pool: int = 0
    contributions: dict[str, MinerContribution] = field(default_factory=dict)
    distributed: bool = False
    distributed_at: float | None = None

    def add_contribution(self, miner_id: str, score: float, shares: int, jobs_completed: int = 1) -> None:
        """Add or update a miner's contribution for this epoch."""
        if miner_id not in self.contributions:
            self.contributions[miner_id] = MinerContribution(
                miner_id=miner_id, score=score, shares=shares, jobs_completed=jobs_completed
            )
        else:
            contrib = self.contributions[miner_id]
            contrib.score = score  # use latest score
            contrib.shares += shares
            contrib.jobs_completed += jobs_completed
        self.total_shares += shares

    def calculate_payouts(self) -> None:
        """Calculate reward amounts for all miners proportional to their shares.

        Rewards are capped at MAX_REWARD_PER_EPOCH per miner.
        Miners with rewards below MINIMUM_PAYOUT are not paid (deferred to next epoch).
        """
        if self.total_shares == 0:
            logger.warning("Epoch %s has zero total shares — no payouts", self.epoch_number)
            return

        for contrib in self.contributions.values():
            # Proportional reward based on shares
            proportional = int(self.total_reward_pool * contrib.shares / self.total_shares)
            # Cap at MAX_REWARD_PER_EPOCH
            contrib.reward_amount = min(proportional, MAX_REWARD_PER_EPOCH)

    def mark_paid(self, miner_id: str, tx_hash: str) -> None:
        """Mark a miner's reward as paid."""
        if miner_id not in self.contributions:
            raise ValueError(f"Miner {miner_id} has no contribution in epoch {self.epoch_number}")
        contrib = self.contributions[miner_id]
        contrib.paid = True
        contrib.paid_at = time.time()
        contrib.tx_hash = tx_hash

    def get_unpaid(self) -> list[MinerContribution]:
        """Get all miners with unpaid rewards above MINIMUM_PAYOUT."""
        return [c for c in self.contributions.values() if not c.paid and c.reward_amount >= MINIMUM_PAYOUT]


class RewardPolicy:
    """Manages reward epochs and payout eligibility.

    Tracks reward epochs, prevents duplicate payouts within the same epoch,
    and calculates reward amounts proportional to miner contribution.
    """

    def __init__(self, current_block_height: int = 0) -> None:
        self._epochs: dict[int, RewardEpoch] = {}
        self._current_epoch: int = calculate_epoch_number(current_block_height)
        self._last_reward_epoch: dict[str, int] = {}  # miner_id → last paid epoch

    @property
    def current_epoch_number(self) -> int:
        return self._current_epoch

    def update_block_height(self, block_height: int) -> int:
        """Update the current block height and return the current epoch number."""
        new_epoch = calculate_epoch_number(block_height)
        if new_epoch > self._current_epoch:
            self._current_epoch = new_epoch
            logger.info("Advanced to reward epoch %s", self._current_epoch)
        return self._current_epoch

    def get_or_create_epoch(self, epoch_number: int | None = None) -> RewardEpoch:
        """Get or create a reward epoch."""
        epoch_num = epoch_number if epoch_number is not None else self._current_epoch
        if epoch_num not in self._epochs:
            block_start = epoch_num * REWARD_EPOCH_LENGTH
            block_end = block_start + REWARD_EPOCH_LENGTH - 1
            total_reward = calculate_block_reward(block_start) * REWARD_EPOCH_LENGTH
            self._epochs[epoch_num] = RewardEpoch(
                epoch_number=epoch_num,
                block_start=block_start,
                block_end=block_end,
                total_reward_pool=total_reward,
            )
        return self._epochs[epoch_num]

    def record_contribution(self, miner_id: str, score: float, shares: int, jobs_completed: int = 1) -> None:
        """Record a miner's contribution in the current epoch."""
        epoch = self.get_or_create_epoch()
        epoch.add_contribution(miner_id, score, shares, jobs_completed)

    def is_eligible_for_payout(self, miner_id: str) -> bool:
        """Check if a miner is eligible for payout (not already paid this epoch)."""
        last_epoch = self._last_reward_epoch.get(miner_id, -1)
        return last_epoch < self._current_epoch

    def calculate_payouts(self) -> RewardEpoch:
        """Calculate payouts for the current epoch."""
        epoch = self.get_or_create_epoch()
        epoch.calculate_payouts()
        return epoch

    def mark_paid(self, miner_id: str, tx_hash: str) -> None:
        """Mark a miner as paid for the current epoch."""
        epoch = self.get_or_create_epoch()
        epoch.mark_paid(miner_id, tx_hash)
        self._last_reward_epoch[miner_id] = self._current_epoch
        logger.info("Miner %s paid in epoch %s (tx=%s)", miner_id, self._current_epoch, tx_hash)

    def get_unpaid_miners(self) -> list[MinerContribution]:
        """Get all miners eligible for payout in the current epoch."""
        epoch = self.get_or_create_epoch()
        return epoch.get_unpaid()

    def get_miner_contribution(self, miner_id: str) -> MinerContribution | None:
        """Get a miner's contribution for the current epoch."""
        epoch = self.get_or_create_epoch()
        return epoch.contributions.get(miner_id)

    def get_epoch(self, epoch_number: int) -> RewardEpoch | None:
        """Get a specific epoch by number."""
        return self._epochs.get(epoch_number)
