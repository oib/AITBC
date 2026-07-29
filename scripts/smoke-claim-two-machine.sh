#!/bin/bash
# =============================================================================
# Two-machine live claim smoke test (ABS-187, spec §9)
# =============================================================================
# OPERATOR-RUN, NOT CI. The full smoke needs live Jira and TWO separate
# checkouts on two machines (or two users) sharing ONE Jira ticket — it cannot
# run inside a single CI subagent (ABS-181 grooming, BSA re-worded AC). This
# script is the runnable half: each machine invokes it against the shared ticket
# with its own ORCH_INSTANCE_ID, and it reuses the REAL orchestrator claim logic
# (sourced, no poll loop) through the configured $TRACKER_CMD adapter.
#
# Goal it proves: with ORCH_CLAIM_MODE=on, exactly ONE of the two machines wins
# the claim for a contested `orchestrator-ready` ticket (one spawn), the other
# records SKIP-CLAIMED.
#
# ---------------------------------------------------------------------------
# PROCEDURE (canonical operational SOP lives in ABS-188 / ORCHESTRATOR_SOP.md)
# ---------------------------------------------------------------------------
#   0. Pick one Jira ticket in an active, non-terminal status, labelled
#      `orchestrator-ready`. Note its key, e.g. ABS-999.
#   1. On MACHINE 1 (checkout A):
#         export TRACKER_CMD="$PWD/scripts/jira-tracker.sh"
#         export ORCH_INSTANCE_ID="machine-1"       # any stable unique id
#         scripts/smoke-claim-two-machine.sh probe ABS-999
#   2. On MACHINE 2 (checkout B), AT THE SAME TIME (within one settle window):
#         export TRACKER_CMD="$PWD/scripts/jira-tracker.sh"
#         export ORCH_INSTANCE_ID="machine-2"
#         scripts/smoke-claim-two-machine.sh probe ABS-999
#   3. On EITHER machine, adjudicate the shared truth:
#         scripts/smoke-claim-two-machine.sh tally ABS-999
#      EXPECT: exactly one live holder; `probe` printed WON on exactly one
#      machine and SKIP-CLAIMED on the other.
#   4. Record the three timing/scale measurements (see `measure` and the
#      evidence doc docs/agent-outputs/qa-validations/ABS-187-claim-mutex-evidence.md).
#
# Zero-dependency: pure bash 3.2 + BSD tools + $TRACKER_CMD. Never spawns a real
# agent — `probe` adjudicates the claim only.
# =============================================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
ORCH="$REPO_ROOT/scripts/orchestrator.sh"

usage() {
    sed -n '2,45p' "$0" | sed 's/^# \{0,1\}//'
    cat <<EOF

USAGE:
  scripts/smoke-claim-two-machine.sh probe <TICKET>   # adjudicate this machine's claim (WON|SKIP-CLAIMED)
  scripts/smoke-claim-two-machine.sh tally <TICKET>   # print live holder + per-instance claim counts
  scripts/smoke-claim-two-machine.sh measure <TICKET> # print the raw signals for the 3 tuning measurements

REQUIRED ENV:
  TRACKER_CMD        the live adapter, e.g. \$PWD/scripts/jira-tracker.sh
  ORCH_INSTANCE_ID   a stable id unique to THIS machine (probe only)
OPTIONAL ENV:
  ORCH_CLAIM_MODE (default on), ORCH_CLAIM_TTL (600), ORCH_CLAIM_SETTLE_MS (1500),
  ORCH_CLAIM_JITTER_MS (1000)
EOF
}

[ $# -ge 1 ] || { usage; exit 2; }
CMD="$1"; shift || true

case "$CMD" in -h|--help|help) usage; exit 0 ;; esac

TICKET="${1:-}"
[ -n "$TICKET" ] || { echo "error: <TICKET> required" >&2; usage; exit 2; }

: "${TRACKER_CMD:?set TRACKER_CMD to the live adapter, e.g. \$PWD/scripts/jira-tracker.sh}"

