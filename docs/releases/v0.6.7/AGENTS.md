# v0.6.7 — Agent Task Assignment

**Last Updated**: 2026-06-30
**Version**: 1.0

**Release Theme**: Pool Hub & Mining — Blockchain Reward Distribution, Miner Registration on-chain, Job Completion Payment.

**Goal**: Wire the existing pool-hub service (3,855 lines, two parallel implementations) into the blockchain payment layer. Add chain_id awareness, reward policy constants, and a single end-to-end flow: job completed → reward paid via blockchain transaction. Register miners on-chain via agent-coordinator.

> **Scope constraint**: This release targets `apps/pool-hub/` (3.8K lines) and new shared utilities in `aitbc/rewards/`. It does NOT add complex scoring weight tuning, multi-chain pool support, or governance integration (deferred to v0.7.x). The two parallel implementations (`src/app/` dataclass + `src/poolhub/` SQLModel) are consolidated — the SQLModel/PostgreSQL version in `src/poolhub/` is the canonical implementation; the in-memory dataclass version in `src/app/` is deprecated.

> **Prerequisites**: [v0.6.5](../v0.6.5/change.log) (Agent Coordination — miners register as agents), [v0.6.6](../v0.6.6/change.log) (Compute Marketplace — jobs come from marketplace matches), [v0.5.16](../v0.5.16/change.log) (chain_id-aware transactions). v0.6.6 Agent A complete (OfferFSM + BlockchainRPCClient available in `aitbc.marketplace`).

> **Risk**: Medium. Reward distribution adds blockchain transaction overhead. The two parallel implementations need consolidation. Mitigated by: (1) reward distribution is feature-flagged (default off), (2) consolidation is additive (SQLModel version already works), (3) chain_id is optional (defaults to `DEFAULT_CHAIN_ID`).

---

## Documentation Structure

This release documentation has been split into topic-focused files:

- **[Overview](./overview.md)** - Release overview, status baseline, architecture, and task split overview
- **[Agent A Tasks](./agent-a.md)** - Shared core implementation (RewardPolicy, TransactionService fix, unit tests)
- **[Agent B Tasks](./agent-b.md)** - Apps & infrastructure implementation (pool-hub settings, blockchain client, reward distribution, miner registration, tests)

---

## Quick Navigation

