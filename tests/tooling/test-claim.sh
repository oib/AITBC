#!/bin/bash
# =============================================================================
# Test: Distributed whole-ticket remote claim (ABS-184, spec §4.3–4.4)
# =============================================================================
# The claim adjudication logic (claim_blocks / first_live_claim /
# own_latest_claim_age) is pure, and acquire_remote_claim / refresh_claim have
# only adapter side effects, so this suite SOURCES scripts/orchestrator.sh (main
# is source-guarded) and exercises the functions directly.
#
# The scheduling clock is injected with ORCH_NOW and the settle sleep is pinned
# to 0ms, so every scenario is deterministic and instant. `tracker` is stubbed
# with an in-file "server" that accumulates claim comments, stamping each with a
# server-assigned `### <at>` header at a test-controlled epoch (FAKE_STAKE_EPOCH)
# — this is the ONLY way to exercise TTL staleness and cross-machine ordering,
# since the real adapter stamps headers with the live wall clock.
#
# Covers all ABS-184 acceptance criteria + DoD unit cases:
#   - exactly one of two concurrent claimants wins
#   - adjudication uses dump (server-creation) order, not the body `at:`
#   - staleness reads the server `### <at>` header, not the body `at:` (BSA AC)
#   - a claim older than ORCH_CLAIM_TTL is reclaimed; a fresh one is not
#   - the holder re-dispatching re-reads its own claim and wins without staking
#   - refresh is throttled to ~TTL/3
#   - a peer never wins for a full >TTL spawn while the holder heartbeats (BSA AC)
#
# bash 3.2 + BSD tools only. Run from repo root: bash tests/tooling/test-claim.sh
# =============================================================================

set -euo pipefail
# PILOT-46: strip inherited backend/tracker env before any fixture runs (tests/sandbox-guard.sh).
# shellcheck source=tests/sandbox-guard.sh
. "$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)/sandbox-guard.sh"

# ABS-285: scrub ambient ORCH_* before driving the real seam/runner. A seat
# exports ~37 of them; a non-empty one leaks into the code under test and makes
# the result a function of the calling seat instead of the commit. Prefix-unset
# covers vars added later. This test sets every ORCH_* it needs, below.
unset "${!ORCH_@}"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"

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
        echo -e "  ${YELLOW}  Output:${NC}"; echo "$output" | head -8 | sed 's/^/    /'; FAIL=$((FAIL + 1)); fi
}
assert_not_contains() {
    local output="$1" expected="$2" label="$3"
    TOTAL=$((TOTAL + 1))
    if ! echo "$output" | grep -qF -- "$expected"; then echo -e "  ${GREEN}PASS${NC} $label"; PASS=$((PASS + 1))
    else echo -e "  ${RED}FAIL${NC} $label (did NOT expect: $expected)"; FAIL=$((FAIL + 1)); fi
}

# --- Deterministic clock + settle window --------------------------------------
NOW=1000000000                       # fixed scheduling clock (round epoch)
export ORCH_NOW=$NOW
export ORCH_CLAIM_TTL=600
export ORCH_CLAIM_SETTLE_MS=0        # no real sleep in tests
export ORCH_CLAIM_JITTER_MS=0

# Load the runner's functions without starting the poll loop.
source "$REPO_ROOT/scripts/orchestrator.sh" >/dev/null 2>&1

# epoch_to_iso <epoch> — UTC ISO-8601 for a unix time (BSD `-r`, GNU `-d @`).
epoch_to_iso() {
    date -u -r "$1" +%Y-%m-%dT%H:%M:%SZ 2>/dev/null || date -u -d "@$1" +%Y-%m-%dT%H:%M:%SZ
}

# claim_block <instance> <server-epoch> [body-at-iso] — render one `kind: claim`
# comment block as the adapter's `get` dump would. Body `at:` defaults to the
# server header time but is set independently in the "ignore body at:" tests.
claim_block() {
    local inst="$1" at_iso body_at
    at_iso="$(epoch_to_iso "$2")"
    body_at="${3:-$at_iso}"
    printf '\n### %s | kind: claim | actor: orchestrator\n\ninstance: %s | at: %s\n' \
        "$at_iso" "$inst" "$body_at"
}

# fenced <status> <body...> — wrap comment body in a minimal frontmatter dump.
fenced() {
    local status="$1"; shift
    printf -- '---\nid: CLAIM-1\nstatus: %s\n---\n%s' "$status" "$*"
}

