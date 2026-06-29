## Preparation Phase
- Verify that all prerequisite releases are merged and tagged.
- Set up a test environment matching the target release's dependencies.
- Run existing test suite to ensure baseline passes before coding.
- Review the CHANGELOG and any linked design documents for ambiguities.
- Coordinate with relevant agents (A/B) to clarify file ownership and avoid conflicts.

# v0.5.19 Suggestions

## Status
**PLANNED 2026-06-29** — v0.5.19 created to track 7 tech debt items deferred from v0.5.13-v0.5.18. After re-verification, 4 items are already resolved, leaving 3 outstanding. NOT on the critical path. Low risk.

## Origin

During v0.7.4 and v0.8.2 release planning, it was discovered that 7 tech debt items were deferred from v0.5.x to "future" but never tracked. These are code quality refactors, dead code cleanup, and test infrastructure items.

## Deferred Items — Verified State (2026-06-29)

### 1. Cross-context import refactor: ai_analytics → analytics (from v0.5.13) — ✅ RESOLVED
- `ai_analytics` context no longer exists — merged into `analytics` as sub-package in v0.5.14
- `apps/coordinator-api/src/app/contexts/analytics/services/ai_analytics/__init__.py:2-4` confirms merge
- **No action needed**

### 2. 7 pricing tables not wired into engine (from v0.5.13) — ⚠️ PARTIALLY ADDRESSED
- Models in `apps/coordinator-api/src/app/contexts/trading/domain/pricing_models.py`:
  - `ProviderPricingStrategy` (line 108) — PARTIALLY WIRED (used in `dynamic_pricing.py:344`)
  - `MarketMetrics` (line 171) — DUPLICATE (also in `marketplace/domain/gpu_marketplace.py:145`)
  - `PriceForecast` (line 234) — DUPLICATE (also in `marketplace/domain/gpu_marketplace.py:82`)
  - `PricingOptimization` (line 287) — NOT WIRED
  - `PricingAlert` (line 351) — NOT WIRED
  - `PricingRule` (line 413) — NOT WIRED
  - `PricingAuditLog` (line 474) — NOT WIRED (should be wired — audit trail)
- **Action needed**: wire or remove 6 unused tables; resolve duplicates

### 3. Certification cross-context import to analytics (from v0.5.13) — ✅ RESOLVED
- 0 imports from certification to analytics/ai_analytics found
- **No action needed**

### 4. Rewards/certification cross-context imports: AgentReputation (from v0.5.13) — ❌ STILL OUTSTANDING
- Certification imports `AgentReputation` from reputation context (20 references):
  - `badge_system.py:10` — 3 references
  - `certification_system.py:17` — 6 references
  - `partnership_manager.py:14` — 11 references
- Import: `from ....reputation.services.reputation_service import AgentReputation`
- Note: `rewards` context does NOT exist — the violation is certification → reputation
- **Action needed**: introduce ReputationDTO/service interface to eliminate direct model import

### 5. _TEMPLATE.md for scenario authors (from v0.5.15) — ✅ RESOLVED
- `docs/scenarios/_TEMPLATE.md` exists (129 lines, complete structure)
- **No action needed**

### 6. 127 skipped CLI tests (from v0.5.17) — ✅ RESOLVED
- Current CLI tests (`cli/tests/`) have 0 permanent skip decorators
- Only conditional skips for service availability (e.g., "edge-api not running")
- `tests/cli/` has ~15 conditional skip statements (down from 127)
- **No action needed** — remaining skips are appropriate integration test guards

### 7. Add fakeredis (from v0.5.18) — ❌ STILL OUTSTANDING
- `tests/conftest_sqlite.py:57` has misleading comment "uses fakeredis" but it's NOT installed
- Not in `requirements.txt` or `pyproject.toml`
- The fixture just sets `REDIS_URL` env var to `redis://localhost:6379/1` — doesn't use fakeredis
- **Action needed**: add fakeredis as deliberate dependency; fix misleading comment

## Summary

| # | Item | Status |
|---|------|--------|
| 1 | ai_analytics → analytics refactor | ✅ Resolved (v0.5.14) |
| 2 | 7 pricing tables not wired | ⚠️ Partially addressed (1/7 wired) |
| 3 | Certification → analytics import | ✅ Resolved |
| 4 | Certification → reputation import (AgentReputation) | ❌ Outstanding (20 references) |
| 5 | _TEMPLATE.md | ✅ Resolved |
| 6 | 127 skipped CLI tests | ✅ Resolved (0 permanent skips) |
| 7 | fakeredis | ❌ Outstanding (not installed) |

**3 items need action**: pricing tables, AgentReputation refactor, fakeredis

## Recommendations

- **Low priority**: These are tech debt items. Pick up opportunistically between feature releases.
- **AgentReputation refactor is coordinator-api internal**: No impact on blockchain-node, trading, or bridge. Introduce a DTO in shared-core or a service interface.
- **Pricing tables need a decision**: Wire into dynamic pricing engine (if useful) or remove (if dead). `PricingAuditLog` should definitely be wired — audit trail for pricing changes is valuable.
- **Resolve duplicates first**: MarketMetrics and PriceForecast exist in both trading and marketplace contexts. Decide which is canonical before wiring or removing.
- **fakeredis is additive**: Adding a test dependency is low-risk. Pin version published >7 days ago. Fix the misleading conftest_sqlite.py comment.
- **NOT on critical path**: No release depends on v0.5.19.
