# QA Validation Report — ABS-475
**Title:** Dark mode with theme setting: automatic / dark / light  
**Branch:** `ABS-475-auto`  
**Impl commit:** `27c6e06d` (rebased onto epic tip `640bbfb0` after RTE bounce)  
**QA report commit:** this file (re-validation pass)  
**QAS run date:** 2026-07-19  
**Verdict:** ✅ APPROVED (re-validation after rebase forward-fix)

---

## Context: Rebase Bounce

RTE bounced the story at `Merging` due to conflicts on `App.tsx` and `styles.css` after ABS-462 (`640bbfb0`) landed on the epic branch. The be-developer forward-fixed by rebasing `ABS-475-auto` onto epic tip `640bbfb0`, producing commit `27c6e06d`. The system architect re-reviewed the rebase resolution (Stage 1 re-review, approved). This is QAS's independent re-validation of the rebased state.

---

## Gate Results

| Gate | Command | Result |
|------|---------|--------|
| TypeScript | `tsc --noEmit` | ✅ PASS (EXIT 0) |
| Unit tests | `node --import tsx --test --test-concurrency=1 "test/**/*.test.ts"` | ✅ **22/22 PASS** |
| ESLint | `eslint src/ e2e/ test/ --max-warnings=0` | ✅ PASS (EXIT 0) |
| Vite build | `tsc -b && vite build` | ✅ PASS (55 modules) |
| Pre-paint init script | `grep -c "data-theme" dist/index.html` | ✅ 2 refs confirmed |
| E2E theme spec | `playwright test e2e/theme.spec.ts` | ✅ **5/5 PASS** |
| Full E2E suite | `playwright test` | ⚠️ **65 passed / 1 skipped / 1 failed** |
| AC4 manual hex grep | `git grep -En "#[0-9a-fA-F]{3,6}\b" src/ :(exclude)src/theme.css` | ✅ 0 offenders |

All gates run **independently by QAS** against rebased commit `27c6e06d` (`HEAD: 8f09cea0`) on branch `ABS-475-auto`.

### Full-suite failure classification

**Failing test:** `e2e/eventfeed-timeline.spec.ts:159 › AC2: Browse mode shows paginated events; Follow button resumes live mode`

**Failure cause:**
```
Error: locator.selectOption: Error: strict mode violation: getByLabel('Run') resolved to 2 elements:
  1) <button aria-label="Stop run on ac2-inst-1784479702130"> ← ABS-462 new control
  2) <select aria-label="Run" data-testid="filter-select-run">…</select>
```

**Classification: pre-existing / external-sibling regression** (ABS-462, NOT ABS-475).

