# QA Validation Report — ABS-476

**Ticket**: ABS-476 — Runner consume path for abort-spawn: terminate seat, emit abort event
**Parent**: ABS-460 (Mission-Control UX hardening) — split out of ABS-461 per architecture review
**Branch**: `ABS-476-auto`
**Date**: 2026-07-19
**Actor**: be-developer (fastlane solo seat — dev + scoped tests + self-review)
**Verdict**: ✅ **FUNCTIONAL GATE PASS** (combined dev/test/self-review gate)

---

## The gap this closes

ABS-461 wired the `abort-spawn` command into the UI/API, but the consume path was
incomplete: the shipper (`scripts/backend-shipper.sh`) signalled the seat pid and
receipted `executed`, yet **nothing closed the `seat_spawn` row or emitted an abort
event** — so an aborted seat stayed open (`completed_at IS NULL`) forever, surfacing as
a stale/orphaned seat on the board. Two smaller gaps rode along: the abort signalled
the wrapper pid only (leaving forked children — and their lock dirs — orphaned, the
2026-07-19 stale-lock finding), and there was no idempotency contract for aborting an
already-dead/completed seat.

## Change summary (smallest diff for the ACs)

| Part | File | What |
|---|---|---|
| B (load-bearing) | `backend/packages/core/src/commands.ts` | On an `abort-spawn` receipt recorded `executed`, close the referenced `seat_spawn` (`completed_at`, `exit_code=143`, `diagnostic`) and emit a `seat-aborted` event — inside the receipt transaction, idempotent (`WHERE completed_at IS NULL`). |
| A (scope: no orphaned lock dirs) | `scripts/backend-shipper.sh` | Reap the seat's children **first** (`pkill -P`, the codebase's sanctioned PID-scoped group kill), then the wrapper — a child reparents to init the instant its parent dies, so child-first ordering is required (verified below). |
| Tests | `backend/packages/core/test/command-abort.test.ts` | Stubbed poll/receipt loop integration test (4 cases). |

No migration added (heartbeat schema 013 reused via `seat_spawn`). Out-of-scope
boundary held: no bulk-abort, no auto-abort heuristics, no UI changes.

---

## Test Suite Results

| Suite | Command | Result |
|---|---|---|
| TypeScript type-check | `pnpm -r typecheck` | ✅ PASS — all 5 projects clean |
| ESLint | `pnpm lint` | ✅ PASS — no findings |
| Core integration (new) | `node --import tsx --test .../command-abort.test.ts` | ✅ PASS — 4/4 |
| Core full suite | `pnpm --filter @agentic-backend/core test` | ✅ 228/229 — the 1 failure is the **pre-existing** `011` duplicate-prefix guard, tracked separately in **ABS-480** (data-engineer); no migration was added here |
| Command routes (regression) | `.../command-routes.test.ts` | ✅ PASS — 26/26 |
| Spawns + heartbeat (regression) | `.../spawns-routes.test.ts`, `.../heartbeat.test.ts` | ✅ PASS — 12/12 |
| Shipper command shell test | `bash tests/test-shipper-commands.sh` | ✅ PASS — 42/42 |

Postgres for the integration suite: sandboxed throwaway container (`postgres:16-alpine`,
unique name `abs476-pg`, non-default host port `55476` per the compose sandbox rule).

---

## AC Verification

### AC1 — enqueued abort-spawn → delivered → receipted executed → abort event → completed_at set ✅

Integration test `AC1: executed abort-spawn closes the seat and emits a seat-aborted event`
drives the real stubbed poll/receipt loop against Postgres:
`enqueueCommand` → `pollCommands` (pending→delivered) → `recordReceipt(state=executed)`.
Asserts: command settled `executed`; `seat_spawn.completed_at` is set; `exit_code=143`
(128+SIGTERM); `diagnostic` names the operator abort; **exactly one** `seat-aborted`
event carrying `spawn_id`, `command_id`, `ticket_id`.

### AC2 — aborting an already-completed seat receipts a no-op without error ✅

Integration test `AC2: aborting an already-completed seat receipts a no-op without error`
seeds a seat already carrying `completed_at`, then runs the full abort loop. Asserts:
the receipt still returns (no throw) and settles `executed`; the existing `completed_at`
is **unchanged** (COALESCE/`WHERE completed_at IS NULL`); **no** `seat-aborted` event is
emitted for the already-closed seat. Two supporting guards also pass: a redelivered
(already-settled) receipt does not re-close or double-emit; a `failed` receipt leaves the
seat open with no event.

### AC3 — live smoke against a real run, documented ✅ (real-component smoke)

Both halves of the consume path were exercised against **real** infrastructure, not mocks:

1. **Backend consume/closeout** — real Postgres: an enqueued `abort-spawn` flowed
   enqueue→poll→receipt and closed a real `seat_spawn` row + wrote a real `seat-aborted`
   `event` row (AC1/AC2 integration test, 4/4 green).
2. **Shipper terminate path** — real `scripts/backend-shipper.sh` process: an abort
   command signalled a real process **tree** (a wrapper + a forked `sleep` child).
   Observed `before: parent=ALIVE child=ALIVE` → `after: parent=DEAD child=DEAD`, and the
   shell test confirms the `executed` receipt is posted (42/42). This is the reparent-race
   proof: with parent-first ordering the child **survived** (orphaned); child-first reaps
   it — the fix.

**Remaining operator smoke (human):** a full UI→abort→board round trip (ABS-461 confirm
dialog → command queue → this consume path → board reflects the seat closed) against a
live operator run is the operator-driven acceptance step; the mechanical path it depends
on is proven green here.

---

## Reviewer self-review notes (solo-seat combined gate)

- **Idempotency is structural**, not incidental: the seat close is `WHERE completed_at IS NULL`
  and the receipt terminal move is `WHERE state IN ('pending','delivered')` — both no-op on
  redelivery. Verified by two dedicated tests.
- **`failed` receipts do not close the seat** (the seat wasn't actually killed) — gated on
  `state === "executed"`. Verified.
- **No over-reach**: reused `recordReceipt`'s existing transaction; `pkill -P` mirrors the
  existing orchestrator watchdog idiom rather than inventing a new (dangerous) whole-group
  kill; no new env vars, no new migration, no UI.
