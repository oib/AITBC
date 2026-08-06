#!/bin/bash
# =============================================================================
# Test: Resume-spawn SPAWN_CWD re-derivation (ABS-194)
# =============================================================================
# Origin — ABS-166 (Operator, 2026-07-09): a be-developer RESUME spawn ran in
# the MAIN checkout despite an existing worktree tmp/ABS-166-work; its Write/Edit
# were denied by the .claude guard and it burned a full escalation cycle. The
# resume/race path had lost ORCH_SPAWN_CWD. The fix re-derives the effective seat
# cwd at the single spawn choke point (run_spawn_cmd) identically to the first
# spawn (worktree_for <ticket>) instead of falling back to the main checkout,
# and logs the resolved cwd per spawn (SEAT-CWD run.log event).
#
# The derivation (resolve_seat_cwd / worktree_eligible_status) is pure, so this
# suite SOURCES scripts/orchestrator.sh (main is source-guarded) and exercises
# the functions directly — same pattern as tests/test-station-guard.sh. No real
# adapter, worktree provisioning or model is touched.
#
# bash 3.2 + BSD tools only. Run from repo root: bash tests/tooling/test-resume-cwd.sh
# =============================================================================

set -euo pipefail

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
assert_true() {  # <cmd...> -- last arg is the label
    local label="${!#}"; set -- "${@:1:$(($#-1))}"
    TOTAL=$((TOTAL + 1))
    if "$@"; then echo -e "  ${GREEN}PASS${NC} $label"; PASS=$((PASS + 1))
    else echo -e "  ${RED}FAIL${NC} $label (expected true, got false)"; FAIL=$((FAIL + 1)); fi
}
assert_false() {
    local label="${!#}"; set -- "${@:1:$(($#-1))}"
    TOTAL=$((TOTAL + 1))
    if "$@"; then echo -e "  ${RED}FAIL${NC} $label (expected false, got true)"; FAIL=$((FAIL + 1))
    else echo -e "  ${GREEN}PASS${NC} $label"; PASS=$((PASS + 1)); fi
}

# Load the runner's functions without starting the poll loop.
source "$REPO_ROOT/scripts/orchestrator.sh" >/dev/null 2>&1

# Isolated fake state root so worktree_for points at a scratch dir we control.
ORCH_STATE_ROOT="$(mktemp -d /tmp/orch-resume-cwd-XXXXXX)"
TICKET="ABS-166"
WT="$(worktree_for "$TICKET")"          # $ORCH_STATE_ROOT/tmp/ABS-166-work
mkdir -p "$WT"                          # simulate an EXISTING provisioned worktree
cleanup() { rm -rf "$ORCH_STATE_ROOT" 2>/dev/null || true; }
trap cleanup EXIT

echo -e "${CYAN}=== Resume-spawn SPAWN_CWD re-derivation (ABS-194) ===${NC}\n"

# =============================================================================
echo -e "${CYAN}worktree_eligible_status — the C9 worktree seats, nothing else${NC}"
# =============================================================================
assert_true  worktree_eligible_status "Ready for Development" "Ready for Development is worktree-eligible"
assert_true  worktree_eligible_status "In Review"             "In Review is worktree-eligible"
assert_true  worktree_eligible_status "In Test"               "In Test is worktree-eligible"
assert_true  worktree_eligible_status "In Progress"           "In Progress IS worktree-eligible (ABS-207 BOUNCE-REROUTE resume)"
assert_false worktree_eligible_status "Done"                  "Done is NOT worktree-eligible"
assert_false worktree_eligible_status "Backlog"               "Backlog is NOT worktree-eligible"

# =============================================================================
echo -e "\n${CYAN}AC1/AC3 — a resume with a LOST cwd re-derives the worktree, no main-checkout fallback${NC}"
# =============================================================================
# The lost-cwd resume: SPAWN_CWD empty (the global never populated on this path),
# worktree spawns on, an existing worktree on disk.
export ORCH_WORKTREE_SPAWNS=1
SPAWN_CWD=""
assert_eq "$(resolve_seat_cwd "$TICKET" "Ready for Development")" "$WT" \
    "resume with empty SPAWN_CWD re-derives the existing worktree (NOT the main checkout)"

# The re-derived path is byte-identical to what the FIRST spawn would set.
assert_eq "$(resolve_seat_cwd "$TICKET" "Ready for Development")" "$(worktree_for "$TICKET")" \
    "resume derivation == first-spawn derivation (worktree_for), no divergence"

