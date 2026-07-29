# QA Validation Report — ABS-419 (Revision 8)

**Ticket**: ABS-419 — S7 Usage & Budget Meter UI  
**Branch**: ABS-419-auto  
**Commits reviewed**: branch tip `84bd3df` (§4.4 ABS-417 Inbox v2 + BudgetAction panel, on top of rev7 `24f2699`)  
**QAS gate**: In Test  
**Date**: 2026-07-19  
**Verdict**: ✅ APPROVED

---

## Context vs. Rev7

Rev7 (`24f2699`) approved the migration rename fix (`011_budget_config.sql`). Since rev7,
two additional commits landed:

- `1760a5e` — `docs(design): ABS-419 §4.4 update — BudgetAction panel for ABS-417 Inbox`
- `84bd3df` — `feat(ui): ABS-419 §4.4 — ABS-417 Inbox v2 + BudgetAction panel`

The §4.4 commit replaces the flat-list Inbox with the ABS-417 AttentionItem architecture
and wires ABS-419's `BudgetAction` into it. The system-architect re-reviewed at `84bd3df`
and confirmed the build gate, 13/13 e2e, and architecture (see SA gate-results comment,
In Review → In Test). This rev8 validates the updated HEAD independently.

---

## Static Gate Results

| Gate | Result | Detail |
|------|--------|--------|
| TypeScript (`pnpm -r typecheck`) | ✅ PASS | 0 errors across 5 workspaces |
| Lint (`pnpm lint` — eslint) | ✅ PASS | 0 errors / 0 warnings |
| Build (`pnpm --filter web build`) | ✅ PASS | 51 modules, 32.88 kB CSS, 234.74 kB JS |

---

## Unit Test Results

| Workspace | Pass | Fail | Skip |
|-----------|------|------|------|
| `apps/web` | 13 | 0 | 0 |
| `packages/core` | 126 | 0 | 92 |
| `packages/webhooks` | 6 | 0 | 10 |
| `packages/forge` | 18 | 0 | 7 |
| `apps/server` | 7 | 0 | 188 (live Postgres skips) |
| **Total** | **170** | **0** | 297 |

`migrate-prefix-guard.test.ts` — GREEN: `126 pass / 0 fail` in `packages/core`.

---

## E2E Results — `e2e/budget.spec.ts` + `eventfeed-timeline.spec.ts` (13 tests)

**DB**: Fresh isolated `postgres:16-alpine` container `abs419-e2e-pg-qas` at port 55419  
**DB_URL**: `postgres://postgres:pw@localhost:55419/agentic`  
**Migrations applied**: 001..011 (including `011_budget_config.sql`, no prefix collision)  
**Duration**: ~14.3s

| # | Test | AC | Result |
|---|------|----|--------|
| 1 | normal state: spend below warning threshold | AC1 | ✅ PASS (692ms) |
| 2 | warning state: spend ≥ 80% of budget | AC1 | ✅ PASS (122ms) |
| 3 | exceeded state: spend ≥ 100% of budget | AC1 | ✅ PASS (122ms) |
| 4 | 2-run project: chip shows most-recent run's spend | AC1 | ✅ PASS (122ms) |
| 5 | run grouping shows both runs | AC2 | ✅ PASS (1.5s) |
| 6 | epic grouping switches to epic group | AC2 | ✅ PASS (1.5s) |
| 7 | seat grouping shows seat roles | AC2 | ✅ PASS (1.5s) |
| 8 | day grouping shows date rows | AC2 | ✅ PASS (1.5s) |
| 9 | incomplete-notice and row badge visible; total marked | AC3 | ✅ PASS (1.5s) |
| 10 | human round-trip: budget edit persists and chip reflects new limit | AC4 | ✅ PASS (1.9s) |
| 11 | agent token (bearer-only) gets 403 from PUT /budget | AC4 | ✅ PASS (5ms) |
| 12 | budget-warning item renders in Inbox with → View Usage link | AC5 | ✅ PASS (1.8s) |
| 13 | Timeline renders budget markers (eventfeed-timeline) | AC3 | ✅ PASS (211ms) |

