# QA Validation Report — ABS-412

**Ticket**: ABS-412 — Seat Heartbeat + Edge-Triggered Staleness Events  
**Branch**: `ABS-412-seat-heartbeat-staleness-events`  
**Commit**: `5d58213`  
**Date**: 2026-07-18  
**Verdict**: ✅ **APPROVED**

---

## Validation Summary

| Check | Result |
|-------|--------|
| `pnpm typecheck` (5 packages) | ✅ PASS |
| `pnpm lint` (eslint) | ✅ PASS |
| `bash -n scripts/backend-shipper.sh` | ✅ SYNTAX OK |
| Core package tests (213 total, with DATABASE_URL) | ✅ 213 PASS / 0 FAIL |
| Server package tests — ABS-412 scope | ✅ No regressions introduced |
| Server package tests — pre-existing failures (8) | ⚠️ Pre-existing on `main` (16 failures); ABS-412 branch reduced to 8 |

---

## AC Coverage Verification

### AC1 — seat-stalled emitted exactly once on threshold crossing; no repeat on subsequent polls

**Test**: `AC1: seat-stalled emitted once on threshold crossing; no repeat on subsequent polls`

**Verification**: The test:
1. Inserts an open spawn with `last_activity` 10s ago (threshold=5s → stale)
2. Calls `checkHeartbeats` → asserts exactly ONE `seat-stalled` event emitted
3. Asserts `stall_emitted_at IS NOT NULL` (edge-trigger guard set)
4. Calls `checkHeartbeats` again (seat still stale) → asserts 0 events (no repeat)
5. Calls a third time → 0 events
6. Queries event log → exactly ONE `seat-stalled` row

**Implementation**: `stall_emitted_at` NULL→non-NULL guard in `checkHeartbeats` ensures the
edge-trigger property. The condition `isStale && !wasStalled` emits only when crossing.

**Result**: ✅ PASS (124.6ms)

---

### AC2 — seat-recovered emitted when new activity clears the stall; stall_emitted_at cleared

**Test**: `AC2: seat-recovered emitted when activity resumes after stall`

**Verification**: The test:
1. Simulates an already-stalled seat (last_activity stale + stall_emitted_at set)
2. Records a fresh heartbeat via `recordHeartbeat`
3. Calls `checkHeartbeats` → asserts ONE `seat-recovered` event
4. Asserts `stall_emitted_at = NULL` (cleared)
5. Second poll → 0 events (no repeat)

**Implementation**: `!isStale && wasStalled` guard in `checkHeartbeats`; clears `stall_emitted_at = NULL` after emitting `seat-recovered`.

**Result**: ✅ PASS (6.3ms)

---

### AC3 — Thresholds configurable per project; read at poll time (no restart)

**Test**: `AC3: thresholds are configurable per project and read at poll time`

**Verification**: The test:
1. Reads default config (no DB row → falls back to `DEFAULT_HEARTBEAT_CONFIG`)
2. Upserts custom thresholds (warn=60s, stale=120s); reads back and asserts match
3. Updates to different thresholds (warn=30s, stale=15s); reads back and asserts immediate effect
4. Creates a seat 20s old; calls `checkHeartbeats` → emits stall under 15s threshold

**Implementation**: `getHeartbeatConfig` called at the top of `checkHeartbeats` every call — no caching, no restart required.

**Result**: ✅ PASS (4.97ms)

---

### AC4 — Events carry run-ID, orchestrator-instance id, ticket, role, attempt

**Test**: `AC4: seat-stalled event payload carries run_id, instance_id, ticket_id, role, attempt`

**Verification**: The test:
1. Opens a spawn with specific `runId`, `ticketId='ABS-412'`, `role='be-developer'`, `attempt=2`
2. Triggers a stall check
3. Asserts the returned `HeartbeatEvent` carries all five fields correctly
4. Queries the `event` table payload (JSONB) and asserts `run_id`, `instance_id`, `ticket_id`, `role`, `attempt` all present and correct

**Implementation**: `emitSeatEvent` inserts a JSONB payload with `run_id`, `instance_id`, `ticket_id`, `role`, `attempt` — AC4 fields sourced from the `seat_spawn` row (attempt comes from DB, not the shipper body).

**Result**: ✅ PASS (4.07ms)

---

### AC5 — ABS-352 completion-timeout staleness works as fallback when last_activity IS NULL

**Test**: `AC5: liveSpawns stale=true for open seat without last_activity (no heartbeat)`

**Verification**: The test:
1. Inserts an open spawn with `started_at = now() - interval '1 hour'` and NO `last_activity`
2. Calls `checkHeartbeats` → asserts 0 events (seats without `last_activity` are skipped)
3. Queries DB directly → confirms `age_sec > 300` and `last_activity = null`

**Additionally**: `spawns-routes.test.ts` AC4 (`open entry older than stale threshold renders as stale=true`) passes — the `stale` field in `liveSpawns` is computed from `started_at` age when `last_activity IS NULL`, exactly the ABS-352 fallback.

**Implementation**: `checkHeartbeats` query filters `WHERE last_activity IS NOT NULL` — seats without heartbeats are invisible to heartbeat checking; `liveSpawns` uses `EXTRACT(EPOCH FROM (now() - started_at)) > stale_threshold_sec` for the `stale` boolean independent of `last_activity`.

**Result**: ✅ PASS (3.0ms)

---

## Additional Tests (Beyond ACs)

| Test | Result |
|------|--------|
| `recordHeartbeat returns 0 when no matching open spawn` | ✅ PASS — idempotent, no error |
| `active seat with recent heartbeat does not emit seat-stalled` | ✅ PASS — fresh heartbeat (5s) under 60s threshold emits nothing |

---

## Architecture Gate Notes (from System Architect, Stage 1)

System Architect reviewed and approved commit `5d58213` (In Review → In Test) noting:
- Pattern compliance: agent-ingest route shape, `principal.targetProjectId` scoping
- Migration additive-only (ABS-288 integrity guard honored)
- Edge-trigger correctness (`stall_emitted_at` guard verified)
- Three non-blocking branch hygiene notes for TDM at PR-cut time

QAS independently confirms: no new test failures introduced; pre-existing 8 server test failures are a proper subset of the 16 on `main`.

---

## Branch Hygiene Note (non-blocking, echoes Architect)

Three ABS-412 branches exist:
- `ABS-412-seat-heartbeat-staleness-events` (commit `5d58213`) — **this is the correct PR branch**
- `ABS-412-auto` — stray, discard
- `ABS-412-seat-heartbeat` — divergent variant (different field names), discard before PR merge

This is a TDM/RTE action at PR-cut time, not a QA gate blocker.

---

## Verdict

**APPROVED** — All 5 ACs verified by integration tests against live Postgres. No regressions. Transition: In Test → Story Acceptance.
