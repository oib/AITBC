# =============================================================================
# PILOT-26 — Live-Spawns PRIMARY producer: the runner emits the seat open/close
# upsert first-hand at spawn/reap (ABS-352 S7 had no production caller).
# -----------------------------------------------------------------------------
# Per-story include (ABS-215 pattern): `source`d by tests/tooling/test-orchestrator.sh
# into the live harness — no shebang, no `set -e` re-entry. Shares assert_eq /
# assert_contains / assert_not_contains, PASS/FAIL/TOTAL, REPO_ROOT, ORCH.
#
# This is the conformance test on the SPAWN SEAM (AC1). It probes the two pure
# functions the primary path is built from, in a child bash that `source`s
# orchestrator.sh (the main-loop guard keeps `main` from running when sourced):
#
#   1. seat_spawn_id is DETERMINISTIC — run_id:ticket:role:attempt. The same
#      inputs always yield the same id, so the open POST and the close POST at
#      reap carry the SAME spawn_id and the endpoint upserts one row (not two).
#   2. A respawn is a DISTINCT id (attempt 1 vs 2), so a genuine retry is a new
#      row and never leaves the predecessor as a phantom active seat.
#   3. emit_seat_upsert is a SILENT no-op when the backend env is absent, and
#      when ORCH_SEAT_UPSERT=0. This is load-bearing: emit_seat_upsert runs
#      inside run_spawn_cmd's command-substitution subshell (out="$(run_spawn_cmd
#      ...)"), so ANY byte it writes to stdout would corrupt the captured
#      handoff. The offline/dry-run test path must stay byte-silent.
#
# The live POST round-trip (seat appears <2s, closes with exit_code) is covered
# by the docker-backed suites (tests/test-backend-shipper.sh drives the same
# endpoint); here we pin the seam contract without a network.
# =============================================================================

echo -e "\n${CYAN}=== PILOT-26 primary Live-Spawns producer (spawn-seam conformance) ===${NC}"

# Probe the seam functions in a child bash so nothing leaks into the test shell.
# stdout of the child is ONLY our explicit report lines (prefixed markers), so a
# stray byte from emit_seat_upsert would show up as an unexpected stdout capture.
_pilot26_probe() {
    ORCH_SEAT_UPSERT="$1" BACKEND_TOKEN="$2" TRACKER_PROJECT="$3" \
    bash -c '
        source "'"$ORCH"'" >/dev/null 2>&1 || { echo "SOURCE-FAIL"; exit 0; }
        export ORCH_RUN_ID="run7" ORCH_INSTANCE_ID="inst9"
        SPAWN_ATTEMPT=1; id1="$(seat_spawn_id PILOT-9 be-developer)"
        SPAWN_ATTEMPT=2; id2="$(seat_spawn_id PILOT-9 be-developer)"
        echo "ID1=$id1"
        echo "ID2=$id2"
        # Capture emit_seat_upsert stdout separately — it MUST be empty.
        emitted="$(SPAWN_ATTEMPT=1 emit_seat_upsert open "$id1" PILOT-9 be-developer 2026-01-01T00:00:00Z "" "" "")"
        rc=$?
        echo "EMIT_RC=$rc"
        echo "EMIT_STDOUT=[$emitted]"
    '
}

# Case A: backend env absent -> silent no-op, deterministic ids.
_pilot26_out="$(_pilot26_probe 1 "" "")"
assert_contains "$_pilot26_out" "ID1=run7:PILOT-9:be-developer:1" \
    "PILOT-26: seat_spawn_id is deterministic run_id:ticket:role:attempt (attempt 1)"
assert_contains "$_pilot26_out" "ID2=run7:PILOT-9:be-developer:2" \
    "PILOT-26: respawn yields a DISTINCT spawn_id (attempt 2) — no phantom predecessor row"
assert_not_contains "$_pilot26_out" "ID2=run7:PILOT-9:be-developer:1" \
    "PILOT-26: attempt-2 id is not equal to attempt-1 id"
assert_contains "$_pilot26_out" "EMIT_RC=0" \
    "PILOT-26: emit_seat_upsert returns 0 when backend env is absent (non-fatal)"
assert_contains "$_pilot26_out" "EMIT_STDOUT=[]" \
    "PILOT-26: emit_seat_upsert writes NOTHING to stdout offline (command-substitution safe)"

# Case B: env present but ORCH_SEAT_UPSERT=0 -> still a silent no-op (kill switch).
_pilot26_off="$(_pilot26_probe 0 tok proj)"
assert_contains "$_pilot26_off" "EMIT_RC=0" \
    "PILOT-26: ORCH_SEAT_UPSERT=0 disables the emit (returns 0)"
assert_contains "$_pilot26_off" "EMIT_STDOUT=[]" \
    "PILOT-26: ORCH_SEAT_UPSERT=0 emits nothing to stdout"

# The seam is wired into run_spawn_cmd at BOTH the open (pre-launch) and close
# (post-reap) points, and the retry path bumps SPAWN_ATTEMPT — assert the wiring
# is present so a future refactor that drops a call is caught (source-checkable).
_pilot26_src="$(cat "$ORCH")"
assert_contains "$_pilot26_src" "emit_seat_upsert open" \
    "PILOT-26: run_spawn_cmd emits the OPEN upsert at spawn"
assert_contains "$_pilot26_src" "emit_seat_upsert close" \
    "PILOT-26: run_spawn_cmd emits the CLOSE upsert at reap"
assert_contains "$_pilot26_src" "SPAWN_ATTEMPT=2" \
    "PILOT-26: the retry path marks a distinct attempt (no phantom on respawn)"
