#!/usr/bin/env bash
set -euo pipefail

# =============================================================================
# run-boilerplate driver — launch & drive the orchestrator in a sandbox
# =============================================================================
# The runnable surface of this repo is scripts/orchestrator.sh (a bash poll
# loop). This driver runs it fully isolated: mock tracker in a mktemp ticket
# store, private ORCH_STATE_DIR, stub spawn seam (no real `claude`, no live
# model, no Jira), worktree provisioning OFF. It never touches a concurrently
# running live orchestrator (whose state lives in its own repo checkout).
#
# Usage (from anywhere inside the repo):
#   .devin/skills/run-boilerplate/driver.sh smoke      # full lifecycle cycle, PASS/FAIL
#   .devin/skills/run-boilerplate/driver.sh sandbox    # print export lines for interactive driving
#   .devin/skills/run-boilerplate/driver.sh clean      # remove driver sandboxes
# =============================================================================

REPO_ROOT="$(git rev-parse --show-toplevel)"
SANDBOX_PARENT="${TMPDIR:-/tmp}"

make_sandbox() {
    local sb
    sb="$(mktemp -d "$SANDBOX_PARENT/run-boilerplate-XXXXXX")"
    mkdir -p "$sb/tickets" "$sb/state"
    echo "$sb"
}

env_exports() {
    local sb="$1"
    cat <<EOF
export MOCK_TRACKER_TICKETS_DIR="$sb/tickets"
export ORCH_STATE_DIR="$sb/state"
export MOCK_TRACKER_STATUSES="$REPO_ROOT/profiles/neutral/adapters/statuses.yaml"
export TRACKER_CMD="$REPO_ROOT/scripts/mock-tracker.sh"
export ORCH_SPAWN_CMD="$REPO_ROOT/tests/fixtures/stub-spawn.sh"
export ORCH_REQUIRE_START_LABEL=0
export ORCH_WORKTREE_SPAWNS=0
export STUB_TRACKER="$REPO_ROOT/scripts/mock-tracker.sh"
export STUB_RECORD_FILE="$sb/spawn-record.txt"
EOF
}

case "${1:-smoke}" in
smoke)
    SB="$(make_sandbox)"
    eval "$(env_exports "$SB")"
    cd "$REPO_ROOT"
    fail=0

    echo "== 1. seed a mock ticket (Backlog) =="
    id="$(scripts/mock-tracker.sh create --type ticket --title "Smoke: demo story" --prefix DEMO --role be-developer)"
    echo "   created $id"

    echo "== 2. dry-run --once: expect intake classify + po-agent spawn intent =="
    out="$(scripts/orchestrator.sh --dry-run --once 2>&1)"
    echo "$out" | grep -E 'INTENT' | sed 's/^/   /'
    echo "$out" | grep -q "INTENT SPAWN ticket=$id role=po-agent" || { echo "   FAIL: no po-agent spawn intent"; fail=1; }

    echo "== 3. release ticket, live --once against the STUB spawn seam =="
    mkdir -p work/scratch
    printf '%s\n' "smoke: release for dev" > work/scratch/smoke-release-reason.md
    scripts/mock-tracker.sh transition "$id" "Ready for Development" \
        --actor human-operator --reason-file work/scratch/smoke-release-reason.md >/dev/null
    STUB_TRANSITION_TO="In Progress" scripts/orchestrator.sh --live --once 2>&1 \
        | grep -E 'INTENT' | sed 's/^/   /'

    echo "== 4. assert the stub seat ran and moved the ticket =="
    status="$(scripts/mock-tracker.sh get "$id" | grep '^status:' | cut -d' ' -f2-)"
    echo "   status=$status  spawn-record=$(tr '\t' ':' < "$STUB_RECORD_FILE" | paste -sd, -)"
    [ "$status" = "In Progress" ] || { echo "   FAIL: expected In Progress"; fail=1; }
    grep -q "be-developer" "$STUB_RECORD_FILE" || { echo "   FAIL: stub never spawned"; fail=1; }

    rm -rf "$SB"
    if [ "$fail" -eq 0 ]; then echo "SMOKE PASS"; else echo "SMOKE FAIL"; exit 1; fi
    ;;
sandbox)
    SB="$(make_sandbox)"
    echo "# eval this in your shell, then drive scripts/orchestrator.sh / scripts/mock-tracker.sh by hand:"
    env_exports "$SB"
    echo "# sandbox: $SB   (remove with: $0 clean)"
    ;;
clean)
    rm -rf "$SANDBOX_PARENT"/run-boilerplate-*
    echo "driver sandboxes removed"
    ;;
*)
    echo "usage: $0 [smoke|sandbox|clean]" >&2; exit 2 ;;
esac
