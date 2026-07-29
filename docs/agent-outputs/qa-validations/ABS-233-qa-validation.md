# QA Validation — ABS-233

**Ticket**: ABS-233 — Backend S1: Workspace-Skeleton, Postgres Schema+Migrations, Auth, /healthz  
**Branch**: ABS-233-auto  
**Commit validated**: 7a3f21f (feat(backend): S1 workspace skeleton…)  
**Validator**: qas  
**Date**: 2026-07-13  
**Verdict**: ✅ APPROVED

---

## Test Execution

All tests run against Postgres 16-alpine in a local Docker container (`abs233-test-pg`, port 15432).

| Suite | Pass | Skip | Fail |
|---|---|---|---|
| packages/core (unit + integration) | 7 | 0 | 0 |
| apps/server (integration) | 7 | 0 | 0 |
| **Total** | **14** | **0** | **0** |

Commands run:

```
pnpm typecheck   → PASS (tsc --noEmit on packages/core and apps/server; 0 errors)
pnpm lint        → PASS (eslint .; 0 violations)
DATABASE_URL=postgres://postgres:testpass@localhost:15432/testdb pnpm test  → 14/14 PASS
```

---

## Acceptance Criteria

### AC#1 — docker compose up (postgres) + pnpm dev starts server; migrations run automatically and idempotently

- `docker-compose.yml` runs `postgres:16-alpine` with a healthcheck; `backend` service depends on `db: condition: service_healthy`.
- `apps/server/src/index.ts` calls `runMigrations(pool)` before `app.listen()` on every boot.
- Test: `second run is a no-op — idempotent (AC#1)` → `runMigrations` returned `[]` on the second call. **PASS**

### AC#2 — All §2 tables exist with indexes (GIN on fields/tsvector, UNIQUE constraints, bigserial event seq)

- `001_init.sql` matches spec §2 DDL verbatim: 11 tables (org, project, entity_type, work_item, work_item_link, comment, work_item_revision, event, consumer_cursor, key_sequence, auth_token).
- Test: `first run applies the init migration; all §2 tables exist` verified all 11 table names present in `information_schema.tables`. **PASS**
- Test: `bigserial + generated tsvector + GIN indexes are present (AC#2)` confirmed `event.seq` is `bigint` (bigserial backing type) and `work_item` has ≥3 GIN indexes (search, fields, title gin_trgm_ops). **PASS**

### AC#3 — /agent/* and /api/* routes without valid token → 401; token carries project scope + role

`server.ts` registers an `onRequest` hook (runs before routing) that calls `authenticate()` for all paths matching `/agent/` or `/api/`. Results:

| Test | Result |
|---|---|
| `401 matrix — missing token` | PASS |
| `401 matrix — wrong/unknown token` | PASS |
| `unmatched /api/* path is guarded (401 before 404)` | PASS |
| `403 — valid token, foreign project scope` | PASS |
| `valid project-scoped token — carries project scope + role` | PASS (status 200, body has `role: "agent"` and `project: "ABC"`) |
| `org-wide admin token accepted for any project` | PASS |

Auth implementation: sha256 digest via `crypto.createHash`, constant-time compare via `timingSafeEqual` (node:crypto). Both are exercised by 4 pure unit tests in `packages/core/test/auth.test.ts`. **PASS**

### AC#4 — /healthz checks DB connectivity

- `pingDatabase()` runs `SELECT 1`; returns `true` on success, `false` on error.
- `/healthz` returns `200 { status: "ok" }` when `pingDatabase` resolves true, `503 { status: "degraded" }` otherwise.
- Test: `healthz reports ok when the DB is reachable (AC#4)` → status 200. **PASS**

---

## Definition of Done

| Item | Status |
|---|---|
| Unit tests for auth-middleware green | ✅ PASS — 6 auth tests pass (4 unit + 2 scoped-token integration) |
| Unit tests for migrations idempotency green | ✅ PASS — `second run is a no-op` passes |
| Lint green | ✅ PASS — eslint 0 violations |
| Typecheck green | ✅ PASS — tsc --noEmit 0 errors |

---

## Observations

No defects. Two minor notes (non-blocking):

1. The `auth-middleware.test.ts` file is placed under `apps/server/test/` but uses the `node:test` runner (not a framework). It is correctly discovered by `node --import tsx --test test/**/*.test.ts`.
2. `packages/realtime` and `apps/web` listed in the spec §1 workspace layout are absent. They are out of scope for S1 per the ticket's "Out of scope" clause and the spec's Phase-2 annotation — not a defect.

---

## Verdict

**APPROVED for Story Acceptance.**

All 4 ACs verified. All DoD items satisfied. 14/14 tests pass against a live Postgres 16 instance. Lint and typecheck clean.