# In Review / In Test resumes (reviewer/qas seats) re-derive too.
SPAWN_CWD=""
assert_eq "$(resolve_seat_cwd "$TICKET" "In Review")" "$WT" "In Review resume re-derives the worktree"
SPAWN_CWD=""
assert_eq "$(resolve_seat_cwd "$TICKET" "In Test")"   "$WT" "In Test resume re-derives the worktree"

# =============================================================================
echo -e "\n${CYAN}AC4 — first spawn (SPAWN_CWD already set) is returned verbatim, no regress${NC}"
# =============================================================================
# The first-spawn path: live_spawn already resolved SPAWN_CWD; resolve_seat_cwd
# must hand it back unchanged (parallel non-resume spawns keep their worktree).
SPAWN_CWD="$WT"
assert_eq "$(resolve_seat_cwd "$TICKET" "Ready for Development")" "$WT" \
    "first spawn: an already-set SPAWN_CWD passes through unchanged"

# A distinct sibling-ticket worktree set by its own subshell is honored as-is
# (each async spawn carries its own SPAWN_CWD — no cross-ticket clobber).
SPAWN_CWD="$ORCH_STATE_ROOT/tmp/ABS-170-work"
assert_eq "$(resolve_seat_cwd "ABS-170" "Ready for Development")" "$ORCH_STATE_ROOT/tmp/ABS-170-work" \
    "first spawn: sibling ticket keeps its own SPAWN_CWD (parallel spawns unaffected)"

# =============================================================================
echo -e "\n${CYAN}Guard rails — never invent a missing worktree, never re-derive for non-worktree seats${NC}"
# =============================================================================
# Provisioning stays fail-closed in live_spawn: resolve_seat_cwd must NOT
# materialize a cwd for a worktree that does not exist on disk.
SPAWN_CWD=""
assert_eq "$(resolve_seat_cwd "ABS-999-missing" "Ready for Development")" "" \
    "no worktree on disk -> empty (never invents one; provisioning stays fail-closed)"

# In Progress became worktree-eligible with ABS-207 (BOUNCE-REROUTE resume runs
# in the ticket worktree) — the resume re-derives the same tree as a first spawn.
SPAWN_CWD=""
assert_eq "$(resolve_seat_cwd "$TICKET" "In Progress")" "$WT" \
    "In Progress (eligible since ABS-207) -> re-derives the ticket worktree"

# Worktree spawns disabled -> honor the operator opt-out (repo-root cwd).
export ORCH_WORKTREE_SPAWNS=0
SPAWN_CWD=""
assert_eq "$(resolve_seat_cwd "$TICKET" "Ready for Development")" "" \
    "ORCH_WORKTREE_SPAWNS=0 -> empty (operator opt-out honored)"
export ORCH_WORKTREE_SPAWNS=1

# =============================================================================
echo -e "\n${CYAN}AC2 — every spawn emits a SEAT-CWD diagnostic line with ticket-id + effective cwd${NC}"
# =============================================================================
# The diagnostic is a structured run.log event (runlog SEAT-CWD). Drive it
# directly and assert the ticket + resolved cwd land in the row.
export ORCH_RUN_LOG="$ORCH_STATE_ROOT/run.log"
: > "$ORCH_RUN_LOG"
runlog SEAT-CWD "$TICKET" "be-developer" "Ready for Development" "cwd=$WT"
seatcwd_row="$(grep 'SEAT-CWD' "$ORCH_RUN_LOG" | head -1)"
assert_true grep -q "SEAT-CWD" "$ORCH_RUN_LOG" "SEAT-CWD diagnostic row is emitted to run.log"
case "$seatcwd_row" in
    *"$TICKET"*"cwd=$WT"*) diag_ok=1 ;;
    *) diag_ok=0 ;;
esac
assert_eq "$diag_ok" "1" "SEAT-CWD row carries the ticket-id AND the resolved worktree cwd (AC3: log shows the worktree path)"

# =============================================================================
echo -e "\n${CYAN}=== Test Results ===${NC}\n"
echo -e "  Total:  $TOTAL"
echo -e "  ${GREEN}Passed: $PASS${NC}"
if [ "$FAIL" -gt 0 ]; then
    echo -e "  ${RED}Failed: $FAIL${NC}"; exit 1
else
    echo -e "  Failed: 0"; echo -e "\n  ${GREEN}ALL TESTS PASSED${NC}\n"; exit 0
fi
