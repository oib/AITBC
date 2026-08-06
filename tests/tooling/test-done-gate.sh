#!/bin/bash
# =============================================================================
# Test: Done-gate — PR-merged-before-Done deterministic runner check (ABS-211)
# =============================================================================
# A story reaches `Done` only when its implementation PR is MERGED on the
# target/epic branch. ABS-192 (epic ABS-190): a story reached Done while PR #133
# was still open; the epic JOIN fired on that FALSE signal and the operator had
# to merge the PR and resume. ABS-202 was the sibling case (PR #129). The Docs
# seat only validates doc-completeness, so an unmerged-PR Done was never caught.
#
# done_pr_gate is the fail-CLOSED backstop: whenever a ticket rests in Done with
# a still-open PR it is redirected back to Merging with a naming gate-results
# comment, BEFORE the epic JOIN can fire. It is fail-OPEN for the boilerplate
# placeholder case (no $FORGE_CMD, or no PR / direct-to-branch merge), so a
# Done with a merged PR — or with no PR platform at all — passes unchanged.
#
# The gate's decision logic (story_pr_state normalization) is pure and its side
# effects (redirect + audit comment + run.log event) mirror station_guard, so
# this suite SOURCES scripts/orchestrator.sh (main is source-guarded) and
# exercises the functions directly with a stubbed `forge`, `tracker`, and
# `ticket_still_in` — no real adapter, forge platform, or model is touched.
#
# bash 3.2 + BSD tools only. Run from repo root: bash tests/tooling/test-done-gate.sh
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
assert_contains() {
    local output="$1" expected="$2" label="$3"
    TOTAL=$((TOTAL + 1))
    if grep -qF -- "$expected" <<<"$output"; then echo -e "  ${GREEN}PASS${NC} $label"; PASS=$((PASS + 1))
    else echo -e "  ${RED}FAIL${NC} $label (expected to find: $expected)"
        echo -e "  ${YELLOW}  Output:${NC}"; head -8 <<<"$output" | sed 's/^/    /'; FAIL=$((FAIL + 1)); fi
}
assert_not_contains() {
    local output="$1" expected="$2" label="$3"
    TOTAL=$((TOTAL + 1))
    if ! grep -qF -- "$expected" <<<"$output"; then echo -e "  ${GREEN}PASS${NC} $label"; PASS=$((PASS + 1))
    else echo -e "  ${RED}FAIL${NC} $label (did NOT expect: $expected)"; FAIL=$((FAIL + 1)); fi
}

# Load the runner's functions without starting the poll loop.
source "$REPO_ROOT/scripts/orchestrator.sh" >/dev/null 2>&1

echo -e "${CYAN}=== Done-gate: PR-merged-before-Done (ABS-211) ===${NC}\n"

# --- forge stub: story_pr_state calls `forge pr-state <ticket>`; we return the
#     canned line in $STUB_PR_LINE (what a real $FORGE_CMD adapter would print).
STUB_PR_LINE=""
forge() { printf '%s\n' "$STUB_PR_LINE"; }

# =============================================================================
echo -e "${CYAN}story_pr_state — normalizes the forge line to STATE\\tREF${NC}"
# =============================================================================
FORGE_CMD="stub"
STUB_PR_LINE="MERGED #133"; assert_eq "$(story_pr_state ABS-1)" "$(printf 'MERGED\t#133')" "merged with ref -> MERGED + ref"
STUB_PR_LINE="OPEN #133";   assert_eq "$(story_pr_state ABS-1)" "$(printf 'OPEN\t#133')"   "open with ref -> OPEN + ref"
STUB_PR_LINE="open #99";    assert_eq "$(story_pr_state ABS-1)" "$(printf 'OPEN\t#99')"    "lower-case state is upper-normalized"
STUB_PR_LINE="DECLINED #5"; assert_eq "$(story_pr_state ABS-1)" "$(printf 'DECLINED\t#5')"  "PILOT-20: DECLINED surfaces distinctly (merge-wait escalation), no longer collapsed to OPEN"
STUB_PR_LINE="SUPERSEDED #7"; assert_eq "$(story_pr_state ABS-1)" "$(printf 'OPEN\t#7')"    "any OTHER non-merged live state still fails closed to OPEN"
STUB_PR_LINE="NONE";        assert_eq "$(story_pr_state ABS-1)" "$(printf 'NONE\t')"       "adapter reports NONE -> NONE (no PR)"
STUB_PR_LINE="";            assert_eq "$(story_pr_state ABS-1)" "$(printf 'NONE\t')"       "empty adapter output -> NONE"
FORGE_CMD=""
STUB_PR_LINE="OPEN #133";   assert_eq "$(story_pr_state ABS-1)" "$(printf 'NONE\t')"       "no \$FORGE_CMD -> NONE (placeholder, forge never called)"

