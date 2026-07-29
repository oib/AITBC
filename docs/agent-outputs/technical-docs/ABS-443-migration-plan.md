# ABS-443 — Mission-Control e2e migration reconciliation (isolated e2e DB)

**Role:** data-engineer · **Type:** enabler · **Schema change:** none (test-harness only)

## Problem (root cause)

The Mission-Control (agentic-backend) Playwright e2e suite was **unrunnable**: the
`webServer` aborted at boot with

```
MigrationDriftError: migration integrity: file missing on disk for already-applied
migration '008_knowledge_adr_policy.sql'.
```

The shared operator Postgres has `008_knowledge_adr_policy.sql` recorded in its
`schema_migrations` history. On disk that file was **renumbered to
`009_knowledge_adr_policy.sql`** when `008_pr_mirror_base_sha.sql` landed on main
(commit `510efd4`, epic/ABS-231 merge). The boot-time content-integrity guard
(ABS-288) sees an applied migration whose file no longer exists on disk and
**fails closed** — the server never reaches ready, so Playwright aborts the whole
suite before any spec runs.

**Reproduced** here by booting the server against the operator DB
(`localhost:5432/agentic`): `MigrationDriftError … '008_knowledge_adr_policy.sql'`,
process exits 1.

The on-disk migration series itself is already self-consistent (`001…009`, only the
grandfathered `004` pair duplicated) — the divergence lived purely in a
**persistent shared database's applied history**, not in the files.

## Fix — `#PATH_DECISION` path (b): isolated, reseeded e2e database (preferred)

The suite now **never** boots against a caller's persistent/shared database. Before
the server starts, the e2e harness drops + recreates a dedicated **`agentic_e2e`**
database, and the server auto-migrates it **clean from an empty schema**. Any future
renumbering on a shared Postgres therefore cannot re-break the epic's e2e.

Changes (test-harness only — no product/runtime schema change):

- `backend/apps/web/e2e/const.ts` — derive the isolated e2e connection: base
  creds/host/port still come from `DATABASE_URL` (so CI points at its own Postgres
  service); only the database **name** is forced to `agentic_e2e` (override with
  `E2E_DB_NAME`). Adds `e2eDatabaseUrl()` + `e2eAdminUrl()`.
- `backend/apps/web/e2e/reset-db.ts` (new) — connects to the maintenance `postgres`
  db, `DROP DATABASE IF EXISTS agentic_e2e WITH (FORCE)` then `CREATE DATABASE
  agentic_e2e`.
- `backend/apps/web/playwright.config.ts` — webServer boots against
  `e2eDatabaseUrl()`, and the command is chained
  `node … reset-db.ts && node … server` so provisioning runs **before** the server
  migrates. (Chosen over `globalSetup` because Playwright starts `webServer`
  *before* `globalSetup`, so a globalSetup hook would create the DB too late.)
- `backend/apps/web/package.json` + `pnpm-lock.yaml` — add `pg` / `@types/pg`
  (already in the workspace via `@agentic-backend/core`; same version, minimal lock
  delta) so `reset-db.ts` can provision the DB.

## AC4 — isolation guarantee siblings inherit

**The e2e database is now ISOLATED and reseeded (dropped + recreated empty) on every
run.** It is no longer the shared operator Postgres. Consequences for sibling
ABS-410 stories whose ACs assert "e2e asserts…":

- The webServer always boots to ready; migration drift on any shared/persistent
  Postgres can never re-break e2e again.
- Each run starts from an **empty** schema; specs must self-seed their fixtures via
  the API in `beforeAll` (they already do). No cross-run state leaks in.
- Override the DB name per parallel/sandboxed run with `E2E_DB_NAME`.

## Evidence

- **Baseline (drift reproduced):** server booted against `localhost:5432/agentic`
  → `MigrationDriftError … '008_knowledge_adr_policy.sql'`, exit 1.
- **AC1 (boots to ready):** with the fix, against the *same* drifted operator server,
  the webServer provisioned `agentic_e2e`, applied `001…009` clean, and logged
  `server: listening on :8478`.
- **AC2 (executes to completion):** `pnpm --filter @agentic-backend/web test:e2e`
  ran the suite to per-test results — **4 passed, 1 skipped, 5 failed** — no
  `webServer` abort. The 5 failures are **pre-existing spec/product issues surfaced
  (not caused) by making the suite runnable**, e.g. `spawns.spec.ts` posts a
  non-UUID `spawn_id` into the `seat_spawn.id uuid` column
  (`22P02 invalid input syntax for type uuid`). Fixing those assertions is explicitly
  out of scope for this enabler and belongs to the owning ABS-410 story.
- **AC3 (self-consistent from empty):** live boot applied
  `001…009` in order; `pnpm --filter @agentic-backend/core test` migration suite
  16/16 pass, incl. *"real migration series carries no ungrandfathered duplicate
  prefix"*.
- **Gates:** `pnpm -r typecheck` PASS · `pnpm lint` PASS.
