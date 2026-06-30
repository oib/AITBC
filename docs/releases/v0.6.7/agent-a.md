# v0.6.7 Pool Hub & Mining — Agent A Tasks

**Last Updated**: 2026-06-30
**Version**: 1.0

**Agent**: Agent A (Shared Core)

**Scope**: Create (1) reward policy constants with epoch tracking and payout calculation, (2) fix the stale port and chain_id default in `TransactionService`. Both are consumed by Agent B's pool-hub reward distribution.

**Working directory**: `/opt/aitbc/aitbc/`

**Verification command**:
```bash
cd /opt/aitbc && ./venv/bin/python -m mypy --show-error-codes aitbc/rewards/ aitbc/crypto/transaction_service.py && ./venv/bin/python -m ruff check aitbc/rewards/ aitbc/crypto/transaction_service.py tests/unit/test_reward_policy.py && ./venv/bin/python -m pytest tests/unit/test_reward_policy.py -q -o addopts=""
```

---

## Tasks

| # | Task | Priority | Files | Status |
|---|------|----------|-------|--------|
| A1 | Create `RewardPolicy` — reward constants + epoch tracking + payout calculation | 🔴 P0 | `aitbc/rewards/policy.py` (new), `aitbc/rewards/__init__.py` (new) | ✅ |
| A2 | Fix `TransactionService` stale port (8006→8202) + chain_id default (""→"ait-hub") | 🔴 P0 | `aitbc/crypto/transaction_service.py` (fix lines 41-42) | ✅ |
| A3 | Unit tests for A1 + verify mypy/ruff/pytest clean | High | `tests/unit/test_reward_policy.py` | ✅ |

---

## A1: RewardPolicy

Create `aitbc/rewards/__init__.py` (empty) and `aitbc/rewards/policy.py`:

```python
"""Reward policy for compute mining pools (v0.6.7 §A1).

Defines reward constants, epoch tracking, and payout calculation
for the pool-hub service. Rewards are distributed proportional to
miner contribution score within each reward epoch.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)

# --- Reward policy constants ---

REWARD_PER_SHARE = 1000          # base reward per share (compute-seconds)
HALVING_INTERVAL = 210_000      # blocks between reward halvings
REWARD_EPOCH_LENGTH = 1_000     # blocks per reward epoch
MAX_REWARD_PER_EPOCH = 100_000  # cap per miner per epoch
MINIMUM_PAYOUT = 3_600          # 1 AIT in compute-seconds (smallest unit)
BASE_BLOCK_REWARD = 50_000      # base reward per block (before halving)


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
    score: float                    # contribution score (0-100)
    shares: int = 0                 # compute-seconds contributed
    jobs_completed: int = 0
    reward_amount: int = 0          # calculated reward (in compute-seconds)
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
        return [
            c for c in self.contributions.values()
            if not c.paid and c.reward_amount >= MINIMUM_PAYOUT
        ]


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

    def record_contribution(
        self, miner_id: str, score: float, shares: int, jobs_completed: int = 1
    ) -> None:
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
```

Export from `aitbc/rewards/__init__.py`:
```python
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
```

---

## A2: Fix TransactionService stale port + chain_id

In `aitbc/crypto/transaction_service.py`, fix lines 41-42:

**Before:**
```python
self.rpc_url = os.getenv("BLOCKCHAIN_RPC_URL", "http://localhost:8006")
self.chain_id = os.getenv("CHAIN_ID", "")
```

**After:**
```python
self.rpc_url = os.getenv("BLOCKCHAIN_RPC_URL", "http://localhost:8202")
self.chain_id = os.getenv("CHAIN_ID", "ait-hub")
```

This is a minimal fix — just changing two default values. The port 8202 matches `aitbc/constants.py:50` (`BLOCKCHAIN_RPC_PORT = 8202`) and `apps/blockchain-node/src/aitbc_chain/config.py:89` (`rpc_bind_port: int = 8202`). The chain_id "ait-hub" matches the default used by the GPU service (v0.6.6 B2) and marketplace (v0.6.6 B1).

---

## A3: Unit tests

**`tests/unit/test_reward_policy.py`**:
- `test_calculate_block_reward_genesis` — height 0 → BASE_BLOCK_REWARD
- `test_calculate_block_reward_after_first_halving` — height 210000 → BASE_BLOCK_REWARD / 2
- `test_calculate_block_reward_after_second_halving` — height 420000 → BASE_BLOCK_REWARD / 4
- `test_calculate_block_reward_many_halvings` — height 210000*64 → 0 (overflow protection)
- `test_calculate_epoch_number_genesis` — height 0 → epoch 0
- `test_calculate_epoch_number_mid_epoch` — height 500 → epoch 0
- `test_calculate_epoch_number_next_epoch` — height 1000 → epoch 1
- `test_reward_epoch_add_contribution_new_miner` — adds contribution
- `test_reward_epoch_add_contribution_existing_miner` — accumulates shares
- `test_reward_epoch_calculate_payouts_proportional` — proportional to shares
- `test_reward_epoch_calculate_payouts_capped` — capped at MAX_REWARD_PER_EPOCH
- `test_reward_epoch_calculate_payouts_zero_shares` — no payouts when zero shares
- `test_reward_epoch_mark_paid` — marks miner as paid
- `test_reward_epoch_get_unpaid` — returns unpaid above MINIMUM_PAYOUT
- `test_reward_epoch_get_unpaid_below_minimum` — excludes below MINIMUM_PAYOUT
- `test_reward_policy_current_epoch` — default epoch is 0
- `test_reward_policy_update_block_height` — advances epoch
- `test_reward_policy_record_contribution` — records in current epoch
- `test_reward_policy_is_eligible_for_payout_new` — new miner is eligible
- `test_reward_policy_is_eligible_after_payout` — not eligible after payout
- `test_reward_policy_mark_paid` — marks paid + updates last_reward_epoch
- `test_reward_policy_get_unpaid_miners` — returns eligible unpaid miners
- `test_reward_policy_get_miner_contribution` — returns contribution
- `test_reward_policy_get_epoch` — returns epoch by number
- `test_package_reexport` — all names exported from aitbc.rewards

---

## Related Topics

- [Overview](./overview.md) - Release overview and status baseline
- [Agent B Tasks](./agent-b.md) - Apps & infrastructure implementation details

---

**Documentation Version**: 1.0
**Last Updated**: 2026-06-30
**Release**: v0.6.7 — Pool Hub & Mining
**Agent**: Agent A (Shared Core)
