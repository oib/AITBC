# QA Validation Report — PILOT-35 (Re-entry r2)

**Ticket**: PILOT-35 — Mission Control: Event-Feed-Einträge zeigen relative Zeit (0m/4m/1h) + volles Datum on hover
**Commit under test**: `d6256253` (rebased from original `7f3fd329` onto `gitlab/main` `7438e790` after RTE-bounce conflict with PILOT-36)
**Branch**: `PILOT-35-auto`
**QAS run date**: 2026-07-25
**Re-entry reason**: Architect (In Review) confirmed conflict-resolution correctness; ticket returned to In Test for QAS functional re-gate.
**Verdict**: ✅ **APPROVED**

---

## Context

After the first full pass (QAS PASS at `7f3fd329`, Design Test PASS, PO ACCEPTED), the RTE
merge attempt was bounced due to a conflict with the PILOT-36 branch (`.feed-event-time` vs
`.feed-event-age` class naming). The architect reviewed the conflict resolution on `PILOT-35-auto`
(rebased onto main at `7438e790`) and confirmed:

- `EventRow` keeps both PILOT-36 `rowClass` and PILOT-35 `ageS`.
- `now={now}` is propagated to all three render sites.
- `.feed-event-time` placeholder cleanly replaced by tested `.feed-event-age`; only an
  explanatory CSS comment remains.
- Duplicate `formatAbsolute` import deduped.
- `tsc --noEmit` exit 0, `npm run build` green, e2e assertions present in both surfaces.

This re-run independently verifies the same on the rebased HEAD.

---

## Acceptance Criteria Verification

| AC | Description | Result |
|----|-------------|--------|
| Relative age per entry (formatAge: 0m/4m/1h/2d) | EventFeed rows and Home Ticker items show `{N}s\|{N}m\|{N}h\|{N}d` | ✅ PASS |
| Hover tooltip = full absolute date+time | `title` attr carries `YYYY-MM-DD HH:MM:SS` on every age span | ✅ PASS |
| Live tick re-render 30–60s interval | One `setInterval(…, 30_000)` per component; no per-second re-render | ✅ PASS |
| All event kinds / both views | EventFeed (Follow + Browse) + Home Ticker — all feed events carry `occurred_at`/`at` | ✅ PASS |
| ABS-470: single time utility, no second impl | `formatAge`/`formatAbsolute` defined ONCE in `src/lib/formatTime.ts`; `util.ts` re-exports | ✅ PASS |
| a11y: title + aria-label (ABS-467 pattern) | `title={formatAbsolute(…)}` + `aria-label="{age} ago — {absolute}"` on all age spans | ✅ PASS |
| e2e: age renders, hover tooltip, format identical to ticket display | 2/2 PILOT-35 e2e tests PASS (22/22 full suite, improved from 20/21 pre-rebase) | ✅ PASS |

---

## Conflict-Resolution Spot-Check

### EventFeed.tsx — both PILOT-35 and PILOT-36 coexist correctly

```
85:  const rowClass = seed ? "feed-item feed-item-seed" : `feed-item${...}`;  // PILOT-36
88:  const ageS = event.occurred_at ...                                         // PILOT-35
92:  <li className={rowClass} ...>                                              // PILOT-36
114:   className="feed-event-age" data-testid="feed-event-age" ...             // PILOT-35
430: <EventRow ... now={now} />   // propagated (Follow)
450: <EventRow ... now={now} />   // propagated (seed)
457: <EventRow ... now={now} />   // propagated (Browse)
```

### styles.css — no orphan refs

```
566: /* trailing slot PILOT-36/ABS-529 reserved (formerly the .feed-event-time
568: .feed-event-age {
```

Only an explanatory comment references `.feed-event-time`; no active CSS rule.

### ABS-470 DAC-18/19 — single definition

```
src/lib/formatTime.ts — defines formatAge + formatAbsolute (line 35, 48)
src/util.ts — re-exports (not a second implementation)
All other files import from one of these two.
```

---

## Test Evidence (ABS-453 green-run proof)

### TypeScript

```
Command: cd backend/apps/web && npx tsc --noEmit
Commit:  d6256253 (HEAD of PILOT-35-auto)
Result:  exit 0 (no errors)
```

### Isolated PILOT-35 e2e run (authoritative green-run)

```
Command: DATABASE_URL=postgres://postgres:postgres@localhost:55432/agentic \
         BACKEND_URL="" BACKEND_TOKEN="" \
         npx playwright test --grep "PILOT-35" --reporter=line
Branch:  PILOT-35-auto
Commit:  d6256253

Running 2 tests using 1 worker

[1/2] [desktop] › e2e/eventfeed-timeline.spec.ts:159:1 › PILOT-35: every EventFeed row shows a relative age stamp with a full-date tooltip
[2/2] [desktop] › e2e/home.spec.ts:262:1 › PILOT-35: ticker items show a relative age stamp with a full-date tooltip
  2 passed (3.2s)

Result: 2 passed, 0 failed ✅
```

### Full suite run of changed spec files

```
Command: DATABASE_URL=postgres://postgres:postgres@localhost:55432/agentic \
         BACKEND_URL="" BACKEND_TOKEN="" \
         npx playwright test e2e/eventfeed-timeline.spec.ts e2e/home.spec.ts --reporter=line
Commit:  d6256253

Running 22 tests using 1 worker
  22 passed (13.3s)

Result: 22 passed, 0 failed ✅
```

> **Note**: Previous run (commit `7f3fd329`) had 20/21 passing (ABS-468 AC2 pre-existing
> failure). After rebase onto `7438e790` (which includes PILOT-36 + PILOT-37), the
> ABS-468 AC2 test now passes, giving a clean 22/22 run.

---

## Verdict

✅ **QAS APPROVED** — All 7 ACs verified. 2/2 PILOT-35 tests pass; 22/22 full
changed-spec suite green. Conflict resolution verified correct. `tsc` clean.

`design` flag set → releasing to **Design Test**.
