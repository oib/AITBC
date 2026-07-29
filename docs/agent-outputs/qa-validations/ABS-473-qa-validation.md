# QA Validation Report — ABS-473

**Ticket**: ABS-473 — Deep links: routable views and filter state  
**Branch**: `ABS-473-auto`  
**HEAD commit**: `27b57977` (DAC-6 fix: focus main landmark on view change)  
**Validator**: QAS (In Test gate, second pass — resume:true)  
**Date**: 2026-07-20  
**Verdict**: ✅ **APPROVED** — Iteration 1 of 3

---

## Context

This report supersedes the prior QA report (written at `86836452`). The System Architect
(second Stage-1 pass) routed the story back to In Test after approving the DAC-6 delta
(`27b57977`): a view-keyed `useEffect` in `App.tsx` that focuses `main.main` on view
change (nav + browser back/forward, skipping initial mount), plus a new e2e assertion in
`a11y.spec.ts`. This report re-verifies all story ACs and produces the ABS-453
green-run proof for the changed test files.

**Commits validated** (`ABS-473-auto` branch, from base):
```
27b57977  fix(web): focus main landmark on view change (DAC-6) [ABS-473]
2ace6cfe  docs(web): fix design §2.1 — 6 routable tokens; report is redirect alias [ABS-473]
a2228eb2  docs(qa): ABS-473 QA validation report — APPROVED [ABS-473]
86836452  docs(adr): reconcile ADR-A-0027 prose with shipped grammar [ABS-473]
85d852af  feat(web): routable views + deep-link filter/drawer state [ABS-473]
a10a6d82  docs(web): add deep-link routing design and DACs [ABS-473]
cee670cc  docs(adr): ADR-A-0027 dashboard URL grammar v2 [ABS-473]
```

---

## Acceptance Criteria Verification

| # | Criterion | Evidence | Result |
|---|-----------|----------|--------|
| AC1 | Pasting a deep link opens the right view with filters applied and drawer open (e2e round-trip) | `filters.spec.ts` — "ABS-473 AC1: pasting a deep link opens the right view with filter applied and drawer open" — PASSED | ✅ PASS |
| AC2 | Browser back closes an opened drawer; a second back returns to the previous view (e2e) | `filters.spec.ts` — "ABS-473 AC2: browser back closes the drawer; a second back returns to the previous view" — PASSED | ✅ PASS |
| AC3 | ABS-420 drawer round-trip semantics preserved; useDrawerURL tests UPDATED to new contract and green | `routing.test.ts` 13 grammar+legacy tests green; `filters.spec.ts` ABS-420 Esc-cleanup tests pass under new grammar; 75/75 unit total | ✅ PASS |
| AC4 | Inert filters on views where they have no effect (e2e spot-check ADR Register) | `filters.spec.ts` — "ABS-473 AC4: on the ADR Register all four global filters are visibly inert" — PASSED (`data-applicable=false` + disabled on all 4 dims) | ✅ PASS |

---

## Test Run Evidence (ABS-453 Green-Run Proof)

### Unit Tests — `routing.test.ts` + full suite

**Command**: `npm test` (`node --import tsx --test --test-concurrency=1 "test/**/*.test.ts"`)  
**Commit**: `27b57977`  
**Location**: `backend/apps/web/`

```
✔ parseHash: empty hash -> home view, no drawer
✔ parseHash: view token only
✔ parseHash: unknown view token falls back to home
✔ parseHash: report token redirects to usage (ABS-469)
✔ parseHash: view + ticket item param
✔ parseHash: view + seat item param
✔ parseHash: legacy ABS-420 #/ticket/<key> -> home view + drawer
✔ parseHash: legacy ABS-420 #/seat/<id> -> home view + drawer
✔ parseHash: malformed item param is ignored
✔ buildHashFragment: view only
✔ buildHashFragment: view + drawer
✔ round-trip: build -> parse is identity for the new grammar
✔ round-trip: identifiers with reserved chars survive encode/decode
[...62 tests from other files, all passing...]
ℹ tests 75
ℹ pass 75
ℹ fail 0
ℹ duration_ms 1662.507083
```

### E2E Tests — `a11y.spec.ts` (ABS-473 DAC-6 test, per ABS-453)

**Command**: `DATABASE_URL=postgres://postgres:pw@localhost:55432/agentic_e2e npx playwright test e2e/a11y.spec.ts --project desktop --grep "DAC-6"`  
**Commit**: `27b57977`

