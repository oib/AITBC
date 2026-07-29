# QA Validation Report — PILOT-24

**Ticket**: PILOT-24 — seat_spawn.session_id: Spawn↔Session-Zuordnung  
**Branch**: PILOT-24-auto  
**Commit**: e4bd39c7df2dd99432b4b22bb7cfe006e4eaa6b7  
**QAS Run**: 2026-07-24  
**Verdict**: APPROVED ✅

---

## Acceptance Criteria Checklist

| AC | Criterion | Result | Evidence |
|----|-----------|--------|---------|
| AC1 | Sandbox-Spawn → seat_spawn row carries session_id; Board Seat-Drawer shows it | ✅ PASS | `PILOT-24 AC1` test: POST with session_id → list and detail both return it. `SeatDrawer.tsx` renders `<MetaField k="session" v={seat.session_id} testid="seat-session-id" />` |
| AC2 | Poisoned spawn → session_stored=false queryable via SQL count | ✅ PASS | `PILOT-24 AC2` test: `SELECT count(*) FROM seat_spawn WHERE session_stored = false` returns 1 after a poison-guard spawn |
| AC3 | Migration additive; 001–018 byte-unchanged; idempotent second boot | ✅ PASS | `git show e4bd39c7 --name-only` lists only `019_seat_spawn_session.sql`. Migrate tests 8/8: first run applies all 19 migrations in order, second run = no-op |
| AC4 | Old rows without session_id render NULL-tolerant in API/UI | ✅ PASS | `PILOT-24 AC4` test: direct INSERT without session columns → GET returns `session_id: null, session_stored: null`. `MetaField` hides when `v` is null/falsy |

---

## Test Run Evidence

### Typecheck
```
pnpm -r typecheck  →  5/5 scoped projects: PASS (apps/web, packages/core, packages/forge, packages/webhooks, apps/server)
```

### ESLint
```
eslint .  →  PASS (no output)
```

### PILOT-24 Conformance Tests (spawns-routes.test.ts — 8/8)
```
✔ AC1: POST spawn (open) → GET returns active entry; POST close → GET returns completed (427ms)
✔ ABS-445: non-UUID structured spawn_id persists (201) and is queryable, no 500 (9ms)
✔ AC3: spawns from instance A do not appear under instance B (12ms)
✔ AC4: open entry older than stale threshold renders as stale=true (5ms)
✔ PILOT-24 AC1: POST spawn carries session_id → GET row carries it back (12ms)
✔ PILOT-24 AC2: poisoned spawn → session_stored=false is queryable (not a log grep) (7ms)
✔ PILOT-24 AC4: a row without session data renders NULL-tolerant (old spawn) (7ms)
✔ POST /spawns with missing fields → 400 (3ms)

tests 8, pass 8, fail 0
```

### Migration Tests (migrate.test.ts — 8/8)
```
✔ first run applies every migration in order; all §2 tables exist (226ms)
✔ second run is a no-op — idempotent (AC#1) (4ms)
... 6 further tests — all pass

tests 8, pass 8, fail 0
```

### Baseline Regression Comparison (ABS-272/285 — back-to-back, same env)

Baseline: commit `3256bc3a` (e4bd39c7^)  
Branch: commit `e4bd39c7`

| Test file | Baseline failures | Branch failures | Delta |
|-----------|------------------|-----------------|-------|
| bootstrap-promotion.test.ts | 3 (pre-existing) | 3 (pre-existing) | 0 |
| report-routes.test.ts | 5 (pre-existing) | 5 (pre-existing) | 0 |
| All PILOT-24 tests | N/A (tests don't exist on baseline) | 0 | — |

**Zero regressions introduced.**

---

## Implementation Review

**Migration 019** (`019_seat_spawn_session.sql`): Two nullable `ALTER TABLE ADD COLUMN` statements — additive, no default, no backfill. Comment explains nullability contract (mock/alt/pre-PILOT-24 rows).

**`core/spawns.ts`**: `SeatSpawn` interface gains `session_id: string | null` and `session_stored: boolean | null`. `UpsertSpawnArgs` gains optional `sessionId`/`sessionStored`. Upsert INSERT + ON CONFLICT uses `COALESCE(EXCLUDED.session_id, seat_spawn.session_id)` — a later close never erases an open value. Both `liveSpawns` and `getSeatById` SELECT the columns and pass them through.

**Route** (`spawns.ts`): `session_stored` coerced with `typeof b.session_stored === 'boolean' ? b.session_stored : null` — non-boolean JSON values (strings, numbers) map to null rather than silently truthy/falsy.

**`SeatDrawer.tsx`**: `MetaField k="session"` hides when `session_id` is null. `session_stored` only renders when `!= null` — the `"no (poison guard dropped it)"` label fires on `false`, not null.

**`apps/web/src/types.ts`**: `SeatSpawn` interface updated with `session_id: string | null` and `session_stored: boolean | null` with accurate JSDoc.

---

## Out-of-Scope Deferral (Noted, not a blocker)

The system architect flagged that no `seat_spawn` producer POSTs to the backend today (`backend-shipper.sh` ships only `/spawns/heartbeat`; runner writes `SPAWN-USAGE` to `run.log`). The schema, API, and UI are end-to-end complete; the shipper-side write is a follow-up in the producer (adjacent to ABS-499). AC1 is satisfied at the DB+API+UI layer. This deferral is documented in the architect's handoff and does not block acceptance.

---

## Gate Result

All four ACs verified. No regressions. Typecheck and lint clean. Migration additive and idempotent.

**Verdict: APPROVED — transitioning to Story Acceptance.**
