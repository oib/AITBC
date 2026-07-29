# QA Validation Report — ABS-502

**Ticket**: ABS-502 — S2: Long-Poll `?wait=<sec>` auf dem Agent-`events`-Op  
**Branch**: `ABS-502-auto`  
**Commit validated**: `29c98418a6dce5552adece0a337a8cb72630ecd9`  
**Date**: 2026-07-20  
**QAS actor**: qas  
**Verdict**: ✅ APPROVED

---

## Test Run Evidence (Green-Run Proof — ABS-453)

**Command**:
```
cd backend && DATABASE_URL="postgres://postgres:test@localhost:55502/agentic" \
  node --import tsx --test --test-concurrency=1 apps/server/test/events-routes.test.ts
```

**Postgres target**: `abs502-pg` container (port 55502) — real Postgres + real bus, no mocks.

**Results** (22 pass / 0 fail):

```
✔ AC#4: POST comment with a valid kind → 201 mock-parity line (276ms)
✔ AC#4: POST comment with an out-of-vocab kind → 400 (6ms)
✔ AC#4: POST comment kind=transition-reason → 400 (reserved) (4ms)
✔ AC#5: POST transition → 200, writes an event with the reason (7ms)
✔ AC#5: illegal transition → 400; stale expect_from → 409 (7ms)
✔ AC#1: two X-Orch-Instance consumers keep independent cursors (15ms)
✔ ABS-427: a freshly created ticket is findable over the event feed (8ms)
✔ AC#3: SSE delivers a transition < 1s after commit (83ms)
✔ AC#3: reconnect with Last-Event-ID replays events missed (15ms)
✔ AC#3: reconnect racing a concurrent commit loses nothing (11ms)
✔ ABS-501 AC1: a transition on instance A reaches instance B's SSE stream < 1s (203ms)
✔ ABS-501 AC2/AC6: NOTIFY carries pointer only, delivered on COMMIT not before (417ms)
✔ ABS-501 AC3: killing B's LISTEN connection → reconnect + no lost event (574ms)
✔ ABS-502 AC1: wait + a later commit → answers with the event; cursor advances (250ms)
✔ ABS-502 AC2: wait with no events → empty answer at ~timeout; cursor unmoved; 200 (2026ms)
✔ ABS-502 AC3: no DB lock is held across the wait phase (381ms)
✔ ABS-502 AC4: two instances — waiter on B, commit on A → answers < 1s (365ms)
✔ ABS-502 AC5: wait=0 is byte-identical to a plain read (44ms)
✔ ABS-502 AC6: client disconnect during the wait removes the subscriber (no leak) (508ms)
✔ ABS-502 AC7: event in the window right after the first empty read → still answers < 1s (25ms)
✔ ABS-502 AC8: a storm of non-feed events does not wake the waiter (wake-filter) (2015ms)
✔ ABS-502 AC9: server shutdown with an open waiter → empty answer, not a torn connection (357ms)

ℹ tests 22 | pass 22 | fail 0 | cancelled 0 | skipped 0 | duration_ms 8048
```

---

## Static Analysis Gates

| Check | Result |
|---|---|
| `pnpm -r typecheck` | ✅ Clean — 5/5 packages (core, forge, webhooks, web, server) |
| `pnpm lint` | ✅ Exit 0 — no violations |

---

## Acceptance Criteria Verification (AC1–AC9)

| AC | Description | Test | Result |
|---|---|---|---|
| **AC1** | wait=30 + event after 2s → answer with event in ~2s, cursor advances | `ABS-502 AC1: wait + a later commit` | ✅ PASS |
| **AC2** | wait=2 with no events → empty answer after ~2s; cursor unmoved; 200 | `ABS-502 AC2: wait with no events` | ✅ PASS |
| **AC3** | No DB lock during wait (pg_locks == 0; parallel poll not blocked) | `ABS-502 AC3: no DB lock is held across the wait phase` | ✅ PASS |
| **AC4** | Two instances: waiter on B, commit on A → answer < 1s (S1 cross-instance) | `ABS-502 AC4: two instances` | ✅ PASS |
| **AC5** | `wait=0`/absent → byte-identical to today's behaviour | `ABS-502 AC5: wait=0 is byte-identical` | ✅ PASS |
| **AC6** | Client disconnect → subscriber removed (leak test via subscriberCount) | `ABS-502 AC6: client disconnect` | ✅ PASS |
| **AC7** | Event commits in the read/park window → still answered < 1s (subscribe-before-read) | `ABS-502 AC7: event in the window right after first empty read` | ✅ PASS |
| **AC8** | Storm of non-feed events (telemetry/signal) → waiter holds to timeout (wake-filter) | `ABS-502 AC8: a storm of non-feed events` | ✅ PASS |
| **AC9** | Server shutdown with open waiter → empty 200, not a torn socket | `ABS-502 AC9: server shutdown with an open waiter` | ✅ PASS |

---

## Implementation Spot-Checks (In-Source)

- **Subscribe-before-read** (AC7 race guard): `bus.subscribe(projectId, …)` called *before* first `readOnce()` — confirmed `server.ts:405` / `server.ts:418`. ✅
- **No lock across wait**: `readOnce()` opens and commits its own transaction; park holds no DB resource — verified in `events.ts` and `server.ts` structure. ✅  
- **Wake-filter on kind** (AC8): `if (e.kind === "transition" || e.kind === "create") resolveWait()` — exactly matches feed's own `e.kind IN ('transition','create')` read filter. ✅  
- **Wait cap**: `eventWaitCapSeconds()` — default 55 s, fail-safe parse (bad/≤0 env → default). ✅  
- **Graceful shutdown** (AC9): `app.addHook("preClose", …)` wakes all waiters AND awaits their flush before Fastify tears down. ✅  
- **Client-disconnect cleanup** (AC6): `request.raw.on("close", resolveWait)` + `try/finally` unsubscribe+delete+markFlushed+off. ✅  
- **`/capabilities` advertises `events-wait`**: `server.ts:237`. ✅  
- **`EventBus.subscriberCount`**: Added for AC6 leak assertion (`events.ts:444`). ✅

---

## Pre-existing Failure Note

`report-routes.test.ts` fails on the base branch (`epic/ABS-500-poll-to-push`) — confirmed unrelated. Diff scope is `events.ts`, `server.ts`, `index.ts`, `events-routes.test.ts` only. Zero report code touched.

---

## Flags

- No `design` flag → exit transition: **Story Acceptance** (not Design Test).

---

## Verdict

**✅ APPROVED — all 9 ACs met, 22/22 tests green vs real Postgres + bus, typecheck + lint clean.**
