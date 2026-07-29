# QA Validation Report — ABS-501

**Ticket**: ABS-501 — S1 Foundation: Postgres-LISTEN/NOTIFY-Backing für den Event-Bus  
**Branch**: ABS-501-auto  
**Commit**: a4381106  
**Validated by**: QAS  
**Date**: 2026-07-20  
**Verdict**: ✅ APPROVED

---

## Validation Summary

| AC | Description | Result |
|----|-------------|--------|
| AC1 | Cross-instance delivery < 1s (two buildServer instances, one DB) | ✅ PASS |
| AC2 | NOTIFY payload is pointer-only (projectId:seq:kind), never event body | ✅ PASS |
| AC3 | Kill LISTEN connection → reconnect + gap-replay, no lost event | ✅ PASS |
| AC4 | Single-instance behavior unchanged; existing events/SSE tests green | ✅ PASS |
| AC5 | ADR-A-0028 authored as `proposed` (human-only accept, ADR-A-0004) | ✅ PASS |
| AC6 | NOTIFY fires inside same transaction as event insert, before COMMIT | ✅ PASS |

---

## Gate Checks

| Check | Result |
|-------|--------|
| `pnpm typecheck` | ✅ Clean (exit 0) |
| `pnpm lint` | ✅ Clean (exit 0) |
| Core unit tests | ✅ 241/241 pass, 0 fail |
| Server integration tests | ✅ 207/215 pass; 8 pre-existing failures (bootstrap-promotion×3, report-routes×5) — files NOT touched by ABS-501 (verified: `git diff main -- test/bootstrap-promotion.test.ts test/report-routes.test.ts` → empty) |

---

## AC Evidence (per criterion)

### AC1 — Cross-instance delivery < 1s
**Test**: `ABS-501 AC1: a transition on instance A reaches instance B's SSE stream < 1s`  
**Command**: `DATABASE_URL=postgresql://postgres:postgres@localhost:5432/agentic pnpm --filter @agentic-backend/server test`  
**Result**: ✅ PASS (210ms execution; test asserts `elapsed < 1000ms`)  
**What it does**: Spins up two `buildServer` instances (`appA`, `appB`) on the same schema; opens SSE stream on B; fires transition on A; asserts B's SSE stream carries the transition frame < 1s.

### AC2 — Pointer-only NOTIFY payload
**Test (integration)**: `ABS-501 AC2/AC6: the NOTIFY carries a pointer only and is delivered on COMMIT, not before` — PASS (424ms)  
**Test (unit)**: `ABS-501 AC2: NOTIFY payload is a pointer only (projectId:seq:kind), never the event body` — PASS  
**Code trace**: `busNotifyPayload()` in `events.ts` returns `${projectId}:${seq}:${kind}` — no event body fields. Integration test asserts `notes[0]` equals `${projectId}:${seq}:transition` and does NOT contain `secret-reason-text`.

### AC3 — LISTEN connection kill → reconnect + gap-replay
**Test**: `ABS-501 AC3: killing B's LISTEN connection → reconnect + no lost event (gap-replay)` — PASS (549ms)  
**What it does**: Opens SSE on B; commits event A1 (establishes gap-replay floor); kills ALL `LISTEN bus_events` backend connections via `pg_terminate_backend`; commits event A2 (NOTIFY lost during disconnect); waits up to 4s; asserts both `"to":"Ready for Development"` AND `"to":"In Progress"` appear in B's SSE buffer (second event delivered via reconnect + `replayGap()`).

### AC4 — Single-instance unchanged
**Core suite**: 241/241 pass — all existing events tests green including pre-ABS-501 SSE tests.  
**Server suite**: 207/215; the 8 failures are in `bootstrap-promotion.test.ts` (needs dev NODE_ENV env boot) and `report-routes.test.ts` (needs `orchestrator-report.sh` in correct path relative to repo root) — both test files have ZERO changes vs main (confirmed by git diff). Bus is in-process-only unless `databaseUrl` is supplied (`buildServer(pool)` without option) — single-instance fast path is entirely unchanged.

