# QA Validation Report — PILOT-46

**Ticket**: PILOT-46 — Sandbox-Env-Leakage mechanisch verhindern  
**Branch**: PILOT-46-auto  
**HEAD commit**: c18e27a714ae1fdf1e0da019503c17bdeb6d653f  
**Validated by**: QAS  
**Date**: 2026-07-25  
**Verdict**: ✅ APPROVED

---

## Acceptance Criteria Validation

### AC1: Suite-Side Guard (`tests/sandbox-guard.sh` + CI check)

| Check | Result | Evidence |
|---|---|---|
| `tests/sandbox-guard.sh` exists and unsets 4 vars | ✅ PASS | File confirmed; unset logic verified |
| Escape hatch `ORCH_TEST_ALLOW_BACKEND=1` preserves env | ✅ PASS | test-sandbox-guard.sh 9/9 |
| Locally-assigned value after sourcing survives | ✅ PASS | test-sandbox-guard.sh 9/9 |
| `scripts/sandbox-guard-check.sh` CI check exists | ✅ PASS | File confirmed |
| CI check reports 35/35 entrypoints guarded | ✅ PASS | `bash scripts/sandbox-guard-check.sh` → `OK — all 35 backend/tracker entrypoints source the guard` |
| CI check wired into `pr-validation.yml` | ✅ PASS | Line 99 in `.github/workflows/pr-validation.yml` |
| Unit test suite: `test-sandbox-guard.sh` | ✅ **9/9 PASS** | Run output: `sandbox-guard: 9/9 passed, 0 failed` |

**Command run**: `bash tests/test-sandbox-guard.sh`  
**Commit verified at**: c18e27a7

```
== guard strips inherited backend/tracker env ==
  PASS all four vars unset by default
== escape hatch keeps env ==
  PASS ORCH_TEST_ALLOW_BACKEND=1 leaves BACKEND_URL intact
== locally-assigned value after sourcing survives ==
  PASS post-source local assignment survives
== CI check passes on the real repo ==
  PASS sandbox-guard-check exits 0 on repo
  PASS reports OK
== CI check FAILS a fixture that omits the guard ==
  PASS check fails when entrypoints omit the guard
  PASS flags run-all.sh
  PASS flags backend-touching test
== CI check passes once the fixture entrypoints source the guard ==
  PASS check passes once the guard is sourced

sandbox-guard: 9/9 passed, 0 failed
```

**`sandbox-guard-check` live run**:
```
sandbox-guard-check: OK — all 35 backend/tracker entrypoints source the guard.
```

---

### AC2: Backend Instance-ID Allowlist (403 on spawn + heartbeat)

| Check | Result | Evidence |
|---|---|---|
| `instanceIdRejection()` function in `routes/spawns.ts` | ✅ PASS | Verified in code; handles unset (open), valid regex (match/reject), bad regex (fail-open) |
| Both spawn POST + heartbeat POST check the allowlist | ✅ PASS | Lines 147–149, 95–97 in routes/spawns.ts |
| Default-open (no `ORCH_INSTANCE_ID_ALLOWLIST` → accept all) | ✅ PASS | `if (!raw) return null;` |
| Bad regex fails open (logs warn once) | ✅ PASS | try/catch with `warnedBadAllowlist` guard |
| Returns `{ error: "instance_not_allowed" }` on 403 | ✅ PASS | Code verified |
| TypeScript typecheck | ✅ PASS | `pnpm typecheck` → no errors |
| Integration tests (Postgres-backed) | ⚠️ SKIPPED (env) | `DATABASE_URL` not available in QAS session; tests skip cleanly with `{ skip: !BASE_URL }`. **Architect verified 11/11 vs real Postgres** (handoff 2026-07-25T20:48:20Z) |
| 3 PILOT-46 tests in spawns-routes.test.ts | SKIP (env) | `PILOT-46: allowlist unset → open`, `allowlist set → 403 spawn+heartbeat`, `unparseable → fail-open` |

**Classification**: Environment constraint — Postgres not available in QAS session. Test skip is expected (by design in test file). Architect ran these 11/11 against real Postgres. This is NOT a code failure per failure-classification rules.

---

### AC3: `scripts/backend-prune-instances.sh` (dry-run default + CSV backup)

| Check | Result | Evidence |
|---|---|---|
| Script exists with dry-run default | ✅ PASS | File confirmed; `APPLY=0` default |
| `--apply` flag required to actually delete | ✅ PASS | Logic verified in code |
| CSV backup written BEFORE any delete | ✅ PASS | `\copy` before DELETE |
| Pattern passed as bound psql variable (SQL-injection safe) | ✅ PASS | `-v pat="$PATTERN"` → `WHERE instance_id ~ :'pat'` |
| `--pattern` required arg (exit 2 if missing) | ✅ PASS | Validated in test |
| `--database-url` / `DATABASE_URL` required (exit 2 if missing) | ✅ PASS | Validated in test |
| Unit test suite: `test-backend-prune-instances.sh` | ✅ **15/15 PASS** | Run output: `backend-prune-instances: 15/15 passed, 0 failed` |

**Command run**: `bash tests/test-backend-prune-instances.sh`  
**Commit verified at**: c18e27a7

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

---

## Additional Checks

| Check | Result |
|---|---|
| No harness/mirror files touched (Rule 10 compliance) | ✅ PASS — `git diff` shows no `harness/` or `agent_providers/` files |
| Commits on correct branch (PILOT-46-auto) | ✅ PASS |
| SAFe commit format with ticket tag | ✅ PASS — all 3 commits follow `type(scope): desc [PILOT-46]` |
| shellcheck-clean scripts (per architect review) | ✅ PASS (architect verified) |
| ABS-66 data-flow clean (no cross-ticket data leaks) | ✅ PASS (architect verified) |
| Ticket `design` flag | Not set → exit to Story Acceptance |

---

## Commits Validated

| Commit | Description |
|---|---|
| `017b8384` | test(sandbox): source sandbox-guard in every backend/tracker test entrypoint + CI check [PILOT-46] |
| `6cfbbac2` | feat(spawns): reject seat_spawn/heartbeat writes outside instance-id allowlist [PILOT-46] |
| `c18e27a7` | feat(scripts): add backend-prune-instances.sh (dry-run default, CSV backup) [PILOT-46] |

---

## Summary

All three acceptance criteria are mechanically verified:

- **AC1** (suite-side guard): 9/9 unit tests PASS; 35/35 entrypoints sourcing the guard; CI check wired.
- **AC2** (backend allowlist 403): TypeScript typecheck clean; logic verified in code; integration tests skip-clean (Postgres env constraint, not a code failure; architect verified 11/11 vs real Postgres).
- **AC3** (prune tooling): 15/15 unit tests PASS; dry-run default confirmed; CSV backup before delete; SQL-injection safe.

**Verdict: APPROVED for Story Acceptance.**
