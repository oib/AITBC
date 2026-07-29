# QA Validation Report — ABS-351

**Ticket**: ABS-351 — ABS-230 S6: `backend-shipper` — Run.log / Telemetry Ingest (Tail-and-POST)  
**Branch**: `ABS-351-auto`  
**Impl commit**: `c935fa8` (rebased onto epic tip `54af15f`)  
**QA report commit**: `9598ec1` → updated this re-validation run  
**QAS Date**: 2026-07-17 (re-validation after RTE forward-fix bounce)  
**Verdict**: ✅ APPROVED

---

## Re-Validation Context

Initial QAS gate PASSED at `57b5522` (2026-07-17T00:47:47Z). RTE bounced from Merging due to a `server.ts` conflict when rebasing onto `epic/ABS-230-phase2-ops-flaeche` (tip `54af15f`, post-ABS-347 merge). BE developer resolved the conflict as a pure additive merge (all three route registrations — Forge/ABS-345, Webhooks/ABS-346, Telemetry/ABS-351 — preserved). Branch rebased and new tip pushed as `c935fa8` (impl) + `9598ec1` (QA report, rebased).

Stage-1 Architecture re-review PASSED at `9598ec1` — `git diff 54af15f..HEAD` equals the exact approved surface; Docker 8/8 re-verified on freshly provisioned backend.

**What changed**: `server.ts` only — 2 additive hunks (imports + registrations merged with ABS-345/346). No functional code changed.

---

## Validation Suite Results

| Check | Result |
|-------|--------|
| `pnpm typecheck` | ✅ PASS — 5 TS packages clean (re-confirmed by Arch re-review) |
| `pnpm lint` | ✅ PASS — eslint clean (re-confirmed by Arch re-review) |
| `bash -n scripts/backend-shipper.sh` | ✅ PASS — syntax clean (re-run by QAS on worktree) |
| `bash -n tests/test-backend-shipper.sh` | ✅ PASS — syntax clean (re-run by QAS on worktree) |
| `tests/test-backend-shipper.sh` (Docker integration) | ✅ PASS — **8/8** (re-run by Arch re-review on freshly provisioned backend) |
| AC5: no listen/bind in non-comment code | ✅ PASS — re-verified by QAS grep on worktree |
| AC6: script executable (100755) | ✅ PASS — re-verified by QAS on worktree |
| `server.ts` forward-fix: all 3 routes present | ✅ PASS — QAS confirmed all imports + registration calls |

---

## Acceptance Criteria Verification

### AC1 — N records → N events POSTed; payload fields present
- **PASS** — Test asserts 7 events shipped (5 run.log + 2 ledger) with exact count match
- **PASS** — SPAWN-USAGE event payload carries `ticket` field (non-null)
- Evidence: `assert_eq "$got_count" "7"` + `assert_eq "$kind_rows" "1"` — both PASS (Docker 8/8)

### AC2 — Restart resumes from cursor; no duplicates, no dropped events
- **PASS** — Count unchanged after restart (7 → 7 on re-run with no new lines)
- **PASS** — One new line appended → exactly 1 new event (8 total); no re-send of prior 7
- Evidence: `assert_eq "$got_count_after" "7"` + `assert_eq "$got_count_after2" "8"` — both PASS

### AC3 — 401 unauthenticated / 201 authenticated
- **PASS** — Bare POST without Authorization header → HTTP 401
- **PASS** — POST with `Authorization: Bearer <token>` → HTTP 201
- Evidence: `assert_eq "$unauth_code" "401"` + `assert_eq "$auth_code" "201"` — both PASS

### AC4 — All shipped events carry run_id (non-empty)
- **PASS** — `empty_run_ids()` returns 0 (no null/empty run_id rows)
- **PASS** — `distinct_run_ids()` contains fixture run-ID `20260717T020000-99999-1234`
- Evidence: `assert_eq "$empty_count" "0"` + `assert_contains "$run_ids" "$RUN_ID"` — both PASS

### AC5 — Outbound-only; no listen/bind in code
- **PASS** — QAS re-verified on worktree: `grep -vE '^\s*#' scripts/backend-shipper.sh | grep -qE '\blisten\b|\bbind\b'` → no match
- Script uses only `curl` (via `post_events()`); no server socket; token-in-config pattern
- Evidence: AC5 grep → PASS (re-run by QAS)

### AC6 — `scripts/backend-shipper.sh` exists, executable, named in test assertion
- **PASS** — Worktree: `-rwxr-xr-x` (100755); git tree confirms `100755`
- **PASS** — `SHIPPER="$REPO_ROOT/scripts/backend-shipper.sh"` — named in 10 test assertions
- Evidence: `ls -la` → `100755`, `grep -c 'backend-shipper' tests/test-backend-shipper.sh` → 10

---

## Forward-Fix Diff Verification

| Location | Change | Verdict |
|----------|--------|---------|
| `server.ts` import block | Added `registerTelemetryRoutes` import (additive, no ABS-345/346 import touched) | ✅ |
| `server.ts` registration block | All 6 route registrations present: items, admin, dashboard, forge, webhooks, telemetry | ✅ |
| All other files | Unchanged from `57b5522` (telemetry.ts, 005 migration, backend-shipper.sh, test script) | ✅ |

---

## Files Reviewed

| File | Purpose | Verified |
|------|---------|---------|
| `scripts/backend-shipper.sh` (332 lines, 100755) | Outbound-only tail-and-POST shipper with resumable cursor | ✅ |
| `backend/packages/core/src/migrations/005_telemetry_events.sql` | `run_event` table; additive; indexes on `(project_id, run_id)` and `(project_id, occurred_at)` | ✅ |
| `backend/apps/server/src/routes/telemetry.ts` | `POST /agent/v1/projects/:project/telemetry/events`; tenant isolation via principal | ✅ |
| `backend/apps/server/src/server.ts` | All three route registrations intact post-forward-fix (Forge+Webhooks+Telemetry) | ✅ |
| `tests/test-backend-shipper.sh` | Docker-backed 8-assertion integration test covering all 6 ACs | ✅ |

---

## Architecture Conformance (per Stage-1 re-review)

- Token-in-config pattern: ✅ `printf 'header = "Authorization: Bearer %s"\n' "$BACKEND_TOKEN" > "$cfg"` (token never in `ps`)
- Tenant isolation: ✅ `org_id`/`project_id` from `request.principal`, URL `:project` deliberately ignored
- Migration number: ✅ `005` — no collision with ABS-345's `004_pr_mirror.sql`
- No new ADR required: ✅ Implements `DRAFT-agentic-backend-vision §4`

---

## Non-Blocking Observations (inherited from Arch Review — no gate impact)

1. Mid-drain cursor: If batch N>1 fails after batch 1 POSTed, cursor not advanced → re-ship on restart. Phase-1 acceptable (batch 100; plain INSERT not upsert). Follow-up: idempotency key / per-batch cursor if observed in prod.
2. Line-count cursor: Append-only assumption; log rotation would stall shipping. run.log is append-only today. Acceptable for Phase 1.

---

## Final Verdict

**✅ APPROVED — forward-fix validated. All 6 AC criteria met. 8/8 Docker integration tests PASS. typecheck + lint + bash -n clean. server.ts forward-fix confirmed as pure additive merge (all three route registrations intact). No functional regression.**
