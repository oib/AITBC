# QA Validation Report — ABS-472 (Re-validation after rebase bounce, r2)

**Ticket**: ABS-472 — Product language: Mission Control naming + one vocabulary  
**QAS run**: r2 (after RTE rebase-bounce; rebased onto epic tip `a488c314`)  
**Branch**: `ABS-472-auto`  
**Commit under test**: `dc791006` (implementation, rebased onto `a488c314`)  
**HEAD at report time**: `c0402eb0` (includes old r1 QA report commit on top of `dc791006`)  
**Validator**: qas  
**Date**: 2026-07-19  
**Verdict**: ✅ **APPROVED**

---

## Context

The first QAS pass (r1, commit `896a32d3`) APPROVED and the ticket reached Merging. The RTE's
rebase onto `epic/ABS-460-mission-control-ux-hardening` failed: epic had since absorbed ABS-464,
ABS-466, ABS-467, ABS-471, ABS-474, ABS-475, all touching overlapping web files. The be-developer
rebased `ABS-472-auto` forward onto the epic tip `a488c314` and re-resolved all three conflicts:

| Path | Conflict resolution |
|------|---------------------|
| `index.html` | ABS-475 pre-paint theme `<script>` retained; `<title>` → "Mission Control" |
| `src/components/HomeView.tsx` | ABS-474 `onEditBudget` prop kept; ABS-472 `onNavigate` union rename applied |
| `e2e/home.spec.ts` | ABS-462 AC1 test preserved; both ABS-472 assertions present |

System-architect (Stage 1 re-gate) verified conflict resolution sound on `dc791006` and approved.

---

## Acceptance Criteria Verification

| # | Criterion | Result | Evidence |
|---|-----------|--------|----------|
| AC1 | No user-visible 'Agentic Board Monitor' remains; browser tab reads "Mission Control" | ✅ PASS | `dist/index.html` `<title>Mission Control</title>`; `grep "Agentic Board Monitor\|Board Monitor" dist/assets/index-ZKEjpPXC.js` → 0 matches; e2e [3/10] confirmed tab + header |
| AC2 | aria-label names equal visible nav names (e2e assertion) | ✅ PASS | All 3 KPI `aria-label` attrs read `"…go to Board"` (HomeView.tsx:172/182/197); e2e [4/10] asserts `contains("go to Board")` + `not.toMatch(/fleet\|inbox/)` |
| AC3 | Policies view explains audience and policy_rev in one plain sentence each | ✅ PASS | `PolicyView.tsx:201`: "— which agent role this policy applies to. Leave blank to apply to every role." (tooltip `audience`); `:383–384`: "The revision is the fingerprint of that resolved policy; agents record it in their audit trail…" (tooltip `policy_rev`) |

---

## Green-Run Proof (ABS-453 — test file changed)

`e2e/home.spec.ts` was modified by this ticket (two new ABS-472 assertions). A green-run of
exactly this file is mandatory per ABS-453.

**Build step (fresh from rebased source)**:
```
npx tsc -b && npx vite build
→ 63 modules transformed, 0 errors. dist/index.html, dist/assets/index-ZKEjpPXC.{css,js} emitted.
```

**E2E run**:
```
Command: DATABASE_URL="postgres://postgres:pw@localhost:55432/agentic" \
         E2E_DB_NAME="agentic_e2e_abs472_regate" CI=1 \
         npx playwright test e2e/home.spec.ts --reporter=line

Results (commit dc791006 / HEAD c0402eb0):
  [1/10]  AC1: all 4 zones render (KPI, attention, epics, ticker)           ✅
  [2/10]  ABS-462 AC1: a listed spawn host never coexists with 'no orchs'   ✅
  [3/10]  ABS-472: browser tab and header read 'Mission Control'             ✅  ← NEW
  [4/10]  ABS-472: KPI aria-labels use visible nav name (Board), not fleet/inbox ✅  ← NEW
  [5/10]  AC2: no vertical scroll on main container at 1440×900              ✅
  [6/10]  AC2: no vertical scroll on main container at 1280×800              ✅
  [7/10]  AC3: 'needs-human' KPI opens Attention Inbox with no narrowing     ✅
  [8/10]  AC3: 'active-seats' KPI opens board filtered to active run         ✅
  [9/10]  AC5: SSE events update ticker without reload                       ✅
  [10/10] AC5: SSE disconnect shows reconnect banner with last-data timestamp ✅

10 passed, 0 failed (9.8s)
```

> Note: 10 tests vs 9 in r1 — ABS-462 AC1 test was added by epic integration before this re-gate.

**Unit tests**:
```
Command: node --import tsx --test --test-concurrency=1 "test/**/*.test.ts"
Result: 52 passed, 0 failed (1516ms)
```
(52 vs 13 in r1 — additional unit tests landed in the epic branch from other stories.)

**TypeCheck**:
```
Command: npx tsc --noEmit
Result: PASS (no output = no errors)
```

---

## Scope Compliance

- ✅ Wire-facing identifiers unchanged: `policy_rev` field, `audience` prop, API routes, event kinds
- ✅ `onNavigate` union `fleet|inbox` → `board-active|board-attention` is a local discriminator only; both branches still call `setView("board")` — behavior unchanged
- ✅ ABS-474 `onEditBudget` prop preserved in conflict resolution
- ✅ ABS-475 pre-paint theme script preserved in `index.html` conflict resolution
- ✅ ABS-462 AC1 test preserved in `home.spec.ts` conflict resolution

---

## Non-Blocking Advisories (Inherited)

- `docs/agent-outputs/designs/ABS-348-design.md:55` contains "Agentic Board Monitor" in a historical ASCII wireframe of a completed design. Not user-visible, not in any AC. Out of scope per system-architect advisory.
- "Relates" link to ABS-467 (now absorbed into epic — no live conflict) still owed in tracker UI.

---

## Definition of Done

| Item | Status |
|------|--------|
| All AC met and evidenced | ✅ |
| TypeCheck PASS | ✅ |
| Unit tests PASS (52/52) | ✅ |
| E2E green run attached (ABS-453 obligation) — 10/10 including both new ABS-472 assertions | ✅ |
| Fresh build verified (63 modules) | ✅ |
| Rebase conflict resolution sound (per Stage 1 gate + independent verification) | ✅ |
| Wire identifiers unchanged | ✅ |
| Epic integrations (ABS-462/ABS-474/ABS-475) preserved | ✅ |

---

**Final Verdict**: ✅ **APPROVED for Story Acceptance**

All 3 ACs verified independently on rebased commit `dc791006`. Green e2e run: 10 passed, 0 failed
on `e2e/home.spec.ts` (CI=1, fresh server from current dist), including both new ABS-472
assertions. Unit 52/52, typecheck clean. Rebase conflict resolution verified sound. No blocking
findings. No design flag — releasing to Story Acceptance.
