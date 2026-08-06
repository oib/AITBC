#!/bin/bash
# =============================================================================
# Test: claim mutual-exclusion across runners (ABS-187, spec §8–§9)
# =============================================================================
# ABS-184/185 proved the claim adjudication and dispatch wiring at the UNIT tier
# by SOURCING orchestrator.sh with a stubbed in-file `tracker` (tests/test-claim.sh,
# tests/test-claim-dispatch.sh). This suite closes the ABS-187 gap: it proves the
# same exactly-one-winner property ACROSS SEPARATE RUNNER PROCESSES driving the
# REAL mock adapter (scripts/mock-tracker.sh) against ONE shared ticket store —
# the inter-runner extension of the ABS-36 §8 intra-runner concurrency test.
#
# Three tiers, all deterministic and zero-dependency (bash 3.2 + BSD tools):
#   Part 1 — Unit (mock): two runner processes, distinct ORCH_INSTANCE_IDs, one
#            mock ticket -> exactly one CLAIM-WON + one SKIP-CLAIMED; the holder
#            re-dispatching is idempotent (no second stake); a claim older than
#            ORCH_CLAIM_TTL is reclaimed by a fresh runner.
#   Part 2 — Concurrency harness: N runners fire acquire_remote_claim in PARALLEL
#            on one ticket -> a single winner (extends ABS-36 §8 to inter-runner).
#   Part 3 — E2E dry-run: the real orchestrator in --dry-run + ORCH_CLAIM_MODE=on
#            logs CLAIM/CLAIM-WON (fresh ticket) and SKIP-CLAIMED (contended
#            ticket) intents; a lost claim spawns nothing.
#
# Each runner is a fresh `bash -c` that SOURCES orchestrator.sh (the main() guard
# keeps the poll loop off when BASH_SOURCE != $0) and calls acquire_remote_claim
# directly, so the only shared state is the mock ticket file — exactly the real
# cross-machine picture with one Jira ticket and N runners.
#
# Run from repo root: bash tests/test-claim-mutex.sh
# =============================================================================

set -euo pipefail
# PILOT-46: strip inherited backend/tracker env before any fixture runs (tests/sandbox-guard.sh).
# shellcheck source=tests/sandbox-guard.sh
. "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/sandbox-guard.sh"

# ABS-285: scrub ambient ORCH_* before driving the real seam/runner. A seat
# exports ~37 of them; a non-empty one leaks into the code under test and makes
# the result a function of the calling seat instead of the commit. Prefix-unset
# covers vars added later. This test sets every ORCH_* it needs, below.
unset "${!ORCH_@}"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
ORCH="$REPO_ROOT/scripts/orchestrator.sh"
TRACKER="$REPO_ROOT/scripts/mock-tracker.sh"
STUB="$REPO_ROOT/tests/fixtures/stub-spawn.sh"

PASS=0; FAIL=0; TOTAL=0
GREEN='\033[0;32m'; RED='\033[0;31m'; CYAN='\033[0;36m'; YELLOW='\033[1;33m'; NC='\033[0m'

assert_eq() {
    local actual="$1" expected="$2" label="$3"
    TOTAL=$((TOTAL + 1))
    if [ "$actual" = "$expected" ]; then echo -e "  ${GREEN}PASS${NC} $label"; PASS=$((PASS + 1))
    else echo -e "  ${RED}FAIL${NC} $label (expected '$expected', got '$actual')"; FAIL=$((FAIL + 1)); fi
}
assert_contains() {
    local output="$1" expected="$2" label="$3"
    TOTAL=$((TOTAL + 1))
    if echo "$output" | grep -qF -- "$expected"; then echo -e "  ${GREEN}PASS${NC} $label"; PASS=$((PASS + 1))
    else echo -e "  ${RED}FAIL${NC} $label (expected to find: $expected)"
        echo -e "  ${YELLOW}  Output:${NC}"; echo "$output" | head -12 | sed 's/^/    /'; FAIL=$((FAIL + 1)); fi
}
assert_not_contains() {
    local output="$1" expected="$2" label="$3"
    TOTAL=$((TOTAL + 1))
    if ! echo "$output" | grep -qF -- "$expected"; then echo -e "  ${GREEN}PASS${NC} $label"; PASS=$((PASS + 1))
    else echo -e "  ${RED}FAIL${NC} $label (did NOT expect: $expected)"; FAIL=$((FAIL + 1)); fi
}

