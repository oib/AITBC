# P2: Cross-Context Import Audit into app/domain/

**Date:** 2026-06-24
**Scope:** `apps/coordinator-api/src/app/contexts/` → `app/domain/` coupling

---

## Summary

The coordinator-api has a flat `app/domain/` package with 27 model files shared across 36 bounded contexts in `app/contexts/`. Contexts import from this flat layer via 4 different relative-import patterns, only one of which is correct (context's own `domain/` subdir). The result is **40 cross-context imports** into the shared domain layer and **10 broken imports** that fail at runtime (masked by `# type: ignore[import-not-found]`).

Only 3 of 36 contexts have their own `domain/` subdirectory with actual model files: `marketplace` (3 files), `agent_identity` (1 file), `payments` (1 file). The remaining 33 contexts depend entirely on the flat `app/domain/` layer.

---

## Import Categories

| Category | Pattern | Resolves to | Count | Status |
|---|---|---|---|---|
| 1 | `from app.domain.X import ...` | `app.domain.X` (flat shared) | 14 | Cross-context coupling |
| 2 | `from ..domain.X import ...` | `app.contexts.<ctx>.domain.X` (own) | 22 | 16 correct, **6 broken** |
| 3 | `from ...domain.X import ...` | `app.contexts.domain.X` (non-existent) | 4 | **All 4 broken** |
| 4 | `from ....domain.X import ...` | `app.domain.X` (flat shared) | 24 | Cross-context coupling |
| 5 | `from ....domain import ...` | `app.domain.__init__` (flat shared) | 2 | Cross-context coupling |

**Totals:** 40 cross-context imports to flat `app/domain/` + 10 broken imports = **50 problematic import statements** across 48 files.

22 of these carry `# type: ignore[import-not-found]` — mypy cannot resolve them.

---

## Broken Imports (10)

### Category 3: `from ...domain.X` — resolves to non-existent `app.contexts.domain`

| File | Import | Should resolve to |
|---|---|---|
| `advanced_rl/services/advanced_rl/engine.py:19` | `from ...domain.agent_performance import ReinforcementLearningConfig` | `app.domain.agent_performance` |
| `advanced_rl/services/advanced_rl/marketplace_optimizer.py:15` | `from ...domain.agent_performance import ReinforcementLearningConfig` | `app.domain.agent_performance` |
| `edge_gpu/services/edge_gpu_service.py:8` | `from ...domain.gpu_marketplace import ConsumerGPUProfile, EdgeGPUMetrics, GPUArchitecture` | `app.domain.gpu_marketplace` |
| `multimodal/services/multi_modal_fusion/fusion_engine.py:17` | `from ...domain.agent_performance import FusionModel` | `app.domain.agent_performance` |

**Root cause:** These files are 3 levels deep (`contexts/<ctx>/services/<pkg>/file.py`), so `...domain` resolves to `app.contexts.domain` which doesn't exist. They should use `....domain` (4 dots) or `app.domain`.

### Category 2: `from ..domain.X` — context has `domain/` dir but module doesn't exist

| File | Import | Missing file |
|---|---|---|
| `cross_chain/services/cross_chain/bridge.py:21` | `from ..domain.cross_chain_bridge import ...` | `contexts/cross_chain/domain/cross_chain_bridge.py` |
| `rewards/routers/rewards.py:213` | `from ..domain.reputation import AgentReputation` | `contexts/rewards/domain/reputation.py` |
| `rewards/routers/rewards.py:358` | `from ..domain.rewards import RewardTierConfig` | `contexts/rewards/domain/rewards.py` |
| `rewards/routers/rewards.py:393` | `from ..domain.rewards import RewardMilestone` | `contexts/rewards/domain/rewards.py` |
| `rewards/routers/rewards.py:432` | `from ..domain.rewards import RewardDistribution` | `contexts/rewards/domain/rewards.py` |
| `trading/services/trading_marketplace/amm.py:19` | `from ..domain.amm import ...` | `contexts/trading/domain/amm.py` |

**Root cause:** These contexts have an empty `domain/__init__.py` but no actual model files. The imports resolve to the context's own `domain/` package but the specific module doesn't exist there. They should import from `app.domain.X` instead.

---

## Cross-Context Coupling Map (40 imports)

### Domain module → importing contexts

| Domain module | Importing contexts | Import count | Owner context (proposed) |
|---|---|---|---|
| `domain.agent` | advanced_rl, agent_coordination, agent_identity, multimodal, security | 5 | agent_coordination |
| `domain.agent_performance` | advanced_rl, agent_coordination, multimodal | 2 (+2 broken) | agent_coordination |
| `domain.reputation` | certification, reputation, rewards | 6 (+1 broken) | reputation |
| `domain.bounty` | bounty, staking | 3 | bounty |
| `domain.multi_chain_transaction` | cross_chain, marketplace | 3 | cross_chain |
| `domain.governance` | governance | 3 | governance |
| `domain.dao_governance` | governance | 1 | governance |
| `domain.certification` | certification | 5 | certification |
| `domain.wallet` | wallet | 2 | wallet |
| `domain.trading` | trading | 2 | trading |
| `domain.amm` | trading | 1 (+1 broken) | trading |
| `domain.rewards` | rewards | 2 (+3 broken) | rewards |
| `domain.analytics` | ai_analytics, analytics | 2 | analytics |
| `domain.community` | community | 1 | community |
| `domain.developer_platform` | developer_platform | 1 | developer_platform |
| `domain.__init__` (Agent, Miner, etc.) | marketplace, multimodal | 2 | shared/core |
| `domain.cross_chain_bridge` | cross_chain | 1 (+1 broken) | cross_chain |
| `domain.gpu_marketplace` | edge_gpu, marketplace | 1 (+1 broken) | marketplace |

### Most coupled domain modules

1. **`domain.reputation`** — 3 contexts (certification, reputation, rewards). `rewards` and `certification` depend on `reputation`'s models — genuine cross-context dependency.
2. **`domain.agent`** — 5 contexts. Core agent model shared widely.
3. **`domain.bounty`** — 2 contexts (bounty, staking). `staking` reuses bounty's `AgentStake`/`PerformanceTier`.
4. **`domain.multi_chain_transaction`** — 2 contexts (cross_chain, marketplace). `marketplace` uses `TransactionPriority` for cross-chain offers.

---

## Orphaned Domain Modules (not imported by any context)

| Module | Imported outside contexts? | Status |
|---|---|---|
| `agent_portfolio` | 1 (services) | Active |
| `atomic_swap` | 2 (services, schemas) | Active |
| `cross_chain_reputation` | 2 (reputation/) | Active |
| `decentralized_memory` | 3 (services, schemas) | Active |
| `federated_learning` | 2 (services, schemas) | Active |
| `job` | 11 (routers, services, core) | Active — core model |
| `job_receipt` | 10 (routers, services) | Active — core model |
| `miner` | 6 (routers, services, models) | Active — core model |
| `pricing_models` | **0** | **Dead code** |
| `pricing_strategies` | 1 (routers) | Active |
| `user` | 1 (routers) | Active — core model |

**`pricing_models` has zero importers anywhere** — candidate for deletion.

---

## Contexts With Own domain/ Subdir

| Context | domain/ files | Status |
|---|---|---|
| `marketplace` | `global_marketplace.py`, `gpu_marketplace.py`, `marketplace.py` | ✅ Has own models |
| `agent_identity` | `agent_identity.py` | ✅ Has own models |
| `payments` | `payment.py` | ✅ Has own models |
| 33 others | empty `__init__.py` or no `domain/` | ❌ Depend on flat `app/domain/` |

---

## Recommendations

### Immediate fixes (P2 scope — no structural change)

1. **Fix 10 broken imports** — repoint to correct module path. These are runtime failures masked by `# type: ignore`. **✅ DONE** (see commit below).
   - 9 imports repointed to `app.domain.X` (flat shared domain)
   - 1 import repointed to `app.contexts.marketplace.domain.gpu_marketplace` (cross-context, model lives in marketplace's domain/)
   - Also fixed 2 non-domain broken imports in `edge_gpu_service.py` (`app.data`, `app.storage`)
2. **Delete `pricing_models.py`** — zero importers, dead code. (Not yet done — deferred to P5.)

### P3 (READMEs + `__all__`)

3. Add `__all__` to each `app/domain/*.py` to declare public API surface.
4. Add `README.md` to each context explaining its domain ownership and dependencies.

### P4 (boundary decision)

5. Decide: move domain models into owning context's `domain/` subdir, or keep flat `app/domain/` as a shared kernel?
   - **Option A (move):** Each context owns its models. Cross-context deps become explicit imports. 40 imports to repoint. High effort, clean result.
   - **Option B (shared kernel):** Keep flat `app/domain/` as intentional shared layer. Fix broken imports, remove `type: ignore`, document the shared kernel contract. Low effort, accepts coupling.

### P5 (restructure — gated on P4)

6. Execute the chosen boundary decision. Only after P4 is decided.
