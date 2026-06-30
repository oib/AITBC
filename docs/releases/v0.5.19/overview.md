# v0.5.19 Tech Debt Cleanup — Overview

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
- [Status Baseline](#status-baseline--verified-code-targets-2026-06-29)
- [Task Split Overview](#task-split-overview)

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

## Related Topics

- [Agent A Tasks](./agent-a.md) - Shared core implementation details
- [Agent B Tasks](./agent-b.md) - Apps & infrastructure implementation details

---

**Documentation Version**: 1.0
**Last Updated**: 2026-06-30
**Release**: v0.5.19 — Tech Debt Cleanup
