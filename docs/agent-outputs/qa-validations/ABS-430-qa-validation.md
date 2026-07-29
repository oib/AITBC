# QA Validation Report — ABS-430 (In Test gate: post-lockfix re-validation)

**Ticket:** ABS-430 — ABS-410 S9b: EventFeed filter UI + Run Timeline view
**QAS Actor:** qas
**Date:** 2026-07-18
**Branch:** `ABS-430-auto`
**Branch tip:** `0a55b40` (lockfile/dep hygiene fix — deps-only, zero production source)
**Verdict:** ✅ APPROVED — All 5 functional ACs PASS; static analysis clean; 6/6 e2e + 13/13 unit tests; Design ACs deferred to qas-design gate (Design Test — iteration 2 of 3)

---

## Validation History

| Pass | Commit | Verdict | Notes |
|---|---|---|---|
| QA iter 1/3 | `a999bd1` | BLOCKED | 5/6 e2e failures (AC2 isolation, AC3/4/5 no spawns) |
| QA iter 2/3 | `322a176` | BLOCKED | AC5 SSE trigger fired illegal transition |
| QA iter 1/3 (fresh budget) | `55556ff` | **APPROVED** | 6/6 e2e PASS; released to Design Test |
| Design Test (qas-design) | `eca1e3c` | BOUNCE | 6 DAC defects (DAC-11/17/19/20/21/22); → impl-fix |
| SA In Review (post-DAC-fix) | `17a74bc` | **Re-approved to In Test** | DAC fixes verified, `tsc` clean |
| QAS post-DAC-fix | `cfd9816` | **APPROVED** | 6/6 e2e PASS, 13/13 unit; Design ACs to Design Test |
| RTE Merging | — | BLOCKED | api.ts rebase conflict (ABS-418 vs ABS-430) |
| FE fix (rebase) | `cfd9816` | resolved | Clean 10-commit rebase onto cd8579d; tsc/lint/build PASS |
| SA In Review (rebase) | `cfd9816` | **CHANGES REQUESTED** | Iter 1 of 3: package.json ↔ pnpm-lock.yaml drift → frozen-lockfile CI fail |
| FE fix (lockfile) | `0a55b40` | applied | Dropped @types/node, regenerated pnpm-lock.yaml, deleted stray package-lock.json |
| SA In Review (re-review) | `0a55b40` | **APPROVED → In Test** | pnpm install --frozen-lockfile → EXIT 0, fix is deps-only |
| **This pass (In Test gate)** | `0a55b40` | **✅ APPROVED** | 6/6 e2e PASS, 13/13 unit PASS, tsc PASS; production source unchanged |

---

## Static Analysis

| Check | Command | Result |
|---|---|---|
| TypeScript (`tsc --noEmit`) | `npx tsc --noEmit` in `tmp/ABS-430-work/backend/apps/web` | ✅ PASS — zero errors |
| Unit tests (13/13) | `npm test` in `tmp/ABS-430-work/backend/apps/web` | ✅ PASS — 13/13 |

**Scope note on tsc:** Test run from the `ABS-430-auto` worktree (`tmp/ABS-430-work`). The main worktree has an unrelated `e2e/reset-db.ts` issue (`pg` module) on a different branch; the ABS-430-auto worktree is clean.

---

## E2E Test Results

**Command:** `DATABASE_URL="postgres://postgres:pw@localhost:55430/agentic" npx playwright test e2e/eventfeed-timeline.spec.ts --reporter=list`

**Container:** `abs430-e2e-pg` on port 55430 (confirmed running via docker ps); Playwright web-server on 8478 (dist/ present).

| # | Test | Result | Duration |
|---|---|---|---|
| 1 | AC1: EventFeed kind filter hides non-matching events; combined ticket+kind filter works | ✅ PASS | 645ms |
| 2 | AC2: Browse mode shows paginated events; Follow button resumes live mode | ✅ PASS | 339ms |
| 3 | AC3: Timeline renders one lane per seat with spawn, completion, stall span, and budget markers | ✅ PASS | 240ms |
| 4 | AC4: clicking a ticket link on a timeline lane opens the TicketDrawer | ✅ PASS | 289ms |
| 5 | AC4: clicking the lane body opens the SeatDrawer (or not-found state) | ✅ PASS | 262ms |
| 6 | AC5: timeline of a still-active run updates when new events arrive via SSE | ✅ PASS | 273ms |

**6/6 PASS. 0 failures. Total: 3.8s**

---

## Delta Assessment — Commit 0a55b40 (lockfile/dep fix)

