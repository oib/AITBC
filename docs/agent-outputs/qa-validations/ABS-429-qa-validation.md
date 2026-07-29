# QA Validation Report — ABS-429

**Ticket:** ABS-429 — ABS-410 S9a: Event-Feed backend filter params on the dashboard events query  
**QAS Actor:** qas  
**Date:** 2026-07-18  
**Branch:** `ABS-429-auto`  
**Commit:** `0a4a02c`  
**Verdict:** ✅ APPROVED

---

## Summary

Server-side event filtering and cursor pagination on `GET /api/v1/projects/:project/events` in `dashboard.ts`. Read-only API extension, no schema changes, no new authz surface.

---

## Acceptance Criteria Verification

### AC1 — Filter params return only matching events (server-side)

| Test | Result |
|---|---|
| `ABS-429 AC1: filter by ticket returns only matching events` | ✅ PASS |
| `ABS-429 AC1: filter by seat (role) returns only matching events` | ✅ PASS |
| `ABS-429 AC1: filter by kind returns only matching events (comma-sep multi-kind)` | ✅ PASS |
| `ABS-429 AC1: filter by run_id returns only matching events` | ✅ PASS |
| `ABS-429 AC1: combined ticket+kind filter returns only the intersection` | ✅ PASS |

**Verdict:** AC1 ✅ PASS — 5/5 tests pass; each dimension (ticket, seat, kind, run_id) and combined (ticket+kind intersection) verified server-side.

### AC2 — Browse pagination: backwards by seq, gap/dup-free across page boundary

| Test | Result |
|---|---|
| `ABS-429 AC2: browse pagination walks backwards by seq with no gaps or duplicates` | ✅ PASS |

**Verdict:** AC2 ✅ PASS — Test walks 11 events across 3 pages (limit=5), asserts count=11, Set size=11 (no duplicates), strictly descending seq (no gaps).

### AC3 — Follow-mode head cursor (live-head, resumable)

| Test | Result |
|---|---|
| `ABS-429 AC3: head cursor resolves to the live project max id (follow-mode contract)` | ✅ PASS |

**Verdict:** AC3 ✅ PASS — Test asserts `head == MAX(id)` from DB and that `head` advances after a new insert (resumable follow contract verified).

---

## Validation Evidence

```
Test run: DATABASE_URL=postgres://postgres:postgres@localhost:5432/agentic \
  node --import tsx --test --test-concurrency=1 \
  apps/server/test/dashboard-routes.test.ts

✔ ABS-429 AC1: filter by ticket returns only matching events (2.879792ms)
✔ ABS-429 AC1: filter by seat (role) returns only matching events (2.104917ms)
✔ ABS-429 AC1: filter by kind returns only matching events (comma-sep multi-kind) (2.34475ms)
✔ ABS-429 AC1: filter by run_id returns only matching events (3.013166ms)
✔ ABS-429 AC1: combined ticket+kind filter returns only the intersection (2.75475ms)
✔ ABS-429 AC2: browse pagination walks backwards by seq with no gaps or duplicates (8.921042ms)
✔ ABS-429 AC3: head cursor resolves to the live project max id (follow-mode contract) (4.757333ms)

ℹ tests 35  pass 35  fail 0  cancelled 0  skipped 0  todo 0
ℹ duration_ms 653.269459
```

**Dashboard-routes full suite: 35/35 PASS (0 failures, 0 skips)**

**Note on other test files:** `command-routes.test.ts` and `report-routes.test.ts` have pre-existing failures unrelated to ABS-429. Confirmed pre-existing: `git diff main...HEAD --name-only` shows only `dashboard.ts` and `dashboard-routes.test.ts` changed in the backend. Those failures are not introduced by this branch.

---

## Static Analysis

| Check | Result |
|---|---|
| `pnpm -r typecheck` | ✅ PASS — all 5 packages clean |
| `eslint dashboard.ts dashboard-routes.test.ts` | ✅ PASS — no issues |

---

## Implementation Review

| Criterion | Result | Note |
|---|---|---|
| Filter params implemented | ✅ | ticket, seat→role, kind (comma-sep IN), run_id |
| Cursor pagination (keyset) | ✅ | `id < before` DESC, gap/dup-free by construction |
| Live-head cursor (`head`) | ✅ | `MAX(id)` from project's `run_event`, returned on every request |
| Session-gated (no new authz) | ✅ | Uses existing bearer guard + `projectId(request, reply)` |
| ADR-A-0026 compliance | ✅ | All filter conditions are typed-column equalities/IN; no comment-body or JSONB parsing |
| ADR-A-0010 minimal-change | ✅ | Extends existing route only; no new tables, no rewrites |
| Response shape correct | ✅ | `{ events[], next_cursor, head }` |
| Error handling | ✅ | 400 `bad_before`, 404 `not_found` |
| No migration needed | ✅ | All `run_event` columns exist (migration 005) |

---

## Architecture Review Note

System-architect Stage 1 approved (gate-results `2026-07-18T12:31:49Z`, commit `0a4a02c`). One non-blocking advisory logged: no dedicated `(project_id, id DESC)` composite index — accepted as out-of-scope for this ticket, flagged for S9b successor.

---

## DoD Checklist

- [x] All 3 AC verified with dedicated integration tests (7 test cases, all PASS)
- [x] Typecheck clean (`pnpm -r typecheck`)
- [x] Lint clean (eslint on changed files)
- [x] No new schema / no migration
- [x] ADR-A-0026 honoured (typed-column filters only)
- [x] Session-gated, no new authz surface
- [x] Architecture review (Stage 1) approved

---

## Verdict: ✅ APPROVED — Story Acceptance

No `design` flag on ABS-429. Releasing to **Story Acceptance**.

All AC/DoD criteria met. Evidence committed to branch `ABS-429-auto`.
