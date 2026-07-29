# QA Validation Report — PILOT-35

**Ticket**: PILOT-35 — Mission Control: Event-Feed-Einträge zeigen relative Zeit (0m/4m/1h) + volles Datum on hover  
**Commit under test**: `7f3fd329`  
**Branch**: `PILOT-35-auto`  
**QAS run date**: 2026-07-25  
**Verdict**: ✅ **APPROVED**

---

## Acceptance Criteria Verification

| AC | Description | Result |
|----|-------------|--------|
| Relative age per entry (formatAge: 0m/4m/1h/2d) | EventFeed rows and Home Ticker items show `{N}s\|{N}m\|{N}h\|{N}d` | ✅ PASS |
| Hover tooltip = full absolute date+time | `title` attr carries `YYYY-MM-DD HH:MM:SS` on every age span | ✅ PASS |
| Live tick re-render 30–60s interval | One `setInterval(…, 30_000)` per component; no per-second re-render | ✅ PASS |
| All event kinds covered | EventFeed (Follow + Browse) + Home Ticker — all feed events carry `occurred_at`/`at` | ✅ PASS |
| ABS-470: single time utility, no second impl | `formatAge`/`formatAbsolute` defined ONCE in `src/lib/formatTime.ts`; `util.ts` is a re-export, not a reimplementation | ✅ PASS |
| a11y: title + aria-label (ABS-467 pattern) | `title={formatAbsolute(…)}` + `aria-label="{age} ago — {absolute}"` on all age spans | ✅ PASS |
| e2e: age renders, hover tooltip, format identical to ticket display | 2/2 PILOT-35 e2e tests PASS | ✅ PASS |

---

## Test Evidence (ABS-453 green-run proof)

### Changed test files

- `backend/apps/web/e2e/eventfeed-timeline.spec.ts` — added PILOT-35 test block
- `backend/apps/web/e2e/home.spec.ts` — added PILOT-35 test block

### Isolated PILOT-35 run (authoritative green-run)

```
Command: DATABASE_URL=postgres://postgres:postgres@localhost:55432/agentic \
         npx playwright test --grep "PILOT-35" --reporter=line
Branch:  PILOT-35-auto
Commit:  7f3fd329e2d8c46a2ccf927487c206e1ec21738c

Running 2 tests using 1 worker

[1/2] [desktop] › e2e/eventfeed-timeline.spec.ts:159:1 › PILOT-35: every EventFeed row shows a relative age stamp with a full-date tooltip
[2/2] [desktop] › e2e/home.spec.ts:262:1 › PILOT-35: ticker items show a relative age stamp with a full-date tooltip
  2 passed (3.0s)
```

**Result: 2 passed, 0 failed** ✅

### Full suite run of changed spec files

```
Command: DATABASE_URL=postgres://postgres:postgres@localhost:55432/agentic \
         npx playwright test e2e/eventfeed-timeline.spec.ts e2e/home.spec.ts --reporter=line
Commit:  7f3fd329e2d8c46a2ccf927487c206e1ec21738c

Running 21 tests using 1 worker
  1 failed (ABS-468 AC2 — pre-existing, see below)
  20 passed (16.4s)
```

**Pre-existing failure note — ABS-468 AC2**: `the state bar exposes seat metadata (spawn id + exit) for hover/click detail` fails when run after AC1 in the full suite (test isolation / shared DB state), but **passes in isolation** (`npx playwright test --grep "ABS-468 AC2"` → `1 passed`). This failure exists on the design commit `3840a0fd` and pre-dates PILOT-35. No new regression introduced by `7f3fd329`.

---

## TypeScript Type Check

```
Command: npx tsc --noEmit
Exit:    0 (no errors)
```

---

## Implementation Quality Checks

### Single time-utility source (DAC-19 / ABS-470)

```
grep "export function formatAge\|export function formatAbsolute" src/**
→ src/lib/formatTime.ts:35: export function formatAbsolute(...)
→ src/lib/formatTime.ts:48: export function formatAge(...)
```

`util.ts` re-exports `formatAge` from `./lib/formatTime` (no local body) — confirmed no second implementation.

### Performance: 30s interval (not per-second)

```
EventFeed.tsx:142: setInterval(() => setNow(Date.now()), 30_000)  → clearInterval on unmount
HomeView.tsx:127:  setInterval(() => setNow(Date.now()), 30_000)  → clearInterval on unmount
```

One state update per 30 seconds per component — compliant with AC.

### a11y (ABS-467 pattern)

EventFeed: `title={formatAbsolute(event.occurred_at)}` + `aria-label="{age} ago — {absolute}"`  
HomeView:  `title={formatAbsolute(e.at)}` + `aria-label="{age} ago — {absolute}"`

---

## Files Changed

```
backend/apps/web/src/components/EventFeed.tsx   — age stamp + 30s tick
backend/apps/web/src/components/HomeView.tsx    — age stamp + 30s tick
backend/apps/web/src/styles.css                 — .feed-event-age + .home-ticker-age
backend/apps/web/e2e/eventfeed-timeline.spec.ts — PILOT-35 e2e tests (DAC-3/4/5/9)
backend/apps/web/e2e/home.spec.ts               — PILOT-35 e2e tests (DAC-3/4/5)
```

---

## Verdict

**✅ APPROVED — PILOT-35 passes all AC/DoD criteria.**

Design flag is set → releasing to **Design Test** (mandatory per exit protocol).
