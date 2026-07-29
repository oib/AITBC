# QA Validation Report — ABS-476 (QAS Gate)

**Ticket**: ABS-476 — Runner consume path for abort-spawn: terminate seat, emit abort event
**Branch**: `ABS-476-auto`
**Commit**: `0ac17c3f36d9b9d28a8c9d5ead2b23f9ffc49cb2`
**Date**: 2026-07-19
**Actor**: qas
**Verdict**: ✅ **APPROVED — All AC met, green-run confirmed**

---

## Green-Run Proof (ABS-453 obligation)

This ticket adds `backend/packages/core/test/command-abort.test.ts` — a new test file.
Per ABS-453, a verbatim green-run of the changed test file is mandatory.

**Command run:**
```
DATABASE_URL="postgresql://postgres:abs476@localhost:55476/postgres" \
  pnpm --filter @agentic-backend/core test
```
Postgres: sandboxed throwaway container `abs476-pg` on host port `55476` (`postgres:16-alpine`).

**Commit hash:** `0ac17c3f36d9b9d28a8c9d5ead2b23f9ffc49cb2`

**Abort test results (4/4 GREEN):**
```
✔ AC1: executed abort-spawn closes the seat and emits a seat-aborted event (142.251833ms)
✔ AC2: aborting an already-completed seat receipts a no-op without error (7.455292ms)
✔ redelivered receipt does not re-close the seat or emit a second event (8.159833ms)
✔ failed abort-spawn receipt leaves the seat open (no close, no event) (5.856125ms)
```

**Full core suite counter:**
```
ℹ tests 229
ℹ pass  228
ℹ fail    1    ← pre-existing 011 duplicate-prefix guard (ABS-480; no migration added here)
ℹ skipped 0
```

The single failure is `real migration series carries no ungrandfathered duplicate prefix` — this
collision (`011_command_reason_length.sql` vs `011_seat_spawn_id_text.sql`) was introduced by
ABS-445/ABS-447 (commits `c0b92b31` / `a6f27767`), which predate ABS-476. ABS-476 adds no
migration files (verified via `git show 0ac17c3f --stat`). Tracked in ABS-480.

---

## Gate Suite

| Check | Command | Result |
|---|---|---|
| TypeScript typecheck | `pnpm -r typecheck` (5 projects) | ✅ PASS — all clean |
| ESLint | `pnpm lint` | ✅ PASS — exit 0, no findings |
| Core integration test suite | `pnpm --filter @agentic-backend/core test` | ✅ 228/229 (1 pre-existing ABS-480 failure) |
| **Abort tests specifically** | `command-abort.test.ts` | ✅ **4/4 GREEN** |
| Shipper shell tests | `bash tests/test-shipper-commands.sh` | ✅ **42/42 PASS** |

---

## Acceptance Criteria Verification

### AC1 — enqueued abort-spawn → delivered → receipted executed → abort event → completed_at set ✅

**Test**: `AC1: executed abort-spawn closes the seat and emits a seat-aborted event` — GREEN (142ms)

**Code path verified** (`backend/packages/core/src/commands.ts`):
- `recordReceipt` performs the terminal receipt move (UPDATE `state=executed`)
- On success: appends the receipt event, then calls `closeAbortedSeat` if `state==="executed"
  && cmd.kind==="abort-spawn" && cmd.ledger_id`
- `closeAbortedSeat` UPDATE sets `completed_at=now()`, `exit_code=143`,
  `diagnostic="aborted by operator (command …)"` WHERE `completed_at IS NULL`
- If the UPDATE returns a row: INSERT into `event` with `kind='seat-aborted'`, carrying
  `spawn_id`, `command_id`, `run_id`, `instance_id`, `ticket_id`, `role`, `attempt`
- All inside the receipt transaction → receipt + closeout settle atomically

Test confirms: command state=`executed`; `seat_spawn.completed_at` is set; `exit_code=143`;
`diagnostic` matches `/aborted by operator/`; exactly one `seat-aborted` event carrying
the correct `spawn_id`, `command_id`, `ticket_id`.

### AC2 — aborting an already-completed seat receipts a no-op without error ✅

**Test**: `AC2: aborting an already-completed seat receipts a no-op without error` — GREEN (7ms)

**Code path verified**: `closeAbortedSeat` UPDATE has `WHERE completed_at IS NULL` — if the
seat is already completed, the UPDATE returns 0 rows; the function returns early (`if (!seat) return`).
No second event, no throw. Receipt still returns and settles `executed`.

Supporting guards tested:
- Redelivered (already-settled) receipt: `settled=false`, no re-close, no second event ✅
- `failed` receipt: seat stays open (`completed_at IS NULL`), no `seat-aborted` event ✅

### AC3 — live smoke against a real run, documented ✅

**Implementation-authored smoke doc**: `docs/agent-outputs/qa-validations/ABS-476-qa-validation.md`
(committed in `0ac17c3f`) documents:
1. Real Postgres closeout: `enqueue→poll→receipt` on real `seat_spawn` row (AC1/AC2 integration tests, 4/4)
2. Real `backend-shipper.sh` process kill: process tree (wrapper + forked `sleep` child).
   Observed `parent=ALIVE child=ALIVE` → `after: parent=DEAD child=DEAD`. Confirms child-first
   reap (`pkill -P`) closes the 2026-07-19 stale-lock/orphaned-lock-dir finding.

QAS independently validated AC1/AC2 against real Postgres (see Green-Run Proof above).

**Noted correctly in smoke doc**: Full UI→abort→board round trip is ABS-461 operator territory;
the mechanical backend path proven here is its foundation.

---

## Implementation Quality Notes (QAS spot-check)

- **Transaction boundary**: `closeAbortedSeat` runs inside the `recordReceipt` transaction.
  If the seat UPDATE or event INSERT fails, the whole receipt rolls back — no partial state.
- **COMMAND_COLUMNS** confirmed to include `ledger_id` and `kind` (line 73), so `cmd.kind` /
  `cmd.ledger_id` are typed through `CommandRow`; TypeScript confirms PASS.
- **No migration added**: confirmed via `git show 0ac17c3f --stat` — only `commands.ts`,
  `command-abort.test.ts`, `ABS-476-qa-validation.md`, `backend-shipper.sh` changed.
  Existing `013_seat_heartbeat` / `004_seat_spawns` columns sufficient.
- **Shipper child-reap ordering**: `pkill -P "$pid"` (child first) then `kill "$pid"` (wrapper).
  The executed-detection `|| ! kill -0 "$pid"` handles the already-dead-wrapper case.
- **Out-of-scope boundary**: No bulk-abort, no auto-abort heuristics, no UI changes, no new env vars.
- **Architecture review** (Stage 1, system-architect): APPROVED at `0ac17c3f` with all gate
  criteria verified. See `kind: gate-results` comment 2026-07-19T17:16:48Z.

---

## Verdict

| Criterion | Status |
|---|---|
| AC1 (integration test: abort-spawn → event + completed_at) | ✅ PASS |
| AC2 (already-completed seat → no-op, no error) | ✅ PASS |
| AC3 (live smoke documented) | ✅ PASS |
| TypeScript typecheck | ✅ PASS |
| ESLint | ✅ PASS |
| Test files green-run (ABS-453) | ✅ 4/4 abort tests + 42/42 shipper shell |
| No regression in pre-existing suite | ✅ 228/229 (1 pre-existing ABS-480 failure, not this ticket) |
| Out-of-scope boundary held | ✅ PASS |

**FINAL VERDICT: ✅ APPROVED**

No design flag → exit transition: `In Test → Story Acceptance`
