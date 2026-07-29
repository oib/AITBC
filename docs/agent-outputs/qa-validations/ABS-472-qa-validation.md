# QA Validation Report — ABS-472

**Ticket**: ABS-472 — Product language: Mission Control naming + one vocabulary  
**Commit**: `896a32d3e49376ffca18db4a165f3096e2635d34`  
**Branch**: `ABS-472-auto`  
**Validator**: qas  
**Date**: 2026-07-19  
**Verdict**: ✅ **APPROVED**

---

## Acceptance Criteria Verification

| # | Criterion | Result | Evidence |
|---|-----------|--------|----------|
| AC1 | No user-visible 'Agentic Board Monitor' remains; browser tab reads "Mission Control" | ✅ PASS | `dist/index.html` title: `<title>Mission Control</title>`; `git grep -i "board monitor"` finds zero live strings in src; e2e ABS-472 test confirmed tab title; e2e also asserts `not.toContainText("Agentic Board Monitor")` |
| AC2 | aria-label names equal visible nav names (axe/e2e assertion) | ✅ PASS | KPI chips now read `"go to Board"` (was `"go to fleet"` / `"go to inbox"`); e2e asserts `contains("go to Board")` + `not.toMatch(/fleet\|inbox/)` for all 3 KPI testids |
| AC3 | Policies view explains audience and policy_rev in one plain sentence each | ✅ PASS | `PolicyView.tsx` diff verified: audience → "which agent role this policy applies to. Leave blank to apply to every role." (tooltip keeps `audience`); policy_rev → "The revision is the fingerprint of that resolved policy; agents record it in their audit trail…" (tooltip keeps `policy_rev`); "Org ∪ Project" de-jargoned with tooltip |

---

## Test Run Evidence (ABS-453 Green-Run Proof)

### Unit Tests — `node --test`
```
Command: npm test (node --import tsx --test --test-concurrency=1 "test/**/*.test.ts")
Result: 13 passed, 0 failed
Duration: 315ms
Commit: 896a32d3e49376ffca18db4a165f3096e2635d34
```
All 13 unit tests pass. Tests cover `orchControls`, `statusRollup`, `visibility`.

### TypeCheck — `tsc --noEmit`
```
Command: npm run typecheck
Result: PASS (no output = no errors)
Commit: 896a32d3e49376ffca18db4a165f3096e2635d34
```

### E2E Tests — `playwright test e2e/home.spec.ts` (ABS-453 proof)
**The ticket adds test cases to `e2e/home.spec.ts`; per ABS-453 a green-run of exactly this file is mandatory.**

```
Command: DATABASE_URL="postgres://postgres:postgres@localhost:5432/agentic" \
         E2E_DB_NAME="agentic_e2e_abs472" CI=1 \
         npx playwright test e2e/home.spec.ts --reporter=line

Results:
  [1/9] AC1: all 4 zones render (KPI, attention, epics, ticker)         ✅
  [2/9] ABS-472: browser tab and header read 'Mission Control'          ✅  ← NEW
  [3/9] ABS-472: KPI aria-labels use visible nav name (Board), not fleet/inbox ✅  ← NEW
  [4/9] AC2: no vertical scroll on main container at 1440×900           ✅
  [5/9] AC2: no vertical scroll on main container at 1280×800           ✅
  [6/9] AC3: 'needs-human' KPI opens Attention Inbox with no narrowing  ✅
  [7/9] AC3: 'active-seats' KPI opens board filtered to active run      ✅
  [8/9] AC5: SSE events update ticker without reload                    ✅
  [9/9] AC5: SSE disconnect shows reconnect banner with timestamp       ✅

9 passed, 0 failed (8.9s)
Commit: 896a32d3e49376ffca18db4a165f3096e2635d34
```

> **Note on first attempt**: A stale server from a prior playwright run (PID 3429)
> was running on port 8478, serving the pre-ABS-472 dist. With
> `reuseExistingServer: !process.env.CI = true`, the first test run hit that
> server and both new assertions failed (tab still "Agentic Board Monitor", KPI
> still "go to fleet"). After killing the stale server and re-running with
> `CI=1` (forces fresh server from the current dist), all 9 tests passed. The
> final green run is against the correct ABS-472 build.

---

## Implementation Review (Independent)

### Scope Compliance
- ✅ Wire-facing identifiers unchanged: `policy_rev` field, `audience` prop, API routes, event kinds — all unmodified
- ✅ `onNavigate` union `fleet|inbox` → `board-active|board-attention` is a **local discriminator only**; both board branches still call `setView("board")` — behavior unchanged
- ✅ No API routes renamed, no event kinds renamed

### Source Verification (AC1)
```bash
git grep -i "board monitor" backend/apps/web/src/ backend/apps/web/index.html
# → (no output) — zero stale brand in source
```

### Source Verification (AC2)
- `App.tsx:228`: nav button visible text is "Board" ✅
- `HomeView.tsx:138/148/163`: aria-labels read `"go to Board"` ✅
- No `fleet|inbox` in aria-labels ✅

### Source Verification (AC3)
- `PolicyView.tsx`: audience label → plain sentence + `title="audience (role token)"` tooltip ✅
- `PolicyView.tsx`: policy_rev section → "revision" display + `title="policy_rev"` tooltip + plain explanation ✅
- Placeholder "Audience (blank = all)" → "Agent role (blank = all roles)" ✅
- "Org ∪ Project" → wrapped in `<span title="Org ∪ Project resolution">` ✅

### Dist Build Verification (AC1)
- `dist/index.html`: `<title>Mission Control</title>` ✅
- Bundle contains "Mission Control" header text ✅

---

## Non-Blocking Advisories (Inherited from system-architect)
- `docs/agent-outputs/designs/ABS-348-design.md:55` contains "Agentic Board Monitor" in a historical ASCII wireframe of a completed design. Not user-visible, not in any AC. Left as-is per system-architect and scope boundary.
- a11y coordination: canonical nav name "Board" chosen; `ABS-467` (a11y) is Backlog, not in flight — no live conflict. "Relates" link still owed in tracker UI (adapter has no relates type).

---

## Definition of Done

| Item | Status |
|------|--------|
| All AC met and evidenced | ✅ |
| TypeCheck PASS | ✅ |
| Unit tests PASS (13/13) | ✅ |
| E2E green run attached (ABS-453 obligation) | ✅ 9/9 passed |
| Wire identifiers unchanged | ✅ |
| No over-engineering (minimal diff) | ✅ |
| QA report committed to branch | ✅ |

---

**Final Verdict**: ✅ **APPROVED for Story Acceptance**

All acceptance criteria verified independently. Green e2e run (9/9 including both new ABS-472 assertions) confirmed on commit `896a32d3`. No blocking findings.
