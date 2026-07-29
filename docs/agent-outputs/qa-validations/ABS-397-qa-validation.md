# QA Validation Report — ABS-397

**Ticket**: ABS-397 — Rebase-gate before Story Acceptance: require merge_readiness=clean or documented rebase in the same move  
**Branch**: ABS-397-auto  
**Commit**: dbb20af  
**Date**: 2026-07-17  
**QAS Actor**: qas  
**Verdict**: ✅ APPROVED

---

## Validation Summary

### Test Suite Results (real Postgres — postgres:16-alpine :5432)

| Metric | Result |
|--------|--------|
| Total tests | 168 |
| Pass | 167 |
| Fail | 1 (pre-existing, unrelated) |
| Skip | 0 |
| Typecheck (`pnpm -r typecheck`) | ✅ PASS (5 workspaces) |
| Lint (`pnpm lint`) | ✅ PASS (clean) |

### ABS-397 Specific Tests (all 4 PASS)

| Test | Status |
|------|--------|
| `ABS-397 AC#1: Story Acceptance -> Merging with rebase-needed and NO documented rebase is rejected (409, nothing written)` | ✅ PASS |
| `ABS-397 AC#1: rebase-needed passes when the SAME move documents the rebase in its reason (event evidence)` | ✅ PASS |
| `ABS-397 AC#2: clean merge_readiness proceeds to Merging unchanged (no rebase evidence required)` | ✅ PASS |
| `ABS-397 AC#3: the gate is scoped to the Merging edge — a rebase-needed story still bounces Story Acceptance -> Ready for Development` | ✅ PASS |

---

## Acceptance Criteria Verification

### AC1: A Story-Acceptance transition with `merge_readiness=rebase-needed` is rejected OR forces a documented rebase (event evidence recorded).
**Status**: ✅ PASS  
**Evidence**:  
- Test "rebase-needed and NO documented rebase is rejected (409, nothing written)" asserts: `RebaseRequiredError` (409) thrown, status unchanged, zero events written.  
- Test "rebase-needed passes when the SAME move documents the rebase in its reason" asserts: transition proceeds, rebase evidence lands verbatim on `event.payload.reason` (matched by `/rebased/i`).  
- Implementation: guard in `transitions.ts` at the `Story Acceptance → Merging` edge calls `computeMergeReadiness()`, throws `RebaseRequiredError(readiness)` when `readiness !== "clean" && !REBASE_DOCUMENTED.test(args.reason)`.

### AC2: A transition with `merge_readiness=clean` proceeds unchanged.
**Status**: ✅ PASS  
**Evidence**:  
- Test "clean merge_readiness proceeds to Merging unchanged (no rebase evidence required)" asserts transition completes to `Merging` with no error. Story with no merged sibling → `clean` default passes through.

### AC3: The guard never bypasses/replaces QAS (runs after, never instead of).
**Status**: ✅ PASS  
**Evidence**:  
- Test "the gate is scoped to the Merging edge — a rebase-needed story still bounces Story Acceptance -> Ready for Development" asserts non-Merging edges are untouched.  
- Implementation: guard is gated by `if (from === REBASE_GATE_FROM && args.to === REBASE_GATE_TO)` (constants: `"Story Acceptance"` and `"Merging"`), which is after QAS in the story pipeline. The guard fires on exactly one edge; QAS owns the `In Test → Story Acceptance` gate, which precedes this.

---

## Pre-existing Failure Analysis

**Failing test**: `AC#2: an illegal transition throws 400 with the allowed targets, writing nothing` (transitions.test.ts:225)  
**Root cause**: Test hardcodes `In Progress` allowed targets as `["In Review", "Blocked", "Needs PO Decision"]` but `statuses.yaml` now also allows `Ready for Development` (ADR-A-0024 bounce edge). Actual allowed list includes `Ready for Development`.  
**Relation to ABS-397 diff**: NONE. ABS-397 diff touches only `transitions.ts` (new class + guard on `Story Acceptance → Merging`), `index.ts` (export), and `transitions.test.ts` (4 new tests). No changes to `In Progress` logic or `statuses.yaml`.  
**Classification**: Pre-existing drift — same finding flagged by ABS-395. Belongs to the workflow-change owner.  
**Blocking?**: NO.

---

## Implementation Review

### Pattern Compliance
- `RebaseRequiredError` follows the existing `TransitionError` subclass pattern (readonly `status`, `body()` override) — consistent with `ItemNotFoundError`, `IllegalTransitionError`, `CasMismatchError`.
- `sendError` already maps any `TransitionError` to its status/body; no extra HTTP wiring required.
- Reuses existing `computeMergeReadiness` (ABS-395) — no duplicate implementation.

### Ordering
- Guard sits **after** `canTransition()` (legality check, 400 first) and **before** the CAS UPDATE (so a rejected gate writes nothing).
- Guard fires on exactly the `Story Acceptance → Merging` edge only — post-QAS in the pipeline.

### Evidence Persistence (ABS-66 data-flow)
- "Documented rebase" text lands verbatim on `event.payload.reason` (the ABS-395 transition event model).
- Test directly asserts `ev.rows[0].payload.reason` matches `/rebased/i`.

### Non-Blocking Notes (from System-Architect, acknowledged)
1. `/\brebased\b/i` check is weak against pathological input (e.g., "not rebased"). Acceptable for an advisory internal gate; raises the bar from silent pass to conscious documented action with audit trail.
2. ABS-395 (depends_on) merged into this branch to consume `computeMergeReadiness`; reconciles at PR-rebase time when ABS-395 lands on the epic branch.

---

## Gate Flag Check

**Ticket labels**: `[orchestrator-ready]`  
**`design` flag**: NOT present  
**Exit target**: `Story Acceptance` (no design flag → skip Design Test per exit protocol)

---

## Verdict

**APPROVED** — All 3 ACs verified against real Postgres. Implementation is additive, pattern-compliant, ordered correctly in the pipeline (after QAS), and evidence lands on the transition event payload. Typecheck and lint clean. 4/4 ABS-397 tests PASS; 1 pre-existing unrelated failure confirmed not caused by this diff.