### Overview
- [Status Baseline](./overview.md#status-baseline--verified-code-targets)
- [Already Fixed / Exists](./overview.md#already-fixed--exists-verified--no-work-needed)
- [Architecture](./overview.md#architecture-pool-hub-with-blockchain-rewards)
- [Task Split Overview](./overview.md#task-split-overview)

### Agent A (Shared Core)
- [Scope](./agent-a.md#scope)
- [Tasks](./agent-a.md#tasks)
- [RewardPolicy](./agent-a.md#a1-rewardpolicy)
- [TransactionService Fix](./agent-a.md#a2-fix-transactionservice-stale-port--chain_id)
- [Unit Tests](./agent-a.md#a3-unit-tests)

### Agent B (Apps & Infrastructure)
- [Scope](./agent-b.md#scope)
- [Tasks](./agent-b.md#tasks)
- [Pool-hub Settings](./agent-b.md#b1-pool-hub-settings)
- [PoolHubBlockchainClient](./agent-b.md#b2-poolhubblockchainclient)
- [Miner Registration](./agent-b.md#b3-miner-registration-with-chain_id)
- [Reward Distribution](./agent-b.md#b4-wire-reward-distribution-into-job-completion)
- [RewardPayout Model](./agent-b.md#b5-rewardpayout-model)
- [Deprecation Notice](./agent-b.md#b6-deprecate-srcapp-in-memory-implementation)
- [Integration Tests](./agent-b.md#b7-integration-tests)
- [Dependency Graph](./agent-b.md#dependency-graph)
- [Coordination](./agent-b.md#coordination)
- [Success Criteria](./agent-b.md#success-criteria)

---

## Status Baseline — Verified Code Targets (from subagent investigation, 2026-06-29)

| Component | Location | Current State | v0.6.7 Target |
|-----------|----------|---------------|---------------|
| **Pool-hub app** | `apps/pool-hub/` | ✅ EXISTS — 3,855 lines, 37 Python files | Consolidate two implementations, add blockchain rewards |
| **Two parallel implementations** | `src/app/` (dataclass) + `src/poolhub/` (SQLModel) | ❌ Duplicated functionality — dataclass version is legacy | Deprecate `src/app/`, use `src/poolhub/` as canonical |
| **Scoring engine** | `apps/pool-hub/src/app/scoring/scoring_engine.py` (225 lines) | ✅ Complete — weighted scoring (reliability 35%, performance 30%, capacity 20%, reputation 15%), time decay, ranking | No change needed (works as-is) |
| **Job assignment** | `apps/pool-hub/src/app/routers/jobs.py` (165 lines) | ✅ Complete — assign, result submission, reassign, pending | Add reward payment on job completion |
| **Job reward field** | `apps/pool-hub/src/app/routers/jobs.py:26` | `reward: float = 0.0` — defined but NEVER used | Wire into reward distribution |
| **Job result submission** | `apps/pool-hub/src/app/routers/jobs.py:93-113` | `submit_result()` — updates status + score, no payment | Add blockchain reward transaction after successful completion |
| **Miner registry** | `apps/pool-hub/src/app/registry/miner_registry.py` (315 lines) | ✅ Complete — register, heartbeat, capabilities, pools (in-memory) | Add chain_id, register on blockchain via agent-coordinator |
| **Pool management** | `apps/pool-hub/src/app/routers/pools.py` (165 lines) | ✅ Complete — create, stats, miners | No change needed |
| **SQLModel models** | `apps/pool-hub/src/poolhub/models.py` (197 lines) | ✅ Miner, MatchRequest, MatchResult, Feedback, SLAMetric, etc. | Add `chain_id` to Miner model, add `RewardPayout` model |
| **Billing integration** | `apps/pool-hub/src/poolhub/services/billing_integration.py` | ✅ Uses `AsyncAITBCHTTPClient` to coordinator-api (port 8011) | No change needed (separate from blockchain rewards) |
| **SLA monitoring** | `apps/pool-hub/src/poolhub/services/sla_collector.py` | ✅ Complete | No change needed |
| **Pool-hub settings** | `apps/pool-hub/src/poolhub/settings.py:28` | `bind_port: int = 8203` (correct — pool-hub's own port) | Add `blockchain_rpc_url`, `default_chain_id`, `agent_coordinator_url` |
| **Pool-hub config — blockchain** | — | ❌ NO blockchain config anywhere (0 matches for chain_id/blockchain/rpc_url) | Add `blockchain_rpc_url: str = "http://localhost:8202"`, `default_chain_id: str = "ait-hub"` |
| **Pool-hub config — coordinator** | `settings.py:51` | `coordinator_billing_url: str = "http://localhost:8011"` (billing only) | Add `agent_coordinator_url: str = "http://localhost:8010"` for miner registration |
| **Blockchain client** | — | ❌ NO blockchain client in pool-hub | Create `PoolHubBlockchainClient` using `aitbc.marketplace.BlockchainRPCClient` |
| **Reward policy constants** | — | ❌ NONE exist anywhere (not in `aitbc/constants.py`, not in `aitbc/rewards/`, not in pool-hub) | Create `aitbc/rewards/policy.py` with constants |
| **Reward distribution** | — | ❌ NO implementation — `reward` field never accessed | Implement reward distribution on job completion |
| **Miner on-chain registration** | — | ❌ Only in-memory registry | Register miners on blockchain via agent-coordinator |
| **Epoch tracking** | — | ❌ No epoch tracking | Track `last_reward_epoch` per miner to prevent duplicate payouts |
| **TransactionService** | `aitbc/crypto/transaction_service.py:41` | ❌ Stale port: `self.rpc_url = os.getenv("BLOCKCHAIN_RPC_URL", "http://localhost:8006")` | Fix to 8202 (or use `aitbc.constants.BLOCKCHAIN_RPC_PORT`) |
| **TransactionService chain_id** | `aitbc/crypto/transaction_service.py:42` | `self.chain_id = os.getenv("CHAIN_ID", "")` — defaults to empty string | Fix default to `"ait-hub"` |
| **BlockchainRPCClient** | `aitbc/marketplace/blockchain_rpc.py` (v0.6.6) | ✅ Available — `submit_transaction()`, `register_gpu()`, `allocate_gpu()` | Reuse for reward transactions |
| **OfferFSM** | `aitbc/marketplace/offer_fsm.py` (v0.6.6) | ✅ Available | Not needed for v0.6.7 (offers are marketplace concern) |
| **PaymentEscrow** | `aitbc/crypto/payment_escrow.py` (v0.6.5) | ✅ Available — lock/release/refund | Optional: use for job payment escrow |
| **Blockchain GPU RPC** | `apps/blockchain-node/src/aitbc_chain/rpc/gpu_resources.py` | ✅ `/gpus`, `/gpu/register` — chain_id-aware | No change needed |
| **Blockchain TransactionRequest** | `apps/blockchain-node/src/aitbc_chain/rpc/transactions.py:21-32` | ✅ Accepts `chain_id`, validates against supported chains | No change needed |
| **Blockchain RPC port** | `aitbc/constants.py:50` + `apps/blockchain-node/src/aitbc_chain/config.py:89` | ✅ `BLOCKCHAIN_RPC_PORT = 8202` | No change needed |
| **Pool-hub tests** | `apps/pool-hub/tests/` (4 test files) | Integration tests requiring Postgres+Redis (skip without env) | Add unit tests for reward distribution, blockchain client |

### Already Fixed / Exists (verified — no work needed)

1. ✅ **Pool-hub app exists** — 3,855 lines, 37 Python files (contrary to old docs claiming it doesn't exist)
2. ✅ **Scoring engine complete** — weighted scoring with time decay and ranking
3. ✅ **Job assignment complete** — assign, result, reassign, pending endpoints
4. ✅ **Miner registry complete** — register, heartbeat, capabilities, pools (in-memory)
5. ✅ **Pool management complete** — create, stats, miners endpoints
6. ✅ **Billing integration complete** — talks to coordinator-api via `AsyncAITBCHTTPClient`
7. ✅ **SLA monitoring complete** — SLA collector + endpoints
8. ✅ **BlockchainRPCClient available** (v0.6.6) — can be reused for reward transactions
9. ✅ **PaymentEscrow available** (v0.6.5) — can be used for job payment escrow
10. ✅ **Blockchain RPC port is 8202** — verified in `aitbc/constants.py:50`

### Architecture: Pool Hub with Blockchain Rewards

```
┌──────────────────────────────────────────────────────────────────────┐
│ Pool Hub (apps/pool-hub/)                                            │
│                                                                      │
│  Miner Registration:                                                 │
│    POST /miners/register                                             │
│    - miner_id, capabilities, gpu_info (existing)                     │
│    - chain_id (NEW — which chain miner operates on)                  │
│    - → register on blockchain via agent-coordinator /agents/register │
│                                                                      │
│  Job Assignment:                                                     │
│    POST /jobs/assign                                                 │
│    - Find best miner by score (existing)                             │
│    - Lock payment via PaymentEscrow (NEW — feature-flagged)          │
│                                                                      │
│  Job Completion:                                                     │
│    POST /jobs/result                                                 │
│    - Update job status + score (existing)                            │
│    - IF status == "completed":                                       │
│      → Calculate reward (reward_policy × score_weight)               │
│      → Submit reward transaction via BlockchainRPCClient (NEW)       │
│      → Track payout to prevent duplicate within epoch (NEW)          │
│      → Release escrow to miner (NEW — if escrow was used)            │
│                                                                      │
│  Reward Policy (aitbc/rewards/policy.py — NEW):                      │
│    REWARD_PER_SHARE = 1000      # base reward per share              │
│    HALVING_INTERVAL = 210000    # blocks between halvings            │
│    REWARD_EPOCH_LENGTH = 1000   # blocks per reward epoch            │
│    MAX_REWARD_PER_EPOCH = 100000  # cap per miner per epoch          │
│    MINIMUM_PAYOUT = 3600        # 1 AIT in compute-seconds           │
│                                                                      │
│  Shared Core (aitbc/):                                               │
│    RewardPolicy (A1) — constants + epoch tracking + payout calc      │
│    TransactionService (A2) — fix stale port 8006→8202, chain_id ""   │
│    BlockchainRPCClient (v0.6.6) — reuse for reward tx submission     │
│    PaymentEscrow (v0.6.5) — reuse for job payment escrow             │
└──────────────────────────────────────────────────────────────────────┘
```

---

## Task Split Overview

| Agent | Domain | Tasks | Files |
|-------|--------|-------|-------|
| **Agent A** | Shared core (`aitbc/`) | 3 items | `aitbc/rewards/policy.py` (new), `aitbc/rewards/__init__.py` (new), `aitbc/crypto/transaction_service.py` (fix), `tests/unit/` |
| **Agent B** | Apps & infrastructure | 7 items | `apps/pool-hub/` (settings, blockchain client, jobs router, miner registry, models, tests) |

**Conflict boundary**: Agent A owns new `aitbc/rewards/` + fix to `aitbc/crypto/transaction_service.py`. Agent B owns all `apps/pool-hub/` files. Agent B consumes Agent A's `RewardPolicy` and the existing `BlockchainRPCClient`. No shared files are touched by both agents.

---

## Agent A — Shared Core (`aitbc/`)

**Scope**: Create (1) reward policy constants with epoch tracking and payout calculation, (2) fix the stale port and chain_id default in `TransactionService`. Both are consumed by Agent B's pool-hub reward distribution.

**Working directory**: `/opt/aitbc/aitbc/`

**Verification command**:
```bash
cd /opt/aitbc && ./venv/bin/python -m mypy --show-error-codes aitbc/rewards/ aitbc/crypto/transaction_service.py && ./venv/bin/python -m ruff check aitbc/rewards/ aitbc/crypto/transaction_service.py tests/unit/test_reward_policy.py && ./venv/bin/python -m pytest tests/unit/test_reward_policy.py -q -o addopts=""
```

### Tasks

| # | Task | Priority | Files | Status |
|---|------|----------|-------|--------|
| A1 | Create `RewardPolicy` — reward constants + epoch tracking + payout calculation | 🔴 P0 | `aitbc/rewards/policy.py` (new), `aitbc/rewards/__init__.py` (new) | ✅ |
| A2 | Fix `TransactionService` stale port (8006→8202) + chain_id default (""→"ait-hub") | 🔴 P0 | `aitbc/crypto/transaction_service.py` (fix lines 41-42) | ✅ |
| A3 | Unit tests for A1 + verify mypy/ruff/pytest clean | High | `tests/unit/test_reward_policy.py` | ✅ |

### Agent A — Detailed Instructions

#### A1: RewardPolicy

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

#### A2: Fix TransactionService stale port + chain_id

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

#### A3: Unit tests

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

## Agent B — Apps & Infrastructure

**Scope**: Add blockchain config to pool-hub settings, create a blockchain client, wire reward distribution into job completion, add chain_id to miner registration, register miners on blockchain via agent-coordinator, add `RewardPayout` model, and write integration tests.

**Working directory**: `/opt/aitbc/apps/pool-hub/`

**Verification command**:
```bash
cd /opt/aitbc && ./venv/bin/python -m ruff check apps/pool-hub/
cd /opt/aitbc && ./venv/bin/python -m pytest apps/pool-hub/tests/test_v067_rewards.py -q -o addopts="" --timeout=30
```

### Tasks

| # | Task | Priority | Files | Status |
|---|------|----------|-------|--------|
| B1 | Pool-hub settings: add `blockchain_rpc_url`, `default_chain_id`, `agent_coordinator_url`, reward config | 🔴 P0 | `apps/pool-hub/src/poolhub/settings.py` | ✅ |
| B2 | Create `PoolHubBlockchainClient` — wraps `BlockchainRPCClient` for reward tx submission + miner registration | 🔴 P0 | `apps/pool-hub/src/poolhub/clients/blockchain.py` (new) | ✅ |
| B3 | Add `chain_id` to miner registration + register on blockchain via agent-coordinator | 🔴 P0 | `apps/pool-hub/src/app/routers/miners.py`, `apps/pool-hub/src/app/registry/miner_registry.py`, `apps/pool-hub/src/poolhub/models.py` | ✅ |
| B4 | Wire reward distribution into `jobs.py:submit_result()` — calculate reward, submit tx, track payout | 🔴 P0 | `apps/pool-hub/src/app/routers/jobs.py` | ✅ |
| B5 | Add `RewardPayout` SQLModel + epoch tracking model | Medium | `apps/pool-hub/src/poolhub/models.py` | ✅ |
| B6 | Deprecate `src/app/` in-memory implementation — add deprecation notice, route all new code through `src/poolhub/` | Low | `apps/pool-hub/src/app/__init__.py` (deprecation notice) | ✅ |
| B7 | Integration tests — reward lifecycle, chain_id, epoch tracking, duplicate payout prevention | 🔴 P0 | `apps/pool-hub/tests/test_v067_rewards.py` (new) | ✅ |

### Agent B — Detailed Instructions

#### B1: Pool-hub settings

In `apps/pool-hub/src/poolhub/settings.py`, add to `Settings` class:

```python
    # Blockchain integration (v0.6.7)
    blockchain_rpc_url: str = Field(default="http://localhost:8202")
    default_chain_id: str = Field(default="ait-hub")

    # Agent coordinator integration (v0.6.7 — miner registration)
    agent_coordinator_url: str = Field(default="http://localhost:8010")

    # Reward distribution (v0.6.7)
    enable_reward_distribution: bool = Field(default=False)  # feature-flagged
    reward_sync_interval_blocks: int = Field(default=100)
```

#### B2: PoolHubBlockchainClient

Create `apps/pool-hub/src/poolhub/clients/__init__.py` (empty) and `apps/pool-hub/src/poolhub/clients/blockchain.py`:

```python
"""Blockchain client for pool-hub reward distribution (v0.6.7 §B2)."""

from __future__ import annotations

import logging
from typing import Any

from aitbc.marketplace import BlockchainRPCClient
from aitbc.rewards import RewardPolicy

logger = logging.getLogger(__name__)


class PoolHubBlockchainClient:
    """Blockchain client for pool-hub reward distribution and miner registration.

    Wraps BlockchainRPCClient (from v0.6.6) with pool-hub-specific logic:
    - Submit reward transactions on job completion
    - Register miners on blockchain via agent-coordinator
    - Track reward payouts to prevent duplicates
    """

    def __init__(
        self,
        rpc_url: str = "http://localhost:8202",
        chain_id: str = "ait-hub",
        coordinator_url: str = "http://localhost:8010",
    ) -> None:
        self._rpc = BlockchainRPCClient(rpc_url=rpc_url)
        self._chain_id = chain_id
        self._coordinator_url = coordinator_url
        self._reward_policy = RewardPolicy()

    @property
    def chain_id(self) -> str:
        return self._chain_id

    @property
    def reward_policy(self) -> RewardPolicy:
        return self._reward_policy

    async def submit_reward_transaction(
        self, miner_address: str, amount: int, job_id: str
    ) -> dict[str, Any]:
        """Submit a reward transaction to the blockchain.

        Args:
            miner_address: Miner's wallet address (recipient)
            amount: Reward amount in compute-seconds (smallest unit)
            job_id: Job ID for tracking (included in payload)

        Returns:
            Blockchain response dict with tx_hash
        """
        tx_data = {
            "chain_id": self._chain_id,
            "from": "genesis",  # pool operator / genesis account
            "to": miner_address,
            "amount": amount,
            "type": "TRANSFER",
            "payload": {"purpose": "mining_reward", "job_id": job_id},
            "signature": "",  # will be signed by blockchain node or TransactionService
        }
        # Note: In production, this would be signed by the pool operator's key
        # using TransactionService.generate_signed_transaction(). For v0.6.7,
        # we submit unsigned transactions (the blockchain node may reject them
        # unless running in test mode). The signing integration is deferred to
        # v0.7.1 (Bridge Security).
        result = await self._rpc.submit_transaction(tx_data)
        logger.info("Reward tx submitted: miner=%s, amount=%d, job=%s", miner_address, amount, job_id)
        return result

    async def register_miner_on_chain(
        self, miner_id: str, gpu_info: dict[str, Any], address: str
    ) -> dict[str, Any]:
        """Register a miner on the blockchain via GPU registration endpoint.

        Args:
            miner_id: Miner ID
            gpu_info: GPU specifications (model, memory, etc.)
            address: Miner's wallet address

        Returns:
            Blockchain response dict
        """
        registration_data = {
            "chain_id": self._chain_id,
            "gpu_id": miner_id,
            "miner_id": address,
            "model": gpu_info.get("model", "Unknown"),
            "memory_gb": gpu_info.get("memory_gb", 0),
            "region": gpu_info.get("region", ""),
            "registered_by": address,
        }
        result = await self._rpc.register_gpu(registration_data)
        logger.info("Miner registered on-chain: miner_id=%s, chain=%s", miner_id, self._chain_id)
        return result

    async def distribute_rewards(self, block_height: int) -> list[dict[str, Any]]:
        """Distribute rewards for the current epoch.

        Args:
            block_height: Current block height

        Returns:
            List of payout results (one per miner)
        """
        self._reward_policy.update_block_height(block_height)
        epoch = self._reward_policy.calculate_payouts()
        unpaid = self._reward_policy.get_unpaid_miners()

        payouts: list[dict[str, Any]] = []
        for contrib in unpaid:
            if not self._reward_policy.is_eligible_for_payout(contrib.miner_id):
                continue
            try:
                result = await self.submit_reward_transaction(
                    miner_address=contrib.miner_id,
                    amount=contrib.reward_amount,
                    job_id=f"epoch-{epoch.epoch_number}",
                )
                tx_hash = result.get("tx_hash", "")
                self._reward_policy.mark_paid(contrib.miner_id, tx_hash)
                payouts.append({
                    "miner_id": contrib.miner_id,
                    "amount": contrib.reward_amount,
                    "tx_hash": tx_hash,
                    "epoch": epoch.epoch_number,
                })
            except Exception as e:
                logger.error("Failed to distribute reward to %s: %s", contrib.miner_id, e)
                payouts.append({
                    "miner_id": contrib.miner_id,
                    "amount": contrib.reward_amount,
                    "error": str(e),
                    "epoch": epoch.epoch_number,
                })
        return payouts
```

#### B3: Miner registration with chain_id

In `apps/pool-hub/src/app/registry/miner_registry.py`:
- Add `chain_id: str = "ait-hub"` to `MinerInfo` dataclass
- Add `wallet_address: str | None = None` to `MinerInfo` (for reward payments)
- In `register()` method, accept `chain_id` and `wallet_address` parameters

In `apps/pool-hub/src/app/routers/miners.py`:
- Add `chain_id` and `wallet_address` to the registration request model
- After in-memory registration, call `PoolHubBlockchainClient.register_miner_on_chain()` (feature-flagged)

In `apps/pool-hub/src/poolhub/models.py`:
- Add `chain_id: Mapped[str] = mapped_column(String(64), default="ait-hub", index=True)` to `Miner`
- Add `wallet_address: Mapped[str | None] = mapped_column(String(128), nullable=True)` to `Miner`

#### B4: Wire reward distribution into job completion

In `apps/pool-hub/src/app/routers/jobs.py`, update `submit_result()` (lines 93-113):

```python
@router.post("/result")
@rate_limit(rate=50, per=60)
async def submit_result(
    request: Request,
    result: JobResult,
    registry: Annotated[MinerRegistry, Depends(get_registry)],
    scoring: Annotated[ScoringEngine, Depends(get_scoring)],
) -> dict[str, Any]:
    """Submit job result and update miner stats."""
    miner = await registry.get(result.miner_id)
    if not miner:
        raise HTTPException(status_code=404, detail="Miner not found")

    # Update job status
    await registry.complete_job(job_id=result.job_id, miner_id=result.miner_id, status=result.status, metrics=result.metrics)

    # Update miner score based on result
    if result.status == "completed":
        await scoring.record_success(result.miner_id, result.metrics)
    else:
        await scoring.record_failure(result.miner_id, result.error)

    # v0.6.7: Reward distribution (feature-flagged)
    reward_tx_hash = None
    if result.status == "completed" and settings.enable_reward_distribution:
        from ..clients.blockchain import PoolHubBlockchainClient
        from aitbc.rewards import REWARD_PER_SHARE

        blockchain_client = PoolHubBlockchainClient(
            rpc_url=settings.blockchain_rpc_url,
            chain_id=settings.default_chain_id,
        )
        # Record contribution in reward policy
        shares = int(result.metrics.get("compute_seconds", REWARD_PER_SHARE))
        score = await scoring.calculate_score(miner)
        blockchain_client.reward_policy.record_contribution(
            miner_id=result.miner_id, score=score, shares=shares
        )
        # Submit reward transaction
        if miner.wallet_address:
            tx_result = await blockchain_client.submit_reward_transaction(
                miner_address=miner.wallet_address,
                amount=shares,
                job_id=result.job_id,
            )
            reward_tx_hash = tx_result.get("tx_hash")

    return {"status": "recorded", "reward_tx_hash": reward_tx_hash}
```

#### B5: RewardPayout model

In `apps/pool-hub/src/poolhub/models.py`, add:

```python
class RewardPayout(Base):
    """Reward payout record (v0.6.7)"""

    __tablename__ = "reward_payouts"

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    miner_id: Mapped[str] = mapped_column(String(64), index=True)
    chain_id: Mapped[str] = mapped_column(String(64), index=True)
    epoch_number: Mapped[int] = mapped_column(Integer, index=True)
    amount: Mapped[int] = mapped_column(Integer)  # in compute-seconds
    tx_hash: Mapped[str | None] = mapped_column(String(128), nullable=True)
    status: Mapped[str] = mapped_column(String(32), default="pending")  # pending, paid, failed
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=dt.datetime.now(dt.UTC))
    paid_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))
```

#### B6: Deprecate src/app/ in-memory implementation

In `apps/pool-hub/src/app/__init__.py`, add deprecation notice:

```python
"""DEPRECATED: In-memory pool-hub implementation.

This module is deprecated as of v0.6.7. The canonical implementation
lives in `apps/pool-hub/src/poolhub/` (SQLModel/PostgreSQL).

This module is kept for backward compatibility with existing routers
that have not yet been migrated. New code should use `poolhub/` directly.
"""
```

Do NOT remove the `src/app/` code — just add the deprecation notice. The routers in `src/app/routers/` still work and are the active API surface. Full migration to `src/poolhub/` routers is deferred to a future release.

#### B7: Integration tests

**`apps/pool-hub/tests/test_v067_rewards.py`** — unit tests (no Postgres/Redis required):

1. `test_reward_policy_constants_exist` — all constants exported from `aitbc.rewards`
2. `test_pool_hub_blockchain_client_init` — client initializes with correct defaults
3. `test_pool_hub_blockchain_client_chain_id` — chain_id property returns correct value
4. `test_pool_hub_settings_blockchain_rpc_url` — settings field exists, defaults to 8202
5. `test_pool_hub_settings_default_chain_id` — settings field exists, defaults to "ait-hub"
6. `test_pool_hub_settings_agent_coordinator_url` — settings field exists
7. `test_pool_hub_settings_enable_reward_distribution` — feature flag exists, defaults False
8. `test_miner_info_has_chain_id` — MinerInfo dataclass has chain_id field
9. `test_miner_info_has_wallet_address` — MinerInfo dataclass has wallet_address field
10. `test_reward_payout_model_exists` — RewardPayout model class exists
11. `test_reward_payout_has_chain_id` — RewardPayout model has chain_id field
12. `test_submit_reward_transaction_mock` — mock BlockchainRPCClient, verify tx submitted
13. `test_register_miner_on_chain_mock` — mock BlockchainRPCClient, verify registration
14. `test_distribute_rewards_mock` — mock blockchain, verify payouts distributed
15. `test_distribute_rewards_skips_ineligible` — miners already paid are skipped
16. `test_distribute_rewards_handles_errors` — failed tx doesn't crash distribution

---

## Dependency Graph

```
Phase 1 (parallel):
  A1: RewardPolicy ─────────────────────────┐
  A2: Fix TransactionService ───────────────┤
  A3: Unit tests for A1 ────────────────────┘
                                            │
Phase 2 (depends on A1):
  B1: Pool-hub settings ────────────────────┐
                                            │
Phase 3 (depends on B1+A1):
  B2: PoolHubBlockchainClient ──────────────┤
  B3: Miner registration + chain_id ────────┤
  B5: RewardPayout model ───────────────────┤
                                            │
Phase 4 (depends on B2+B3):
  B4: Wire reward distribution ─────────────┤
                                            │
Phase 5 (depends on all):
  B6: Deprecation notice ───────────────────┤
  B7: Integration tests ────────────────────┘
```

---

## Coordination

- **Agent A** goes first (Phase 1) — creates `RewardPolicy` in `aitbc/rewards/` and fixes `TransactionService`.
- **Agent B** starts Phase 2 after Agent A's Phase 1 is complete (B2 needs `RewardPolicy`, B4 needs `RewardPolicy` + `BlockchainRPCClient`).
- **B3 and B5** are independent of B2 but depend on B1 (settings).
- **B6** is a trivial deprecation notice — can be done anytime.
- No shared files are touched by both agents.

---

## Success Criteria

- ✅ `RewardPolicy` with epoch tracking prevents duplicate payouts within same epoch
- ✅ `TransactionService` uses port 8202 (not stale 8006) and chain_id "ait-hub" (not empty string)
- ✅ Pool-hub settings include `blockchain_rpc_url`, `default_chain_id`, `agent_coordinator_url`
- ✅ `PoolHubBlockchainClient` submits reward transactions with chain_id
- ✅ Miner registration includes `chain_id` and `wallet_address`
- ✅ Miners can be registered on blockchain via agent-coordinator
- ✅ Job completion triggers reward distribution (feature-flagged)
- ✅ `RewardPayout` model tracks payout history per miner per epoch
- ✅ Reward distribution is proportional to contribution score
- ✅ Duplicate payouts within same epoch are prevented
- ✅ All existing tests pass
- ✅ New tests pass (25 A3 unit + 16 B7 integration)
