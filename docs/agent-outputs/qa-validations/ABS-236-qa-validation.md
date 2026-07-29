# QA Validation — ABS-236

**Ticket**: ABS-236 Backend S4: Comments, Transition-Route, Event-Log-Ops  
**Branch**: ABS-236-auto (HEAD b65e88a)  
**Date**: 2026-07-15  
**QAS verdict**: ✅ APPROVED

---

## Test Suite Results

| Suite | Pass | Fail | Command |
|-------|------|------|---------|
| `@agentic-backend/core` | **59/59** | 0 | `pnpm --filter @agentic-backend/core test` |
| `@agentic-backend/server` | **16/16** | 0 | `pnpm --filter @agentic-backend/server test` |
| `pnpm -r typecheck` | ✅ clean | — | tsc --noEmit (both packages) |
| `eslint .` | ✅ clean | — | no warnings or errors |

**Total**: 75/75 tests PASS.

### Environment note — transient OID error (not a product bug)

On the first `pnpm -r test` parallel run a single test (`AC#5: priority is NOT NULL and indexed`)
emitted `could not open relation with OID …` — a well-known Postgres catalog-cache race that
occurs when one test schema is DROPped while a parallel pool connection still holds the OID
cached. Second isolated `core` run: 59/59 PASS. This is classified **environment** (test
isolation under parallel run) — no product code change needed.

---

## Acceptance Criteria Verification

### AC#1 — Two consumers with independent cursors, no starvation

**PASS**

- `readEventsForConsumer` uses `FOR UPDATE` scoped to `(consumer_id, project_id)` — different
  consumers lock different rows, never contend.
- `consumer_cursor` table has one row per `(consumer_id, project_id)` pair; the `X-Orch-Instance`
  header differentiates instances of the same token.
- Test: *"AC#1: two X-Orch-Instance consumers keep independent cursors over the same token"*
  — both consumers saw the same event independently; second poll for the caught-up consumer
  returned empty (`""`). ✅
- Core test: *"AC#1: two consumers with own cursors each see all events from their own position"* ✅

### AC#2 — Mock-format lines; semantic deviation documented; batch dispatch safety proven

**PASS**

- `formatEventLine` emits `{ticket_id: X, from: Y, to: Z, at: T}` — byte-identical to
  `mock-tracker.sh events` output.
- Semantic deviation (each transition is its own line vs. mock's snapshot-diff A→B→C collapse)
  is documented in `events.ts` JSDoc: *"A→B→C collapses in the mock; here it is three lines.
  The orchestrator dedups on `(ticket, to, at)` and re-reads state before spawning, so a
  same-ticket multi-event batch is dispatch-safe (spec §8, AC#2)."*
- Test: *"AC#2: A→B→C on ONE ticket surfaces as three distinct lines in a single poll"* ✅
- Test: *"AC#2: event lines are byte-identical to the mock `events` format"* ✅

### AC#3 — SSE < 1s delivery; Last-Event-ID reconnect loses nothing

**PASS** (all three SSE tests green)

- `buildServer` creates a single `EventBus`; the transition route's `publish` callback fires
  post-commit.
- **Subscribe-before-replay race fix** (commit `b65e88a`): SSE handler subscribes to the bus
  *before* querying the replay log, buffers live events during the replay window, then does a
  synchronous `buffered = buffer; buffer = null` swap (no `await` between swap and flush, so
  no publish can interleave and be lost), and flushes with a `replayed` seq-Set to dedup the
  overlap. Steady-state streaming holds no dedup state.
- Tests:
  - *"AC#3: SSE delivers a transition < 1s after commit"* — elapsed < 1000ms ✅
  - *"AC#3: reconnect with Last-Event-ID replays events missed while disconnected"* — missed event
    replayed; event at/under Last-Event-ID NOT re-sent ✅
  - *"AC#3: reconnect racing a concurrent commit loses nothing and never duplicates"* — concurrent
    event delivered exactly once (occurrences == 1) ✅

### AC#4 — Out-of-vocab comment kinds → 400; `transition-reason` as new comment → 400

**PASS**

- `WRITABLE_COMMENT_KINDS` = all 10 vocabulary kinds except `transition-reason`.
- `postComment` throws `BadCommentKindError(400)` before any DB write for any non-writable kind.
- Tests:
  - *"AC#4: POST comment with a valid kind → 201 mock-parity line"* ✅
  - *"AC#4: POST comment with an out-of-vocab kind → 400"* ✅
  - *"AC#4: POST comment kind=transition-reason → 400 (reserved for import/projection)"* ✅

### AC#5 — Transition writes NO comment row; N transitions → N events with reason; S3 projection renders mock-identical blocks

**PASS**

- `transition()` in `transitions.ts` contains no `INSERT INTO comment`. The comment block in the
  JSDoc explicitly states `[A-313] No transition-reason comment row — the reason lives on the
  event payload below and only there`.
- Event INSERT carries `JSON.stringify({ from, to, reason })` on payload.
- Tests:
  - *"AC#5: POST transition → 200, writes an event with the reason and NO comment row"*:
    `comments.rowCount === 0`, `events.rowCount === 1`, `payload.reason === "claiming"` ✅
  - *"AC#5: N transitions add N events with reason and 0 comment rows (commentless invariant)"*
    (core suite) ✅
  - S3 projection: verified by the SA (ABS-235 renderer confirmed to render `transition-reason`
    blocks from events, not from comment rows — see Architecture Review gate-results on ABS-236).

---

## Definition of Done Checklist

| Item | Status |
|------|--------|
| Routes/Cursor/SSE tests green (incl. reconnect test) | ✅ 16/16 |
| S2 engine tests adapted for commentless transaction | ✅ 59/59 |
| `pnpm -r typecheck` clean | ✅ |
| `eslint .` clean | ✅ |
| SSE reconnect race fix (subscribe-before-replay + dedup) | ✅ commit b65e88a |
| [A-313] transition invariant (CAS + event, no comment) | ✅ |
| Semantic deviation documented in events.ts JSDoc | ✅ |

---

## Evidence

```
Core suite (isolated):
  ℹ tests 59 | pass 59 | fail 0 | duration_ms 622ms

Server suite (isolated):
  ℹ tests 16 | pass 16 | fail 0 | duration_ms 1605ms

typecheck: Done (both packages)
eslint: (no output = clean)
```

**Verdict**: All 5 ACs and all DoD items verified. **APPROVED for Story Acceptance.**