# --- Shared mock adapter + scratch ticket store -------------------------------
TEST_DIR="$(mktemp -d /tmp/claim-mutex-test-XXXXXX)"
export MOCK_TRACKER_TICKETS_DIR="$TEST_DIR/work/tickets"
export MOCK_TRACKER_STATUSES="$REPO_ROOT/profiles/neutral/adapters/statuses.yaml"
export TRACKER_CMD="$TRACKER"
mkdir -p "$MOCK_TRACKER_TICKETS_DIR" "$TEST_DIR/state"
cleanup() { rm -rf "$TEST_DIR"; }
trap cleanup EXIT

tracker() { bash "$TRACKER" "$@"; }

# claim_run <instance-id> <ticket> — one runner process: source orchestrator.sh
# (no poll loop) and adjudicate a whole-ticket claim against the shared mock.
# Optional overrides via env: CLAIM_NOW (ORCH_NOW clock), CLAIM_TTL,
# CLAIM_SETTLE_MS, CLAIM_JITTER_MS. Emits the runner's INTENT lines + "__RC=<n>".
claim_run() {
    local inst="$1" ticket="$2"
    local state="$TEST_DIR/state/$inst" now_env=""
    mkdir -p "$state"
    [ -n "${CLAIM_NOW:-}" ] && now_env="ORCH_NOW=$CLAIM_NOW"
    env \
        ORCH_INSTANCE_ID="$inst" \
        ORCH_STATE_DIR="$state" \
        TRACKER_CMD="$TRACKER" \
        MOCK_TRACKER_TICKETS_DIR="$MOCK_TRACKER_TICKETS_DIR" \
        MOCK_TRACKER_STATUSES="$MOCK_TRACKER_STATUSES" \
        ORCH_CLAIM_TTL="${CLAIM_TTL:-600}" \
        ORCH_CLAIM_SETTLE_MS="${CLAIM_SETTLE_MS:-0}" \
        ORCH_CLAIM_JITTER_MS="${CLAIM_JITTER_MS:-0}" \
        $now_env \
        bash -c '
            source "$1" >/dev/null 2>&1
            set +e +u +o pipefail
            rc=0; acquire_remote_claim "$2" || rc=$?
            echo "__RC=$rc"
        ' _runner "$ORCH" "$ticket"
}

claim_count() { tracker get "$1" | grep -c "kind: claim" || true; }

echo -e "${CYAN}=== Claim mutual-exclusion across runners (ABS-187) ===${NC}\n"

# =============================================================================
echo -e "${CYAN}Part 1 — Unit (mock): two runners, one contested ticket${NC}"
# =============================================================================
T1="$(tracker create --type ticket --title "contested ticket (sequential)")"

out_a="$(claim_run machine-A "$T1")"
out_b="$(claim_run machine-B "$T1")"

assert_contains "$out_a" "INTENT CLAIM-WON ticket=$T1"   "runner A (first) wins the claim"
assert_contains "$out_a" "__RC=0"                        "runner A returns 0 (win)"
assert_contains "$out_b" "INTENT SKIP-CLAIMED ticket=$T1" "runner B (second) skips the claimed ticket"
assert_contains "$out_b" "holder=machine-A"              "runner B names A as the live holder"
assert_contains "$out_b" "__RC=1"                        "runner B returns 1 (loss)"
wins="$(printf '%s\n%s\n' "$out_a" "$out_b" | grep -c 'INTENT CLAIM-WON' || true)"
skips="$(printf '%s\n%s\n' "$out_a" "$out_b" | grep -c 'INTENT SKIP-CLAIMED' || true)"
assert_eq "$wins" "1" "exactly one CLAIM-WON across the two runners"
assert_eq "$skips" "1" "exactly one SKIP-CLAIMED across the two runners"
assert_eq "$(claim_count "$T1")" "1" "only the winner staked a claim comment (loser stakes nothing)"

echo -e "\n${CYAN}Part 1b — idempotent re-dispatch by the holder (no second stake)${NC}"
out_a2="$(claim_run machine-A "$T1")"
assert_contains "$out_a2" "INTENT CLAIM-WON ticket=$T1" "holder re-dispatch re-wins its own claim"
assert_contains "$out_a2" "reclaim=own idempotent"      "holder re-dispatch is flagged idempotent"
assert_eq "$(claim_count "$T1")" "1" "holder re-dispatch inside the refresh throttle stakes no second claim"

echo -e "\n${CYAN}Part 1c — a claim older than ORCH_CLAIM_TTL is reclaimed${NC}"
T2="$(tracker create --type ticket --title "stale-claim ticket")"
# Stake as A under a 2s TTL, let it age past TTL, then a fresh runner reclaims.
CLAIM_TTL=2 out_stale_a="$(claim_run machine-A "$T2")"
assert_contains "$out_stale_a" "INTENT CLAIM-WON ticket=$T2" "A first-wins the soon-to-be-stale claim"
sleep 3
CLAIM_TTL=2 out_reclaim="$(claim_run machine-C "$T2")"
assert_contains "$out_reclaim" "INTENT CLAIM-WON ticket=$T2" "fresh runner reclaims A's expired (age>TTL) claim"
assert_contains "$out_reclaim" "__RC=0"                      "reclaiming runner returns 0 (win)"

