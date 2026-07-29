# QA Validation Report — ABS-445

**Ticket**: ABS-445 — Bug: spawns create route 500s on non-UUID spawn_id (22P02) — align seat_spawn id contract  
**Branch**: `ABS-445-auto`  
**Commit under review**: `60ff9e6` — `fix(api): store seat_spawn.id as text so non-UUID spawn ids no longer 500 [ABS-445]`  
**QA report commit**: `8f3f647` (updated below; previous report referenced stale commit `50c8d1a`/`010_seat_spawn_id_text.sql` — superseded by this revision after BE renumbered the migration `010→011`)  
**QAS Actor**: qas  
**Date**: 2026-07-18  
**Verdict**: ✅ **APPROVED**

---

## Context: Migration Renumbering (010 → 011)

After the first QAS pass approved `50c8d1a` (migration `010_seat_spawn_id_text.sql`), story ABS-441 merged `010_command_reason.sql` into main — occupying the `010` prefix. The BE fix-forward renumbered the ABS-445 migration to `011_seat_spawn_id_text.sql` (SQL body byte-identical, `uuid→text`). This report covers the renumbered commit `60ff9e6`. A second Test Prep pass (data-provisioning-eng) re-verified the full chain end-to-end on a throwaway Postgres (port 55493, ABS-374 compliant).

---

## Diff Scope (commit 60ff9e6 vs its parent)

| File | Change |
|------|--------|
| `backend/apps/server/test/spawns-routes.test.ts` | +46 lines — new ABS-445 integration test |
| `backend/packages/core/src/migrations/011_seat_spawn_id_text.sql` | +12 lines — migration (`uuid → text`), renumbered from `010` |
| `backend/packages/core/test/migrate.test.ts` | +1 line — add `"011_seat_spawn_id_text.sql"` to expected applied list (after `"010_command_reason.sql"`) |

No product route code was changed — only the schema (migration) + test coverage.

Migration sequence on branch (from `git ls-files`):
```
001_init.sql
002_work_item_priority.sql
003_orchestration_and_link_facets.sql
004_pr_mirror.sql
004_seat_spawns.sql          ← grandfathered duplicate-004 pair
005_telemetry_events.sql
006_command_queue.sql
007_dashboard_session_store.sql
008_pr_mirror_base_sha.sql
009_knowledge_adr_policy.sql
010_command_reason.sql       ← ABS-441 (on main)
011_seat_spawn_id_text.sql   ← ABS-445 (this fix, renumbered)
```

---

## Acceptance Criteria Verification

### AC1 — Valid non-UUID spawn id persists (2xx) and is queryable; integration test asserts

- **PASS** ✅
- `spawns-routes.test.ts` contains the ABS-445 integration test: POSTs `spawn_id = "i-1-T1-1"` (structured orchestrator id, not a UUID), asserts `statusCode == 201` (not 500), then GETs the spawn list and asserts `inst.active[0].id === "i-1-T1-1"` (persisted row carries the structured id).
- Test is DB-guarded (`{ skip: !BASE_URL }`). Data-provisioning-eng (second pass, port 55493) executed it on a throwaway `postgres:16-alpine` with `CI=1`: **201, no 500, row queryable** — PASS.
- `seedSpawn()` in e2e spec also asserts `expect(r.status()).toBe(201)` after each seed, providing additional cross-validation.

### AC2 — No unhandled HTTP 500 / 22P02; test asserts status + body

- **PASS** ✅
- Assertion: `assert.notEqual(open.statusCode, 500, open.body)` in the ABS-445 integration test.
- Root-cause fix eliminates the error class: widening `seat_spawn.id uuid → text` means Postgres never throws `22P02` (invalid text representation) for non-UUID values.

### AC3 — `backend/apps/web/e2e/spawns.spec.ts` (DAC-14/15/16/17) PASS

- **PASS** ✅ (DB-gated, verified by data-provisioning-eng, second Test Prep pass)
- `spawns.spec.ts` seeds via `seedSpawn()` using non-UUID ids of the form `${instanceId}-${ticketId}-${Date.now()}` — exactly the shape that caused 22P02 before the fix.
- Data-provisioning-eng confirmed on throwaway Postgres (`CI=1`, fresh server, port 8478 orphan terminated): **DAC-14/15/16/17 all 4 PASS**.
- No-regression proof provided: base `67b3e55` (uuid column) = 8 fail; branch `60ff9e6` = 8 fail (identical names, all pre-existing/out-of-scope); net delta = **+1 passing test = ABS-445 test only**.

