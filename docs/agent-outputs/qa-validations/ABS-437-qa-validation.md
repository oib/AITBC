# QA Validation Report — ABS-437

**Ticket**: ABS-437 — Wire Mission-Control Home KPI deep-links to pre-filtered views + applied-filter e2e  
**Commit**: `f7cd0bc` on branch `ABS-437-auto` (rebased onto `epic/ABS-410-mission-control-ux`)  
**Date**: 2026-07-19  
**Validator**: qas  
**Verdict**: ✅ APPROVED → Design Test

---

## Validation Suite Results

| Check | Result | Notes |
|-------|--------|-------|
| `eslint .` | ✅ PASS | No lint errors |
| `tsc --noEmit` (all workspaces) | ✅ PASS | Full typecheck clean |
| `tsc -b && vite build` | ✅ PASS | Production build succeeds, 225 kB bundle |
| Unit tests (13 tests) | ✅ PASS | 13/13 pass, 0 fail |
| Home e2e `home.spec.ts` (7 tests) | ✅ PASS | 7/7 pass including both strengthened AC3 tests |

---

## Acceptance Criteria Verification

### AC1: `needs-human` KPI → Attention Inbox, pre-filtered + e2e asserts applied filter
- **Status**: ✅ PASS  
- **Evidence**: e2e test 4 (`AC3: 'needs-human' KPI opens the Attention Inbox with no narrowing filter`) PASSED.  
  Asserts: `inbox` visible, `filter-chips` count=0 (EMPTY_FILTERS applied), `inbox-empty` count=0 (items shown).  
  App.tsx:305 — `setFilters(EMPTY_FILTERS)` on `dest === "inbox"` branch.

### AC2: `active-seats` KPI → Fleet/Orchestrators filtered to active run + e2e asserts applied filter
- **Status**: ✅ PASS  
- **Evidence**: e2e test 5 (`AC3: 'active-seats' KPI opens the board filtered to the active run`) PASSED.  
  Asserts: `board` visible, `filter-chips` visible, `filter-chip-run` visible + contains `run-hm`, `page.url()` matches `/run=/`.  
  App.tsx:308 — `setFilters({ ...EMPTY_FILTERS, run: activeRunId })` on else branch.

### AC3: `onNavigate` no longer contains a no-op branch
- **Status**: ✅ PASS  
- **Evidence**: DAC-1 grep contract verified live:
  ```
  App.tsx:305:  setFilters(EMPTY_FILTERS);      ← inbox branch
  App.tsx:308:  setFilters({ ...EMPTY_FILTERS, run: activeRunId });  ← fleet branch
  App.tsx:310:  setView("board");               ← shared, after filter set
  ```
  The old no-op `if (dest === "inbox") setView("board"); else setView("board");` is gone. Two distinct filter states per branch.

### AC4: `home.spec.ts` passes; AC1/AC2/AC4/AC5 no regression
- **Status**: ✅ PASS  
- **Evidence**: All 7 home.spec.ts tests pass:
  - ✅ AC1: all 4 zones render (KPI, attention, epics, ticker)
  - ✅ AC2 (×2): no vertical scroll at 1440×900, 1280×800
  - ✅ AC3 (×2): both strengthened deep-link + applied-filter assertions
  - ✅ AC5 (×2): SSE counter update + reconnect banner

---

## DAC Verification (Design ACs — DAC-1..DAC-11)

QAS verifies functional DACs (DAC-1..DAC-4, DAC-9..DAC-11). DAC-5..DAC-8 (a11y, contrast, responsive) are owed to the **Design Test / qas-design gate**.

| DAC | Description | Status | Evidence |
|-----|-------------|--------|----------|
| DAC-1 | `onNavigate` has distinct `setFilters` per branch | ✅ PASS | grep: App.tsx:305/308 distinct calls |
| DAC-2 | `kpi-needs-human` → inbox visible, no filter-chips, no inbox-empty | ✅ PASS | e2e test 4 passed |
| DAC-3 | `kpi-active-seats` → board visible, filter-chips + filter-chip-run + run= URL | ✅ PASS | e2e test 5 passed |
| DAC-4 | Two clicks produce different filter states | ✅ PASS | EMPTY_FILTERS vs run-pinned (e2e tests 4+5 combined) |
| DAC-5 | `aria-label` retained on KPI buttons | ✅ PASS (read-only) | HomeView.tsx:134,144 aria-labels intact; design gate to re-validate |
| DAC-6 | Keyboard-only nav (Tab+Enter) | 🔶 DEFERRED | Deferred to Design Test (qas-design) |
| DAC-7 | `filter-chip-run` contrast ≥ 4.5:1 | 🔶 BLOCKED | Blocked-on-tokens per design artifact (Deviation 1 §6) |
| DAC-8 | Responsive: no horizontal scroll at 1440×900 / 1280×800 | 🔶 DEFERRED | Deferred to Design Test (qas-design) |
| DAC-9 | ≤ 2 steps to all N attention items from Home | ✅ PASS | e2e test 4: click kpi-needs-human → Inbox visible, items shown |
| DAC-10 | ≤ 2 steps to run-filtered fleet from Home | ✅ PASS | e2e test 5: click kpi-active-seats → board + filter-chip-run + run= URL |
| DAC-11 | Existing AC1/AC2/AC5 tests pass without regression | ✅ PASS | 5 pre-existing tests remain green |

---

## Notes

- **Pre-existing failures (out of scope)**: 9 tests in `filters`/`board`/`knowledge` specs fail due to landing-view drift (login helpers expect `board` immediately, but landing is now `home` since ABS-416). These fail at sign-in before any diff-touched code; correctly flagged for separate epic cleanup.
- **Fixture fix**: `spawn_id → crypto.randomUUID()` is in-scope (latent bug that blocked active-seats path from having a real run to filter on); match pattern in `inbox.spec`.
- **DAC-5 aria-labels**: `aria-label` attributes confirmed present in `HomeView.tsx` lines 134/144. Design gate re-validates interaction-level a11y.
- **Design flag**: Ticket carries `design` flag → exit to **Design Test** gate (qas-design re-validates DAC-5..DAC-8). Not Story Acceptance directly.

---

## Final Verdict

**APPROVED** → Design Test

All 4 ACs met. All functional DACs (1–4, 9–11) verified. Validation suite PASS (lint + typecheck + build + unit tests 13/13 + home e2e 7/7). Design flag set → routing to Design Test for qas-design re-validation of DAC-5..DAC-8 (a11y/contrast/responsive).
