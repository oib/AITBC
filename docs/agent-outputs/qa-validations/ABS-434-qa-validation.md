# QA Validation Report — ABS-434

**Ticket**: ABS-434 — Test-infra: provision Postgres so Mission-Control (ABS-410) web-tier e2e runs in CI/QAS  
**Branch**: `ABS-434-auto`  
**Commit**: `8bd2745` (`ci(pipeline): execute Mission-Control web e2e on a provisioned Postgres [ABS-434]`)  
**Diff surface**: `bitbucket-pipelines.yml` only (+67 lines)  
**QAS run date**: 2026-07-18  
**Verdict**: ✅ APPROVED

---

## Validation Scope

ABS-434 is a YAML-only CI test-infra enabler. The `flags: [data]` route sent it through Test Prep; no product/application code was modified. QAS success criterion (carried from architect + data-provisioning-eng, confirmed independently): **"the web e2e suite EXECUTES and reports per-test results (no `localhost:55432` env-skip)"** — NOT "all e2e green."

---

## Acceptance Criteria — Verdict Per Criterion

### AC1 ✅ MET — Suite executes with per-test results; no `localhost:55432` env-skip

**Evidence:**
- `playwright.config.ts:21` confirmed to fall back to `postgres://postgres:pw@localhost:55432/agentic` when `DATABASE_URL` is unset — the exact ABS-434 defect.
- The `web-e2e-validation` step exports `DATABASE_URL="postgres://postgres:postgres@127.0.0.1:5432/agentic"` BEFORE calling `pnpm --filter @agentic-backend/web test:e2e`, overriding that fallback.
- The step uses a `pg_isready` fail-loud wait (30 retries × 2s = 60s cap) — if Postgres is not reachable, the step FAILS rather than falling back to the env-skip path.
- Implementer verified end-to-end locally (isolated Postgres on `:55439`): suite executed to completion reporting **4 passed, 1 skipped, 5 failed** — confirming per-test results are produced (NOT an env-skip).

### AC2 ✅ SATISFIED BY CONSTRUCTION (external dependency, pending ABS-420 merge)

**Evidence:**
- `git ls-tree HEAD -- backend/apps/web/e2e/filters.spec.ts` → empty (not on this branch)
- `git ls-tree main -- backend/apps/web/e2e/filters.spec.ts` → empty (not on main)
- `playwright.config.ts:4` uses `testDir: "./e2e"` — `playwright test` globs `e2e/*.spec.ts` automatically
- Once ABS-420 merges, `filters.spec.ts` is auto-picked up with no infrastructure change
- Classification: **external dependency** (unmerged branch) — not bounced per architect's correct classification

### AC3 ✅ MET — Migrations + seed run before the suite

**Evidence:**
- Step script order confirmed: `NODE_ENV=development pnpm migrate` executes BEFORE `pnpm --filter @agentic-backend/web test:e2e`
- 10 SQL migration files confirmed: `001_init.sql` through `009_knowledge_adr_policy.sql` (+ two `004_` variants) in `backend/packages/core/src/migrations/`
- Seed fixtures: each spec self-seeds in-band in `beforeAll` via `POST /api/admin/projects` (unique `E2E${Date.now()}` project) — confirmed in `backend/apps/web/e2e/{board,report,knowledge,spawns}.spec.ts`
- No separate seed script needed or expected — data-provisioning-eng confirmed the provisioning chain is complete

### AC4 ✅ MET — e2e job wired into the pipeline on the web-app path

**Evidence (YAML parsed, confirmed valid):**
- `definitions.steps[1]` (Web e2e step): `condition.changesets.includePaths: ["backend/apps/web/**", "bitbucket-pipelines.yml"]`
- `pipelines.pull-requests.'**'`: 3 steps (full-validation, backend-validation, web-e2e-validation)
- `pipelines.branches.main`: 3 steps (full-validation, backend-validation, web-e2e-validation)
- YAML parse: `python3 yaml.safe_load` → VALID; no syntax errors

---

## Pre-existing Failures — NOT ABS-434 Blockers

The enabler surfaced 5 pre-existing failures in `backend/apps/web/e2e/` — these are on ALREADY-MERGED code; the ABS-434 diff is YAML-only.

| Spec | Failures | Root Cause | Classification |
|---|---|---|---|
| `spawns.spec.ts` | 4 (DAC-14/15/16/17) | Non-UUID `spawn_id` (`i-1-T1-1`) posted to `seat_spawn.id` (`uuid PRIMARY KEY`) → Postgres 22P02 → HTTP 500 | Pre-existing test-data/contract mismatch — needs follow-up ticket |
| `board.spec.ts` | 1 (S9) | `release-toggle` checkbox `.check()` "did not change its state" — click does not toggle | Pre-existing UI product defect — needs follow-up ticket |

**Required follow-ups (PO/BSA, NOT this gate):**
1. `spawns` spawn_id UUID contract mismatch → file against epic ABS-410
2. Board S9 `release-toggle` UI defect → file against epic ABS-410

**Merge sequencing**: PO/RTE decision needed — (a) land infra now + track failures as known-issue, fix-forward; or (b) fix defects first, then the step goes green. This is a delivery call, not a QAS gate blocker.

---

## QA Checklist

- [x] Diff reviewed: YAML-only, +67 lines, `bitbucket-pipelines.yml`
- [x] `playwright.config.ts:21` localhost:55432 fallback confirmed and fix mechanism confirmed
- [x] YAML syntax valid (python3 `yaml.safe_load` clean)
- [x] Step wired into both PR (`**`) and `branches.main` pipelines
- [x] `includePaths` guard covers `backend/apps/web/**` and the pipeline file
- [x] `postgres` service reused from existing `backend-validation` step (pattern compliance)
- [x] `pg_isready` fail-loud wait present (no silent env-skip)
- [x] `DATABASE_URL` override exports before test:e2e
- [x] Migrations run before suite (AC3)
- [x] `filters.spec.ts` confirmed absent on this branch and main (AC2 external dep)
- [x] 5 surfaced failures classified as pre-existing, out-of-scope — not bounced

---

## Verdict

**✅ APPROVED**

All four ACs are met or satisfied by construction (AC2 external dependency). The implementation is a minimal, pattern-compliant YAML-only CI enabler. The 5 surfaced pre-existing failures are the infra working as designed (exposing previously env-skipped regressions) — they are NOT ABS-434 defects and do not block this gate.

**Next**: No `design` flag → transition to `Story Acceptance`.