# =============================================================================
# done_pr_gate side effects — stub the adapter + status probe (as station-guard).
# =============================================================================
STUB_CALLS=""; STUB_IN=0
tracker() {
    case "$1" in
        get)        : ;;
        comment)    shift; printf 'COMMENT %s\n' "$*" >> "$STUB_CALLS" ;;
        transition) shift; printf 'TRANSITION %s\n' "$*" >> "$STUB_CALLS" ;;
        *)          : ;;
    esac
}
ticket_still_in() { return "$STUB_IN"; }

STUB_CALLS="$(mktemp /tmp/dg-calls-XXXXXX)"
ORCH_RUN_LOG="$(mktemp /tmp/dg-runlog-XXXXXX)"

# run_gate <ticket> <to> — run done_pr_gate, capturing stdout(intent) + rc.
run_gate() {
    : > "$STUB_CALLS"; : > "$ORCH_RUN_LOG"
    local rc=0 out
    out="$(done_pr_gate "$1" "$2" 2>/dev/null)" || rc=$?
    printf '%s\n%s' "$rc" "$out"
}

# =============================================================================
echo -e "\n${CYAN}AC1 — Done with an OPEN PR is caught, redirected to Merging, audited (live)${NC}"
# =============================================================================
MODE="live"; FORGE_CMD="stub"; STUB_IN=0; STUB_PR_LINE="OPEN #133"
res="$(run_gate "ABS-999" "Done")"; rc="${res%%$'\n'*}"; out="${res#*$'\n'}"
assert_eq "$rc" "0" "gate INTERVENES (rc 0) on a Done whose PR is still open"
assert_contains "$out" "INTENT DONE-PR-GATE ticket=ABS-999 role=- to=Merging" "logs the DONE-PR-GATE intent redirecting to Merging"
calls="$(cat "$STUB_CALLS")"
assert_contains "$calls" "TRANSITION ABS-999 Merging" "re-transitions the ticket back to Merging"
assert_contains "$calls" "COMMENT ABS-999 --kind gate-results --actor orchestrator" "posts a naming gate-results comment as the orchestrator"
assert_contains "$calls" "#133" "AC1: the comment NAMES which PR is missing (#133)"
assert_contains "$calls" "ABS-211" "audit comment cites ABS-211"
assert_contains "$(cat "$ORCH_RUN_LOG")" "INTENT-DONE-PR-GATE	ABS-999" "writes an INTENT-DONE-PR-GATE run.log event (AC4)"

# =============================================================================
echo -e "\n${CYAN}AC2 — Done with a MERGED PR passes unchanged (no writes)${NC}"
# =============================================================================
MODE="live"; FORGE_CMD="stub"; STUB_IN=0; STUB_PR_LINE="MERGED #133"
res="$(run_gate "ABS-998" "Done")"; rc="${res%%$'\n'*}"; out="${res#*$'\n'}"
assert_eq "$rc" "1" "merged PR -> no-op (rc 1), Done passes"
assert_not_contains "$out" "INTENT DONE-PR-GATE" "no gate intent when the PR is merged"
assert_eq "$(cat "$STUB_CALLS")" "" "no adapter writes when the PR is merged"

# =============================================================================
echo -e "\n${CYAN}AC2/guardrail — no PR (direct-to-branch) and no forge both fail OPEN${NC}"
# =============================================================================
MODE="live"; FORGE_CMD="stub"; STUB_IN=0; STUB_PR_LINE="NONE"
res="$(run_gate "ABS-997" "Done")"; rc="${res%%$'\n'*}"
assert_eq "${res%%$'\n'*}" "1" "no PR for the story (direct-to-branch) -> no-op (rc 1)"
assert_eq "$(cat "$STUB_CALLS")" "" "no writes when the story has no PR"

MODE="live"; FORGE_CMD=""; STUB_IN=0; STUB_PR_LINE="OPEN #133"
res="$(run_gate "ABS-996" "Done")"; rc="${res%%$'\n'*}"
assert_eq "${res%%$'\n'*}" "1" "no \$FORGE_CMD (boilerplate placeholder) -> gate skipped, Done passes (rc 1)"
assert_eq "$(cat "$STUB_CALLS")" "" "no writes when no forge platform is configured"

# =============================================================================
echo -e "\n${CYAN}Dry-run logs the intent but performs NO adapter writes${NC}"
# =============================================================================
MODE="dry-run"; FORGE_CMD="stub"; STUB_IN=0; STUB_PR_LINE="OPEN #133"
res="$(run_gate "ABS-995" "Done")"; rc="${res%%$'\n'*}"; out="${res#*$'\n'}"
assert_eq "$rc" "0" "dry-run still reports the intervention (rc 0)"
assert_contains "$out" "INTENT DONE-PR-GATE ticket=ABS-995 role=- to=Merging" "dry-run logs the redirect intent"
assert_eq "$(cat "$STUB_CALLS")" "" "dry-run makes NO tracker comment/transition calls"
MODE="live"

