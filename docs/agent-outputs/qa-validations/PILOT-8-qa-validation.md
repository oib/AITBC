# QA Validation Report — PILOT-8

**Ticket**: PILOT-8 — v3-Parität: Linktyp `relates` end-to-end  
**Branch**: `PILOT-8-auto`  
**Implementation commit**: `f0c4b12e425e54d48fbb7886b9d02f63cc22aff1`  
**Validator**: QAS (resume — attempt 2)  
**Date**: 2026-07-22  
**Verdict**: ✅ APPROVED

---

## Personal Green-Run Evidence (ABS-453)

All test suites below were personally executed by QAS in this session against commit `f0c4b12e`.  
Sandbox Postgres: throwaway Docker container `pilot8-qas-1784726596`, ephemeral port 58762 (ABS-374 compliant), torn down after testing.

---

## Acceptance Criteria Verification

### AC#1 — `backend-tracker.sh link A B relates` → `get A` shows `relates:B`; idempotent replay says "already linked"

**Status**: ✅ PASS

**Evidence** — backend conformance suite (`bash tests/test-backend-tracker.sh`):
```
PASS  relates link recorded in links facet
PASS  relates is NOT mirrored into depends_on
PASS  replayed relates link is idempotent (already linked)
```
Counter: **194 passed, 0 failed**  
Commit: `f0c4b12e`

---

### AC#2 — Invalid types list `relates` in error message of all three adapters

**Status**: ✅ PASS

**Evidence** — negative CLI tests:
```
$ bash scripts/mock-tracker.sh link DEMO-1 DEMO-2 bogus-type
ERROR: link: invalid link type 'bogus-type' (parent-child|depends-on|origin-review|pr|relates)

$ bash scripts/jira-tracker.sh link JIRA-1 JIRA-2 bogus-type
ERROR: link: invalid link type 'bogus-type' (parent-child|depends-on|origin-review|pr|relates)
```

Backend (items.ts:563 — error propagated through backend-tracker.sh at runtime):
```
throw new OpError(400, `link: invalid link type '${ltype}' (parent-child|depends-on|origin-review|pr|relates)`)
```

Conformance suite includes `assert_nonzero_exit` for `friend-of` invalid type against the live server (194/194 passed).

---

### AC#3 — `mock-tracker.sh link A B relates` and `jira-tracker.sh link A B relates` work; conformance/golden case added in tests/test-backend-tracker.sh

**Status**: ✅ PASS

**Evidence**:
- `bash tests/test-mock-tracker.sh` → **184 passed, 0 failed** (includes 3 relates golden assertions)
- `bash tests/test-backend-tracker.sh` → **194 passed, 0 failed** (conformance golden cases)

Commands run against commit `f0c4b12e`.

---

### AC#4 — Export→Import roundtrip: `get A` shows `relates:B` unchanged

**Status**: ✅ PASS

**Evidence** — admin-routes test suite:
```
Command: DATABASE_URL=postgres://postgres:testpassword@localhost:58762/agentic \
         node --import tsx --test --test-concurrency=1 \
         apps/server/test/admin-routes.test.ts

✔ PILOT-8 relates link survives export → import into a wiped project (36.687459ms)
```
Counter: **18 passed, 0 failed** (items-routes + admin-routes combined)  
Commit: `f0c4b12e`  
Sandbox: ephemeral Docker Postgres on port 58762 (ABS-374 compliant)

---

### AC#5 — Migrations 001..014 byte-unchanged; new migration idempotent (second boot)

**Status**: ✅ PASS

**Evidence**:
- `git diff f0c4b12e~1 f0c4b12e -- backend/packages/core/src/migrations/ --name-only` → only `015_work_item_link_relates.sql` added; 001..014 untouched ✅
- Migrate test suite:
  ```
  Command: DATABASE_URL=... node --import tsx --test --test-concurrency=1 \
           packages/core/test/migrate.test.ts \
           packages/core/test/migrate-integrity.test.ts \
           packages/core/test/migrate-prefix-guard.test.ts

  ✔ second run is a no-op — idempotent (AC#1) (3.182041ms)
  ✔ work_item_link.kind CHECK admits `relates`, still rejects unknown kinds (PILOT-8) (5.734459ms)
  ```
  Counter: **17 passed, 0 failed**  
  Commit: `f0c4b12e`

---

### AC#6 — `backend/apps/server/test/items-routes.test.ts` covers `relates` including idempotency

**Status**: ✅ PASS

**Evidence**:
```
Command: DATABASE_URL=... node --import tsx --test --test-concurrency=1 \
         apps/server/test/items-routes.test.ts

✔ link kind `relates` — symmetric soft link, one-sided persist + idempotent (PILOT-8) (27.048666ms)
```
Test covers: POST link → 200; GET shows `links: [relates:DEMO-2]`; relates NOT mirrored to depends_on; one-sided (no auto-reverse); idempotent replay → "already linked"; unknown target → 404.  
Counter: **18 passed, 0 failed** (items-routes + admin-routes combined)  
Commit: `f0c4b12e`

---

## Test Suite Summary

| Suite | Command | Result | Commit |
|-------|---------|--------|--------|
| Mock tracker | `bash tests/test-mock-tracker.sh` | **184/184** ✅ | f0c4b12e |
| Backend conformance | `bash tests/test-backend-tracker.sh` | **194/194** ✅ | f0c4b12e |
| migrate + integrity + prefix-guard | `node --import tsx --test ...` | **17/17** ✅ | f0c4b12e |
| items-routes + admin-routes | `node --import tsx --test ...` | **18/18** ✅ | f0c4b12e |

**Total**: 413 assertions, 0 failures across all PILOT-8 test files.

---

## Additional Checks

- **ABS-374 compliance**: Throwaway sandbox on ephemeral port 58762 (project `pilot8-qas-1784726596`), torn down after testing ✅
- **ABS-288 guard**: Only migration 015 added; 001..014 byte-unchanged (verified via `git diff`) ✅
- **ADR-A-0021 wording**: All three adapters enumerate `relates` in their validation error message ✅
- **Symmetry / one-sided persist**: `relates` not mirrored into `depends_on`, not rendered on reverse side — spec-correct ✅
- **ABS-482 branch hygiene**: Committed on `PILOT-8-auto` only; only `docs/agent-outputs/**` staged ✅

---

## Verdict

**✅ APPROVED — All 6 ACs PASSED**

Ticket has `data` flag but no `design` flag → exit target: **Story Acceptance**.

*Validated by QAS resume (attempt 2) — prior attempt 1 produced identical test evidence but runner marked spawn non-zero (missing handoff comment); this attempt re-ran all suites personally and posts the gate-results comment.*
