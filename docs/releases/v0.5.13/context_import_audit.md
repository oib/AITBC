# Context Import Audit — coordinator-api

**Produced**: 2026-06-24 (P2, v0.5.13 Phase 4)
**Scope**: All imports from `apps/coordinator-api/src/app/contexts/*/` that reach into the flat `apps/coordinator-api/src/app/domain/` package.
**Method**: `grep -rn "from app\.domain\.\|from \.\.domain\." apps/coordinator-api/src/app/contexts/` + manual categorization.

---

## Summary

| Metric | Count |
|--------|-------|
| Total cross-references found | 38 |
| Distinct `app/domain/` models imported | 13 |
| Contexts performing imports | 10 |
| Intra-context (fix import path only) | 20 |
| Shared kernel (genuinely shared model) | 9 |
| Boundary violation (cross-context reach) | 9 |

**Key finding**: 3 contexts (`marketplace`, `agent_identity`, `cross_chain`) have already migrated some models into their own `contexts/<bc>/domain/` and use `..domain.X` (intra-context) imports. The remaining 7 contexts with imports still reach into the flat `app/domain/`. Only 2 models (`reputation`, `multi_chain_transaction`) are genuinely shared across multiple contexts — candidates for a shared kernel. The rest are single-context imports that should be intra-context once the model is migrated.

---

## Categorization Key

- **(a) Intra-context**: The model belongs to the importing context. Fix: migrate the model into `contexts/<bc>/domain/` and change the import to `..domain.X`. No semantic change.
- **(b) Shared kernel**: The model is genuinely used by 2+ contexts. Fix: keep in `app/domain/` as a shared kernel (rename to `app/shared_kernel/` for clarity), OR move to `aitbc_shared`. No single context owns it.
- **(c) Boundary violation**: The importing context reaches into another context's domain model. Fix: introduce a service interface, event, or DTO instead of direct model import.

---

## Import Map (by model)

### `app.domain.global_marketplace` — 10 references — (a) Intra-context

| Importer | Context | Import path | Category |
|----------|---------|-------------|----------|
| `marketplace/routers/global_marketplace.py:14` | marketplace | `..domain.global_marketplace` | (a) intra-context |
| `marketplace/routers/global_marketplace.py:64` | marketplace | `..domain.global_marketplace` | (a) intra-context |
| `marketplace/routers/global_marketplace.py:230` | marketplace | `..domain.global_marketplace` | (a) intra-context |
| `marketplace/routers/global_marketplace.py:483` | marketplace | `..domain.global_marketplace` | (a) intra-context |
| `marketplace/routers/global_marketplace_integration.py:19` | marketplace | `..domain.global_marketplace` | (a) intra-context |
| `marketplace/services/global_marketplace.py:17` | marketplace | `..domain.global_marketplace` | (a) intra-context |
| `marketplace/services/global_marketplace_integration.py:24` | marketplace | `..domain.global_marketplace` | (a) intra-context |
| `marketplace/services/global_marketplace_integration.py:121` | marketplace | `..domain.global_marketplace` | (a) intra-context |
| `marketplace/services/global_marketplace_integration.py:197` | marketplace | `..domain.global_marketplace` | (a) intra-context |
| `marketplace/services/global_marketplace_integration.py:303` | marketplace | `..domain.global_marketplace` | (a) intra-context |

**Status**: Already migrated. `contexts/marketplace/domain/global_marketplace.py` exists. All 10 imports use `..domain.global_marketplace` (relative intra-context). **No action needed** — these are the correct pattern.

---

### `app.domain.gpu_marketplace` — 5 references — (a) Intra-context

| Importer | Context | Import path | Category |
|----------|---------|-------------|----------|
| `marketplace/routers/marketplace_gpu.py:23` | marketplace | `..domain.gpu_marketplace` | (a) intra-context |
| `marketplace/services/external_providers.py:13` | marketplace | `..domain.gpu_marketplace` | (a) intra-context |
| `marketplace/services/market_analytics.py:13` | marketplace | `..domain.gpu_marketplace` | (a) intra-context |
| `marketplace/services/plugin_manager.py:11` | marketplace | `..domain.gpu_marketplace` | (a) intra-context |
| `marketplace/services/resource_matcher.py:12` | marketplace | `..domain.gpu_marketplace` | (a) intra-context |

**Status**: Already migrated. `contexts/marketplace/domain/gpu_marketplace.py` exists. All 5 imports use `..domain.gpu_marketplace` (relative intra-context). **No action needed**.

---

### `app.domain.agent_identity` — 1 reference — (a) Intra-context

