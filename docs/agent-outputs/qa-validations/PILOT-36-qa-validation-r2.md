# QA Validation Report — PILOT-36 (Iteration 2)

**Ticket**: PILOT-36 — Mission Control: Event-Feed-Follow-Modus seedet beim Mount mit den letzten N Events  
**Validator**: QAS  
**Date**: 2026-07-25  
**Commits under test**: 912f9b73 (fix), 2192a550 (QA r1 evidence), b87da7dc (impl)  
**Branch**: PILOT-36-auto  
**Verdict**: ✅ PASS  
**Iteration**: 2 of 3  
**Exit route**: → Design Test (flags: [design])

---

## Fix Under Review

Commit 912f9b73 `fix(ui): drop cross-table seq dedup in EventFeed seam [PILOT-36]`:
- Removed `seqGt` helper (was comparing incomparable sequences)
- Removed `seedMaxSeq` / `setSeedMaxSeq` state
- Removed the seam dedup guard from `followShown` useMemo
- Updated dependency array (`seedMaxSeq` removed)
- Fixed e2e test: `${project}-1` → newly created dedicated ticket (CAS isolation fix)

All removals match the root cause documented in Iteration 1 bounce.

---

## Static Checks (all unset BACKEND_URL/BACKEND_TOKEN)

| Check | Result | Detail |
|---|---|---|
| TypeScript typecheck | ✅ PASS | `pnpm typecheck` — 5 packages, 0 errors |
| ESLint | ✅ PASS | `pnpm lint` — 0 errors, 0 warnings |
| Build | ✅ PASS | `tsc -b && vite build` — 68 modules, dist produced |
| Unit tests | ✅ PASS | **248/248** (web 75, core 142, webhooks 6, forge 18, server 7) |

---

## E2E Tests (ABS-453 green-run proof obligation)

**PILOT-36 test** — `postgres://postgres:postgres@localhost:55432/agentic`, unset BACKEND_URL/BACKEND_TOKEN:

| Run | PILOT-36 test | Full spec (10 tests) |
|---|---|---|
| Run 1 | ✅ 1/1 PASS (423ms) | 9/10 — AC1 flake (see below) |
| Run 2 | ✅ 1/1 PASS (230ms) | 10/10 PASS |
| Run 3 | ✅ 1/1 PASS (258ms) | 9/10 — AC1 flake (see below) |

**PILOT-36 test: 3/3 PASS across all runs.**

---

## AC1 Flake Analysis (non-attributable)

**Test**: `AC1: EventFeed kind filter hides non-matching events; combined ticket+kind filter works`  
**Failure**: `Expected: 1 / Received: 3` at `eventfeed-timeline.spec.ts:145`  
**Pattern**: Intermittent (~2/3 runs fail); Browse mode only

**Root cause** (pre-existing Browse mode race, NOT caused by PILOT-36):

The test sets `ticketFilter` then `kindFilter` in rapid succession. React fires two `loadPage` useEffect calls in quick succession:
- Request A: captures `ticket=X, kind=` (pre-kind-change snapshot of `loadPage` closure)
- Request B: captures `ticket=X, kind=spawn`

When Request A (→ 3 items) returns after Request B (→ 1 item), it overwrites `browseEvents` with 3 items. The `toHaveCount(1, { timeout: 5000 })` assertion sees 3 for the full 5s window.

**Why not attributable to PILOT-36**:
1. PILOT-36 touches Follow-mode seed only; Browse mode render path (`follow = false`) is unchanged
2. In Browse mode, `seedShown` is NOT rendered (JSX: `{follow ? <seed section> : <browse section>}`)
3. The race is between two concurrent Browse `loadPage` calls — unrelated to seed feature
4. System-architect independently confirmed: "AC1 Browse-filter flake the dev flagged (line 145, path this ticket doesn't touch — watch, don't attribute here)"

**Action**: file a separate ticket for the Browse-mode stale-result race (loadPage should cancel in-flight requests when a newer call starts, or `browseEvents` should be reset to `[]` on filter change).

---

## Acceptance Criteria Verification

| AC | Status | Evidence |
|---|---|---|
| Follow mode loads last N events on mount via api.getEvents | ✅ | Seed fetch on mount, SEED_LIMIT=50, `api.getEvents` |
| Seed entries dimmed (`.feed-item-seed`, opacity 0.6) | ✅ | CSS + `data-seed="true"` attribute |
| "── ab hier live ──" separator between live and seed | ✅ | `feed-seed-separator` element rendered when `seedShown.length > 0` |
| No behaviour change in Browse mode | ✅ | Browse render path unmodified; PILOT-36 e2e verifies Browse unchanged |
| Filter change re-seeds (server-side dims) | ✅ | `useEffect` deps: `[follow, project, filters.run, filters.role, ticketFilter, kindFilter]` |
| No duplicates at the seam | ✅ (by construction) | Dedup removed; seed=`run_event` (telemetry), live=`event` (transitions) — temporally disjoint, never overlap |
| e2e: reload → seed shows + new SSE event without dup | ✅ | PILOT-36 e2e 3/3 PASS |

---

## Non-blocking Carry-forward (Design Test scope)

1. Separator wording "── ab hier live ──" vs. newest-first layout — Design Test call (PO/design spec says "ab hier live", wording is correct as-is per ticket)
2. DAC-8 mobile-hide premise: feed is full-width on mobile in this codebase (no hiding code — correct, non-issue)
3. AC1 Browse-mode race: pre-existing flake, not attributable, file separately

---

## Verdict

**✅ PASS — transitioning to Design Test**

- All static/unit checks: PASS (0 errors)
- PILOT-36 e2e: **3/3 PASS** (100%)
- Full spec 28/30 across 3 runs (2 AC1 flake hits, non-attributable, pre-existing)
- All ticket ACs verified against current code
- Failure class from Iteration 1 (cross-table seq dedup) fully resolved
