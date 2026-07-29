# QA Validation — ABS-417 (Attention Inbox v2)

**Role:** qas  
**Ticket:** ABS-417 — Single Queue, Oldest-First with Age, One-Click Resolve Actions  
**Branch:** `ABS-417-auto`  
**Commits reviewed:** `316e047 72c1d53 e0e50e0` (latest TDM-authorized product+test fix pass)  
**Date:** 2026-07-19  
**Verdict: BLOCKED — QAS iteration cap exceeded (N>3); escalating to TDM**  
**Failure class:** `code` (test isolation defect — 1 remaining test failure)

---

## TDM-Authorized Fresh Cycle #2 Context

After the Same-Error-Twice escalation, TDM authorized product+test fixes (`e0e50e0`):
- **F-A (product code):** `Inbox.tsx::toggleRelease` wrapped in `try { … } finally { setBusy(false) }`, `onChanged()` removed from success branch (gate item persists by status, not label — unmounting was the toggle-stuck root cause)
- **F-B (test):** AC1 ordering assertion switched from positional `.first()`/`.nth(1)` to bounding-box `y`-comparison, robust to stalled-seat (2h) appearing before ticket items

System-architect reviewed and approved `e0e50e0` (typecheck exit 0).  
This report covers the fresh QAS cycle against commit `e0e50e0`.

---

## Validation Suite Results

| Check | Result | Notes |
|---|---|---|
| `tsc --noEmit` (web) | ✅ PASS | exit 0 |
| `tsc --noEmit` (server) | ✅ PASS | exit 0 |
| `tsc --noEmit` (core) | ✅ PASS | exit 0 |
| `eslint .` | ✅ PASS | no violations |
| `vite build` (web) | ✅ PASS | 225 kB bundle |
| Unit tests (core) | ⚠️ 1 pre-existing FAIL | `migrate-prefix-guard`: duplicate `010` prefix (ABS-412 vs ABS-414); previously routed to TDM; NOT ABS-417 code |
| **E2E: `inbox.spec.ts`** | **8/9 PASS** | **1 failure — see below** |

---

## E2E Results — 9 tests

| # | Test | Result |
|---|---|---|
| 1 | AC1: attention items render oldest-first with age badges and source links | ✅ PASS ← **FIXED by F-B** |
| 2 | AC1: source link on a ticket item opens the ticket drawer | ✅ PASS |
| 3 | AC2: escalation resolve — posting a decision comment reclassifies item | ✅ PASS |
| 4 | AC2: blocker resolve — transition removes item on next attention fetch | ✅ PASS |
| 5 | AC2: gate release-lever toggle is visible and interactive | ✅ PASS ← **FIXED by F-A** |
| 6 | AC3: stop-run requires confirm dialog with non-empty reason | ✅ PASS |
| 7 | AC4: unread badge appears/clears on board view | ✅ PASS |
| 8 | AC5: agent/orchestrator sessions cannot trigger actions (read-only notice) | **❌ FAIL** |
| 9 | Empty state: 'Nothing needs you' shown when no items | ✅ PASS |

---

## Failure Analysis

### FAILURE — Test 8 (AC5) — Test isolation defect (cross-test state mutation)

**Error:**
```
Error: expect(locator).toBeVisible() failed
Locator: getByTestId('escalation-body-INX1784442270956-1')
Expected: visible
Timeout: 5000ms
Error: element(s) not found
```

**Root cause:** All 9 tests share the single `project = \`INX${Date.now()}\`` variable (one project for all tests). Test 3 (AC2 escalation) is designed to post a "decision" comment on `${project}-1`, which PERMANENTLY reclassifies item 1 from `escalation` to `blocker` in the DB:
- Seed: `${project}-1` = Blocked + kind:notification → **escalation**
- After Test 3 submits the decision comment: `${project}-1` = Blocked + kind:decision → **blocker**

