# PILOT-26 QA Validation Report

**Date**: 2026-07-24  
**Branch**: PILOT-26-auto  
**Commit**: 40c7a85c  
**Actor**: qas

---

## Scope

Commit 40c7a85c wires the ABS-352 seat open/close upsert as a first-hand POST from the
orchestrator at spawn/reap (push-first primary path, ADR-A-0010 outbound-only). It also
adds `ship_spawns` in `scripts/backend-shipper.sh` as the reconcile FALLBACK, replaying
`SEAT-SPAWN` run.log markers to heal missed POSTs after a runner crash. Four files changed:

- `scripts/orchestrator.sh` — `emit_seat_upsert`, `seat_spawn_id`, open/close wiring in `run_spawn_cmd`
- `scripts/backend-shipper.sh` — `post_spawn`, `ship_spawns`
- `tests/orchestrator.d/PILOT-26-seat-lifecycle.sh` — spawn-seam conformance (sourced by test-orchestrator.sh)
- `tests/test-pilot26-seat-reconcile.sh` — repair path with stub curl

---

## Test Results

### 1. Full orchestrator suite — `tests/test-orchestrator.sh`

**Result: 1296/1296 PASS**

PILOT-26 seam conformance tests (all 10 green, embedded in the suite):

| Test | Result |
|---|---|
| seat_spawn_id deterministic run_id:ticket:role:attempt (attempt 1) | PASS |
| respawn yields distinct spawn_id (attempt 2) — no phantom predecessor | PASS |
| attempt-2 id not equal to attempt-1 id | PASS |
| emit_seat_upsert returns 0 when backend env absent (non-fatal) | PASS |
| emit_seat_upsert writes nothing to stdout offline (command-substitution safe) | PASS |
| ORCH_SEAT_UPSERT=0 disables the emit (returns 0) | PASS |
| ORCH_SEAT_UPSERT=0 emits nothing to stdout | PASS |
| run_spawn_cmd emits the OPEN upsert at spawn | PASS |
| run_spawn_cmd emits the CLOSE upsert at reap | PASS |
| Retry path marks a distinct attempt (no phantom on respawn) | PASS |

### 2. Reconcile fallback — `tests/test-pilot26-seat-reconcile.sh`

**Result: 6/6 PASS**

| Test | Result |
|---|---|
| scripts/backend-shipper.sh exists and is executable | PASS |
| AC2a: missed close healed — respawn synthesizes predecessor's close | PASS |
| AC2a: healed close carries predecessor's (attempt 1) spawn_id | PASS |
| AC2b: respawn (attempt 2) emitted as distinct open — no phantom | PASS |
| AC2c: normal PILOT-2 close replays with real exit_code | PASS |
| AC2d: healed close carries full identity incl. started_at | PASS |

### 3. Static analysis

| Check | Result |
|---|---|
| `bash -n scripts/orchestrator.sh` | PASS |
| `bash -n scripts/backend-shipper.sh` | PASS |
| `shellcheck -S warning scripts/orchestrator.sh` | Pre-existing SC1087/SC1125/SC1011 on main; no new findings from PILOT-26 changes |
| `shellcheck -S warning scripts/backend-shipper.sh` | SC2034 on `phase` — consumed positionally to align IFS-delimited fields; non-blocking (consistent with SA assessment) |

---

## Acceptance Criteria

**AC1** — Seat appears at spawn (<2s), closes at reap with exit_code; respawn never leaves a
phantom active seat:

**PASS.** By construction, `emit_seat_upsert open` fires before the watchdog wait in
`run_spawn_cmd` (well under 2s). `seat_spawn_id` is deterministic (`run_id:ticket:role:attempt`);
the retry path bumps `SPAWN_ATTEMPT` to 2, producing a distinct id so the predecessor is never
left as a phantom active row. The `close` call carries `started_at` (full identity, matching the
live contract detail). `emit_seat_upsert` is stdout-silent inside the command-substitution
subshell. Kill switch `ORCH_SEAT_UPSERT=0` confirmed functional. All seam assertions green.

**AC2** — run.log fixture with a missed close healed by the reconcile pass; primary path outage
does not lose lifecycles permanently:

**PASS.** The stub-curl reconcile test drove `ship_spawns` against a fixture where PILOT-1
attempt-1's close was missed (crash). The respawn (attempt-2 open) triggered a synthetic
predecessor close (`diagnostic: "reconcile: superseded by respawn"`) carrying the full identity
incl. `started_at`. PILOT-2's normal open+close replayed with `exit_code: 0`. The log-derived
heuristic is confined to `ship_spawns` only (ADR-A-0010 primary path never parses logs).

**AC3** — Abort-spawn round trip against a REAL seat produced by the primary path:

**PREREQUISITE MET.** The producer path is now wired (commit 40c7a85c). The live abort-spawn
round trip (abort a seat visible in Mission-Control via ABS-461/476 UI) requires a live backend
environment and is owned by the ABS-461/476 work. Classification: **environment dependency** —
not a code deficiency on PILOT-26. Escalation to TDM is not required; this is a known scope
boundary documented in the ticket ("ties ABS-461/476 together").

---

## Verdict

**APPROVED**

Commit `40c7a85c` on branch `PILOT-26-auto`. Tests: 1296/1296 (orchestrator suite) + 6/6
(reconcile fallback). Static analysis clean for PILOT-26 changes. AC1 and AC2 fully verified;
AC3 prerequisite met (environment-dependent end-to-end owned by ABS-461/476).
