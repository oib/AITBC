# v0.5.19 Tech Debt Cleanup — Agent B Tasks

**Last Updated**: 2026-06-30
**Version**: 1.0

**Agent**: Agent B (Apps & Infrastructure)

**Scope**: Refactor certification to use ReputationDTO, clean up pricing tables, add fakeredis.

**Working directory**: `/opt/aitbc/apps/coordinator-api/`, `/opt/aitbc/tests/`

**Prerequisite**: Agent A A1 complete (for ReputationDTO).

---

## Tasks

| # | Task | Priority | Files | Status |
|---|------|----------|-------|--------|
| B1 | Refactor certification to use ReputationDTO instead of AgentReputation | Medium | `apps/coordinator-api/src/app/contexts/certification/services/certification/badge_system.py`, `certification_system.py`, `partnership_manager.py` | ✅ complete |
| B2 | Resolve duplicate pricing models (MarketMetrics, PriceForecast in trading vs marketplace) | Medium | `apps/coordinator-api/src/app/contexts/trading/domain/pricing_models.py`, `apps/coordinator-api/src/app/contexts/marketplace/domain/gpu_marketplace.py` | ✅ complete |
| B3 | Wire or remove unused pricing tables (PricingOptimization, PricingAlert, PricingRule, PricingAuditLog) | Medium | `apps/coordinator-api/src/app/contexts/trading/domain/pricing_models.py`, `dynamic_pricing.py` | ✅ complete |
| B4 | Add fakeredis dependency + fix misleading conftest_sqlite.py comment | Low | `requirements.txt` or `pyproject.toml`, `tests/conftest_sqlite.py` | ✅ complete |
| B5 | Integration tests | Low | `tests/unit/test_v0519_tech_debt.py` (new) | ✅ complete |

---

## B1: Certification Refactor

Refactor 3 files to use `ReputationDTO` instead of `AgentReputation`:
- `badge_system.py:10` — replace import + 3 references
- `certification_system.py:17` — replace import + 6 references
- `partnership_manager.py:14` — replace import + 11 references

Add a conversion function in reputation context: `to_dto(agent_reputation) -> ReputationDTO`

---

## B2: Resolve Duplicate Pricing Models

- `MarketMetrics`: exists in both `trading/domain/pricing_models.py:171` and `marketplace/domain/gpu_marketplace.py:145`
- `PriceForecast`: exists in both `trading/domain/pricing_models.py:234` and `marketplace/domain/gpu_marketplace.py:82`
- Decide: which context is canonical? Move to shared package? Remove duplicate?
- Add Alembic migration if tables are removed

---

## B3: Wire or Remove Unused Pricing Tables

- `PricingAuditLog` (line 474) — **WIRE** into `dynamic_pricing.py` (audit trail for pricing changes)
- `PricingAlert` (line 351) — wire if alerting use case exists, else remove
- `PricingRule` (line 413) — wire if rule-based pricing use case exists, else remove
- `PricingOptimization` (line 287) — likely remove (no clear use case)

---

## B4: fakeredis

- Add `fakeredis` to `pyproject.toml` dev-dependencies (pin version published >7 days ago)
- Update `tests/conftest_sqlite.py:57` to actually use fakeredis (or remove misleading comment)
- Verify Redis-dependent tests pass with fakeredis

---

## B5: Integration Tests

`tests/unit/test_v0519_tech_debt.py` — tests for:
- ReputationDTO serialization
- Certification using DTO (no direct AgentReputation import)
- Pricing table wiring (if wired)
- fakeredis fixture works

---

## Related Topics

- [Overview](./overview.md) - Release overview and status baseline
- [Agent A Tasks](./agent-a.md) - Shared core implementation details

---

**Documentation Version**: 1.0
**Last Updated**: 2026-06-30
**Release**: v0.5.19 — Tech Debt Cleanup
**Agent**: Agent B (Apps & Infrastructure)
