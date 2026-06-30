# v0.5.19 — Agent Task Assignment

**Last Updated**: 2026-06-30
**Version**: 1.0

**Release Theme**: Tech Debt Cleanup — Cross-Context Import Refactor, Dead Pricing Models, fakeredis

**Goal**: Address 3 outstanding tech debt items deferred from v0.5.13-v0.5.18. After re-verification, 4 of 7 original items are already resolved.

> **Not on the critical path**: No release depends on v0.5.19. Pick up opportunistically.

> **Prerequisites**: [v0.5.18](../v0.5.18/change.log) ✅.

> **Risk**: Low. All items are coordinator-api internal or test infrastructure.

---

## Documentation Structure

This release documentation has been split into topic-focused files:

- **[Overview](./overview.md)** - Release overview, status baseline, and task split overview
- **[Agent A Tasks](./agent-a.md)** - Shared core implementation (ReputationDTO)
- **[Agent B Tasks](./agent-b.md)** - Apps & infrastructure implementation (certification refactor, pricing cleanup, fakeredis)

---

## Quick Navigation

### Overview
- [Status Baseline](./overview.md#status-baseline--verified-code-targets-2026-06-29)
- [Task Split Overview](./overview.md#task-split-overview)

### Agent A (Shared Core)
- [Scope](./agent-a.md#scope)
- [Tasks](./agent-a.md#tasks)
- [ReputationDTO](./agent-a.md#a1-reputationdto)
- [Unit tests](./agent-a.md#a2-unit-tests-for-reputationdto)

### Agent B (Apps & Infrastructure)
- [Scope](./agent-b.md#scope)
- [Tasks](./agent-b.md#tasks)
- [Certification Refactor](./agent-b.md#b1-certification-refactor)
- [Resolve Duplicate Pricing Models](./agent-b.md#b2-resolve-duplicate-pricing-models)
- [Wire or Remove Unused Pricing Tables](./agent-b.md#b3-wire-or-remove-unused-pricing-tables)
- [fakeredis](./agent-b.md#b4-add-fakeredis-dependency--fix-misleading-conftest_sqlitepy-comment)
- [Integration Tests](./agent-b.md#b5-integration-tests)

---

## Status Baseline — Verified Code Targets (2026-06-29)

| Component | Location | Current State | v0.5.19 Target |
|-----------|----------|---------------|----------------|
| **Certification → reputation import** | `apps/coordinator-api/src/app/contexts/certification/services/certification/` | ❌ 20 cross-context imports of `AgentReputation` across 3 files | Refactor to DTO/service interface |
| **Pricing tables** | `apps/coordinator-api/src/app/contexts/trading/domain/pricing_models.py` | ⚠️ 1/7 wired (ProviderPricingStrategy), 6 unused, 2 duplicates | Wire or remove; resolve duplicates |
| **fakeredis** | — | ❌ Not installed, misleading comment in conftest_sqlite.py:57 | Add as deliberate dependency |

### Already Resolved (no work needed)

1. ✅ **ai_analytics → analytics refactor** — merged in v0.5.14
2. ✅ **Certification → analytics import** — 0 imports exist
3. ✅ **_TEMPLATE.md** — exists at `docs/scenarios/_TEMPLATE.md` (129 lines)
4. ✅ **127 skipped CLI tests** — 0 permanent skips, only conditional service-availability skips

---

## Task Split Overview

| Agent | Domain | Tasks | Files |
|-------|--------|-------|-------|
| **Agent A** | Shared core (`aitbc/`) | 1 item | Reputation DTO/interface (if placed in shared core) |
| **Agent B** | Apps & infrastructure | 4 items | `apps/coordinator-api/`, `tests/`, `requirements.txt` |

**Note**: This is a small release. Agent A's involvement is minimal (1 DTO). Most work is Agent B (coordinator-api refactors + test infrastructure).

**Sequencing**: Agent A creates the DTO first (if needed), Agent B refactors certification to use it. Pricing table cleanup and fakeredis can proceed independently.

---

**Documentation Version**: 1.0
**Last Updated**: 2026-06-30
**Release**: v0.5.19 — Tech Debt Cleanup

---

## Agent A — Shared Core

**Scope**: Create a ReputationDTO that can be used across contexts without direct model import.

**Working directory**: `/opt/aitbc/aitbc/` or `packages/aitbc-shared/`

**Prerequisite**: v0.5.18 ✅.

### Tasks

| # | Task | Priority | Files | Status |
|---|------|----------|-------|--------|
| A1 | Create `ReputationDTO` dataclass — fields needed by certification context (agent_id, reputation_score, total_tasks, success_rate, etc.) | Medium | `packages/aitbc-shared/aitbc_shared/models/reputation.py` (new or extend) | ✅ complete |
| A2 | Unit tests for ReputationDTO | Low | `tests/unit/test_reputation_dto.py` (new) | ✅ complete |

### Agent A — Detailed Instructions

#### A1: ReputationDTO

Create a DTO that certification context can use instead of directly importing `AgentReputation`:

```python
@dataclass
class ReputationDTO:
    """DTO for cross-context reputation data access."""
    agent_id: str
    reputation_score: float
    total_tasks: int
    success_rate: float
    # Add fields as needed by certification context
```

Place in `packages/aitbc-shared/aitbc_shared/models/reputation.py` or a new shared location.

---

## Agent B — Apps & Infrastructure

**Scope**: Refactor certification to use ReputationDTO, clean up pricing tables, add fakeredis.

**Working directory**: `/opt/aitbc/apps/coordinator-api/`, `/opt/aitbc/tests/`

**Prerequisite**: Agent A A1 complete (for ReputationDTO).

### Tasks

| # | Task | Priority | Files | Status |
|---|------|----------|-------|--------|
| B1 | Refactor certification to use ReputationDTO instead of AgentReputation | Medium | `apps/coordinator-api/src/app/contexts/certification/services/certification/badge_system.py`, `certification_system.py`, `partnership_manager.py` | ✅ complete |
| B2 | Resolve duplicate pricing models (MarketMetrics, PriceForecast in trading vs marketplace) | Medium | `apps/coordinator-api/src/app/contexts/trading/domain/pricing_models.py`, `apps/coordinator-api/src/app/contexts/marketplace/domain/gpu_marketplace.py` | ✅ complete |
| B3 | Wire or remove unused pricing tables (PricingOptimization, PricingAlert, PricingRule, PricingAuditLog) | Medium | `apps/coordinator-api/src/app/contexts/trading/domain/pricing_models.py`, `dynamic_pricing.py` | ✅ complete |
| B4 | Add fakeredis dependency + fix misleading conftest_sqlite.py comment | Low | `requirements.txt` or `pyproject.toml`, `tests/conftest_sqlite.py` | ✅ complete |
| B5 | Integration tests | Low | `tests/unit/test_v0519_tech_debt.py` (new) | ✅ complete |

### Agent B — Detailed Instructions

#### B1: Certification Refactor

Refactor 3 files to use `ReputationDTO` instead of `AgentReputation`:
- `badge_system.py:10` — replace import + 3 references
- `certification_system.py:17` — replace import + 6 references
- `partnership_manager.py:14` — replace import + 11 references

Add a conversion function in reputation context: `to_dto(agent_reputation) -> ReputationDTO`

#### B2: Resolve Duplicate Pricing Models

- `MarketMetrics`: exists in both `trading/domain/pricing_models.py:171` and `marketplace/domain/gpu_marketplace.py:145`
- `PriceForecast`: exists in both `trading/domain/pricing_models.py:234` and `marketplace/domain/gpu_marketplace.py:82`
- Decide: which context is canonical? Move to shared package? Remove duplicate?
- Add Alembic migration if tables are removed

#### B3: Wire or Remove Unused Pricing Tables

- `PricingAuditLog` (line 474) — **WIRE** into `dynamic_pricing.py` (audit trail for pricing changes)
- `PricingAlert` (line 351) — wire if alerting use case exists, else remove
- `PricingRule` (line 413) — wire if rule-based pricing use case exists, else remove
- `PricingOptimization` (line 287) — likely remove (no clear use case)

#### B4: fakeredis

- Add `fakeredis` to `pyproject.toml` dev-dependencies (pin version published >7 days ago)
- Update `tests/conftest_sqlite.py:57` to actually use fakeredis (or remove misleading comment)
- Verify Redis-dependent tests pass with fakeredis

#### B5: Integration Tests

`tests/unit/test_v0519_tech_debt.py` — tests for:
- ReputationDTO serialization
- Certification using DTO (no direct AgentReputation import)
- Pricing table wiring (if wired)
- fakeredis fixture works

---

## Coordination

### Shared Files

Agent A creates `ReputationDTO` in shared package. Agent B refactors coordinator-api to use it. No file conflicts.

### Sequencing

1. **Phase 1**: Agent A A1 (ReputationDTO), Agent B B2-B3 (pricing tables — independent), Agent B B4 (fakeredis — independent)
2. **Phase 2**: Agent B B1 (certification refactor — needs A1)
3. **Phase 3**: Agent A A2 + Agent B B5 (tests)

### Dependencies

```
v0.5.18 ✅
    │
    ├── A1 (ReputationDTO) ──┐
    │                         ├── A2 (tests)
    │                         │
    ├── B1 (certification refactor) ── needs A1
    ├── B2 (resolve duplicates) ── independent
    ├── B3 (wire/remove pricing) ── independent
    ├── B4 (fakeredis) ── independent
    └── B5 (tests) ── needs A1 + B1
```
