# Orphan Models Audit — coordinator-api `app/domain/`

**Produced**: 2026-06-24 (follow-up to `context_import_audit.md`)
**Scope**: The 17 models listed in `context_import_audit.md` §"Remaining `app/domain/` models" as having "zero context imports".
**Method**: Grepped all importers across `apps/coordinator-api/` (src + tests) AND the full repo for each model, using multiple import patterns:
- `from app.domain.<model> import` (absolute)
- `from ..domain.<model> import` (2-dot relative)
- `from ...domain.<model> import` (3-dot relative)
- `from ....domain.<model> import` (4-dot relative — **missed by the original audit**)
- `from ..domain import <Name>` (name import via `__init__.py` re-export — **missed by the original audit**)

---

## Headline Findings

1. **The audit said "14 models" but listed 17.** The count in `context_import_audit.md` line 253 ("These 14 models") is wrong — the list on line 255 contains 17 names. All 17 were audited.
2. **5 of the 17 were incorrectly classified as orphans** due to two grep gaps in the original audit:
   - **4-dot relative imports** (`....domain.X`) were not matched — `governance` is actively imported by `contexts/governance/` (3 importers).
   - **Name imports via `__init__.py` re-exports** (`from ..domain import X`) were not matched — `job`, `job_receipt`, `miner`, `user` are re-exported by `app/domain/__init__.py` and imported by name throughout top-level `app/` code.
3. **Only 1 model is true dead code**: `pricing_models.py` (zero importers anywhere).
4. **16 of 17 are "migrate"** (have live importers); **1 is "dead code"**.

---

## Classification Summary

| # | Model | Importers | Classification | Notes |
|---|-------|-----------|----------------|-------|
| 1 | `agent_portfolio` | 1 (intra-app) | **MIGRATE** | Only live importer: `services/agent_coordination/portfolio.py`. Cross-app import in `apps/agent-management/` is **broken** (file absent there, `# type: ignore[import-not-found]`). |
| 2 | `atomic_swap` | 2 | **MIGRATE** | `services/atomic_swap_service.py`, `schemas/atomic_swap.py`. |
| 3 | `bounty` | 3 src + 4 test | **MIGRATE** | `services/bounty_service.py`, `services/ecosystem_service.py`; tests: `tests/services/test_staking_service.py` (×2), `tests/integration/test_staking_lifecycle.py`, `tests/fixtures/staking_fixtures.py`. |
| 4 | `community` | 1 | **MIGRATE** | `services/community_service.py`. |
| 5 | `cross_chain_reputation` | 2 | **MIGRATE** | `reputation/engine.py`, `reputation/aggregator.py`. |
| 6 | `dao_governance` | 2 | **MIGRATE** | `schemas/dao_governance.py`, `contexts/governance/services/dao_governance_service.py` (4-dot relative). `services/governance_service.py` defines its **own** local `ProposalType` — not an importer. |
| 7 | `decentralized_memory` | 3 | **MIGRATE** | `services/zk_memory_verification.py`, `services/ipfs_storage_adapter.py`, `schemas/decentralized_memory.py`. |
| 8 | `developer_platform` | 3 | **MIGRATE** | `services/developer_platform_service.py`, `schemas/developer_platform.py`. (Counted as 3 because the service file has a multi-line import.) |
| 9 | `federated_learning` | 3 | **MIGRATE** | `services/federated_learning.py`, `schemas/federated_learning.py`. |
| 10 | `governance` | 3 | **MIGRATE** ⚠️ | **NOT an orphan** — audit gap. Imported by `contexts/governance/services/governance_service.py`, `contexts/governance/routers/governance.py`, `contexts/governance/routers/governance_enhanced.py` (all `....domain.governance`, 4-dot). Should move to `contexts/governance/domain/`. |
| 11 | `job` | 8+ | **MIGRATE** ⚠️ | **NOT an orphan** — audit gap. Re-exported by `domain/__init__.py`; imported by name (`from ..domain import Job`) in `main.py`, `core/lifespan.py`, `utils/cache_management.py`, `services/receipts.py`, `services/jobs.py`, `services/explorer.py`, `routers/admin.py` (×4). |
| 12 | `job_receipt` | 3 | **MIGRATE** ⚠️ | **NOT an orphan** — audit gap. Re-exported by `domain/__init__.py`; imported by name in `services/receipts.py`, `services/jobs.py`, `services/explorer.py`. |
| 13 | `miner` | 4+ | **MIGRATE** ⚠️ | **NOT an orphan** — audit gap. Re-exported by `domain/__init__.py`; imported by name in `services/miners.py`, `services/jobs.py`, `services/python_13_optimized.py`, `routers/admin.py` (×2). |
| 14 | `pricing_models` | **0** | **DEAD CODE** | Zero importers. All `pricing_models` grep hits are local variable/feature names (`routers/registry.py`, `scripts/enterprise_scaling.py`), not imports. Independent from `pricing_strategies.py` (no cross-import). Safe to delete. |
| 15 | `pricing_strategies` | 1 | **MIGRATE** | `routers/dynamic_pricing.py` (`..domain.pricing_strategies`). |
| 16 | `user` | 1+ | **MIGRATE** ⚠️ | **NOT an orphan** — audit gap. Re-exported by `domain/__init__.py`; imported by name (`from ..domain import User, Wallet`) in `routers/users.py`. |
| 17 | `wallet` | 2 | **MIGRATE** | `schemas/wallet.py` (`..domain.wallet`), `routers/users.py` (via `from ..domain import Wallet`). |

