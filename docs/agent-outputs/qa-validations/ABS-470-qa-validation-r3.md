# QA Validation Report — ABS-470 (Re-validation r3, post-second-rebase)

**Ticket:** ABS-470 — One time-and-date language across the app
**Date:** 2026-07-19
**QAS run:** r3 (after 2nd RTE rebase-bounce; branch rebased d55fa62a→380f192e onto epic tip 3c4f7b74)
**Branch:** ABS-470-auto
**HEAD commit:** f77476ed (QA r2 report on top of 380f192e impl)
**Impl commit:** 380f192e
**Verdict:** ✅ APPROVED → Story Acceptance

---

## Environment

| Item | Value |
|---|---|
| Postgres container | `abs470-qas3-pg` (postgres:16-alpine), port 55473 |
| Database | `agentic_e2e`, migrations applied via `node --import tsx e2e/reset-db.ts` |
| Node | v26.3.1 |
| Commit validated | `f77476ed` (HEAD) / impl `380f192e` |

---

## Gates (independently run by QAS r3)

| Check | Result |
|---|---|
| `npm run typecheck` (tsc --noEmit) | ✅ PASS — 0 errors |
| `npm test` (node --test) | ✅ **35/35 PASS** (6 formatTime + pre-existing + sibling-story additions from rebased epic tip 3c4f7b74) |
| `npm run build` (tsc -b && vite build) | ✅ PASS — 239.55 kB bundle, 0 errors |
| `playwright test seat-drawer.spec.ts inbox.spec.ts` | ✅ **18/18 PASS** (7.3s, isolated Postgres :55473) |

---

## Green-run proof (ABS-453)

**Command:** `DATABASE_URL=postgres://postgres:pw@localhost:55473/agentic_e2e npx playwright test seat-drawer.spec.ts inbox.spec.ts --reporter=list`
**Counter:** **18 passed, 0 failed**
**Commit:** `f77476edcec5dd36e1dc19ebc6338f89d3094fb3`

---

## AC Verification

### AC1 — No raw ISO renders in web src (all through the util)

**PASS**

- `git grep "toLocaleString\|toLocaleDateString"` in `src/**` → **0 matches** (exit 1)
- `git grep "\.toISOString()"` in `src/**` → 1 match: `App.tsx:105: const now = new Date().toISOString()` — internal state write to `lastDataAtRef.current` / `setLastDataAt`, not rendered display text. Correctly out of scope.
- `git grep "toLocaleTimeString"` in `src/**` → 2 pre-existing matches:
  - `Inbox.tsx:104` — "last checked HH:MM" clock-only label (not raw ISO, not a relative-time-hiding-absolute)
  - `RunTimeline.tsx:379` — chart axis tick label (clock-only)
  - Both correctly left out of scope; noted by Stage 1 architect

### AC2 — Every relative time exposes absolute via title/tooltip; e2e spot-checks drawer/attention/live

**PASS**

- `title={formatAbsolute(...)}` wired at all relative-time render sites:
  - `HomeView.tsx:140` — reconnect banner
  - `Inbox.tsx:233` — attention-age card
  - `SeatDrawer.tsx:156` — drawer last-activity age
  - `LiveSpawns.tsx:55` — live-spawns elapsed
- E2E assertions in `seat-drawer.spec.ts` (started format regex + live-panel elapsed title) and `inbox.spec.ts` (attention-age title) — **all 18/18 green**

### AC3 — Home KPI shows a human date

**PASS**

- `HomeView.tsx`: KPI label is `run {formatDate(activeRun.startedAt)}`
- Full `runId — started <absolute>` in `title`
- "RUN 26-07-19" oddity gone

### DoD — Format contract documented

**PASS**

- `backend/apps/web/docs/COMPONENT_NOTES.md` documents the format contract with helper table, rules, and the `<time dateTime>` semantic-attribute exemption

---

## Rebase integration note (r3)

Branch was rebased a second time from epic tip `640bbfb0` → `3c4f7b74` (ABS-468 + other siblings merged in between). The impl SHA changed from `d55fa62a` to `380f192e`; the QA r2 report commit (`f77476ed`) rides on top unchanged. Unit test count grew from 24/24 → 35/35 as sibling story tests are now on the base. All ABS-470 ACs remain intact on the rebased branch — confirmed by typecheck + unit + build + 18/18 e2e on isolated Postgres.

---

## Advisory (pre-existing, non-blocking)

`RunTimeline.tsx:379` axis ticks use `toLocaleTimeString()` — pre-existing locale drift, out of scope. Already noted by Stage 1 architect; routed to drawer/timeline sibling story owner within epic ABS-460.

---

**No `design` flag** — transitioning to **Story Acceptance**.
