# QA Validation Report — ABS-428

**Ticket**: ABS-428 — Migrations-Präfix-Guard: doppelte Nummernvergabe zwischen parallelen Epics verhindern  
**Branch**: `ABS-428-auto`  
**Commit**: `80a08a6`  
**QAS run date**: 2026-07-18  
**Verdict**: ✅ APPROVED

---

## Files Under Review

| File | Change |
|------|--------|
| `backend/packages/core/src/migrate.ts` | +40 lines — `migrationPrefix()`, `findDuplicateMigrationPrefixes()`, `GRANDFATHERED_DUPLICATE_PREFIXES` |
| `backend/packages/core/test/migrate-prefix-guard.test.ts` | +50 lines — 4 pure-fs guard tests (no DB) |
| `backend/README.md` | +18 lines — "Adding a migration — numbering convention (ABS-428)" section |

---

## Acceptance Criteria Verification

### AC 1 — Guard fails when two migration files share a numeric prefix

- **Implementation**: `findDuplicateMigrationPrefixes(files: string[]): string[]` exported from `migrate.ts`; scans `.sql` files for duplicate numeric prefixes, returns the offending prefix list (empty = clean).
- **Test**: `"simulated collision goes RED (guard detects a new duplicate)"` — inputs `["001_a.sql", "010_first.sql", "010_second.sql", "011_c.sql"]`, asserts result equals `["010"]`. **PASS ✅**
- **Test auto-collected**: `package.json` test script globs `test/**/*.test.ts` — the new file is included in `pnpm test` automatically. Verified by seeing it run in the live output.
- **Real-series test**: `"real migration series carries no ungrandfathered duplicate prefix"` — reads the actual `migrations/` directory, asserts `[]`. **PASS ✅**

**AC 1: PASSED ✅**

### AC 2 — Convention documented for parallel-branch numbering in Migration-Workflow-Doku

- **Location**: `backend/README.md` — "Adding a migration — numbering convention (ABS-428)" section.
- **Content covers**:
  - Reserve next-free number on `main` (not local branch)
  - Rebase-on-collision: second-merger renumbers
  - Never renumber an already-merged migration (ABS-288 integrity guard reason)
  - Reference to the guard function `findDuplicateMigrationPrefixes`
- **Anchor phrase**: "fails closed on every `pnpm test` including CI without a database"

**AC 2: PASSED ✅**

### AC 3 — Existing 001-009 series untouched; simulated-collision test red

- **Migration files verified** (no modification in commit `80a08a6`):
  ```
  001_init.sql
  002_work_item_priority.sql
  003_orchestration_and_link_facets.sql
  004_pr_mirror.sql          ← pre-existing grandfathered duplicate
  004_seat_spawns.sql        ← pre-existing grandfathered duplicate
  005_telemetry_events.sql
  006_command_queue.sql
  007_dashboard_session_store.sql
  008_pr_mirror_base_sha.sql
  009_knowledge_adr_policy.sql
  ```
  All byte-for-byte untouched (pure additions in commit, no existing-file modification).
- **Grandfathered `004` pair**: `GRANDFATHERED_DUPLICATE_PREFIXES = new Set(["004"])` — the `004` pair passes (`grandfathered 004 pair does not trip the guard` test **PASS ✅**).
- **Simulated collision red**: `010` pair input → `["010"]` (non-empty = guard fires). **PASS ✅**

**AC 3: PASSED ✅**

---

## Test Suite Results (independently re-run)

```
pnpm test  (backend/packages/core)

tests 200  |  pass 119  |  fail 0  |  skipped 81  |  duration ~2944ms

Guard tests (all 4):
  ✔ real migration series carries no ungrandfathered duplicate prefix
  ✔ simulated collision goes RED (guard detects a new duplicate)
  ✔ grandfathered 004 pair does not trip the guard
  ✔ non-.sql and unnumbered files are ignored
```

Skipped = DB-dependent tests; no DB available in QAS environment. This is expected and matches the stated "119 pass / 81 DB-skipped / 0 fail" evidence from the implementer.

---

## Quality Checks

| Check | Result |
|-------|--------|
| `tsc --noEmit` | ✅ PASS (exit 0) |
| `eslint src/migrate.ts test/migrate-prefix-guard.test.ts` | ✅ PASS (exit 0) |
| `pnpm test` (full core suite) | ✅ 119 pass / 0 fail |
| 4 guard tests pass | ✅ |
| No regressions in existing tests | ✅ |

---

## Architecture Review Concurrence

System-architect Stage 1 review **APPROVED** (comment 2026-07-18T11:18:31Z):
- Pure fs/array guard (no RLS/auth surface)
- Test wired into `pnpm test` glob (not aspirational)
- ABS-66 data-flow verified
- No `any` types; TSC clean
- Non-blocking note: grandfather set keys on prefix, not file pair (hypothetical 3rd `004` would also be exempt — acceptable, series max is `009`, convention forbids reusing `004`)

---

## Design Flag Check

Ticket has **no `design` flag** → exit transition: `Story Acceptance`.

---

## Verdict

**APPROVED ✅ — All ACs PASSED. Releasing to Story Acceptance.**