# =============================================================================
echo -e "\n${CYAN}Part 2 — Concurrency harness: N parallel runners, single winner${NC}"
# =============================================================================
T3="$(tracker create --type ticket --title "contested ticket (parallel burst)")"
# Seed the '## Comments' section once so parallel stakers only ever append.
tracker comment "$T3" --kind decision --actor bsa --body "harness seed" >/dev/null
N=4
pids=""
for i in $(seq 1 "$N"); do
    ( CLAIM_SETTLE_MS=300 claim_run "runner-$i" "$T3" > "$TEST_DIR/cout-$i" 2>&1 ) &
    pids="$pids $!"
done
for p in $pids; do wait "$p"; done
all_out="$(cat "$TEST_DIR"/cout-*)"
pwins="$(printf '%s\n' "$all_out" | grep -c 'INTENT CLAIM-WON' || true)"
pskips="$(printf '%s\n' "$all_out" | grep -c 'INTENT SKIP-CLAIMED' || true)"
assert_eq "$pwins" "1"          "exactly one winner among $N parallel runners"
assert_eq "$pskips" "$((N-1))"  "the other $((N-1)) runners all SKIP-CLAIMED"

# =============================================================================
echo -e "\n${CYAN}Part 3 — E2E dry-run: real orchestrator logs claim intents${NC}"
# =============================================================================
export ORCH_STOP_FILE="$TEST_DIR/work/.orchestrator-stop"
export ORCH_SPAWN_CMD="$STUB"
orch_dry() {  # <instance> <extra-env-assignments...> -> runs --dry-run --once
    local inst="$1"; shift
    env "$@" \
        ORCH_INSTANCE_ID="$inst" \
        ORCH_STATE_DIR="$TEST_DIR/e2e-state/$inst" \
        ORCH_RECONCILE_ON_STARTUP=0 \
        TRACKER_CMD="$TRACKER" \
        MOCK_TRACKER_TICKETS_DIR="$MOCK_TRACKER_TICKETS_DIR" \
        MOCK_TRACKER_STATUSES="$MOCK_TRACKER_STATUSES" \
        ORCH_SPAWN_CMD="$STUB" \
        bash "$ORCH" --dry-run --once 2>/dev/null
}

# 3a — fresh ticket: dry-run stakes + wins the claim, then logs the SPAWN intent.
TW="$(tracker create --type ticket --title "e2e win" --role be-developer)"
orch_dry drainer ORCH_CLAIM_MODE=off >/dev/null 2>&1 || true   # drain creation event
tracker transition "$TW" "Ready for Development" --actor po-agent --reason "prioritized" >/dev/null
out_win="$(orch_dry machine-1 ORCH_CLAIM_MODE=on)"
assert_contains "$out_win" "INTENT CLAIM ticket=$TW"     "dry-run logs the CLAIM stake intent"
assert_contains "$out_win" "INTENT CLAIM-WON ticket=$TW" "dry-run logs CLAIM-WON for the uncontested ticket"
assert_contains "$out_win" "INTENT SPAWN ticket=$TW role=be-developer" "a won claim proceeds to the (dry) spawn intent"

# 3b — pre-claimed ticket: a foreign live holder -> dry-run SKIP-CLAIMED, no spawn.
TS="$(tracker create --type ticket --title "e2e skip" --role be-developer)"
tracker comment "$TS" --kind claim --actor orchestrator --body "instance: foreign-machine | at: seed" >/dev/null
orch_dry drainer2 ORCH_CLAIM_MODE=off >/dev/null 2>&1 || true
tracker transition "$TS" "Ready for Development" --actor po-agent --reason "prioritized" >/dev/null
out_skip="$(orch_dry machine-1 ORCH_CLAIM_MODE=on)"
assert_contains "$out_skip" "INTENT SKIP-CLAIMED ticket=$TS" "dry-run logs SKIP-CLAIMED when a foreign runner holds the claim"
assert_contains "$out_skip" "holder=foreign-machine"        "SKIP-CLAIMED names the foreign holder"
assert_not_contains "$out_skip" "INTENT SPAWN ticket=$TS"   "a lost claim spawns nothing"

# =============================================================================
echo ""
if [ "$FAIL" -eq 0 ]; then
    echo -e "${GREEN}=== ALL $TOTAL CHECKS PASSED ===${NC}"
    exit 0
else
    echo -e "${RED}=== $FAIL of $TOTAL CHECKS FAILED ===${NC}"
    exit 1
fi