# Sensible live defaults; the operator can override any of them.
export ORCH_CLAIM_MODE="${ORCH_CLAIM_MODE:-on}"
export ORCH_CLAIM_TTL="${ORCH_CLAIM_TTL:-600}"
export ORCH_CLAIM_SETTLE_MS="${ORCH_CLAIM_SETTLE_MS:-1500}"
export ORCH_CLAIM_JITTER_MS="${ORCH_CLAIM_JITTER_MS:-1000}"
# Isolate per-machine runner state (instance-id file, locks) from the checkout.
export ORCH_STATE_DIR="${ORCH_STATE_DIR:-$REPO_ROOT/.orchestrator}"
mkdir -p "$ORCH_STATE_DIR"

# Load the orchestrator's claim functions without starting the poll loop.
# shellcheck disable=SC1090
source "$ORCH" >/dev/null 2>&1
set +e +u +o pipefail

case "$CMD" in
    probe)
        : "${ORCH_INSTANCE_ID:?set ORCH_INSTANCE_ID to a stable per-machine id}"
        echo "== claim probe: ticket=$TICKET instance=$ORCH_INSTANCE_ID settle=${ORCH_CLAIM_SETTLE_MS}ms(+${ORCH_CLAIM_JITTER_MS}ms) ttl=${ORCH_CLAIM_TTL}s =="
        started="$(date -u +%s)"
        if acquire_remote_claim "$TICKET"; then
            echo "RESULT: WON  (this machine would spawn) after $(( $(date -u +%s) - started ))s"
            exit 0
        else
            echo "RESULT: SKIP-CLAIMED  (a peer holds the claim) after $(( $(date -u +%s) - started ))s"
            exit 3
        fi
        ;;
    tally)
        dump="$(tracker get "$TICKET" 2>/dev/null)"
        holder="$(first_live_claim "$dump")"
        echo "== claim tally: ticket=$TICKET =="
        echo "live holder (adjudicated winner): ${holder:-<none>}"
        echo "claim comments per instance:"
        claim_blocks "$dump" | awk '{c[$2]++} END{for(i in c) printf "  %-24s %d\n", i, c[i]}'
        n_holders="$( [ -n "$holder" ] && echo 1 || echo 0 )"
        echo "distinct live holders: $n_holders  (PASS iff exactly 1 for a contested ticket)"
        [ "$n_holders" -le 1 ] || exit 1
        ;;
    measure)
        # Raw signals for the three ABS-187 #PLAN_UNCERTAINTY measurements. Run
        # after a live episode; feed the numbers into the evidence doc.
        dump="$(tracker get "$TICKET" 2>/dev/null)"
        echo "== measurement signals: ticket=$TICKET =="
        echo "-- (1) settle window: post a claim then time how long it takes to read back --"
        stake_claim "$TICKET"
        # Poll read-back visibility of our own just-staked claim.
        for ms in 100 250 500 1000 2000 4000; do
            sleep "$(awk -v m="$ms" 'BEGIN{printf "%.3f", m/1000}')"
            if tracker get "$TICKET" 2>/dev/null | grep -q "instance: ${ORCH_INSTANCE_ID:-}"; then
                echo "   own claim visible within ~${ms}ms  -> recommend ORCH_CLAIM_SETTLE_MS >= ${ms} (+jitter)"
                break
            fi
        done
        echo "-- (2) TTL headroom: largest gap between consecutive claim/active timestamps --"
        claim_blocks "$dump" | awk '{print $1}'
        echo "   (compute max delta between consecutive active episodes; must be < ORCH_CLAIM_TTL=${ORCH_CLAIM_TTL}s)"
        echo "-- (3) owned drift: distinct tickets this instance currently holds --"
        echo "   (run 'tally' across the active ticket set; if one machine holds > ORCH_MAX_CONCURRENT, consider ORCH_CLAIM_MAX_OWNED)"
        ;;
    *)
        echo "error: unknown command '$CMD'" >&2; usage; exit 2 ;;
esac
