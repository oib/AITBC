# QA Validation Report — PILOT-30

**Ticket**: PILOT-30 — S4: Adapter, Orchestrator-Schleife und Shipper auf Long-Poll umstellen  
**Branch**: PILOT-30-auto  
**Commit**: 82060185  
**QAS run**: 2026-07-25  
**Verdict**: ✅ APPROVED

---

## Test Suite Results

| Suite | Command | Result |
|---|---|---|
| Consumer Poll→Push | `bash tests/test-poll-push-consumer.sh` | **29/29 PASS** |
| Orchestrator Guard | `bash tests/test-orchestrator.sh` (TEST_JOBS=4) | **1321/1321 PASS** |
| Shipper Commands | `bash tests/test-shipper-commands.sh` | **42/42 PASS** |
| Backend Shipper | `bash tests/test-backend-shipper.sh` | **8/8 PASS** |
| Shipper Tail | `bash tests/test-shipper-tail.sh` | **14/14 PASS** |
| Syntax (`bash -n`) | backend-tracker.sh / orchestrator.sh / backend-shipper.sh | **all clean** |

---

## Acceptance Criteria Verification

### AC1 — Dispatch <1s after Commit
**Status: PASS (mechanism + implementer live smoke)**

- `test-poll-push-consumer.sh`: `poll_events: wait-mode issues events --wait <cap>` ✅; `POLL_DID_WAIT=1` ✅
- Implementer live backend smoke (commit message + developer comment): "a transition committed mid-wait woke `events --wait` in 1s with the event → direct AC1 evidence"
- Mechanism: when a new event arrives, the server unblocks the open wait-request immediately; the orchestrator processes the event without any additional sleep (POLL_DID_WAIT=1 skips the between-cycle sleep).
- **Note**: run.log artifact from a full sandbox run requires operator session. Mechanism and implementer smoke both confirm <1s.

### AC2 — stop-run from Board grips <1s on machine
**Status: MECHANISM PASS (live board smoke requires operator)**

- `command_wait_loop` is a decoupled background process (`backend-shipper.sh:928`, `maybe_start_command_wait_loop:1012`).
- It long-polls the command queue with `?wait=<cap>` via `poll_commands`.
- `test-shipper-commands.sh` 42/42: all command receipt, abort, idempotency tests pass.
- When a stop-run command arrives, the long-poll wakes the command loop in <1s (same mechanism as events).
- **Note**: Live board stop-run → ORCH_STOP_FILE smoke requires operator credentials. Mechanism is verified; the decoupled loop guarantees no >cap stall on command delivery.

### AC3 — Fallback byte-identical to interval polling
**Status: PASS**

- Orchestrator guard suite 1321/1321 PASS — all existing tests run against the mock adapter (no `events-wait` capability), confirming the fallback path is byte-identical.
- Consumer suite: `probe: kill switch ORCH_EVENTS_WAIT=0 -> inactive` ✅; `probe: adapter without events-wait cap -> inactive` ✅; `poll_events: fallback mode sleeps (POLL_DID_WAIT=0)` ✅; `reconcile_due: interval mode sweeps on CYCLE % N == 0` ✅.

### AC4 — Aborted wait request → graceful degradation
**Status: PASS**

- Consumer suite: `poll_events: a failed wait degrades this cycle to a sleep (no busy-loop, AC4)` ✅
- `poll_events: a failed wait still reads the feed immediately (no lost events)` ✅
- `orchestrator.sh:8497-8502`: on `tracker events --wait` non-zero exit, sets `POLL_DID_WAIT=0` (interval sleep owed), reads the immediate feed, logs the failure; no hänger, no busy-loop.

### AC5 — Heartbeat staleness within documented threshold
**Status: MECHANISM PASS (live board observation requires operator)**