```
Running 1 test using 1 worker

  ✓  1 [desktop] › e2e/a11y.spec.ts:106:1 › ABS-473 DAC-6: view nav and browser back move focus to the main landmark (1.0s)

  1 passed (2.9s)
```

**Full `a11y.spec.ts` run** (6 tests):

```
Running 6 tests using 1 worker

  ✓  1 [desktop] › e2e/a11y.spec.ts:65:1  › AC1: Home has zero serious/critical a11y violations (1.0s)
  ✓  2 [desktop] › e2e/a11y.spec.ts:73:1  › AC1: Board has zero serious/critical a11y violations; AC3 legend present (1.1s)
  ✓  3 [desktop] › e2e/a11y.spec.ts:87:1  › AC1: open ticket drawer has zero serious/critical a11y violations (1.2s)
  ✓  4 [desktop] › e2e/a11y.spec.ts:99:1  › AC3: status-color legend is discoverable on the Home attention list (744ms)
  ✓  5 [desktop] › e2e/a11y.spec.ts:106:1 › ABS-473 DAC-6: view nav and browser back move focus to the main landmark (800ms)
  ✘  6 [desktop] › e2e/a11y.spec.ts:126:1 › AC2: keyboard-only path board → card → drawer → transition confirm (827ms)

  1 failed, 5 passed
```

> **Note on AC2 pre-existing failure** — The AC2 test (`keyboard-only path board → card → drawer → transition confirm`) fails with:
> ```
> Error: strict mode violation: getByLabel('target status') resolved to 2 elements:
>   1) <select aria-label="target status" data-testid="transition-target">…</select>
>   2) <select data-testid="transition-target-more" aria-label="backward or exotic target status">…</select>
> ```
> This is a **pre-existing defect** in `a11y.spec.ts` caused by the transition-controls split in
> `TicketDrawer.tsx` (the primary and secondary target selects each carry `aria-label="target status"`,
> making `getByLabel` resolve 2 elements). `TicketDrawer.tsx` and `transition-controls` are
> **not touched by the ABS-473 branch**. The System Architect confirmed this in the Stage-1 gate-results
> comment: "genuine pre-existing drift from the transition-controls split in `TicketDrawer.tsx` —
> NOT an ABS-473 regression, correctly avoided as a cross-ticket drive-by."
> Fix: use `getByTestId("transition-target")` (one-liner). Route to the ABS-467/TicketDrawer owner.
> Classification: **code** — separate ticket.

### E2E Tests — `filters.spec.ts` (full suite, incl. ABS-473 AC1/AC2/AC4)

**Command**: `DATABASE_URL=postgres://postgres:pw@localhost:55432/agentic_e2e npx playwright test e2e/filters.spec.ts --project desktop`  
**Commit**: `27b57977`

```
Running 10 tests using 1 worker

  ✓   1 [desktop] › e2e/filters.spec.ts:110:1 › AC1: epic+role filters persist across view switch and page reload (297ms)
  ✓   2 [desktop] › e2e/filters.spec.ts:160:1 › AC2: #/ticket/<key> cold navigation opens TicketDrawer; Esc closes and cleans URL (149ms)
  ✓   3 [desktop] › e2e/filters.spec.ts:180:1 › AC2: #/seat/<id> cold navigation opens SeatDrawer; Esc closes and cleans URL (143ms)
  ✓   4 [desktop] › e2e/filters.spec.ts:223:1 › AC3: saved filter applies all dimensions in one click; count badge matches (312ms)
  ✓   5 [desktop] › e2e/filters.spec.ts:261:1 › AC4: non-applicable dimension greyed in non-board views; value preserved on switch-back (262ms)
  ✓   6 [desktop] › e2e/filters.spec.ts:300:1 › AC5: KPI agent-row click produces same URL state as manual role filter (single mechanism) (245ms)
  ✓   7 [desktop] › e2e/filters.spec.ts:352:1 › Design AC: empty result state names active filters and offers clear (225ms)
  ✓   8 [desktop] › e2e/filters.spec.ts:388:1 › ABS-473 AC1: pasting a deep link opens the right view with filter applied and drawer open (182ms)
  ✓   9 [desktop] › e2e/filters.spec.ts:404:1 › ABS-473 AC2: browser back closes the drawer; a second back returns to the previous view (216ms)
  ✓  10 [desktop] › e2e/filters.spec.ts:430:1 › ABS-473 AC4: on the ADR Register all four global filters are visibly inert (212ms)

  10 passed (3.9s)
```