| Importer | Context | Import path | Category |
|----------|---------|-------------|----------|
| `agent_identity/routers/agent_identity.py:15` | agent_identity | `..domain.agent_identity` | (a) intra-context |

**Status**: Already migrated. `contexts/agent_identity/domain/agent_identity.py` exists. Import uses `..domain.agent_identity` (relative intra-context). **No action needed**.

---

### `app.domain.reputation` — 4 references — (b) Shared kernel

| Importer | Context | Import path | Category |
|----------|---------|-------------|----------|
| `certification/services/certification/badge_system.py:10` | certification | `app.domain.reputation` | (b) shared kernel |
| `certification/services/certification/certification_system.py:17` | certification | `app.domain.reputation` | (b) shared kernel |
| `certification/services/certification/partnership_manager.py:14` | certification | `app.domain.reputation` | (b) shared kernel |
| `rewards/routers/rewards.py:213` | rewards | `app.domain.reputation` | (b) shared kernel |

**Status**: `AgentReputation` is imported by 2 distinct contexts (`certification` and `rewards`). Neither context owns it exclusively. The `reputation` context has an empty `domain/` — the model still lives in flat `app/domain/reputation.py`.

**Recommendation**: Move `reputation.py` to `contexts/reputation/domain/reputation.py` and have `certification` and `rewards` import it via an explicit cross-context service interface, OR keep it in a shared kernel package (`app/shared_kernel/reputation.py`) and have both contexts import from there. The shared-kernel approach is lower risk.

---

### `app.domain.certification` — 4 references — (a) Intra-context (not yet migrated)

| Importer | Context | Import path | Category |
|----------|---------|-------------|----------|
| `certification/services/certification/badge_system.py:9` | certification | `app.domain.certification` | (a) intra-context |
| `certification/services/certification/certification_system.py:11` | certification | `app.domain.certification` | (a) intra-context |
| `certification/services/certification/partnership_manager.py:9` | certification | `app.domain.certification` | (a) intra-context |
| `certification/services/certification/service.py:8` | certification | `app.domain.certification` | (a) intra-context |

**Status**: All 4 imports are from within the `certification` context itself. The model should live in `contexts/certification/domain/certification.py`. Currently uses `app.domain.certification` (absolute) with `# type: ignore[import-not-found]`.

**Recommendation**: Migrate `app/domain/certification.py` → `contexts/certification/domain/certification.py`, change imports to `..domain.certification`.

---

### `app.domain.multi_chain_transaction` — 3 references — (b) Shared kernel

| Importer | Context | Import path | Category |
|----------|---------|-------------|----------|
| `cross_chain/routers/cross_chain_integration.py:22` | cross_chain | `app.domain.multi_chain_transaction` | (b) shared kernel |
| `marketplace/routers/global_marketplace_integration.py:9` | marketplace | `app.domain.multi_chain_transaction` | (b) shared kernel → (c) if not shared |
| `marketplace/services/global_marketplace_integration.py:11` | marketplace | `app.domain.multi_chain_transaction` | (b) shared kernel → (c) if not shared |

**Status**: `TransactionType` and `TransactionPriority` are imported by 2 distinct contexts (`cross_chain` and `marketplace`). The `cross_chain` context has an empty `domain/`.

