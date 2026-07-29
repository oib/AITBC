# QA Validation — PILOT-78

**Ticket**: PILOT-78 — spawn_id nicht eindeutig: alle ops-sweep-Spawns eines Runs teilen dieselbe Id  
**Branch**: PILOT-78-auto  
**Commit**: d0e9399f  
**QAS run date**: 2026-07-27  
**Verdict**: APPROVED

---

## Test Results (freshly run by QAS)

| Suite | Count | Result |
|---|---|---|
| `PILOT-78-ops-sweep-spawn-id.sh` | 8/8 | PASS |
| `PILOT-26-seat-lifecycle.sh` | 10/10 | PASS |
| `PILOT-27-seat-session.sh` | 8/8 | PASS |
| `PILOT-42-ops-sweep-cadence.sh` | 7/7 | PASS |
| `PILOT-43-ops-sweep-tiers.sh` | 6/6 | PASS |
| `test-pilot26-seat-reconcile.sh` | 6/6 | PASS |
| `bash -n scripts/orchestrator.sh` | — | CLEAN |

---

## AC Verification

**AC1** (unique id, attempt preserved): PASS.  
`SPAWN_SEQ=1` → `run7:ops-sweep:tdm:1#1`; `SPAWN_SEQ=2` → `run7:ops-sweep:tdm:1#2`. Attempt stays `1` in both — verified by test probe output. Ticket seats (unset `SPAWN_SEQ`) produce byte-identical `run_id:ticket:role:attempt`, confirmed by test assertion `TKT=run7:PILOT-9:be-developer:1`.

**AC2** (≥2 dispatches distinct, with test): PASS.  
End-to-end probe drives two `SPAWN_SEQ` values; ids diverge at the `#N` suffix. Source-text assertion in the test pins `local SPAWN_SEQ="$OPS_SWEEP_COUNT"` inside `ops_sweep_dispatch`. QAS confirmed that line present in the diff at line 8289 of `scripts/orchestrator.sh`.

**AC3** (overlap behavior tested): PASS.  
The pre-existing single-flight lock suppresses a second concurrent dispatch. Test seeds the cadence marker, holds the lock via `mkdir -p locks/ops-sweep`, then drives a due sweep: output contains `INTENT SKIP-LOCKED ticket=ops-sweep role=tdm` and no `INTENT OPS-SWEEP`. Two live opens on one id cannot arise. Suppression approach documented in the test header.

**AC4** (evaluators searched and pulled): PASS.  
QAS ran `grep -n "spawn_id" scripts/ops-sweep-sensors.sh` → no output. `grep -n "spawn_id" scripts/run-status-collector.sh` → no output. Neither script pairs by spawn_id. `backend-shipper.sh` carries `spawn_id` as a payload field to `post_spawn` (line 568) and reads it from `SEAT-SPAWN` markers via `tok($6,"spawn_id")` (line 632) for the reconcile path; it does not pair open/close by spawn_id. Producer-only fix is correct; no consumer changes needed.

---

## Scope Check

Two files changed: `scripts/orchestrator.sh` (+17 lines, `seat_spawn_id` and `ops_sweep_dispatch`) and `tests/orchestrator.d/PILOT-78-ops-sweep-spawn-id.sh` (89 lines, new). No RLS, auth, migration, or schema surface. No consumer changes required.

---

## Verdict: APPROVED for Story Acceptance
