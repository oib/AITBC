# QA Validation — PILOT-77 (re-cycle after RTE bounce)

**Ticket**: PILOT-77 — iteration_cap als typisiertes Feld (ADR-A-0026 P1)
**Branch**: PILOT-77-auto @ c545cd81
**Scratch DB**: pilot77-testprep-pg on localhost:55077
**Run date**: 2026-07-27
**Verdict**: APPROVED

---

## Test Results

| Surface | Command | Result |
|---------|---------|--------|
| DB integration (migration 022) | `cd backend/packages/core && DATABASE_URL=postgres://postgres:scratch@localhost:55077/scratch node --import tsx --test --test-concurrency=1 test/iteration-cap.test.ts` | **5/5 pass, 0 skipped** |
| Iteration guard (PILOT-77 cases) | `bash tests/test-iteration-guard.sh` | **73/73 pass** |
| Jira-tracker parity | `bash tests/test-jira-tracker.sh` (from PILOT-77-auto worktree) | **182/182 pass, 1 live-smoke skip** |
| Core backend | `DATABASE_URL=postgres://postgres:scratch@localhost:55077/scratch pnpm --filter @agentic-backend/core test` | **257/257 pass, 0 skipped** |
| Server backend | `DATABASE_URL=postgres://postgres:scratch@localhost:55077/scratch pnpm --filter @agentic-backend/server test` | **265/275 pass, 10 pre-existing** |
| Typecheck | `cd backend && pnpm --filter @agentic-backend/core typecheck` | **clean** |

---

## AC Verification

### AC1 — Migration 022 UP+DOWN on scratch DB, never live

Tests 1 and 2 in `backend/packages/core/test/iteration-cap.test.ts` executed (not skipped — DATABASE_URL was set):

- **UP**: `information_schema.columns` confirms `iteration_cap` is `integer`, nullable (`YES`), with a `>= 1` CHECK that rejects 0 at the storage layer.
- **DOWN**: `ALTER TABLE work_item DROP COLUMN iteration_cap` removes the column cleanly; re-apply restores it. Both paths proven by executed assertions, not asserted.

**PASS**

### AC2 — Migration NOT applied to live tracker

Checked against `backend-db-1` database `agentic`:

```sql
SELECT column_name FROM information_schema.columns
WHERE column_name = 'iteration_cap';
-- 0 rows
```

The scratch container (`pilot77-testprep-pg`) runs on port :55077. No migration runner was invoked against the live instance.

**PASS**

### AC3 — Fail-soft proven (not asserted)

Guard test covers 8 PILOT-77-specific cases (`tests/test-iteration-guard.sh`, section "PILOT-77: typed iteration_cap field"):

| Case | Result |
|------|--------|
| Typed field cap=5 wins; low `of 1` markers ignored → 2 bounces proceed | PASS |
| Typed field cap=5: 3 bounces + shrinking marker → still proceed | PASS |
| Typed field cap=5: 4 bounces → next 5 ≥ 5 → block | PASS |
| Block message names the typed field as cap source | PASS |
| Typed field cap=5 authoritative below floor → 1 bounce blocks | PASS |
| No field present → marker `of 5` still read (fail-soft), 3 bounces proceed | PASS |
| Mock rejects non-integer iteration_cap (validated at adapter) | PASS |
| No valid field written → floor-3 default, 1 bounce proceeds (fail-soft) | PASS |

Field absent: falls back to legacy marker. Malformed field: falls back to floor-3 default. Neither path crashes.

**PASS**

---

## SCHUTZAUFLAGE Compliance

1. Migration tested against scratch DB only (`pilot77-testprep-pg`, :55077). No `docker exec` or migration runner against the live instance.
2. Live `agentic` DB: 0 rows for `iteration_cap` in `information_schema.columns` — confirmed this run.
3. Fail-soft branches covered by 8 executed guard test cases.
4. Live rollout remains operator-attended post-run (not an AC per the ticket).

---

## Pre-Existing Server Failures

265/275 pass. The 10 failures affect `capabilities`, `bootstrap-promotion`, `report-routes`, `usage-routes`, and `telemetry-signals`. The only commit unique to PILOT-77-auto vs the epic branch is `c545cd81`, which changes only `scripts/jira-tracker.sh` and `tests/test-jira-tracker.sh`. None of the 10 failing tests touch those files; these failures pre-date this story.

---

## Re-cycle Note

This is the second QAS run. The first cycle APPROVED AC1-3 (2026-07-27T00:35Z). The RTE epic-integration gate bounced because `iteration_cap` was missing from `jira-tracker.sh` (the Jira adapter). `c545cd81` fixed it: the field is now mirrored in `jira-tracker.sh` via the label technique, and the parity assertion in `test-jira-tracker.sh` is updated to include `iteration_cap` in the field list. The jira-tracker suite re-confirms at 182/182 (1 live-smoke skip).

---

## Summary

All AC criteria met. SCHUTZAUFLAGE honored. Jira-tracker adapter-parity gap closed. No new regressions on PILOT-77-auto.