### AC4 — Migration `011_seat_spawn_id_text.sql` added and applies cleanly via `pnpm migrate`

- **PASS** ✅
- File: `backend/packages/core/src/migrations/011_seat_spawn_id_text.sql`
- Content: `ALTER TABLE seat_spawn ALTER COLUMN id TYPE text USING id::text;`
- Lossless widening (`uuid::text` cast preserves any existing data); no DROP, no data-loss.
- No FK references `seat_spawn.id` (verified by SA independently via grep; ON CONFLICT (id) upsert works unchanged).
- Prefix `011` is unique — only `011_seat_spawn_id_text.sql` in this series (no collision).
- `migrate.test.ts` extended: `"010_command_reason.sql"` at line 73, `"011_seat_spawn_id_text.sql"` at line 74 — correct sequential ordering.
- Data-provisioning-eng confirmed (second pass): `NODE_ENV=development pnpm migrate` applied `001..011`; `seat_spawn.id data_type = text`; PK `seat_spawn_pkey` preserved; `migrate.test.ts` core suite 218/218 pass (prefix-guard clean, no dup `011`).

---

## Code Quality Checks (independently run from worktree HEAD `8f3f647`)

| Check | Command | Result |
|-------|---------|--------|
| `pnpm lint` (eslint, all packages) | `pnpm lint` | ✅ exit 0 |
| `pnpm typecheck` (tsc, 5 workspace projects) | `pnpm -r typecheck` | ✅ clean (all 5 pass) |
| Core tests (218 total) | `pnpm --filter @agentic-backend/core test` | ✅ 133 pass, 0 fail, 85 skip |
| Core: migrate-prefix-guard | (above) | ✅ PASS — no duplicate for `011`; grandfathered `004` pair OK |
| Server tests (170 total) | `pnpm --filter @agentic-backend/server test` | ✅ 7 pass, 0 fail, 163 skip |
| ABS-445 integration test appears in server suite | (above) | ✅ Present (skipped cleanly without BASE_URL) |

---

## Architecture Confirmation (SA gate already verified, In Review stage)

The System Architect independently confirmed (gate-results comment 2026-07-18T17:36:42Z):
- `ON CONFLICT (id) DO UPDATE` upsert **requires** a deterministic shipper-known id; `uuid` was architecturally incompatible; `text` is correct.
- Migration is a lossless widening; no FK on `seat_spawn.id`; no data-loss risk.
- `pnpm typecheck` clean; `pnpm lint` exit 0 (SA scope).
- The `#PLAN_UNCERTAINTY` was resolved correctly — root-cause fix, not a bandaid.

---

## Pre-existing Out-of-Scope Failures

| Failure | Status |
|---------|--------|
| `board.spec.ts` S9 release-toggle (ABS-241/446) | Out of scope per ticket — explicit separate follow-up |
| `report-routes.test.ts` telemetry aggregation | Pre-existing, independent of this diff |
| `auth-bootstrap` DB-gated server tests (3 tests) | Pre-existing, DB-gated, no BASE_URL |

These are **not** regressions from ABS-445 and are not counted against this validation.

---

## Flags Check

- `flags: [data]` — **no `design` flag**
- Exit target: **Story Acceptance** (design-flag pipeline not triggered)

---

## Final Verdict

| Criterion | Result |
|-----------|--------|
| AC1 — valid non-UUID spawn id persists (integration test) | ✅ PASS |
| AC2 — no unhandled 500/22P02 | ✅ PASS |
| AC3 — e2e DAC-14/15/16/17 PASS | ✅ PASS |
| AC4 — migration 011 applies cleanly | ✅ PASS |
| lint / typecheck | ✅ PASS |
| migrate-prefix-guard (no duplicate 011) | ✅ PASS |
| No FK on seat_spawn.id (no migration risk) | ✅ CONFIRMED |
| Root-cause fix (not a bandaid) | ✅ CONFIRMED |
| No regressions (delta = +1 test only) | ✅ CONFIRMED |

**Verdict: APPROVED → Story Acceptance**  
All 4 ACs met. Code quality gates pass. Migration renumbering (`010→011`) is clean and correctly ordered after `010_command_reason.sql`. No bounce required. Releasing to Story Acceptance.
