# QA Validation Report — ABS-470 (Re-validation after rebase, r2)

**Ticket:** ABS-470 — One time-and-date language across the app
**Date:** 2026-07-19
**QAS run:** r2 (after RTE rebase-bounce; ABS-462 integration re-verified)
**Branch:** ABS-470-auto
**Commit:** d55fa62a (1 ahead of epic tip 640bbfb0)
**Verdict:** ✅ APPROVED → Story Acceptance

---

## Environment

| Item | Value |
|---|---|
| Postgres container | `abs470-qas2-pg` (postgres:16-alpine), port 55472 |
| Database | `agentic_e2e`, migrations applied via `e2e/reset-db.ts` |
| Node | v26.3.1 |
| Commit | `d55fa62a` |

---

## Gates (independently run by QAS)

| Check | Result |
|---|---|
| `tsc --noEmit` (typecheck) | ✅ PASS — 0 errors |
| `npm test` (node --test) | ✅ **24/24 PASS** (6 new formatTime + 5 attentionSummary from ABS-462 + 13 pre-existing) |
| `npm run build` (tsc -b && vite build) | ✅ PASS |
| `playwright test seat-drawer.spec.ts inbox.spec.ts` | ✅ **18/18 PASS** (7.0s, isolated Postgres :55472) |

---

## Green-run proof (ABS-453)

**Command:** `DATABASE_URL=postgres://postgres:pw@localhost:55472/agentic_e2e npx playwright test seat-drawer.spec.ts inbox.spec.ts --reporter=list`
**Counter:** **18 passed, 0 failed**
**Commit:** `d55fa62a97aa15c4ee03edde82767921fe04b312`

---

## AC Verification

### AC1 — No raw ISO renders in web src (all through the util)

**PASS**

- `git grep "toLocaleString\|toLocaleDateString\|\.toISOString()"` in `src/**` → **0 matches** (exit 1)
- `formatAbsolute`/`formatDate` imported and used in every component that renders timestamps
- Two remaining `toLocaleTimeString` sites (`RunTimeline.tsx:323` chart axis ticks) are clock-only labels, not raw ISO, correctly out of scope
- Pre-existing `App.tsx` `.toISOString()` calls are internal state writes to `lastSeenAt` localStorage — not rendered display text; correctly outside AC scope

### AC2 — Every relative time exposes absolute via title/tooltip; e2e spot-checks drawer/attention/live

**PASS**

- `title={formatAbsolute(...)}` wired at all relative-time render sites:
  - `HomeView.tsx:140` — reconnect banner
  - `Inbox.tsx:233` — attention-age card
  - `SeatDrawer.tsx:156` — drawer last-activity age
  - `LiveSpawns.tsx:55` — live-spawns elapsed (`\`started ${formatAbsolute(spawn.started_at)}\``)
- E2E assertions in `seat-drawer.spec.ts` (started format regex + live-panel elapsed title) and `inbox.spec.ts` (attention-age title regex) — **all 18/18 green**

### AC3 — Home KPI shows a human date

**PASS**

- `HomeView.tsx`: KPI label is `run {formatDate(activeRun.startedAt)}`
- Full `runId — started <absolute>` in `title`
- "RUN 26-07-19" oddity gone

### DoD — Format contract documented

**PASS**

- `backend/apps/web/docs/COMPONENT_NOTES.md` documents the format contract with helper table, rules, and the `<time dateTime>` semantic-attribute exemption

---

## Rebase integration verification

The rebase from `216e888e` onto epic tip `640bbfb0` (ABS-462 landed first) was verified clean:

- `HomeView.tsx` import block retains BOTH feature sets (`summarizeAttention/healthLine` from ABS-462 + `formatAbsolute/formatDate` from ABS-470)
- `LiveSpawns.tsx` carries ABS-462's `⚠ STALE` badge alongside ABS-470's `formatAbsolute` title
- No unused import breakage; 24/24 unit tests confirm both ABS-462 and ABS-470 logic coexists

---

## Advisory (pre-existing, non-blocking)

`RunTimeline.tsx:323` axis ticks use `toLocaleTimeString()` — pre-existing locale drift, out of scope for this story. Already noted by Stage 1 architect and routed to the drawer/timeline sibling story owner within epic ABS-460.

---

**No `design` flag** — transitioning to **Story Acceptance**.

**QAS:** Independent re-validation on rebased commit `d55fa62a` (r2 pass, no iteration counter applies — this is a mechanical rebase bounce, not an AC failure).
