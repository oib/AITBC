# QA Validation Report — PILOT-36

**Ticket**: PILOT-36 — Mission Control: Event-Feed-Follow-Modus seedet beim Mount mit den letzten N Events  
**Validator**: QAS  
**Date**: 2026-07-25  
**Commit under test**: b87da7dc  
**Branch**: PILOT-36-auto  
**Verdict**: ❌ BLOCKED  
**Failure classification**: `code`  
**Iteration**: 1 of 3

---

## Static Checks

| Check | Result | Detail |
|---|---|---|
| TypeScript typecheck | ✅ PASS | `pnpm typecheck` — all 5 packages, 0 errors |
| ESLint | ✅ PASS | `pnpm lint` — 0 warnings, 0 errors |
| Build (`tsc -b && vite build`) | ✅ PASS | 68 modules, dist produced |
| Unit tests | ✅ PASS | 248/248 across 5 packages (apps/web 75, core 142, webhooks 6, forge 18, server 7) |

Command run: `unset BACKEND_URL BACKEND_TOKEN && pnpm typecheck && pnpm lint && pnpm test`  
Commit: b87da7dc

---

## E2E Tests (ABS-453 green-run proof obligation)

**The ticket adds a new e2e test (`eventfeed-timeline.spec.ts` +53 lines) — a green-run of the new test is mandatory per ABS-453.**

### Run

```
DATABASE_URL="postgres://postgres:postgres@localhost:55432/agentic" \
  unset BACKEND_URL BACKEND_TOKEN && \
  node_modules/.bin/playwright test --grep "PILOT-36" --project desktop
```

### Result

```
Running 1 test using 1 worker

  ✘ [desktop] › e2e/eventfeed-timeline.spec.ts:536:1 › 
      PILOT-36: Follow mode shows the last events on load (seed) + a new SSE event with no duplicate (5.4s)

  Error: expect(locator).toHaveCount(expected) failed
  Locator: locator('[data-testid="feed-item"]:not([data-seed="true"])')
  Expected: 1
  Received: 0
  Timeout:  5000ms

1 failed
```

**Result: 0/1 PASSED — FAIL**

---

## Root Cause Analysis

### Bug: Cross-table seq comparison in the seam dedup

`EventFeed.tsx` at the `followShown` useMemo (line ~284) applies a seam dedup guard:

```typescript
// PILOT-36 DAC-11: seam dedup
if (seedMaxSeq !== null) ev = ev.filter((e) => seqGt(e.seq, seedMaxSeq));
```

This compares two values from **independent database sequences**:

| Value | Source | DB table | PK column |
|---|---|---|---|
| `e.seq` (SSE LiveEvent) | `event.seq` from `INSERT INTO event … RETURNING seq` | `event` (transition log) | `bigserial seq` |
| `seedMaxSeq` | `run_event.id` from `api.getEvents` (dashboard route `SELECT re.id … FROM run_event re`) | `run_event` (telemetry) | `bigserial id` |

**These are two completely independent `bigserial` sequences from different tables.** They are not numerically comparable.

### Consequence in the e2e test

1. `seedEvents` inserts 2 rows into `run_event` → `run_event.id` values advance (e.g., to 3, 4)
2. `seedMaxSeq = "4"` (highest `run_event.id` in the seed)
3. The transition (status change) inserts the **first row** into the `event` table → `event.seq = 1`
4. SSE delivers the event with `seq: "1"`
5. Dedup: `seqGt("1", "4")` → `BigInt(1) > BigInt(4)` → **false** → event is FILTERED OUT
6. The live section shows 0 events instead of 1 — test fails

### Why there are no real duplicates to prevent

The `run_event` (telemetry) rows in the seed are **never** the same as the `event` (transition) rows in the SSE tail — they are different event types from different tables. No genuine dedup is possible or necessary between these two sources.

---

## Acceptance Criteria Verification

| AC | Spec Clause | Status |
|---|---|---|
| Follow mode loads last N events on mount via api.getEvents | Seed fetched (DAC-10) | ✅ Implementation correct |
| Seed entries visually offset (dimmed + "ab hier live" separator) | CSS `.feed-item-seed` + separator element | ✅ Implementation correct |
| No behaviour change in Browse mode | Browse path unchanged | ✅ Implementation correct |
| Filter change re-seeds | useEffect deps include filter dims | ✅ Implementation correct |
| No duplicates at the seam (seq-based dedup) | DAC-11 seam dedup | ❌ **BROKEN** — cross-table seq comparison incorrectly filters all SSE events |
| e2e: Reload → seed shows + new SSE event without duplicate | eventfeed-timeline.spec.ts:536 | ❌ **FAIL** — 0/1 |

---

## Fix Direction

Remove the seq-based cross-table dedup guard in `followShown`:

```diff
- // PILOT-36 DAC-11: seam dedup — a live event at or below the seed high-water
- // mark is already shown in the seed, so keep only strictly-newer events here.
- if (seedMaxSeq !== null) ev = ev.filter((e) => seqGt(e.seq, seedMaxSeq));
```

**Rationale**: `run_event` (seed) and `event` (SSE) are different tables with independent sequences. A seed row (`run_event` — telemetry: spawn/budget/log) can never be the same event as a live SSE row (`event` — transition: status change). No duplicates at the seam are possible; the guard is unnecessary and its broken cross-table comparison is the cause of the failure.

If a dedup guard is desired for correctness in edge cases (e.g., future same-table mixing), it must compare within the same table's sequence space. For now, removing the guard is the correct and simplest fix (YAGNI).

Also remove the unused `seedMaxSeq` state and `setSeedMaxSeq` since they are only used for the dedup.

---

## Non-blocking Notes (Carried from System-Architect)

These are Design-Test scope, not blocking for this In-Test gate:
1. Separator wording "── ab hier live ──" vs. newest-first layout — Design-Test call
2. DAC-8 mobile-hide premise: feed is full-width on mobile (no hiding code — correct)

---

## Verdict

**❌ BLOCKED — returning to fe-developer for code fix**

- Static checks (typecheck/lint/build/unit): ✅ All pass
- E2e green-run (ABS-453 obligation): ❌ FAIL — 0/1 — the PILOT-36 test fails due to a cross-table seq comparison bug in the seam dedup
- Failure class: `code` (wrong logic in seam dedup comparing independent DB table sequences)