Test 8 (AC5) runs after Test 3 with a FRESH page (new browser context). It fetches fresh data from the server — which returns item 1 as "blocker" (the decision comment persists in the DB). The test:
1. Clicks the action button on item 1 ✅ — the action panel IS opened
2. Verifies `attention-readonly` is NOT visible ✅ — admin does see action controls
3. Asserts `escalation-body-${project}-1` is visible ❌ — NOT FOUND because item 1 is a blocker, showing `TransitionAction` (Unblock form), not `EscalationAction` (comment body)

**Classification:** `code` — test isolation defect in `inbox.spec.ts`. The test at line 504 is tightly coupled to item 1's type, which changes during the test run. The AC5 CORE INTENT (admin sees action controls, agent gets 403) is still satisfied — the admin sees the blocker action panel — but the type-specific `escalation-body` assertion fails.

**Evidence from error-context page dump:**
```
Attention 4
  1. stalled-seat (2h)        ← stalled-seat seeded 2h ago
  2. blocker (item 1, 3s)     ← action panel OPEN, shows "Unblock" (TransitionAction)
  3. gate (item 3, 3s)
  4. blocker (item 4, 0s)     ← AC4-seeded item
```
Admin session, `attention-readonly` NOT present, but panel shows blocker form not escalation form.

**Two viable minimal fixes (for TDM/fe-developer to choose):**

Option A — Remove the type-specific assertion at line 504 (simplest):
```typescript
// The admin sees action controls — verified above (action panel is visible, no readonly notice).
// Note: item 1 was reclassified to 'blocker' by the AC2 escalation test; the admin sees
// the blocker TransitionAction, which equally proves the admin role shows action forms.
// Removing the escalation-body assertion (type-specific, broken by cross-test mutation).
// await expect(page.getByTestId(`escalation-body-${project}-1`)).toBeVisible(); // ← DELETE
```

Option B — Use a separate project for AC5 (isolated, tests fresh escalation item):
```typescript
let ac5Project = "";
// in beforeAll: seed ac5Project with its own escalation item 1
// in Test 8: await page.getByLabel("project").selectOption(ac5Project);
//             use ac5Project instead of project for all assertions
```

---

## AC / DoD Verification

| AC | Status | Evidence |
|---|---|---|
| AC1: All types oldest-first, age, source links | ✅ PASS | bounding-box ordering + age badges + source links verified |
| AC2: Resolve actions call endpoint, item disappears | ✅ PASS | escalation ✅, blocker ✅, gate toggle ✅ (F-A fix) |
| AC3: Stop-run confirm dialog + reason enforcement | ✅ PASS | dialog, non-empty-reason, reason-in-POST verified |
| AC4: Unread badge counts/clears | ✅ PASS | |
| AC5: Agent sessions → 403, error shown | ❌ PARTIAL | 403 server assertion not reached (test fails before it); admin-sees-controls partially verified (panel open, no readonly notice, but type-specific escalation-body assertion fails) |
| Design AC1: Inbox only actionable surface | ✅ PASS (code review) | |
| Design AC2: Age always visible, needs-human accent | ✅ PASS (code review) | |
| Design AC3: One-click, max one dialog deep | ✅ PASS (code review) | |

---

## Iteration Cap Status

Prior bounce comments with "Iteration N of 3" marker in tracker: 3 (Iterations 1, 2, 3).  
N for the next bounce = 4 → **BOUNCING FORBIDDEN** (cap is N = 3).  
Additionally: Same-Error-Twice escalation was posted (not a bounce, no "Iteration N of 3").  
This fresh cycle is TDM-authorized; the iteration counter was not explicitly reset.

**Decision: Escalate to TDM/POPM.** The remaining failure is a small, targeted test isolation fix. TDM to decide whether to authorize another minimal fix pass or take another resolution path.

---

## Gate Verdict: BLOCKED (TDM Escalation — Cap)

**Progress:** 8/9 tests pass. F-A (product code) and F-B (test ordering) are confirmed fixed.  
**One remaining failure:** Test 8 (AC5) — test isolation defect, type-specific assertion broken by cross-test state mutation.  
**Fix scope:** 1 assertion change or 1 separate project setup — minimal.  
**Next:** TDM to authorize the fix and authorize a 4th fresh QAS cycle.