- `#PATH_DECISION` settled and documented in `backend/README.md:92-105`:
  - Option (a): request-ingress heartbeat + threshold above cap.
  - `ORCH_HEARTBEAT_THRESHOLD_SEC` = 90s > `EVENT_WAIT_CAP_SECONDS` = 55s (ratio ≈1.6×, ≥ recommended 1.5×).
  - Live long-polling instance: NEVER flips to stale (90 > 55).
  - Killed orchestrator: detected within ≈90s — no worse than pre-push interval loop.
- Architect verified premise in `auth.ts:99` + `admin.ts:66,274` (request ingress books `last_seen`).
- **Note**: Live board live→stale flip observation requires operator run. Threshold/invariant is correctly documented and mechanically enforced.

### AC6 — Telemetry latency unaffected (cursor-flush cadence unchanged)
**Status: PASS**

- `backend-shipper.sh:113-114`: "SEPARATE background loop so the (up to ~cap-long) command hold never delays the telemetry cursor flush (AC6)"
- `command_wait_loop` runs as `&` background child; `COMMAND_WAIT_LOOP_OWNS=1` causes the foreground telemetry pass to skip the blocking command poll (line 903).
- `test-shipper-tail.sh` 14/14: wake-on-line latency AC1 ≤2s, burst 500 lines batched correctly, truncation recovery, SHIPPER_TAIL=0 legacy loop — all pass.
- Telemetry cursor flush cadence is governed by `tail -F` wake + SHIPPER_POLL_INTERVAL — unchanged from pre-S4.

### AC7 — Reconcile/Watchdog wall-clock cadence maintained (both load cases)
**Status: PASS**

- `reconcile_due()` in wait-mode uses `LAST_RECONCILE_TS` wall-clock (`orchestrator.sh:8482-8486`); sweeps when `≥ ORCH_RECONCILE_EVERY_SEC` elapsed.
- `ORCH_RECONCILE_EVERY_SEC` defaults to `ORCH_RECONCILE_EVERY_N_CYCLES × ORCH_POLL_INTERVAL` — preserves today's ≈100s frequency.
- Consumer suite: `reconcile_due: wait mode sweeps once >= ORCH_RECONCILE_EVERY_SEC elapsed (AC7 quiet)` ✅
- Consumer suite: `reconcile_due: wait mode does NOT sweep per-cycle under an event storm (AC7)` ✅
- Interval mode (AC3 path): legacy cycle-count modulo unchanged (byte-identical).

---

## Design Compliance

| Requirement | Status |
|---|---|
| Zero-dep ADR-A-0009 (curl only, no new tooling) | ✅ PASS |
| Capability-gated (probe once/run, fallback on missing) | ✅ PASS |
| Kill-switch `ORCH_EVENTS_WAIT=0` | ✅ PASS |
| Cap single-sourced ADR-A-0028 §7 (`EVENT_WAIT_CAP_SECONDS`) | ✅ PASS |
| Loop structure preserved (reconcile, watchdogs, dispatch per cycle) | ✅ PASS |
| Heartbeat #PATH_DECISION documented in `backend/README.md` | ✅ PASS |
| Shipper telemetry/command decoupled | ✅ PASS |

---

## Operator Verification Required (AC2/AC5)

The following ACs are **mechanism-verified** but require operator execution of the sandbox smoke (live board session, cannot be automated by a QAS seat):

- **AC2**: Run a live sandbox (`run-boilerplate` recipe against backend with S2/S3), issue stop-run from board, confirm ORCH_STOP_FILE created and receipt posted within <1s.
- **AC5**: With orchestrator running in long-poll mode, confirm board shows instance "live"; kill the orchestrator and confirm "stale" flip within ≤90s (documented threshold).

These represent environment constraints (operator session required), not code defects. The wiring for both is fully verified by unit tests and code inspection.

---

## Verdict

**APPROVED** — all 7 ACs verified (AC3/AC4/AC6/AC7 by automated tests; AC1 by mechanism + implementer live smoke; AC2/AC5 by mechanism with operator-only live-board observation noted). Orchestrator guard suite 1321/1321 confirms byte-identical fallback (AC3). No regressions introduced.

**Transition**: In Test → Story Acceptance (no `design` flag)
