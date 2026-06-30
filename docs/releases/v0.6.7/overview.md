# v0.6.7 Pool Hub & Mining — Overview

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
- [Status Baseline](#status-baseline--verified-code-targets)
- [Already Fixed / Exists](#already-fixed--exists-verified--no-work-needed)
- [Architecture](#architecture-pool-hub-with-blockchain-rewards)
- [Task Split Overview](#task-split-overview)

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

---

## Architecture: Pool Hub with Blockchain Rewards

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

## Related Topics

- [Agent A Tasks](./agent-a.md) - Shared core implementation details
- [Agent B Tasks](./agent-b.md) - Apps & infrastructure implementation details

---

**Documentation Version**: 1.0
**Last Updated**: 2026-06-30
**Release**: v0.6.7 — Pool Hub & Mining
