# QA Validation Report — ABS-427

**Ticket**: ABS-427 — Backend-Event-Feed liefert keine create-Events
**Branch**: `ABS-427-auto`
**Commit**: `249962a`
**QAS Run Date**: 2026-07-18
**Verdict**: ✅ APPROVED

---

## Validation Summary

| Check | Result | Detail |
|-------|--------|--------|
| `pnpm typecheck` | ✅ PASS | All 5 packages — zero errors |
| `pnpm lint` | ✅ PASS | No lint violations |
| Core events.test.ts | ✅ 8/8 PASS | All tests including 2 new ABS-427 tests |
| Server events-routes.test.ts | ✅ 10/10 PASS | All tests including 1 new ABS-427 test |
| Pre-existing failures (bootstrap-promotion, command-routes, reporting) | ⚠️ 16 fail | PRE-EXISTING; unrelated to events feed (auth/session/bootstrap infra) |

---

## Acceptance Criteria Verification

### AC1 — Contract Decision Documented (Spec §8)
**Status: ✅ PASS**

Decision documented in `specs/ABS-229-agentic-backend-phase1-spec.md` §8:
> "**Create events are delivered (ABS-427)**: a freshly-created ticket surfaces as a creation line `{ticket_id: X, from: null, to: Backlog, at: T}` — parity with the mock's `events`, where a newly-appeared ticket is a creation event. Decision: deliver create events (restores mock parity) rather than ratify transition-only."

The contract choice (deliver create-events) is explicitly justified and documented. System Architect confirmed: defect fix restoring documented mock-parity, no ADR needed.

### AC2 — `?since=<seq>` History / Reject (No Silent Empty)
**Status: ✅ PASS**

Verified in `server.ts:312-314`:
- `since=0` → `Number("0") = 0` which is finite → `floor = 0` → query `seq > 0` → full history from seq 1
- Non-numeric `since` → `!Number.isFinite(NaN) = true` → `400 bad_since`

Test evidence:
```
✔ ABS-427: since=0 returns the full history including the create event (no silent empty) (7.3ms)
✔ ABS-427: a freshly created ticket is findable over the event feed (create line, no silent empty) (8.7ms)
```
The HTTP route test also asserts `bad.statusCode === 400` and `bad.json().error === "bad_since"` for `?since=nope`.

### AC3 — Conformance: Freshly-Created Ticket Findable Over Feed
**Status: ✅ PASS**

Tested at two layers:
1. **Core layer** (`events.test.ts`): `createItem()` → `readEventsForConsumer()` → asserts `lines[0].ticketId`, `lines[0].from === null`, `lines[0].to === "Backlog"`, byte-identical mock format
2. **HTTP layer** (`events-routes.test.ts`): `createItem()` → `GET /agent/v1/projects/:p/events?since=0` → asserts `200`, body matches `{ticket_id: ABS-1, from: null, to: Backlog, at: ...}\n`

---

## Code Review Notes

### Root Cause Fix (events.ts)
- Query changed from `e.kind = 'transition'` → `e.kind IN ('transition', 'create')`
- `COALESCE(e.payload->>'to', 'Backlog')` renders create events correctly — `createItem` always inserts status `'Backlog'`, COALESCE is correct and faithful (verified against `items.ts:383`)

### since=0 Semantics (server.ts:312-320)
- `Number("0") = 0` → `Number.isFinite(0) = true` → not rejected → `floor = 0` → `seq > 0` → returns seq 1 onwards (full history)
- Matches spec §8: "since=0 = the full history from seq 1"

### Pre-Existing Failures (Not ABS-427 Related)
The following tests fail in the current operator Postgres environment and are **NOT related to this change**:
- `bootstrap-promotion.test.ts` — 3 failures (dev/non-dev boot token state — requires a clean DB)
- `command-routes.test.ts` — 5 failures (session auth, queue state — infra-dependent)
- Other reporting tests — 8 failures (aggregation/analytics)

These are infrastructure-dependent failures on the shared operator Postgres. The implementer confirmed them as pre-existing via baseline stash run on a fresh Docker Postgres. The ABS-427 diff touches only `events.ts`, `events.test.ts`, `events-routes.test.ts`, and spec §8 — no overlap with failing tests.

### Non-Blocking Nit (from System Architect, acknowledged)
`server.ts:301` route comment still reads "one line per transition event" (stale after this change). No behavior impact; spec §8 and docstring in events.ts are correct.

### Scope Boundary (Correct)
SSE live-publish of create-events intentionally excluded. The orchestrator uses the polling feed (`GET /events`), not the SSE dashboard stream. Not an AC — YAGNI scope-out confirmed correct.

---

## ABS-66 Data-Flow Verification
- create event produced by `createItem` → persists in `event` table with `kind='create'`
- surfaced by `readTransitionEventsSince` (now reads `kind IN ('transition','create')`)
- delivered on `GET /agent/v1/projects/:p/events`
- consumed by `ORCH_REQUIRE_START_LABEL=0` dispatch (the mock-parity line it already parses)
- ✅ End-to-end data-flow complete

---

## Final Verdict

**✅ APPROVED FOR STORY ACCEPTANCE**

All 3 acceptance criteria met. Core tests 8/8 PASS, HTTP route tests 10/10 PASS, typecheck+lint PASS. The fix is minimal, correct, and pattern-compliant. No design flag on this ticket.

QAS gate: **PASSED** — transitioning to `Story Acceptance`.
