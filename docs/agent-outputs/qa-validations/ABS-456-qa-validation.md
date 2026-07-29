# QA Validation Report — ABS-456

**Ticket**: Fix Mission-Control e2e login helpers for post-ABS-416 home landing view  
**Branch**: `ABS-456-auto` (based on `epic/ABS-410-mission-control-ux`)  
**Commits reviewed**: `ecf8535` (iter-1 fix), `36b74ac` (iter-2 fix)  
**QAS iteration**: 2 of 3  
**Verdict**: ✅ APPROVED  
**Date**: 2026-07-19  

---

## Validation History

| Iteration | Result | Key Finding |
|-----------|--------|-------------|
| 1 of 3 | BLOCKED | 2 code failures: re-entrant login + drawer-scrim |
| 2 of 3 | **APPROVED** | Both code failures fixed; 2 remaining failures are PO-carved-out product bug (→ ABS-458) |

---

## Diff Scope (AC4)

```
git diff 7ed1c68...36b74ac --name-only
backend/apps/web/e2e/filters.spec.ts
docs/agent-outputs/qa-validations/ABS-456-qa-validation.md   ← QAS-authored evidence, not product source
```

**AC4 PASS** ✅ — Only `backend/apps/web/e2e/filters.spec.ts` is product-scope-eligible. No product/app source changed.

---

## Static Gates

| Gate | Result |
|------|--------|
| `pnpm tsc --noEmit` | ✅ exit 0 |
| `eslint e2e/filters.spec.ts` | ✅ exit 0 |
| `playwright test --list e2e/filters.spec.ts` | ✅ 7/7 compile clean |

---

## Fix Analysis (iter-2 commit `36b74ac`)

### Issue 1 resolved — re-entrant login (iter-1 failure `filters.spec.ts:85`)
The helper now waits for `tokenField OR nav-home` to settle before attempting sign-in, then conditionally signs in only when the Login form is visible. On re-entry with a live session (AC1's post-reload second `loginAndSelectProject` call, AC2's cold-URL navigation), the Login form doesn't render — the helper correctly skips the fill/click and proceeds.

### Issue 2 resolved — drawer-scrim blocking nav-board (iter-1 failure `filters.spec.ts:135`)
The helper now:
1. Moves `selectOption(project)` before the view switch — native `<select>` has no pointer hit-test, unaffected by the scrim.
2. Detects a cold-URL drawer via `/#\/(ticket|seat)\//.test(page.url())`.
3. Skips the Home→Board view switch when a drawer is open. The drawer specs assert the drawer, not the Board — they never needed the view switch. This eliminates the scrim-interception timeout.

---

## E2E Results — abs430-e2e-pg (`postgres://postgres:pw@localhost:55430/agentic`)

### filters.spec.ts — 5 passed / 2 failed

| Test | Result | Notes |
|------|--------|-------|
| AC1: epic+role filters persist across view switch and page reload | ✅ PASS | |
| AC2: #/ticket cold navigation opens TicketDrawer; Esc closes and cleans URL | ❌ (carved out) | Product bug in `useDrawerURL.applyHash` → ABS-458 |
| AC2: #/seat cold navigation opens SeatDrawer; Esc closes and cleans URL | ❌ (carved out) | Env 500 on spawn seed + same product bug → ABS-458 |
| AC3: saved filter applies all dimensions in one click | ✅ PASS | |
| AC4: non-applicable dimension greyed; value preserved on switch-back | ✅ PASS | |
| AC5: KPI-click produces same URL state as manual role filter | ✅ PASS | |
| Design AC: empty result state names active filters and offers clear | ✅ PASS | |

The 2 `#/ticket`/`#/seat` failures are identical to what the fe-developer reported and are **not login-helper regressions**. Both were adjudicated by PO as carved out to ABS-458 (`useDrawerURL.applyHash` product bug, forbidden by AC4's test-only constraint).

### home.spec.ts — 6 passed / 1 failed

| Test | Result | Notes |
|------|--------|-------|
| home.spec.ts:203 — AC3: 'active-seats' KPI opens board filtered to active run | ❌ | Pre-existing env failure (no active-run seed in abs430-e2e-pg) — identical to Iteration 1 finding. Not caused by ABS-456. |
| All other 6 home tests | ✅ PASS | |

---

## Acceptance Criteria Assessment

| AC | Criterion | Result | Evidence |
|----|-----------|--------|---------|
| AC1 | board/knowledge/filters navigate to target view after login | ✅ PASS | filters: 5/7 login-path ✅; board/knowledge: unchanged from ABS-416-fixed state ✅ |
| AC2 | Three suites green (re-scoped: login/landing-view path; excluding carved-out `#/ticket`/`#/seat`) | ✅ PASS | filters 5/7 ✅; the 2 excluded tests are product bug (ABS-458) + env failure |
| AC3 | home.spec.ts / inbox.spec.ts no regression | ✅ PASS | home:203 failure is pre-existing env issue (unchanged from iter-1); ABS-456 diff does not touch either spec |
| AC4 | Diff limited to `backend/apps/web/e2e/` | ✅ PASS | `git diff --name-only` = `filters.spec.ts` only (product scope); docs file is QAS evidence |

---

## PO Rescope Record

AC2 was re-scoped by PO (2026-07-19T11:09:30Z per ABS-458 origin comment) to:
> "login/landing-view path green across board/knowledge/filters; exclude exactly the two carved-out drawer-URL tests `#/ticket`/`#/seat`"

ABS-458 ("Fix `useDrawerURL.applyHash` to clean the URL hash on drawer close") confirmed in tracker — `status: Backlog`, created 2026-07-19T11:14:10Z.

---

## Verdict

**APPROVED** — All 4 acceptance criteria met under the PO-rescoped bar.  
No design flag → transitioning to **Story Acceptance**.
