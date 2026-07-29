# QA Validation Report — ABS-479

**Ticket**: ABS-479 — Stall push-notifications (opt-in browser notifications)
**Branch**: ABS-479-auto
**Commit**: 07e0eb0618153127a58759f2a5f26fbe895f8d67
**QAS Actor**: qas
**Date**: 2026-07-20
**Verdict**: ✅ APPROVED

---

## Acceptance Criteria Verification

| # | Criterion | Result | Evidence |
|---|-----------|--------|----------|
| AC1 | With permission granted, a new stall event fires **exactly one** browser notification with a working deep link (e2e with mocked Notification API). | ✅ PASS | e2e AC1 test: `window.__notifs.length === 1`; `data.source_ref === newKey`; drawer opens and shows ticket title. |
| AC2 | Reconnect replay of N historical events fires **zero** notifications. | ✅ PASS | e2e AC2 test: baseline seeded silently (count 0); SSE replay of same items keeps count at 0. |
| AC3 | Toggle state persists across reloads; default is off. | ✅ PASS | e2e AC3 test: `aria-pressed=false` on first load; after toggle + reload still `aria-pressed=true`. |

---

## Green-Run Proof (ABS-453)

**Command**: `pnpm exec playwright test push-notifications.spec.ts --reporter=list`
**Commit**: `07e0eb0618153127a58759f2a5f26fbe895f8d67`
**Result**:
```
Running 3 tests using 1 worker

  ✓  1 e2e/push-notifications.spec.ts:106:1 › AC3: toggle defaults off and persists across reload (407ms)
  ✓  2 e2e/push-notifications.spec.ts:125:1 › AC2: historical items and SSE replay fire zero notifications (3.2s)
  ✓  3 e2e/push-notifications.spec.ts:159:1 › AC1: a new stall fires exactly one notification with a working deep link (306ms)

  3 passed (5.3s)
```

---

## Static Gates

| Gate | Command | Result |
|------|---------|--------|
| TypeScript | `pnpm typecheck` (web) | ✅ EXIT=0 (tsc --noEmit, no errors) |
| ESLint | `pnpm lint -- <3 changed files>` | ✅ EXIT=0 (clean) |

---

## Regression Run

**Command**: `pnpm exec playwright test home.spec.ts inbox.spec.ts --reporter=list`
```
Running 16 tests using 1 worker
  ✓  [home.spec.ts]   7/7 tests passed
  ✓  [inbox.spec.ts]  9/9 tests passed
  16 passed (10.3s)
```

---

## Diff Scope Review

Files changed: 3 (`+342/-0`)
- `apps/web/src/useStallNotifications.ts` — NEW hook: opt-in toggle + baseline-seed seen-set + digest burst-collapsing + localStorage persistence (default off)
- `apps/web/src/App.tsx` — Wires hook; adds `notif-toggle` button with `aria-pressed` + `data-testid`; deep-link dispatch via existing `DrawerTarget`/`openDrawer` (ABS-473)
- `apps/web/e2e/push-notifications.spec.ts` — 3 e2e tests, one per AC; Notification API mocked in-page via `addInitScript`; permission pre-granted

**Out-of-scope items confirmed absent**: no email/mobile-push infra; no new API endpoints; no DB/RLS surface; no per-user preference granularity beyond on/off.

---

## Architecture Alignment

- ✅ Signal derives from ABS-462 attention aggregation via props (no direct data-layer access; ADR-A-0011 honored)
- ✅ Deep-link via ABS-473 `DrawerTarget` union + `openDrawer` — same shape as 9 existing call sites
- ✅ Hook shape mirrors sibling hooks (`useBudget`, `useDrawerURL`)
- ✅ No DB/RLS/auth surface — frontend-only
- ✅ Debounce/digest is an explicit AC requirement, not speculation (YAGNI/Ponytail compliant)

---

## Flags Check

Ticket labels: `orchestrator-ready, ux-review-2026-07` — no `design` flag. Exit target: **Story Acceptance**.

---

## Verdict

**APPROVED** — All 3 ACs met. Green-run: 3/3 pass. typecheck EXIT=0, eslint EXIT=0. Regression: 16/16 pass. No blocking defects. Releasing to Story Acceptance.
