# QA Validation Report — ABS-474

**Ticket:** ABS-474 — Budget affordance: visible limit state, one-click path to set it  
**Branch:** ABS-474-auto  
**Commits (rebased):**
- `2488de66` — feat(web): make Home budget chip a one-click path to set a limit [ABS-474]
- `b432ec27` — docs(qa): ABS-474 QA validation report — APPROVED
- `e858151a` — fix(web): give formatAge a local binding in util.ts so tsc passes [ABS-474]

**QAS Iteration:** 2 of 3 (post-RTE Merging bounce; forward-fix rebase onto epic tip `d9d90bc6`)  
**Verdict:** APPROVED  
**Date:** 2026-07-19

---

## Context: Why Iteration 2

Iteration 1 (QAS APPROVED, commit `04e1417c`) passed all gates and advanced to Story Acceptance → Merging. The RTE seat bounced from Merging due to a rebase conflict (`App.tsx` + `BudgetChip.tsx`) against sibling stories ABS-465/ABS-475 already merged onto the epic branch. The implementer performed a forward-fix rebase onto `d9d90bc6` (current epic tip), resolved conflicts (ABS-465 burger nav coexists with ABS-474 chip wiring), added an out-of-scope `util.ts` TS2552 unblock (`e858151a`) pre-verified against the pristine epic tip. Architecture re-review APPROVED (Iteration 2 of 3). This is the QAS re-validation of the rebased branch.

---

## Acceptance Criteria Verification

| # | Criterion | Result | Evidence |
|---|-----------|--------|----------|
| AC1 | Clicking the Home budget chip opens the budget editor; setting a limit updates the chip without reload | ✅ PASS | e2e `budget.spec.ts "ABS-474 AC1"` — no-limit chip → click → UsageView budget editor auto-opens → save $50 → Home chip shows `$4.00 / $50`, no-limit class gone. Test 13/26 ✓ |
| AC2 | No-limit renders visually distinct from limit-set; 80%/100% bands render warning/critical (component test with three seeded ratios) | ✅ PASS | Unit `budgetState.test.ts` — 4 tests: 20%→normal, 85%→warning, 105%→exceeded, exact 80%/100% boundaries, no-limit distinctness, DAC-4 color-not-sole prefixes. Tests 6-9/48 ✓ |
| AC3 | Auth behavior unchanged; agent tokens still cannot set budgets | ✅ PASS | e2e `budget.spec.ts "ABS-474 AC3"` — bearer token PUT /budget → 403. Test 14/26 ✓ |

---

## Green-Run Proof (ABS-453 obligation)

**All commands run in `backend/apps/web/` within worktree `tmp/ABS-474-work`.**  
**Commit verified at HEAD:** `e858151a6c2256bd4ae5e56ef9679afc11e3b07f`

### Unit Tests — `test/budgetState.test.ts` (new file, AC2 tests)

**Command:** `npm test` (node --test)  
**Result: 48 passed, 0 failed**

```
✔ AC2: three seeded ratios classify into normal / warning / critical bands (1.11ms)
✔ AC2: band boundaries — exactly 80% is warning, exactly 100% is critical (0.06ms)
✔ AC2: no limit set is a distinct warning affordance, not a spend band (0.07ms)
✔ AC2: warning / critical bands carry color-not-sole text prefixes (DAC-4) (0.05ms)
[... + 44 existing baseline tests across budgetState, util, component tests ...]
ℹ tests 48
ℹ pass 48
ℹ fail 0
ℹ duration_ms 1322.582959
```

### E2E Tests — Full Suite Fresh Run (budget + home + mobile)

**Command:**  
```
DATABASE_URL=postgres://postgres:pw@localhost:55411/agentic \
  E2E_DB_NAME=agentic_e2e_474_qas2 \
  npx playwright test e2e/budget.spec.ts e2e/home.spec.ts e2e/mobile.spec.ts
```
**Commit:** `e858151a` (HEAD of ABS-474-auto)  
**Result: 26 passed, 0 failed**