The fix commit (architect's Stage-1 finding resolution) touches ONLY:
- `backend/apps/web/package.json` — `@types/node ^26.1.1` removed from devDependencies
- `backend/pnpm-lock.yaml` — regenerated without the apps/web `@types/node` importer entry
- `backend/package-lock.json`, `backend/apps/web/package-lock.json` — stray npm artifacts deleted

**Zero production source files changed.** All EventFeed.tsx, RunTimeline.tsx, styles.css, api.ts, types.ts, App.tsx, and e2e spec are **identical to the APPROVED state** (commit `cfd9816`).

Spot-check confirmations (via git show ABS-430-auto):
- `apps/web/package.json` devDependencies: `@playwright/test`, `@types/react`, `@types/react-dom`, `@vitejs/plugin-react`, `typescript`, `vite` — **no `@types/node`** ✅
- `api.ts` imports (merged conflict): `EventsPage`, `SeatLogResponse`, `SeatSpawn` all present; `getSeatDetail`, `getSeatLogs`, `getEvents` all present at lines 116/123/135 ✅
- Accessibility spot-checks: `role="img"` + `aria-label` on `.tl-lane-track` (line 155-156); `aria-pressed` on Follow/Browse buttons (lines 244/252); `tabIndex={0}` + `aria-label` on `.tl-marker` (line 74/78) ✅

---

## AC-by-AC Verification

### AC1 ✅ PASS (e2e test 1)
EventFeed kind filter (feed-local `<select>`, `aria-label="kind filter"`) correctly hides non-matching events. Combined ticket+kind filter confirmed: ticket filter narrows server-side (Browse API call), kind filter feed-local — together yield 1 spawn event; non-matching ticket ID yields 0 results.

**SA non-blocking note (carry-forward for Story Acceptance/PO):** The `ticket` dimension is implemented feed-local (`EventFeed.tsx:120`) rather than wired to the S8 GlobalFilterBar — because GlobalFilterBar does not expose a ticket dimension. AC1 says "ticket... wired to the S8 global bar"; the implementation provides equivalent server-side filtering behavior via a feed-local input. Code comment at EventFeed.tsx:260: *"ticket not yet in GlobalFilterBar FilterState."* This is an AC-intent question for the PO/Story Acceptance seat — not a functional failure, as the filtering works correctly. Flagged, not blocked.

### AC2 ✅ PASS (e2e test 2)
Browse mode shows exactly 2 run-scoped events (server-side `run_id` filter via ABS-429 cursor). `← Newer / page N / Older →` pagination renders; `feed-page-num` present. Follow mode shows `aria-pressed="true"` default; Browse toggle flips `aria-pressed`. `feed-resume-live` reactivates Follow. cursorHistoryRef model confirmed gap/dup-free.

### AC3 ✅ PASS (e2e test 3)
Timeline renders one lane for `fe-developer` after selecting seeded run. `tl-stall-span` visible. `tl-marker` count > 0. In Lifecycle density mode (default), `transition`-kind markers absent from DOM (DAC-6 confirmed). Lane-per-seat grouping correct.

### AC4 ✅ PASS (e2e tests 4 + 5)
**AC4a:** `tl-ticket-link` click opens `data-testid="drawer"` containing ticketId text. Escape closes.
**AC4b:** `tl-lane-track` click opens `data-testid="seat-drawer"`. Escape closes.

### AC5 ✅ PASS (e2e test 6)
Timeline of a still-active run updates via SSE without reload. SSE LiveEvent emitted → `loadRun()` triggered → completion marker appears within 4s (observed: 273ms). No page reload required.

---

## Design ACs Status

The 3 ticket-level Design ACs and 25 DACs (DAC-1..DAC-25) in `docs/agent-outputs/designs/ABS-430-design.md` are verified at the **qas-design gate (Design Test)**, not at this In Test gate. The `design` flag routes this story to `Design Test` next.

Prior Design Test iteration bounced 6 DACs (DAC-11/17/19/20/21/22). All 6 were fixed in commit `f73cd93`. Per the SA handoff, the qas-design seat at Design Test must re-verify these 6 DACs — **this is iteration 2 of 3 on the qas-design counter**.

---

## Summary

| Category | Result |
|---|---|
| AC1 (EventFeed filters — ticket feed-local noted) | ✅ PASS |
| AC2 (Follow/Browse + pagination gap-free) | ✅ PASS |
| AC3 (Timeline lane rendering) | ✅ PASS |
| AC4 (Drawer navigation — ticket + seat) | ✅ PASS |
| AC5 (SSE live update) | ✅ PASS |
| TypeScript (`tsc --noEmit`) | ✅ PASS — zero errors |
| Unit tests (13/13) | ✅ PASS |
| E2E suite (6/6) | ✅ PASS |
| Lockfile/dep hygiene (0a55b40 delta) | ✅ PASS — @types/node removed; frozen-lockfile clean |
| Design ACs (DAC-1..DAC-25) | ⏳ qas-design gate (Design Test) — iteration 2 of 3 |

**Verdict: ✅ APPROVED — releasing to Design Test**

All 5 functional ACs independently verified by QAS this pass. Static analysis clean. The `design` flag routes this story to Design Test (qas-design gate) for DAC re-verification (6 DAC fixes from commit `f73cd93` must be re-checked at Design Test). AC1 ticket-dimension note carried forward for PO/Story Acceptance.