# --- Stubbed adapter: an in-file server that accumulates claim comments --------
SERVER=""
FAKE_STAKE_EPOCH=""   # server header epoch used when the stub records a stake
new_server() {
    SERVER="$(mktemp /tmp/claim-server-XXXXXX)"
    printf -- '---\nid: CLAIM-1\nstatus: %s\n---\n' "${1:-In Progress}" > "$SERVER"
}
claim_count() { grep -c '^instance:' "$SERVER" 2>/dev/null || echo 0; }

tracker() {
    case "$1" in
        get) cat "$SERVER" ;;
        comment)
            shift
            local body=""
            while [ $# -gt 0 ]; do
                case "$1" in --body) body="$2"; shift 2 ;; *) shift ;; esac
            done
            printf '\n### %s | kind: claim | actor: orchestrator\n\n%s\n' \
                "$(epoch_to_iso "${FAKE_STAKE_EPOCH:-$ORCH_NOW}")" "$body" >> "$SERVER"
            ;;
        *) : ;;
    esac
}

echo -e "${CYAN}=== Distributed remote claim (ABS-184) ===${NC}\n"

# =============================================================================
echo -e "${CYAN}claim_blocks — one line per claim, server-at + instance, in dump order${NC}"
# =============================================================================
DUMP="$(fenced "In Progress" \
    "$(claim_block inst-A $((NOW-100)))$(claim_block inst-B $((NOW-50)))")"
assert_eq "$(claim_blocks "$DUMP" | wc -l | tr -d ' ')" "2" "two claim comments -> two rows"
assert_eq "$(claim_blocks "$DUMP" | awk 'NR==1{print $2}')" "inst-A" "first row = first (oldest) claim in dump order"

# =============================================================================
echo -e "\n${CYAN}AC: adjudication uses dump (server-creation) order, NOT body at:${NC}"
# =============================================================================
# First-in-dump claim carries a LATER body at: than the second; the winner must
# still be the first in dump order (body at: is never consulted for ordering).
DUMP="$(fenced "In Progress" \
    "$(claim_block inst-first $((NOW-100)) "$(epoch_to_iso $((NOW-10)))")$(claim_block inst-second $((NOW-50)) "$(epoch_to_iso $((NOW-90)))")")"
assert_eq "$(first_live_claim "$DUMP")" "inst-first" "first live claim = first in dump order, ignoring body at:"

# =============================================================================
echo -e "\n${CYAN}AC (BSA): staleness reads the server ### <at> header, NOT body at:${NC}"
# =============================================================================
# Body at: is fresh (now) but the server header is beyond TTL -> reclaimed.
DUMP="$(fenced "In Progress" \
    "$(claim_block inst-A $((NOW-700)) "$(epoch_to_iso $NOW)")")"
assert_eq "$(first_live_claim "$DUMP")" "" "server-header-stale claim reclaimed even though body at: is fresh"

# =============================================================================
echo -e "\n${CYAN}AC: a claim older than ORCH_CLAIM_TTL is reclaimed; a fresh one is not${NC}"
# =============================================================================
assert_eq "$(first_live_claim "$(fenced "In Progress" "$(claim_block inst-A $((NOW-601)))")")" "" \
    "age 601s (> TTL 600) -> reclaimed (no holder)"
assert_eq "$(first_live_claim "$(fenced "In Progress" "$(claim_block inst-A $((NOW-599)))")")" "inst-A" \
    "age 599s (< TTL 600) -> still the holder"

# =============================================================================
echo -e "\n${CYAN}AC: a terminal-status ticket's claim is ignored${NC}"
# =============================================================================
assert_eq "$(first_live_claim "$(fenced "Done" "$(claim_block inst-A $NOW)")")" "" \
    "fresh claim on a Done ticket -> ignored (no holder)"

# =============================================================================
echo -e "\n${CYAN}AC: exactly one of two concurrent claimants wins${NC}"
# =============================================================================
# Both stake before either adjudicates; adjudication is deterministic on server
# creation order, so first_live_claim names a single winner and the other loses.
new_server
FAKE_STAKE_EPOCH=$NOW       ORCH_INSTANCE_ID=inst-A stake_claim CLAIM-1
FAKE_STAKE_EPOCH=$((NOW+1)) ORCH_INSTANCE_ID=inst-B stake_claim CLAIM-1
DUMP="$(tracker get CLAIM-1)"
winner="$(first_live_claim "$DUMP")"
assert_eq "$winner" "inst-A" "single deterministic winner across two concurrent stakes"
a_wins=$([ "$winner" = "inst-A" ] && echo 1 || echo 0)
b_wins=$([ "$winner" = "inst-B" ] && echo 1 || echo 0)
assert_eq "$((a_wins + b_wins))" "1" "exactly one claimant wins (not zero, not two)"