```
✓  1 [desktop] › budget.spec.ts › AC1: normal state (520ms)
✓  2 [desktop] › budget.spec.ts › AC1: warning state ≥ 80% (124ms)
✓  3 [desktop] › budget.spec.ts › AC1: exceeded state ≥ 100% (110ms)
✓  4 [desktop] › budget.spec.ts › AC1: 2-run project (125ms)
✓  5 [desktop] › budget.spec.ts › AC2: run grouping (1.5s)
✓  6 [desktop] › budget.spec.ts › AC2: epic grouping (1.5s)
✓  7 [desktop] › budget.spec.ts › AC2: seat grouping (1.6s)
✓  8 [desktop] › budget.spec.ts › AC2: day grouping (1.6s)
✓  9 [desktop] › budget.spec.ts › AC3: incomplete-cost badge (1.5s)
✓ 10 [desktop] › budget.spec.ts › AC4: human round-trip (2.0s)
✓ 11 [desktop] › budget.spec.ts › AC4: agent token → 403 (8ms)
✓ 12 [desktop] › budget.spec.ts › AC5: Inbox budget link → Usage (1.8s)
✓ 13 [desktop] › budget.spec.ts › ABS-474 AC1: no-limit chip → editor → save → chip updated (2.0s) ✅
✓ 14 [desktop] › budget.spec.ts › ABS-474 AC3: bearer token → 403 unchanged (11ms) ✅
✓ 15 [desktop] › home.spec.ts › AC1: all 4 zones render (796ms)
✓ 16 [desktop] › home.spec.ts › ABS-462 AC1: no coexistence with no-orchestrators (760ms)
✓ 17 [desktop] › home.spec.ts › AC2: no vertical scroll 1440×900 (762ms)
✓ 18 [desktop] › home.spec.ts › AC2: no vertical scroll 1280×800 (757ms)
✓ 19 [desktop] › home.spec.ts › AC3: needs-human KPI opens Inbox (797ms)
✓ 20 [desktop] › home.spec.ts › AC3: active-seats KPI opens board filtered (777ms)
✓ 21 [desktop] › home.spec.ts › AC5: SSE events update ticker (775ms)
✓ 22 [desktop] › home.spec.ts › AC5: SSE disconnect shows reconnect banner (764ms)
✓ 23 [mobile]  › mobile.spec.ts › AC1: burger menu nav entries reachable (838ms)
✓ 24 [mobile]  › mobile.spec.ts › AC2: opening Live Spawns no layout shift (796ms)
✓ 25 [mobile]  › mobile.spec.ts › AC3: ticker hidden drawer (840ms)
✓ 26 [mobile]  › mobile.spec.ts › smoke: no horizontal overflow at 375px (756ms)

26 passed (26.3s)
```

> **Note — mobile spec run order:** An initial isolated run of `mobile.spec.ts` alone (after a
> separate `budget+home` desktop run) produced 4 mobile failures. Investigation confirmed this was
> a `reuseExistingServer` artifact — Playwright reused the server from the prior invocation whose
> DB state was inconsistent with the fresh mobile seed expectations. A **fresh full-suite run**
> (single invocation, new isolated DB `agentic_e2e_474_qas2`) yielded 26/26 green. This is an
> environment/test-infrastructure artefact, not a code defect. ABS-465 conflict resolution is
> verified correct in the fresh run (tests 23–26 pass).

---

## Quality Gates (independently verified in this seat)

| Gate | Result |
|------|--------|
| `tsc --noEmit` (typecheck) | ✅ PASS — clean, exit 0 |
| `npm test` (unit, node --test) | ✅ PASS — 48/48 |
| `eslint src/ test/` | ✅ PASS — clean, exit 0 |
| `tsc -b && vite build` | ✅ PASS — 247.5 kB bundle, 61 modules |
| e2e `budget.spec.ts` (incl. 2 new ABS-474) | ✅ PASS — 14/14 ✓ |
| e2e `home.spec.ts` (regression) | ✅ PASS — 8/8 ✓ |
| e2e `mobile.spec.ts` (ABS-465 regression) | ✅ PASS — 4/4 ✓ (fresh run) |

---

## Conflict Resolution Assessment

The forward-fix rebase resolved two conflicts:

**App.tsx:** Both ABS-465's `menuOpen`/`go()` burger nav state **and** ABS-474's
`openBudgetOnEntry`/`consumeBudgetOpen` chip wiring coexist correctly. The old
ABS-419 `dest==="usage"` deep-link branch is correctly absent (chip routes via
`onEditBudget`). The epic-deleted `lastSeenAt`/`unreadCount` block was correctly
not reintroduced.

**BudgetChip.tsx:** Doc-comment merge only; the button/onEditBudget code
auto-merged cleanly. Both features coexist with no behavior regression.

**`e858151a` (util.ts, out-of-scope unblock):** Verified against the pristine epic
tip — a genuine pre-existing ABS-470 defect (TS2552 on `export { formatAge } from …`
used locally by `humanizeTimestamp`). One-line import+re-export fix, no behavior
change. Correctly attributed and flagged to the epic owner.

---

## Flags

- No `design` flag → transition target: **Story Acceptance** (not Design Test)
- No DB migrations, no RLS changes
- Iteration: **2 of 3**

---

**QAS Final Verdict: APPROVED** — All three ACs independently verified via green test runs on rebased commits. unit 48/48 · e2e 26/26 (fresh) · tsc/eslint/build clean.
