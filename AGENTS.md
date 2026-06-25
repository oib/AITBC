# AGENTS.md — AITBC Project Rules & Agent Plans

This file is the source of truth for project conventions, verification commands, and per-agent task plans. Agent-specific plans live at `docs/releases/<version>/AGENTS.md`; this root file holds the stable conventions and the **current** in-flight plan.

## Project Layout

- `aitbc/` — shared core library (types, config, db, logging, queues, crypto, network, agent_bridge, agent_protocols, agent_registry, etc.)
- `apps/` — microservices (coordinator-api, blockchain-node, exchange, wallet, marketplace, miner, edge, gpu, governance, …)
- `cli/` — `aitbc_cli` command-line tool
- `packages/py/` — publishable Python packages
- `tests/` — `unit/`, `integration/`, `e2e/`, `coordinator/`
- `scripts/` — ops, deployment, monitoring, migration, security
- `docs/releases/<version>/` — per-release changelogs and agent task assignment

## Verification Commands

```bash
# Type check (shared core)
./venv/bin/python -m mypy --show-error-codes aitbc/

# Lint (whole repo)
./venv/bin/python -m ruff check .

# Tests (note: requires pytest-rerunfailures + pytest-asyncio; add -o addopts="" to bypass if missing)
./venv/bin/python -m pytest tests/unit -q
./venv/bin/python -m pytest tests/integration -q

# Coordinator-api tests (needs PYTHONPATH=src and aitbc_shared installed)
cd apps/coordinator-api && PYTHONPATH=src ../../venv/bin/python -m pytest tests -q -o addopts=""
```

## Conventions

- **Python 3.13**, line length 127 (black + ruff), `target-version = "py313"`.
- **SQLModel** for ORM models in `apps/coordinator-api/src/app/domain/`. Add `index=True` on columns filtered/ordered at the SQL layer. Composite indexes via `sqlalchemy.Index(...)` in `__table_args__` tuple.
- **Config**: `pydantic_settings.BaseSettings`. Shared base lives in `apps/shared-core/src/app/core/config.py` (`ServiceSettings`, `DatabaseConfig`). New services should subclass these rather than redefining `DatabaseConfig`.
- **Logging**: `aitbc.aitbc_logging` is canonical. `aitbc/log_utils/logging.py` is a thin re-export shim — do not duplicate logging setup.
- **Constants**: `aitbc/constants.py` sources `REPO_DIR` from `AITBC_REPO_DIR` env var (defaults to `/opt/aitbc`).
- **DB init**: services call `SQLModel.metadata.create_all` (or `Base.metadata.create_all`). `create_all` only adds indexes to fresh DBs; for existing DBs add an Alembic migration under `apps/coordinator-api/alembic/versions/` using `if_not_exists=True`.
- **Commit style**: `type(scope): subject` — see `git log --oneline`. Include `Generated with [Devin]` trailer + Co-Authored-By when committing via Devin.
- **Do not** edit files outside your agent's ownership without coordinating (see conflict boundaries in the release plan).

## Agent Roles (stable across releases)

| Agent | Domain | Owns |
|-------|--------|------|
| **Agent A** | Type safety & shared core (`aitbc/`) | All of `aitbc/` except `aitbc/constants.py`, `aitbc/log_utils/` |
| **Agent B** | Bug fixes, infrastructure & apps | `aitbc/constants.py`, `aitbc/log_utils/`, all `apps/`, `cli/`, systemd config |

**Conflict boundary**: both agents must not edit the same file. Shared files (`aitbc/database/replica.py`, `aitbc/network/circuit_breaker.py`, agent bridge imports) are sequenced — see the release plan's Coordination Protocol.

---

## Current Plan — v0.5.12 (Agent B) — ✅ COMPLETE

**Release theme**: Duplication elimination & large-file decomposition in `apps/` and `cli/`.

**All B1–B7 tasks complete** (verified 2026-06-24). Full task table, detailed instructions, execution order, and coordination notes moved to <ref_file file="/opt/aitbc/docs/releases/v0.5.12/change.log" /> (see "Completed Work (Agent B)" section).

