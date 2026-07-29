# QA Validation Report — ABS-469 (Re-validation after RTE rebase-bounce)

**Ticket:** ABS-469 — Consolidate Report into Usage; de-leak internals from the UI
**Branch:** ABS-469-auto (rebased onto `epic/ABS-460-mission-control-ux-hardening` tip `8dabfbb5`)
**Commits:** `7a9dddd0` (implementation) + `a0301496` (QA report)
**Validator:** qas
**Date:** 2026-07-20
**Verdict:** ✅ APPROVED

---

## Context

This is a **re-validation** after the RTE rebase-bounce (ABS-469 previously approved at `a2633fa8`,
but rebased due to 4 conflicts on the epic branch). The BE re-resolved conflicts onto
`epic/ABS-460-mission-control-ux-hardening` tip `8dabfbb5` (carrying ABS-465/466/474/477 work).
The system-architect completed a Stage 1 re-review and approved. This QAS run re-verifies all 4 ACs
on the rebased tree and provides a new green-run proof (ABS-453).

---

## Acceptance Criteria Verification

### AC1 — Nav shows one cost view (Usage) with all former Report pivots; /report deep-links redirect

**Result: ✅ PASS**

- `ReportView.tsx` deleted (`git rm`); Report nav entry removed from `App.tsx`.
- `UsageView` group switcher: Run / Epic / Seat / Day / **Story** / **Tools** (6 groups). Story
  (`/report by_story`) and Tools (`/report tools`) are the only additive pivots; Seat ≡ "By Agent"
  and Epic ≡ "By Epic" were already present.
- Legacy `/report` deep-links redirect to Usage via mount effect; path cleaned via
  `history.replaceState`; project context API-derived (not URL path).
- Epic ABS-465/466/474/477 changes to App.tsx correctly preserved (burger menu, budget-on-entry,
  ConnectionBanner/skeleton/error surface).
- **e2e evidence:** `report.spec.ts` 4/4 PASS — "Report nav entry is gone", "Usage carries Story + Tools",
  redirect, `nav-report` count = 0.

---

### AC2 — grep of web src shows no snake_case column labels rendered to users

**Result: ✅ PASS**

- Independent grep of `src/` confirms all `tokens_in`, `tokens_out`, `cost_usd` occurrences are
  **data field accesses** (computation, reduce, cell value rendering) or type definitions — never
  rendered as column header labels.
- Actual `<th>` labels: **Key, Spawns, Tokens in, Tokens out, Cost, Budget, Role, Tools used,
  Granted but never used** — all humanized.
- Developer "Supersedes scripts/orchestrator-report.sh" footer removed from the UI.
- Epic's ABS-466 `col-secondary` responsive classes preserved (headers already humanized — no AC2
  regression, no ABS-466 regression).
- **e2e evidence:** `report.spec.ts` test 3 asserts page body contains no `tokens_in`/`cost_usd`/
  `Supersedes`/`orchestrator-report.sh` — PASS.

---

### AC3 — Banner absent on $0.00-clean dataset; present with real unknown-model rows

**Result: ✅ PASS**

- Banner (`data-testid="incomplete-notice"`) keyed on `anyRowIncomplete = rows.some((r) => r.incomplete)`.
- Sentence case: `⚠ Incomplete cost — some rows use unknown models, so dollar totals are a floor, not exact.`
- Per-row `⚠` icon with tooltip kept.
- `reportRowToUsage` sets `incomplete: false` for Story/Tools pivots — no spurious banner on report data.
- **e2e evidence:** `budget.spec.ts` AC3 test: unknown-model row → `incomplete-notice` visible;
  clean datasets → absent — PASS.

---

### AC4 — Existing usage/report e2e adapted and green

**Result: ✅ PASS**

- `report.spec.ts` fully rewritten (4 tests for consolidated Usage view).
- `filters.spec.ts`, `inbox.spec.ts`, `budget.spec.ts` retargeted off removed nav-report.
- Epic's `inbox.spec.ts` version taken wholesale (already retargeted off nav-report by the epic's
  Inbox v2 rewrite — ABS-469's conflict resolution chose the epic version, correct).
- **All 34 targeted tests: PASS.**

---

## Independent Test Run Evidence (ABS-453)

**Branch:** `ABS-469-auto`
**Commit (HEAD):** `a03014960ba5d7720a57e44e80ad28ad60ef4db9`
**Implementation commit:** `7a9dddd0`

```
TypeScript check (tsc --noEmit):
  EXIT 0 — clean

Vite build:
  ✓ 65 modules transformed
  249.56 kB / gzip: 75.39 kB
  built in 323ms — clean

Unit tests (node --import tsx --test):
  pass: 52  fail: 0  skipped: 0  (52/52)
  (52 vs 13 from pre-rebase run — epic branch added 39 tests from ABS-466/477/etc.)

E2E — targeted files (ABS-453 green-run proof):
  Command: DATABASE_URL=postgres://postgres:pw@localhost:55432/agentic npm run test:e2e -- --reporter=list e2e/report.spec.ts e2e/budget.spec.ts e2e/filters.spec.ts e2e/inbox.spec.ts
  Result:  34 passed, 0 failed (20.9s)
  Commit:  a03014960ba5d7720a57e44e80ad28ad60ef4db9

  report.spec    4/4  PASS  (AC1 redirect+pivots, AC2 no-snake_case, AC4 adapted)
  budget.spec   14/14 PASS  (AC3 banner + budget mechanics)
  filters.spec   7/7  PASS  (retargeted, no nav-report refs)
  inbox.spec     9/9  PASS  (epic version, no nav-report refs)

E2E — full suite (pre-existing failure triage):
  96 passed, 2 failed, 1 skipped
  Failing tests (UNRELATED TO ABS-469):
    a11y.spec.ts:106 — strict mode violation on 'target status' (ABS-464 transition-more UX, pre-existing on epic)
    board.spec.ts:128 — ABS-464 backward-move test card-id parse failure (pre-existing on epic)
  Skipped: knowledge.spec.ts:181 — pre-existing, unrelated.
  Both pre-existing failures exist on the epic branch independent of ABS-469.
```

---

## Additional Checks

- **ABS-434 fastlane docs /report reference:** No docs reference the `/report` route. Confirmed unaffected.
- **Redirect safety:** Project derived from API response, not URL path — no context loss.
- **Epic work preserved:** ABS-465 burger menu, ABS-466 responsive columns, ABS-474 budget-on-entry,
  ABS-477 ConnectionBanner/skeleton/error — all intact in rebased diff.
- **Orphaned `handleNavigate` removed:** Its only consumer was `ReportView`; removing it keeps tsc clean.
- **Net diff vs epic tip:** +279 / -395 lines (including the QA report file).

---

## Final Verdict

**✅ APPROVED — all 4 ACs met; 34/34 targeted e2e green; typecheck/build/unit clean;
no design flag; pre-existing a11y/board failures unrelated to this ticket.**

**Exit → Story Acceptance** (no design flag; Design Test skipped per exit protocol).