# End-to-end intent paths: A acquires and wins, B arrives after and loses.
# (`if` guards keep the loser's rc 1 from tripping `set -e` on the capture.)
new_server
if outA="$(ORCH_INSTANCE_ID=inst-A acquire_remote_claim CLAIM-1)"; then rcA=0; else rcA=$?; fi
if outB="$(ORCH_INSTANCE_ID=inst-B acquire_remote_claim CLAIM-1)"; then rcB=0; else rcB=$?; fi
assert_eq "$rcA" "0" "first claimant returns win (rc 0)"
assert_contains "$outA" "INTENT CLAIM-WON ticket=CLAIM-1" "winner emits CLAIM-WON"
assert_eq "$rcB" "1" "second claimant returns loss (rc 1)"
assert_contains "$outB" "INTENT SKIP-CLAIMED ticket=CLAIM-1" "loser emits SKIP-CLAIMED"

# =============================================================================
echo -e "\n${CYAN}AC: holder re-dispatch re-reads its own claim and wins WITHOUT a second stake${NC}"
# =============================================================================
new_server
FAKE_STAKE_EPOCH=$((NOW-10)) ORCH_INSTANCE_ID=inst-A stake_claim CLAIM-1   # own, fresh (age 10 < throttle 200)
before="$(claim_count)"
if out="$(ORCH_INSTANCE_ID=inst-A acquire_remote_claim CLAIM-1)"; then rc=0; else rc=$?; fi
after="$(claim_count)"
assert_eq "$rc" "0" "holder re-dispatch wins (rc 0)"
assert_contains "$out" "INTENT CLAIM-WON ticket=CLAIM-1" "idempotent re-read emits CLAIM-WON"
assert_not_contains "$out" "INTENT CLAIM ticket=CLAIM-1" "no fresh stake intent on idempotent re-read"
assert_eq "$after" "$before" "no second claim comment posted (throttled refresh was a no-op)"

# =============================================================================
echo -e "\n${CYAN}AC: refresh is throttled to ~TTL/3${NC}"
# =============================================================================
# throttle window = ORCH_CLAIM_TTL / 3 = 200s.
new_server
FAKE_STAKE_EPOCH=$((NOW-10)) ORCH_INSTANCE_ID=inst-A stake_claim CLAIM-1    # age 10 < 200
FAKE_STAKE_EPOCH=$NOW        ORCH_INSTANCE_ID=inst-A refresh_claim CLAIM-1
assert_eq "$(claim_count)" "1" "refresh within throttle window -> no re-stake"

new_server
FAKE_STAKE_EPOCH=$((NOW-300)) ORCH_INSTANCE_ID=inst-A stake_claim CLAIM-1   # age 300 >= 200
FAKE_STAKE_EPOCH=$NOW         ORCH_INSTANCE_ID=inst-A refresh_claim CLAIM-1
assert_eq "$(claim_count)" "2" "refresh past throttle window -> re-stakes"

# =============================================================================
echo -e "\n${CYAN}AC (BSA): peer never wins for a full >TTL spawn while the holder heartbeats${NC}"
# =============================================================================
new_server
FAKE_STAKE_EPOCH=$NOW ORCH_INSTANCE_ID=inst-A stake_claim CLAIM-1
peer_lost_every_time=1
step=$((ORCH_CLAIM_TTL / 3))              # heartbeat cadence 200s (< TTL 600)
t=0
while [ "$t" -le $((2 * ORCH_CLAIM_TTL)) ]; do
    cur=$((NOW + t))
    export ORCH_NOW=$cur
    FAKE_STAKE_EPOCH=$cur ORCH_INSTANCE_ID=inst-A refresh_claim CLAIM-1
    if FAKE_STAKE_EPOCH=$cur ORCH_INSTANCE_ID=inst-B acquire_remote_claim CLAIM-1 >/dev/null 2>&1; then
        peer_lost_every_time=0
    fi
    t=$((t + step))
done
export ORCH_NOW=$NOW
assert_eq "$peer_lost_every_time" "1" "peer's acquire returns false for the whole 2*TTL heartbeated spawn"

# =============================================================================
echo -e "\n${CYAN}=== Results: ${GREEN}$PASS passed${NC}, ${RED}$FAIL failed${NC}, $TOTAL total ===${NC}"
[ "$FAIL" -eq 0 ] || exit 1