### TypeScript Type Check

**Command**: `npx tsc --noEmit`  
**Commit**: `27b57977`  
**Result**: CLEAN — no output, exit 0

---

## Implementation Review (Delta `86836452..27b57977`)

The only code change in the DAC-6 delta is a view-keyed `useEffect` in `App.tsx`:

```typescript
// ABS-473 DAC-6: on a view change — whether from a nav click or a browser
// back/forward that lands on a different view — move focus to the active
// <main> landmark so keyboard and screen-reader users land in the new view's
// content (design §8). Skip the initial mount so a cold-loaded deep link (and
// any drawer it opens) keeps its own focus rather than being yanked to <main>.
const isFirstViewRender = useRef(true);
useEffect(() => {
  if (isFirstViewRender.current) {
    isFirstViewRender.current = false;
    return;
  }
  const main = document.querySelector<HTMLElement>("main.main");
  if (main) {
    main.tabIndex = -1; // make the landmark programmatically focusable
    main.focus();
  }
}, [view]);
```

**Assessment**: Minimal, additive, correct-altitude. The `useEffect` is keyed on `view` (from `useRoutingURL`) so it fires on every view change (nav click or `popstate` back). The initial-mount skip prevents focus interference on cold deep-link load. The `tabIndex = -1` trick makes `<main>` programmatically focusable without adding a tab stop. Conforms to ADR-A-0027 §8.

---

## Key Seams Verified (Full Branch)

| Component | Expected | Actual |
|-----------|----------|--------|
| `useDrawerURL.ts` | Extended into `useRoutingURL`; exports `parseHash`, `buildHashFragment`, `useRoutingURL` | ✅ Single file, backward-compatible; no fork |
| `App.tsx` | View state from hash; nav + ABS-469 redirect + DAC-6 focus effect | ✅ Confirmed — `useRoutingURL()` drives view; DAC-6 `useEffect` present and tested |
| `GlobalFilterBar.tsx` | `applicable()` matrix; `data-applicable`, `disabled`, `title` attributes | ✅ Confirmed — board=all4; timeline=run+timeRange; home/adrs/policies/usage=none |
| `ADR-A-0027` | Committed as `proposed`; human ratification at epic merge (ADR-A-0004) | ✅ Committed; reconciled at `86836452`; 6 routable tokens documented |
| Legacy ABS-420 links | `#/ticket/<key>` and `#/seat/<id>` graceful fallback | ✅ `parseHash` shim; AC2 e2e tests cover both cases |
| History semantics | view-nav → pushState; drawer-open → pushState; close/filter → replaceState | ✅ AC2 e2e proves pushState; replaceState via Esc cleanup tests |

---

## Definition of Done

- [x] All 4 story ACs verified with evidence (e2e + unit) at `27b57977`
- [x] Test files changed: `routing.test.ts` (+13 tests, 75/75 green), `filters.spec.ts` (+3 ABS-473 tests, 10/10 green), `a11y.spec.ts` (+1 DAC-6 test, green) — green-run proofs attached above (ABS-453 ✅)
- [x] TypeScript CLEAN at `27b57977`
- [x] ADR-A-0027 committed (`proposed`; ratification at epic→main merge per ADR-A-0004)
- [x] ABS-420 contract superseded; tests updated to new grammar and green
- [x] `useDrawerURL.ts` extended (not forked)
- [x] DAC-6 (focus `<main>` on view change) verified via `a11y.spec.ts` test — PASS
- [x] Pre-existing `a11y.spec.ts` AC2 locator failure documented; classified as cross-ticket `code` defect (ABS-467/TicketDrawer owner); not an ABS-473 regression

---

## Cross-Ticket Finding

**`a11y.spec.ts` AC2 locator defect** — `getByLabel("target status")` resolves to 2 elements because
the transition-controls split created two `aria-label="target status"` selects in `TicketDrawer.tsx`.
Fix: `getByTestId("transition-target")`. Route to ABS-467 / TicketDrawer owner. One-liner.

---

**Final verdict: APPROVED — Iteration 1 of 3**  
All 4 story ACs met. 75/75 unit + 10/10 filters.spec.ts + 1/1 DAC-6 e2e green at commit `27b57977`.  
Pre-existing AC2 locator failure in `a11y.spec.ts` is not an ABS-473 regression (documented above).  
Design flag is set → releasing to **Design Test** (pipeline: In Test → Design Test → Story Acceptance).
