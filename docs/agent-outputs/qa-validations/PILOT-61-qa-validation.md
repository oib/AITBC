# QA Validation — PILOT-61

**Ticket**: PILOT-61 — main ist rot: test-backend-prune-instances 4/15  
**Commit validated**: `d0be228d` on branch `PILOT-61-auto`  
**Base commit**: `cc1ea37e`  
**Changed files**: `scripts/backend-prune-instances.sh`, `tests/test-backend-prune-instances.sh`  
**QAS run date**: 2026-07-26  
**Verdict**: **APPROVED**

---

## AC1 — Suite is green (15/15) on main

**Command run**: `bash tests/test-backend-prune-instances.sh`  
**Result**: 15/15 passed, 0 failed

```
== AC3: dry-run default ==
  PASS dry-run exits 0
  PASS reports match count from psql
  PASS announces dry-run
  PASS issued a count query
  PASS wrote a CSV backup
  PASS pattern passed as bound psql variable
  PASS dry-run issues NO DELETE
  PASS CSV backup file created
== AC3: --apply deletes ==
  PASS --apply exits 0
  PASS backup written before delete
  PASS --apply issues DELETE
  PASS reports deleted count
== AC3: setup errors ==
  PASS missing --pattern → exit 2
  PASS explains missing pattern
  PASS missing database URL → exit 2

backend-prune-instances: 15/15 passed, 0 failed
```

**PASS** ✅

---

## AC2 — Root causes named

Two independent root causes, both confirmed in code comments and verified empirically:

**Root cause 1 (test)**: `tests/test-backend-prune-instances.sh` called `mktemp -d "$REPO_ROOT/work/scratch/prune-test-XXXXXX"` but `work/scratch/` is gitignored and does not exist on a clean checkout. The `mktemp` call fails silently, leaving `$WORK` empty, which cascades into `"backup dir does not exist"` (exit 2) on every test case — 11 spurious failures. Fix at line 41: `mkdir -p "$REPO_ROOT/work/scratch"` before `mktemp`.

**Root cause 2 (tool)**: `scripts/backend-prune-instances.sh` used `psql -c "… :'pat' …"`. psql only interpolates `:'var'` bound variables for SQL read from stdin or `-f`; with `-c`, the string reaches the server verbatim, and Postgres returns `ERROR: syntax error at or near ":"`. This means the prune tool never worked against a real database. Fix: all three SQL queries (count, COPY backup, DELETE) are now fed via stdin (`printf '…\n' | "$PSQL" …`).

Both documented in code comments at lines 63-70 of `scripts/backend-prune-instances.sh`.

**PASS** ✅

---

## AC3 — Suite prints actual tool output on failure

`bad()` signature changed to accept an optional 2nd arg (the actual haystack). On failure it pipes that arg through `sed 's/^/         actual| /'` before printing.

Verified with a controlled failure:

```
  FAIL AC3-diagnostic-test (missing: EXPECTED_STRING_NOT_PRESENT)
         actual| backend-prune-instances: unknown argument: --bad-flag
```

A failure no longer just prints `missing: <string>` — it shows what the tool actually emitted.

**PASS** ✅

---

## AC4 — E2E against throwaway database (not prod)

Throwaway container: `pilot61-qas-pg-44550` (postgres:16-alpine, port 15461). Container stopped and removed after the run.

**Setup**: Created `seat_spawn` table, seeded 5 rows:
- r1: `devops01.local-12345-abc` ← matching
- r2: `devops01.local-67890-def` ← matching
- r3: `devops01.local-99999-ghi` ← matching
- r4: `prod-instance-42`         ← non-matching
- r5: `staging-instance-99`      ← non-matching

**Dry-run** (`--pattern '^devops01\.local-'`, no `--apply`):
```
backend-prune-instances: 3 row(s) match instance_id ~ ^devops01\.local-
backend-prune-instances: CSV backup written to …/seat_spawn-prune-20260726T183250Z.csv
backend-prune-instances: DRY-RUN — no rows deleted. Re-run with --apply to delete.
```
CSV backup held exactly 3 rows (r1, r2, r3). Table still had 5 rows after dry-run. ✅

**`--apply`**:
```
backend-prune-instances: 3 row(s) match instance_id ~ ^devops01\.local-
backend-prune-instances: CSV backup written to …/seat_spawn-prune-20260726T183256Z.csv
backend-prune-instances: DELETED 3 row(s) matching ^devops01\.local- (backup: …)
```
Rows remaining after delete: r4 (`prod-instance-42`) and r5 (`staging-instance-99`) only. Matching row count: 0. ✅

Pattern matched exactly 3, CSV backup created, dry-run deleted nothing, `--apply` deleted exactly 3 and preserved the 2 non-matching rows.

**PASS** ✅

---

## Additional checks

- **shellcheck**: `shellcheck scripts/backend-prune-instances.sh tests/test-backend-prune-instances.sh` → clean (0 warnings)
- **Branch hygiene**: commit `d0be228d` is on `PILOT-61-auto`, not on main
- **SQL injection safety**: pattern travels as `-v pat="$PATTERN"` (bound psql variable, never string-concatenated into SQL)
- **Backup-before-delete safety**: `ON_ERROR_STOP=1` on the COPY step + `set -euo pipefail` means a failed backup aborts before any DELETE reaches the server
- **No design flag** on this ticket → exit target is `Story Acceptance`

---

## Summary

| AC | Criterion | Result |
|----|-----------|--------|
| AC1 | 15/15 assertions green | ✅ PASS |
| AC2 | Root cause named (test + tool) | ✅ PASS |
| AC3 | Suite prints actual output on failure | ✅ PASS |
| AC4 | E2E against throwaway DB: 3 matched/backed up/deleted, 2 preserved | ✅ PASS |

**Verdict: APPROVED** — all ACs met, evidence gathered independently.