### AC5 — ADR amendment as `proposed`
**File**: `adrs/agentic/ADR-A-0028-multi-instance-event-bus.md`  
**Status line**: `- **Status:** proposed`  
**Content**: Amends ADR-A-0021 §(e); resolves all three `#PATH_DECISION` items:
- Channel granularity: one global `bus_events` channel, filtered in-process
- Payload format: `<projectId>:<seq>:<kind>` (kind included)
- wait-Cap: `EVENT_WAIT_CAP_SECONDS` default 55 (one value, one source for S2/S3/S4)
- ADR acceptance is human-only per ADR-A-0004 ✅

### AC6 — Transactional NOTIFY (same transaction as event insert)
**Test**: `ABS-501 AC2/AC6: the NOTIFY carries a pointer only and is delivered on COMMIT, not before` — PASS  
**Code trace** (`transitions.ts`):
1. `BEGIN` on `client`
2. `UPDATE work_item ...`
3. `INSERT INTO event ...` → returns `seq`
4. `notifyBusEvent(client, { projectId, seq, kind: "transition" })` → `SELECT pg_notify(...)` ON THE SAME `client`, BEFORE `COMMIT`
5. `COMMIT`
6. `publish?.(result)` (post-commit in-process fast path)

**Integration test proof**: Inserts event + calls `pg_notify` inside an explicit BEGIN/COMMIT. A raw LISTEN client asserts `notes.length === 0` after 200ms wait BEFORE the COMMIT, then `notes.length === 1` after COMMIT — proving zero app-code window between event durable in the log and subscriber wake.

---

## Code Quality Verification

### `events.ts` (core implementation)
- `EventBus` class: in-process `EventEmitter` + optional Postgres LISTEN backing
- `start()` is idempotent; no-op without pool + connectionString
- Dedicated `pg.Client` (never from pool) with `error`/`end` → `scheduleReconnect()`
- Reconnect backoff: 100ms → doubling → 5s cap (unit-tested)
- `deliver()` single gate: seq-based dedup (`seen` bounded FIFO, 5000 entries), `lastSeqByProject` floor tracking
- `replayGap()` on reconnect: refcount-gated (only projects with live subscribers), reads `readBusEventsSince`
- `close()` is idempotent; `reconnectTimer.unref()` used (no process-hold)

### `transitions.ts` (AC6 key path)
- `notifyBusEvent(client, ...)` called between `INSERT INTO event` and `client.query("COMMIT")` — on the same `PoolClient` (`BEGIN`-wrapped), not after commit

### `ADR-A-0028`
- Status: `proposed` ✅
- Resolves all three `#PATH_DECISION` items ✅
- Amends ADR-A-0021 §(e) ✅
- Honestly records the out-of-order-seq gap as accepted/out-of-scope for S1 ✅
- Human-only accept per ADR-A-0004 ✅

---

## Non-Blocking Notes (forwarded from arch review)

1. **ADR back-link**: ADR-A-0021 should get a reciprocal reference to ADR-A-0028 added when a human accepts the ADR (do not add a back-link to a `proposed` ADR prematurely). No code gate.
2. **Seq ordering gap**: documented and accepted for S1; S2 should keep it in view if stronger ordering guarantees are added later.

---

## Flags Check

Labels: `[orchestrator-ready]` — no `design` flag → exit to **Story Acceptance** (not Design Test).

---

## Final Verdict

**APPROVED** — All 6 ACs met. typecheck and lint clean. Core: 241/241. Server: 207/215 (8 pre-existing, files untouched by ABS-501). ABS-501-specific integration tests: AC1, AC2/AC6, AC3 all PASS. ADR-A-0028 `proposed` with all `#PATH_DECISION` items resolved.

Run against commit: `a4381106` on branch `ABS-501-auto`.