**Status of prior phases**:
- Phase 1 (quick wins): ✅ DONE (committed in `38a0c70cc`)
- Phase 2 (test split): ✅ DONE — `tests/integration/test_agent_coordinator.py` (3,177 lines) split into 9 domain files; original deleted.
- Phase 3 (dedup + indexes): ✅ DONE — B1–B7 all complete. Verified 2026-06-24.
- Phase 4 (coordinator-api bounded context): P1 ✅ DONE, P2 ✅ DONE, P3 ✅ DONE, P4 ✅ DONE, P5 ⏭️ SKIPPED. **Phase 4 complete.**

**Agent B working directory**: `/opt/aitbc/` (cross-cutting: `apps/`, `cli/`).

**Verification**:
```bash
cd /opt/aitbc && ./venv/bin/python -m ruff check apps/ cli/ && ./venv/bin/python -m mypy --show-error-codes apps/coordinator-api/src apps/blockchain-node/src
```

---

## Open Tasks — v0.5.13 (Agent B): Phase 4 — coordinator-api bounded context — ✅ COMPLETE

**Full task details, grounding facts, and corrections from the rejected draft are in** <ref_file file="/opt/aitbc/docs/releases/v0.5.12/change.log" /> (see "Phase 4 Open Tasks" section).

### Task Summary

| # | Task | Priority | Status |
|---|------|----------|--------|
| P1 | Standardize on PyJWT — migrate `jwt_auth.py` from `python-jose` to `PyJWT`, drop `python-jose` dep | High | ✅ DONE |
| P2 | Audit + document cross-context imports into `app/domain/` | High | ✅ DONE |
| P2-followup | Orphan-models audit — classify 17 `app/domain/` models with zero context imports | Medium | ✅ DONE |
| P3 | Add `README.md` to each `contexts/*/` + `__all__` to `__init__.py` files | Medium | ✅ DONE |
| P4 | Decide agent-coordinator service boundary (fold in vs keep separate) + add README | Medium | ✅ DONE |
| P5 | Restructure agent-coordinator into bounded context (GATED on P4) | Low | ⏭️ SKIPPED (P4 decided "keep separate") |
| T1 | Tier 1 intra-context domain model migrations (certification, rewards, amm, trading, cross_chain_bridge, analytics) | High | ✅ DONE (all 6 models migrated) |
| T2 | Tier 2 shared-kernel model migrations (reputation, multi_chain_transaction) | High | ✅ DONE (both models migrated to owning contexts) |
| T2-r | Rename MultiChainTransaction → ChainTransaction (misnomer: transaction is single-chain) | Medium | ✅ DONE (class + table + file + alias + manager renamed) |
| T3 | Tier 3 boundary-violation migrations (agent, agent_performance) + document analytics cross-context | Medium | ✅ DONE (2 models migrated, 1 documented) |

**All Phase 4 tasks complete.** P5 skipped — P4 decision doc (`docs/releases/v0.5.13/agent_coordinator_boundary.md`) recommends keeping agent-coordinator as a separate service (zero runtime coupling between the two services).

**T1 follow-up**: All 6 Tier 1 intra-context domain models migrated from flat `app/domain/` to their owning `contexts/<bc>/domain/`. See <ref_file file="/opt/aitbc/docs/releases/v0.5.13/change.log" /> §"T1" for details. `analytics.py` ownership decided: `analytics` context owns it, `ai_analytics` imports cross-context (known boundary violation).

**T2 follow-up**: Both Tier 2 shared-kernel models migrated — `reputation.py` → `contexts/reputation/domain/` (15 importers fixed), `multi_chain_transaction.py` → `contexts/cross_chain/domain/` (5 importers fixed). See <ref_file file="/opt/aitbc/docs/releases/v0.5.13/change.log" /> §"T2".