# =============================================================================
echo -e "\n${CYAN}AC3 — path-independent: any Done landing with an open PR bounces to Merging${NC}"
# =============================================================================
# The guard/repair chain (qas declares Done directly -> station_guard redirects
# the skip) must never let a story settle in Done without a merged PR. done_pr_gate
# keys only on the resting status + PR state, so it fires regardless of HOW Done
# was reached — closing the Merging-skip-without-PR gap (ABS-202).
MODE="live"; FORGE_CMD="stub"; STUB_IN=0; STUB_PR_LINE="OPEN #129"
res="$(run_gate "ABS-994" "Done")"; rc="${res%%$'\n'*}"
assert_eq "${res%%$'\n'*}" "0" "repair-chain Done with open PR #129 is bounced to Merging (rc 0)"
assert_contains "$(cat "$STUB_CALLS")" "TRANSITION ABS-994 Merging" "AC3: routes back through Merging (no Merging-skip without a merged PR)"

# =============================================================================
echo -e "\n${CYAN}Scoping — non-Done target and already-moved-on ticket are no-ops${NC}"
# =============================================================================
MODE="live"; FORGE_CMD="stub"; STUB_IN=0; STUB_PR_LINE="OPEN #133"
res="$(run_gate "ABS-993" "Docs")"; assert_eq "${res%%$'\n'*}" "1" "to != Done -> no-op (only guards the Done landing)"
STUB_IN=1
res="$(run_gate "ABS-992" "Done")"; assert_eq "${res%%$'\n'*}" "1" "ticket_still_in false (moved on) -> no-op, no stale write"
assert_eq "$(cat "$STUB_CALLS")" "" "no writes once the ticket has left Done"

# =============================================================================
echo -e "\n${CYAN}ABS-267 — the DONE-GATE redirect does not burn a rework unit${NC}"
# =============================================================================
# The redirect is Done(12) -> Merging(10): BACKWARD along the canonical chain, and
# applied as --actor orchestrator. It is the runner's own bookkeeping, not a seat
# rejecting the work, so rework_count() must ignore it — otherwise the gate doing
# its job costs the story a third of its rework budget (ABS-267, ABS-235).
#
# Two halves, asserted together:
#   1. the gate really emits that backward transition as `orchestrator` (drive it);
#   2. the counter really ignores it (feed it the dump such a redirect produces).
MODE="live"; FORGE_CMD="stub"; STUB_IN=0; STUB_PR_LINE="OPEN #133"
run_gate "ABS-267" "Done" >/dev/null   # side effect under test: the recorded adapter calls
calls="$(cat "$STUB_CALLS")"
assert_contains "$calls" "TRANSITION ABS-267 Merging" "the gate's redirect really is the backward move Done -> Merging"
assert_contains "$calls" "--actor orchestrator" "the gate's redirect really is applied as --actor orchestrator"

# The dump the redirect above produces, in the adapter's verbatim comment format.
# (Built here rather than walked through the mock tracker: the neutral profile's
# statuses.yaml has no Done -> Merging edge, so that adapter rejects the move. The
# counter parses dump TEXT, which is exactly what is reproduced here.) A GENUINE
# qas bounce rides along, so the same dump proves the counter is still live.
dg_dump="$(cat <<'EOF'
### 2026-07-13T10:00:00Z | kind: transition-reason | actor: qas

Transition: In Test -> In Progress. Reason: rework: test fail

### 2026-07-13T11:00:00Z | kind: transition-reason | actor: orchestrator

Transition: Done -> Merging. Reason: DONE-GATE: implementation PR #133 not merged (OPEN) — redirect Done -> Merging (ABS-211)
EOF
)"
assert_eq "$(rework_count "$dg_dump")" "1" "AC4: DONE-GATE redirect burns NO unit; the genuine qas bounce still counts"

# --- cleanup temp files -------------------------------------------------------
rm -f "$STUB_CALLS" "$ORCH_RUN_LOG" 2>/dev/null || true

# =============================================================================
echo -e "\n${CYAN}=== Test Results ===${NC}\n"
echo -e "  Total:  $TOTAL"
echo -e "  ${GREEN}Passed: $PASS${NC}"
if [ "$FAIL" -gt 0 ]; then
    echo -e "  ${RED}Failed: $FAIL${NC}"; exit 1
else
    echo -e "  Failed: 0"; echo -e "\n  ${GREEN}ALL TESTS PASSED${NC}\n"; exit 0
fi
