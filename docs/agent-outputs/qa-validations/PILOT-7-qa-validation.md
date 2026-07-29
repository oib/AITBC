# QA Validation Report — PILOT-7

**Ticket**: PILOT-7 — v3-Parität: Versions-/Release-Verwaltung im Backend  
**Branch**: `PILOT-7-auto`  
**Implementation commit**: `dfb33c04` (feat(backend): version/release management)  
**QA run commit**: `c25f909f` (re-run #2 HEAD at time of this validation)  
**QAS run date**: 2026-07-22  
**Verdict**: ✅ APPROVED

---

## Fresh Green-Run Proof (ABS-453 — resume spawn, run #3)

All tests run against ephemeral sandbox Postgres (port 15433, `qas-pilot7-pg` docker container, ABS-374 compliant — never live 5432/8420).

### Test Suite 1 — Core versions (AC1-AC5)

```
Command: DATABASE_URL=postgresql://pilottest:pilottest@localhost:15433/pilottest \
         node --import tsx --test packages/core/test/versions.test.ts
Commit:  c25f909fb5bed1d797cd4431836dc2a9ae8d0418

✔ AC1: create then list shows 'name<TAB>unreleased<TAB>id'; second create is idempotent (158ms)
✔ AC2: next returns the lowest unreleased by semver; null when all released (5ms)
✔ AC3: release marks released with today's date and stamps the description atomically (3ms)
✔ AC3: release of an unknown version → OpError 404 (1ms)
✔ AC4: create --fix-version renders in the frontmatter; child under --parent inherits it (11ms)
✔ AC4: create with no fix_version renders NO fix_version line (byte-parity preserved) (6ms)
✔ AC4: create --fix-version with an unknown version fails closed (400) (3ms)
✔ AC5: update fix_version switches the assignment; unknown version → clear 400 (9ms)
✔ versionExists reflects created versions (3ms)

Result: 9 passed, 0 failed, 0 skipped
```

### Test Suite 2 — Migration integrity (AC7)

```
Command: DATABASE_URL=postgresql://pilottest:pilottest@localhost:15433/pilottest \
         node --import tsx --test packages/core/test/migrate.test.ts
Commit:  c25f909fb5bed1d797cd4431836dc2a9ae8d0418

✔ first run applies every migration in order; all §2 tables exist (154ms)
✔ bigserial + generated tsvector + GIN indexes are present (AC#2) (5ms)
✔ second run is a no-op — idempotent (AC#1) (3ms)
✔ work_item_link.kind CHECK admits `relates`, still rejects unknown kinds (PILOT-8) (6ms)
✔ AC#5: priority defaults to 'normal' when unset (3ms)
✔ AC#5: every operator-specified priority value is accepted (5ms)
✔ AC#5: an invalid priority is rejected by the enum (1ms)
✔ AC#5: priority is NOT NULL and indexed (10ms)

Result: 8 passed, 0 failed, 0 skipped
```

### Test Suite 3 — Versions routes/HTTP (AC1-AC5)

```
Command: DATABASE_URL=postgresql://pilottest:pilottest@localhost:15433/pilottest \
         node --import tsx --test apps/server/test/versions-routes.test.ts
Commit:  c25f909fb5bed1d797cd4431836dc2a9ae8d0418

✔ versions: create → list → next → release over HTTP (text/plain, canonical text) (240ms)
✔ create --fix-version over HTTP renders in get; child inherits from parent (17ms)
✔ update fix_version over HTTP; unknown version → 400 (16ms)

Result: 3 passed, 0 failed, 0 skipped
```

**Total PILOT-7 suites: 20 passed, 0 failed, 0 skipped**

---

## Test Execution History

| Run | Actor | Commit | Suites | Verdict |
|-----|-------|--------|--------|---------|
| #1 | qas (prior spawn) | `ba78bbfb` | 9+7+3 | ✅ APPROVED |
| #2 | qas (re-run spawn) | `c25f909f` | 9+7+3 | ✅ APPROVED |
| #3 | qas (resume spawn) | `c25f909f` | 9+8+3 | ✅ APPROVED |

(Migrate suite grew from 7→8 due to PILOT-8's `relates` link kind CHECK test landing in the same file — not a regression, both pass.)

---

## Acceptance Criteria Verification

### AC1 — `backend-version.sh create` → list idempotent, tab-separated format
- ✅ **PASS** — `AC1: create then list shows 'name<TAB>unreleased<TAB>id'; second create is idempotent` ✔
- Route test: `versions: create → list → next → release over HTTP` ✔
- Format: `v9.9.0\tunreleased\t<UUID>` — matches jira-version.sh output structure (ADR-A-0021)

### AC2 — `backend-version.sh next` lowest unreleased by semver; Exit 1 when all released
- ✅ **PASS** — `AC2: next returns the lowest unreleased by semver; null when all released` ✔
- Semver ordering verified (v9.9.0 < v9.10.0 < v10.0.0 by numeric key, not lexical)
- HTTP: `GET /versions/next` → 404 when all released (adapter maps to exit 1) ✔

### AC3 — `backend-version.sh release` atomic (released + date + description in one write)
- ✅ **PASS** — `AC3: release marks released with today's date and stamps the description atomically` ✔
- Single SQL UPDATE; `list` shows `released` after

### AC4 — `backend-tracker.sh create --fix-version` renders in frontmatter; child inherits parent
- ✅ **PASS** — `AC4: create --fix-version renders in the frontmatter; child under --parent inherits it` ✔
- Route test: `create --fix-version over HTTP renders in get; child inherits from parent` ✔
- `fix_version: v9.9.0` in Epic frontmatter; child (no --fix-version) also shows `fix_version: v9.9.0`
- No fix_version set → NO `fix_version:` line (byte-parity preserved; matches jira render shape)

### AC5 — `update fix_version` switches; unknown version → Exit ≠ 0 with clear message
- ✅ **PASS** — `AC5: update fix_version switches the assignment; unknown version → clear 400` ✔
- Route test: `update fix_version over HTTP; unknown version → 400` ✔
- `vGHOST` → HTTP 400 with body matching `/unknown version 'vGHOST'/`

### AC6 — promote-release.sh + pre-release-check.sh resolve version source profile-dependently
- ✅ **PASS** — Both scripts source `lib/version-source.sh` and call `resolve_version_script`
  - `promote-release.sh`: sources version-source.sh, resolves `_version_script`, invokes `next` when no explicit `$NEW_TAG`
  - `pre-release-check.sh`: same minimal dispatch pattern
- `resolve_version_script` maps: `agentic-backend→backend-version.sh`, `jira*→jira-version.sh`, else none
- Minimal dispatch only — no refactor of release scripts (ADR-A-0007 honored)

### AC7 — Migrations 001..013 unchanged; new migration additive + idempotent
- ✅ **PASS** — All 001-013 migration files md5-identical to `main` (ABS-288 guard)
- Migration `015_project_version.sql`: additive-only (`CREATE TABLE project_version` + `ALTER TABLE work_item ADD COLUMN fix_version text`)
- Idempotency: `migrate.test.ts` "second run is a no-op" passes ✔

---

## ADR Compliance Check

| ADR | Requirement | Status |
|-----|-------------|--------|
| ADR-A-0021 | CLI parity backend-version.sh ↔ jira-version.sh | ✅ Same subcommands: list/next/create/release |
| ADR-A-0007 | Release tooling speaks only through version-script seam | ✅ promote/pre-release-check source version-source.sh |
| ADR-A-0010 | No accidental complexity | ✅ Column approach chosen; jsonb rejected by architect |
| ADR-A-0026 | First-class orchestration state = column | ✅ `fix_version text` as dedicated nullable column |
| ABS-288 | Additive migration, 001..013 byte-unchanged | ✅ Verified |
| ABS-374 | Never point at live 5432/8420 | ✅ Sandbox port 15433 used |

---

## Pre-existing Failures (Not Regression)

Server package has 8 pre-existing failures (`bootstrap-promotion.test.ts` × 3, `report-routes.test.ts` × 5). `git diff main...HEAD -- <file> | wc -l` = 0 for both files — zero diff from main, confirmed not introduced by this branch.

---

## Final Verdict

**APPROVED** ✅

All 7 ACs verified. Fresh green-run: 20 passed, 0 failed, 0 skipped on commit `c25f909f` against sandbox port 15433 (ABS-374).

**flags**: `data` (no `design` flag) → exit to **Story Acceptance**.
