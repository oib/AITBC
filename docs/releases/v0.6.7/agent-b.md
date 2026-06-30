# v0.6.7 Pool Hub & Mining — Agent B Tasks

**Last Updated**: 2026-06-30
**Version**: 1.0

**Agent**: Agent B (Apps & Infrastructure)

**Scope**: Add blockchain config to pool-hub settings, create a blockchain client, wire reward distribution into job completion, add chain_id to miner registration, register miners on blockchain via agent-coordinator, add `RewardPayout` model, and write integration tests.

**Working directory**: `/opt/aitbc/apps/pool-hub/`

**Verification command**:
```bash
cd /opt/aitbc && ./venv/bin/python -m ruff check apps/pool-hub/
cd /opt/aitbc && ./venv/bin/python -m pytest apps/pool-hub/tests/test_v067_rewards.py -q -o addopts="" --timeout=30
```

---

## Tasks

| # | Task | Priority | Files | Status |
|---|------|----------|-------|--------|
| B1 | Pool-hub settings: add `blockchain_rpc_url`, `default_chain_id`, `agent_coordinator_url`, reward config | 🔴 P0 | `apps/pool-hub/src/poolhub/settings.py` | ✅ |
| B2 | Create `PoolHubBlockchainClient` — wraps `BlockchainRPCClient` for reward tx submission + miner registration | 🔴 P0 | `apps/pool-hub/src/poolhub/clients/blockchain.py` (new) | ✅ |
| B3 | Add `chain_id` to miner registration + register on blockchain via agent-coordinator | 🔴 P0 | `apps/pool-hub/src/app/routers/miners.py`, `apps/pool-hub/src/app/registry/miner_registry.py`, `apps/pool-hub/src/poolhub/models.py` | ✅ |
| B4 | Wire reward distribution into `jobs.py:submit_result()` — calculate reward, submit tx, track payout | 🔴 P0 | `apps/pool-hub/src/app/routers/jobs.py` | ✅ |
| B5 | Add `RewardPayout` SQLModel + epoch tracking model | Medium | `apps/pool-hub/src/poolhub/models.py` | ✅ |
| B6 | Deprecate `src/app/` in-memory implementation — add deprecation notice, route all new code through `src/poolhub/` | Low | `apps/pool-hub/src/app/__init__.py` (deprecation notice) | ✅ |
| B7 | Integration tests — reward lifecycle, chain_id, epoch tracking, duplicate payout prevention | 🔴 P0 | `apps/pool-hub/tests/test_v067_rewards.py` (new) | ✅ |

---

## B1: Pool-hub settings

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

---

## B2: PoolHubBlockchainClient

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

---

## B3: Miner registration with chain_id

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

---

## B4: Wire reward distribution into job completion

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

---

## B5: RewardPayout model

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

---

## B6: Deprecate src/app/ in-memory implementation

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

---

## B7: Integration tests

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

---

## Related Topics

- [Overview](./overview.md) - Release overview and status baseline
- [Agent A Tasks](./agent-a.md) - Shared core implementation details

---

**Documentation Version**: 1.0
**Last Updated**: 2026-06-30
**Release**: v0.6.7 — Pool Hub & Mining
**Agent**: Agent B (Apps & Infrastructure)