**Totals**: 16 MIGRATE, 1 DEAD CODE.

---

## Dead Code Detail

### `pricing_models.py` — DELETE

- **File**: `apps/coordinator-api/src/app/domain/pricing_models.py`
- **Importers**: 0 (verified across entire repo)
- **Content**: SQLModel definitions for pricing history/strategies/market metrics (`PricingStrategyType` enum, plus likely `PricingHistory`, `MarketMetrics` tables).
- **Relationship to `pricing_strategies.py`**: None. `pricing_strategies.py` is an independent dataclass-based module (`PricingStrategy` enum, `StrategyLibrary`). They do not import each other and define overlapping-but-separate `PricingStrategy`/`PricingStrategyType` enums.
- **Confusion source**: The 9 grep hits for `pricing_models` are all local variable names or feature-flag strings in `routers/registry.py` and `scripts/enterprise_scaling.py` — not imports of the domain module.
- **Recommendation**: Safe to delete. If any of its SQLModel tables exist in a production DB, coordinate a migration to drop them first.

---

## Migration Targets (for the 16 live models)

These models are imported by top-level `app/` code (services, routers, schemas) and/or by `contexts/` code. Migration destination depends on ownership:

| Model | Owning area | Suggested destination |
|-------|-------------|-----------------------|
| `agent_portfolio` | `services/agent_coordination/` | `contexts/agent_coordination/domain/agent_portfolio.py` |
| `atomic_swap` | top-level services | `contexts/atomic_swap/domain/` (new context) or keep in shared `app/domain/` |
| `bounty` | top-level services + tests | `contexts/bounty/domain/` (new context) or keep in shared `app/domain/` |
| `community` | `services/community_service.py` | `contexts/community/domain/` (new context) or keep |
| `cross_chain_reputation` | `reputation/` module | `contexts/reputation/domain/cross_chain_reputation.py` |
| `dao_governance` | `contexts/governance/` | `contexts/governance/domain/dao_governance.py` |
| `decentralized_memory` | top-level services | `contexts/decentralized_memory/domain/` (new) or keep |
| `developer_platform` | top-level services | `contexts/developer_platform/domain/` (new) or keep |
| `federated_learning` | top-level services | `contexts/federated_learning/domain/` (new) or keep |
| `governance` | `contexts/governance/` | `contexts/governance/domain/governance.py` |
| `job` | top-level (re-exported) | Shared kernel — keep in `app/domain/` (cross-cutting) |
| `job_receipt` | top-level (re-exported) | Shared kernel — keep in `app/domain/` |
| `miner` | top-level (re-exported) | Shared kernel — keep in `app/domain/` |
| `pricing_strategies` | `routers/dynamic_pricing.py` | `contexts/dynamic_pricing/domain/` (new) or keep |
| `user` | top-level (re-exported) | Shared kernel — keep in `app/domain/` |
| `wallet` | top-level | Shared kernel — keep in `app/domain/` (or `contexts/wallet/domain/`) |

**Note**: `job`, `job_receipt`, `miner`, `user` are re-exported by `app/domain/__init__.py` and used across many top-level modules — they function as a **shared kernel** already. Migrating them out would require updating the `__init__.py` and all name-imports. Lower risk to keep them in `app/domain/` (optionally rename to `app/shared_kernel/`).

---

## Audit Gaps in `context_import_audit.md`

The original audit (P2) used `grep -rn "from app\.domain\.\|from \.\.domain\."` which missed two import patterns:

1. **4-dot relative imports** (`from ....domain.X`) — used by `contexts/governance/` to reach `governance` and `dao_governance`. This caused `governance` to be falsely listed as an orphan.
2. **Name imports via `__init__.py`** (`from ..domain import X`) — used for the 5 re-exported models (`agent`, `job`, `job_receipt`, `miner`, `user`). This caused `job`, `job_receipt`, `miner`, `user` to be falsely listed as orphans. (`agent` was correctly captured in the original audit because it also has 2 `app.domain.agent` context imports.)

**Recommendation**: Update `context_import_audit.md` §"Remaining models" to correct the count (17 listed, not 14) and remove the 5 false orphans (`governance`, `job`, `job_receipt`, `miner`, `user`), leaving 12 genuine orphans (11 migrate + 1 dead code).

---

## Verification

- [x] All 17 listed models grepped across `apps/coordinator-api/` (src + tests) and full repo
- [x] Five import patterns checked (absolute, 2/3/4-dot relative, name-import via `__init__.py`)
- [x] `pricing_models` confirmed zero importers (all grep hits are local variables)
- [x] `agent_portfolio` cross-app import in `apps/agent-management/` confirmed broken (file absent, `type: ignore[import-not-found]`)
- [x] `governance`, `dao_governance` context imports confirmed via 4-dot relative pattern
- [x] `job`, `job_receipt`, `miner`, `user` confirmed re-exported by `domain/__init__.py` and imported by name