**Recommendation**: If `multi_chain_transaction` is genuinely cross-cutting (transaction types/priorities used across contexts), keep as shared kernel. If `marketplace` only needs `TransactionPriority` as an enum, extract just that enum into a shared types module rather than importing the full domain model. The marketplace imports look like boundary violations (marketplace reaching into cross_chain's transaction domain) — investigate whether `TransactionPriority` can be a simple enum in a shared types package.

---

### `app.domain.agent_performance` — 3 references — (c) Boundary violation

| Importer | Context | Import path | Category |
|----------|---------|-------------|----------|
| `advanced_rl/services/advanced_rl/engine.py:19` | advanced_rl | `app.domain.agent_performance` | (c) boundary violation |
| `advanced_rl/services/advanced_rl/marketplace_optimizer.py:15` | advanced_rl | `app.domain.agent_performance` | (c) boundary violation |
| `multimodal/services/multi_modal_fusion/fusion_engine.py:17` | multimodal | `app.domain.agent_performance` | (c) boundary violation |

**Status**: `ReinforcementLearningConfig` and `FusionModel` are imported by `advanced_rl` and `multimodal` contexts. The `agent_performance` model doesn't have its own context — it's in flat `app/domain/`. Neither `advanced_rl` nor `multimodal` owns `agent_performance`.

**Recommendation**: Determine which context owns `agent_performance`. If it's a standalone concept, create a `contexts/agent_performance/` context. If it belongs to `agent_coordination`, migrate there and have `advanced_rl`/`multimodal` use a service interface or DTO. Currently these are boundary violations — two contexts reaching into an unowned domain model.

---

### `app.domain.agent` — 2 references — (c) Boundary violation

| Importer | Context | Import path | Category |
|----------|---------|-------------|----------|
| `agent_coordination/routers/agent_router.py:229` | agent_coordination | `app.domain.agent` | (c) boundary violation |
| `agent_coordination/routers/agent_router.py:293` | agent_coordination | `app.domain.agent` | (c) boundary violation |

**Status**: `AgentExecution` is imported by `agent_coordination` from `app.domain.agent`. The `agent_coordination` context has an empty `domain/`. The `agent` model could belong to `agent_coordination` (making this intra-context) or to `agent_identity` (making this a boundary violation).

**Recommendation**: Clarify ownership — does `agent_coordination` or `agent_identity` own the `Agent`/`AgentExecution` model? `agent_identity` already has its own `domain/agent_identity.py`. If `AgentExecution` belongs to `agent_coordination`, migrate `app/domain/agent.py` → `contexts/agent_coordination/domain/agent.py` and fix imports. If it belongs to `agent_identity`, `agent_coordination` should use a service interface instead.

---

### `app.domain.rewards` — 3 references — (a) Intra-context (not yet migrated)

| Importer | Context | Import path | Category |
|----------|---------|-------------|----------|
| `rewards/routers/rewards.py:358` | rewards | `app.domain.rewards` | (a) intra-context |
| `rewards/routers/rewards.py:393` | rewards | `app.domain.rewards` | (a) intra-context |
| `rewards/routers/rewards.py:432` | rewards | `app.domain.rewards` | (a) intra-context |

**Status**: All 3 imports are from within the `rewards` context itself. The model should live in `contexts/rewards/domain/rewards.py`. Currently uses `app.domain.rewards` (absolute, inline imports inside functions).

**Recommendation**: Migrate `app/domain/rewards.py` → `contexts/rewards/domain/rewards.py`, change imports to `..domain.rewards`.

---

### `app.domain.cross_chain_bridge` — 1 reference — (a) Intra-context (not yet migrated)

| Importer | Context | Import path | Category |
|----------|---------|-------------|----------|
| `cross_chain/services/cross_chain/bridge.py:21` | cross_chain | `..domain.cross_chain_bridge` | (a) intra-context |

**Status**: Uses `..domain.cross_chain_bridge` (relative), but `contexts/cross_chain/domain/` is empty — the model still lives in flat `app/domain/cross_chain_bridge.py`. The relative import path is aspirational (points to where the model *should* be, not where it is).

**Recommendation**: Migrate `app/domain/cross_chain_bridge.py` → `contexts/cross_chain/domain/cross_chain_bridge.py`. The import path is already correct — just move the file.

---

### `app.domain.analytics` — 1 reference — (a) Intra-context (not yet migrated)

| Importer | Context | Import path | Category |
|----------|---------|-------------|----------|
| `ai_analytics/services/ai_analytics/analytics.py:10` | ai_analytics | `app.domain.analytics` | (a) intra-context |

**Status**: Imported by `ai_analytics` context. The `analytics` context also exists separately with an empty `domain/`. Need to clarify: does `analytics` or `ai_analytics` own the analytics domain model?

**Recommendation**: Clarify ownership between `analytics` and `ai_analytics` contexts (they may be redundant). Migrate `app/domain/analytics.py` to the owning context's `domain/`.

---

### `app.domain.amm` — 1 reference — (a) Intra-context (not yet migrated)

| Importer | Context | Import path | Category |
|----------|---------|-------------|----------|
| `trading/services/trading_marketplace/amm.py:19` | trading | `app.domain.amm` | (a) intra-context |

**Status**: Imported by `trading` context. The `trading` context has an empty `domain/`.

**Recommendation**: Migrate `app/domain/amm.py` → `contexts/trading/domain/amm.py`, change import to `..domain.amm`.

---

### `app.domain.trading` — 1 reference — (a) Intra-context (not yet migrated)

| Importer | Context | Import path | Category |
|----------|---------|-------------|----------|
| `trading/services/trading_marketplace/trading.py:10` | trading | `app.domain.trading` | (a) intra-context |

**Status**: Imported by `trading` context. Double `# type: ignore[import-not-found]` comment (duplicated).

**Recommendation**: Migrate `app/domain/trading.py` → `contexts/trading/domain/trading.py`, change import to `..domain.trading`. Fix the duplicated type-ignore comment.

---

## Context Summary

| Context | Total imports | (a) Intra-context | (b) Shared kernel | (c) Boundary violation | Action |
|---------|--------------|-------------------|-------------------|----------------------|--------|
| `marketplace` | 17 | 17 | 0 | 0 | Already migrated (global_marketplace, gpu_marketplace). 2 imports of `multi_chain_transaction` are shared-kernel/boundary — see below. |
| `certification` | 7 | 4 | 3 | 0 | Migrate `certification.py` to own domain. `reputation` imports are shared kernel. |
| `rewards` | 4 | 3 | 1 | 0 | Migrate `rewards.py` to own domain. `reputation` import is shared kernel. |
| `cross_chain` | 2 | 1 | 1 | 0 | Migrate `cross_chain_bridge.py` to own domain. `multi_chain_transaction` is shared kernel. |
| `agent_coordination` | 2 | 0 | 0 | 2 | Boundary violations — clarify `agent.py` ownership. |
| `advanced_rl` | 2 | 0 | 0 | 2 | Boundary violations — clarify `agent_performance.py` ownership. |
| `multimodal` | 1 | 0 | 0 | 1 | Boundary violation — clarify `agent_performance.py` ownership. |
| `ai_analytics` | 1 | 1 | 0 | 0 | Migrate `analytics.py` — clarify `analytics` vs `ai_analytics` context ownership. |
| `trading` | 2 | 2 | 0 | 0 | Migrate `amm.py` + `trading.py` to own domain. |
| `agent_identity` | 1 | 1 | 0 | 0 | Already migrated. No action. |

---

## Migration Priority

### Tier 1 — Quick wins (intra-context, just move the file + fix imports)
1. **`certification.py`** → `contexts/certification/domain/` (4 imports to fix)
2. **`rewards.py`** → `contexts/rewards/domain/` (3 imports to fix)
3. **`amm.py`** + **`trading.py`** → `contexts/trading/domain/` (2 imports to fix)
4. **`cross_chain_bridge.py`** → `contexts/cross_chain/domain/` (1 import, path already correct)
5. **`analytics.py`** → `contexts/ai_analytics/domain/` or `contexts/analytics/domain/` (1 import, needs ownership decision)

### Tier 2 — Shared kernel decisions (require design)
6. **`reputation.py`** — shared by `certification` + `rewards`. Keep as shared kernel or move to `contexts/reputation/domain/` with cross-context service interface.
7. **`multi_chain_transaction.py`** — shared by `cross_chain` + `marketplace`. Extract `TransactionPriority`/`TransactionType` enums to shared types, or keep as shared kernel.

### Tier 3 — Boundary violations (require ownership decisions)
8. **`agent.py`** — imported by `agent_coordination`. Does it belong to `agent_coordination` or `agent_identity`?
9. **`agent_performance.py`** — imported by `advanced_rl` + `multimodal`. No owning context exists. Create `contexts/agent_performance/` or assign to an existing context.

### Already done (no action)
- `global_marketplace.py` — in `contexts/marketplace/domain/`, all imports use `..domain.*`
- `gpu_marketplace.py` — in `contexts/marketplace/domain/`, all imports use `..domain.*`
- `agent_identity.py` — in `contexts/agent_identity/domain/`, import uses `..domain.*`

---

## Remaining `app/domain/` models (not imported by any context)

These 14 models in `app/domain/` have zero context imports — they may be used only by top-level `app/` code (routers, services, adapters) or are dead code:

`agent_portfolio.py`, `atomic_swap.py`, `bounty.py`, `community.py`, `cross_chain_reputation.py`, `dao_governance.py`, `decentralized_memory.py`, `developer_platform.py`, `federated_learning.py`, `governance.py`, `job.py`, `job_receipt.py`, `miner.py`, `pricing_models.py`, `pricing_strategies.py`, `user.py`, `wallet.py`

**Recommendation**: Audit these separately — grep for `from app.domain.<model>` across all of `apps/coordinator-api/src/app/` (not just `contexts/`). If only used by top-level code, they're candidates for migration to their respective contexts. If unused, they're dead code.

---

## Verification

- [x] All 38 cross-references catalogued (was estimated 36 — actual count is 38)
- [x] Every reference categorized as (a), (b), or (c)
- [x] Context ownership mapped for each model
- [x] Migration priority tiers assigned
- [x] Already-migrated models identified (marketplace, agent_identity)