**Total: 13/13 PASS**

---

## §4.4 Change Verification (new since rev7)

The `84bd3df` commit introduced ABS-417 Inbox v2 + BudgetAction panel. Key points
verified against the code:

| Check | Evidence |
|-------|----------|
| `BudgetAction` renders `budget-view-usage-{source_ref}` button | `Inbox.tsx:388` |
| `onNavigate("usage")` wired through Inbox → AttentionRow → ActionPanel → BudgetAction | `Inbox.tsx:305,267,149` |
| `App.tsx` threads `onNavigate` to Inbox; "usage" routes to `setView("usage")` | `App.tsx` wiring |
| `queryBudgetAlerts()` in `attention.ts` reads BUDGET-WARNING / BUDGET-EXCEEDED from `run_event` | `attention.ts:339,351` |
| Budget attention item type-border uses `var(--emphasis-border)` (orange), exceeded `var(--stale)` (red) — no new colors | `styles.css:675,682` |
| AC5 test updated to ABS-417 testids (`attention-{ref}`, `attention-action-btn-{ref}`, `budget-view-usage-{ref}`) | `budget.spec.ts:437,443,449` |

---

## AC/DoD Verification

| Criterion | Status | Evidence |
|-----------|--------|----------|
| AC1: Budget chip 3 threshold states (normal/warning/exceeded) | ✅ | Tests 1–3 PASS; `BudgetChip.tsx:47-51` |
| AC1: Burn rate + 2-run alignment | ✅ | Test 4 PASS |
| AC2: Usage view per-run/epic/seat/day groupings matching S6 API | ✅ | Tests 5–8 PASS; `UsageView.tsx:136` group switcher |
| AC3: Incomplete-cost badge (not silently wrong) | ✅ | Test 9 PASS; `UsageView.tsx:214-218` `data-testid="incomplete-notice"` |
| AC4: Budget edit human-gated, 403 for agent tokens, re-arms meter | ✅ | Tests 10–11 PASS; `canEditBudget()`, `budget-403` testid |
| AC5: Budget attention items appear in Inbox with → View Usage link | ✅ | Test 12 PASS; `BudgetAction` in `Inbox.tsx:374+` |
| DoD: All unit tests pass | ✅ | 170/170 pass, 0 fail |
| DoD: Migration prefix guard (ABS-428) | ✅ | `packages/core` 126/126 pass; `011_budget_config.sql` no collision |
| DoD: No new chart dependency (ADR-A-0010) | ✅ | SA confirmed; tables/bars only |
| DoD: Budget edits human-gated server-side | ✅ | `requireHuman` in server usage.ts (SA confirmed) |
| Design AC: 5-state color reuse (no new colors) | ✅ | `var(--emphasis-border)`, `var(--stale)`, `var(--stale-bg)` — existing tokens |
| Design AC: KPI chip glanceable (one number + bar; detail in Usage view) | ✅ | `BudgetChip.tsx` minimal chip; drill-down navigates to UsageView |

---

## Carry-Over (Non-blocking, tracked)

**SSE-id seq:"0" defect** (flagged rev5): `budget` BusEvent emits `seq:"0"`. Tracked for
ABS-410 epic fast-follow before main merge. Does NOT affect any ABS-419 AC.

---

## Verdict

✅ **APPROVED** — All 5 ACs PASS. 13/13 e2e PASS. 170/170 unit tests PASS (0 fail).  
Static gates (typecheck/lint/build) all clean. §4.4 BudgetAction + Inbox v2 verified.

**Design flag set → transitioning `In Test → Design Test`** (DAC-1..16 to be verified
by qas-design seat against running UI).

**QAS**: qas-seat (ABS-419 In Test gate, rev8 `84bd3df`)  
**Date**: 2026-07-19