**T2-r follow-up**: Renamed `MultiChainTransaction` → `ChainTransaction` — the model was misnamed (a transaction is single-chain; "multi-chain" described the manager's capability, not the transaction). Class, table, file, alias, and manager class all renamed. See <ref_file file="/opt/aitbc/docs/releases/v0.5.13/change.log" /> §"T2-r".

**T3 follow-up**: Both Tier 3 boundary-violation models migrated — `agent.py` and `agent_performance.py` → `contexts/agent_coordination/domain/` (17 importers fixed). See <ref_file file="/opt/aitbc/docs/releases/v0.5.13/change.log" /> §"T3". All Tier 1–3 migrations complete.

---

## Current Plan — v0.5.14 (Agent B): Cross-Context Dependency Elimination

**Release theme**: Eliminate the 4 remaining cross-context domain-model imports in coordinator-api.

**Full task details, grounding facts, and suggested fixes are in** <ref_file file="/opt/aitbc/docs/releases/v0.5.14/change.log" />.

### Task Summary

| # | Task | Priority | Status |
|---|------|----------|--------|
| X1 | `security` → `agent_coordination.domain.agent` — extract `AIAgentWorkflow` DTO or service interface | Medium | ✅ DONE |
| X2 | `advanced_rl` → `agent_coordination.domain.agent_performance` — extract `ReinforcementLearningConfig` | Medium | ✅ DONE |
| X3 | `multimodal` → `agent_coordination.domain.agent_performance` — extract `FusionModel` | Medium | ✅ DONE |
| X4 | `ai_analytics` → `analytics.domain.analytics` — merge contexts or introduce service interface | Medium | ✅ DONE |
| X5 | Verify zero cross-context domain-model imports remain + update audit docs | High | ✅ DONE |
| X6 | `marketplace` → `cross_chain` — move `TransactionPriority` to shared kernel | Medium | ✅ DONE |
| X7 | `edge_gpu` → `marketplace` — move 3 GPU models to `edge_gpu/domain/` | Medium | ✅ DONE |
| X8 | `marketplace` → `agent_identity` — change service to accept `agent_id: str` | Medium | ✅ DONE |
| X9 | `certification` + `rewards` → `reputation` — re-export from service layer | Medium | ✅ DONE |
| L1–L9 | Migrate 7 flat `app/domain/*.py` files to owning bounded contexts (12 imports) | Medium | ✅ DONE |
| L10–L19 | Migrate 10 remaining flat `app/domain/*.py` files to bounded contexts | Medium | ✅ DONE |

**Agent B working directory**: `/opt/aitbc/` (cross-cutting: `apps/`, `cli/`).

---

## Current Plan — v0.5.15 (Agent B): Flat-to-Context Migration (Phase 1)

**Release theme**: Begin paying down flat-directory architectural debt (services/, routers/, schemas/) identified in the post-v0.5.14 audit. Phase 1 addresses low-risk, high-value fixes.

**Full task details in** <ref_file file="/opt/aitbc/docs/releases/v0.5.15/change.log" />.

### Task Summary

| # | Task | Priority | Status |
|---|------|----------|--------|
| P1-1 | Fix broken `MarketplaceOffer` import in `routers/marketplace_enhanced.py` | High | ✅ DONE |
| P1-2 | Add missing `__init__.py` to `contexts/ipfs/` and `contexts/knowledge/` | Medium | ✅ DONE |
| P1-3 | Verify "duplicate" service subdirs — NOT duplicates, skipped | Low | ✅ DONE (no action) |
| P1-4 | Eliminate `domain/__init__.py` shim usage — 13 files updated to import directly from `contexts.infrastructure.domain` | Medium | ✅ DONE |
| X10 | Eliminate cross-context import: `multimodal` → `agent_coordination.domain.agent` (dead code removal) | Medium | ✅ DONE |
| P2 | Merge flat `reputation/` directory into `contexts/reputation/services/` | Medium | ✅ DONE |

**Phase 1 + Phase 2 complete.** Remaining phases (P3: schemas, P4: services, P5: routers) deferred to future releases.