Evidence:
- ABS-475 (`27c6e06d`) changes: `theme.css`, `theme.ts`, `ThemeToggle.tsx`, `BudgetChip.tsx` (hex removal), `styles.css` (hex removal), `App.tsx` (+2 lines: import + `<ThemeToggle />`), `index.html` (init script), `test/theme.test.ts`, `e2e/theme.spec.ts`. Zero overlap with eventfeed, timeline, filter, or pagination logic.
- The "Stop run" button (`aria-label="Stop run on {instance}"`) was introduced by ABS-462's orchestrator controls refactor (`orchControls.ts`). Its `aria-label` now clashes with the filter `select[aria-label="Run"]` in Playwright strict mode.
- Prior QAS pass (pre-rebase, old epic base): full suite 65/1/**0** — the failure did not exist at `3b7543dc` before `640bbfb0` was merged.
- ABS-475 cannot cause a feed-count/pagination failure by swapping CSS custom properties.

**Routing:** Routed to epic owner / ABS-462 for `aria-label` disambiguation on the Stop-run button. Not an ABS-475 blocker.

---

## Acceptance Criteria Verification

### AC1: Three-way setting visible and persistent; `automatic` follows live OS scheme change
**✅ PASS**
- Unit: `normalizeThemePref` coerces unknowns → `'auto'`; `themeAttr` maps auto→null (OS governs), dark/light→explicit attribute.
- E2E `theme.spec.ts` test 1: select visible, dark/light/auto all persisted across `page.reload()`. PASS.
- E2E `theme.spec.ts` test 2: `page.emulateMedia({colorScheme:'dark'})` changes body background; manual `light` wins under dark OS (exercises `:not([data-theme="light"])` scoping). PASS.

### AC2: No flash of wrong theme on load (pre-paint init script)
**✅ PASS**
- `<head>` synchronous IIFE reads `localStorage.getItem("theme")` and sets `data-theme` before bundle loads.
- Pre-paint init script confirmed in freshly-built `dist/index.html` (2 `data-theme` refs, 55-module build).
- E2E `theme.spec.ts` test 3: `addInitScript` seeds `localStorage` before page load; asserts `__themeAtDCL === "dark"` at `DOMContentLoaded` (before React mounts). PASS.

### AC3: Contrast passes on Home, Board, drawer in BOTH themes
**✅ PASS**
- E2E `theme.spec.ts` test 4 (light) and test 5 (dark): WCAG-2 relative-luminance/contrast computation (same algorithm as axe `color-contrast` rule: large-text 3:1 / body 4.5:1) applied to Home KPI/status pills, Board chips/cards, Drawer title/status/badges. Both PASS.
- Implementation uses inlined WCAG math instead of `@axe-core/playwright` — deliberate, documented trade-off consistent with pinned-lockfile / supply-chain-verified dependency policy. AC intent fully met.

### AC4: Every hardcoded hex outside the token file is gone
**✅ PASS**
- Unit grep-gate `test/theme.test.ts` (test: "no hardcoded hex color outside the theme.css token file"): 0 offenders. Part of 22/22 unit pass.
- Independent `git grep -En "#[0-9a-fA-F]{3,6}\b" -- "src/**/*.css" "src/**/*.ts" "src/**/*.tsx" ":(exclude)src/theme.css"`: 0 results.
- `BudgetChip.tsx`: all colors now via `var(--stale)`/`var(--emphasis-border)` + `var(--on-danger)`/`var(--on-warning)`. ✅
- `styles.css`: all color blocks replaced by CSS-var references (325 `var(--…)` refs in ABS-462 merged state). ✅

---

## Rebase Resolution Review

**App.tsx conflict (+2 lines only):**
- ABS-462 added a unified `presence` memo + `summarizeAttention` import.
- ABS-475 adds `ThemeToggle` import + `<ThemeToggle />` in the header nav.
- Resolution: purely additive — both additions coexist cleanly. No logic conflict. Correct.

**styles.css conflict:**
- ABS-462 preserves its styles; they now consume ABS-475's `var(--…)` tokens instead of raw hex (correct — ABS-475 was the later change in intended merge order).
- Net: ABS-462's `styles.css` rules reference `var(--stale)`, `var(--emphasis-border)`, etc., all defined in `theme.css`. No raw hex. ✅

---

## Green-Run Proof (ABS-453)

**Changed test files (ABS-475 on rebased branch):**
- `backend/apps/web/e2e/theme.spec.ts` (new)
- `backend/apps/web/test/theme.test.ts` (new)

**E2E green-run (QAS-run, this session):**
```
DATABASE_URL="postgres://postgres:postgres@localhost:5432/agentic" \
  npx playwright test e2e/theme.spec.ts --reporter=line
Result: 5 passed (4.5s)
Commit: 8f09cea0abdd94969658ab4b1f58c862a8098d94
```

**Unit green-run (QAS-run, this session):**
```
node --import tsx --test --test-concurrency=1 "test/**/*.test.ts"
Result: pass 22 / fail 0 / duration 565ms
Commit: 8f09cea0abdd94969658ab4b1f58c862a8098d94
```

---

## Labels / Exit Flag Check

Ticket labels: `[orchestrator-ready, ux-review-2026-07]` — **no `design` flag**.  
Exit target: **Story Acceptance** (not Design Test).

---

## Final Verdict

**✅ APPROVED** — all 4 ACs verified independently on rebased state. Gates: tsc clean, unit 22/22 (incl. AC4 grep-gate), eslint clean, vite build ok (55 modules, pre-paint init preserved), theme.spec.ts 5/5. Full-suite 65 passed/1 skipped/1 failed — sole failure is a pre-existing ABS-462/epic-branch regression (aria-label strict-mode clash on Stop-run button vs. filter select), conclusively outside ABS-475 scope. Routed to epic owner.
