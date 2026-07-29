#!/bin/bash
# =============================================================================
# Test: Ready-for-Merge MR-existence gate + self-heal (ABS-454)
# =============================================================================
# A story rests at `Ready for Merge` (the human merge gate) only when its MR
# actually EXISTS — open OR merged. On 2026-07-18 three stories reached it with
# NO mirrored MR and stalled human-invisibly: ABS-425 (branch pushed, MR-create
# failed), ABS-420 (no MR), ABS-416 (branch only local — push + MR lost in a
# runner restart); the operator repaired all three by hand (ABS-354 class).
#
# ready_for_merge_mr_gate is the SELF-HEAL backstop: when a story rests at
# `Ready for Merge` with NO MR at all it is redirected back to `Merging` with a
# naming gate-results comment, so the RTE respawn (re)pushes the branch AND
# creates the MR (a stall becomes an automatic recovery). It fires ONLY on state
# NONE: an OPEN MR (the ABS-270 docs_pr_gate merge-wait park) and a MERGED MR are
# both satisfied and left untouched (no false alarm). It is fail-OPEN for the
# placeholder case (no $FORGE_CMD), so a run with no MR platform is unchanged.
#
# ABS-481 adds the never-pushed / lost-push half, checked FIRST and independently
# of $FORGE_CMD: story_branch_remote_state probes the ACTIVE remote(s) for the
# story branch and the gate self-heals a local-only branch (ABSENT) or fails LOUD
# on degraded connectivity (UNREACHABLE) instead of silent-passing the merge gate.
# This suite covers both the pure helper (against a temp local bare remote — no
# network) and the gate's wiring (via a stubbed story_branch_remote_state).
#
# The gate's side effects (redirect + audit comment + run.log event) mirror
# done_pr_gate, so this suite SOURCES scripts/orchestrator.sh (main is
# source-guarded) and exercises the function directly with a stubbed `forge`,
# `tracker`, and `ticket_still_in` — no real adapter, forge platform, or model.
#
# bash 3.2 + BSD tools only. Run from repo root:
#   bash tests/test-ready-for-merge-gate.sh
# =============================================================================

set -euo pipefail

# ABS-285: scrub ambient ORCH_* before driving the real seam/runner.
unset "${!ORCH_@}"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

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

echo -e "${CYAN}=== Ready-for-Merge MR-existence gate + self-heal (ABS-454 / ABS-481) ===${NC}\n"

# =============================================================================
echo -e "${CYAN}ABS-481 helper — story_branch_remote_state resolves the branch against the ACTIVE remote${NC}"
# =============================================================================
# Exercise the REAL helper (before any stub shadows it) against a temp local bare
# "remote" — fully hermetic, no network. Reproduces the ABS-461 defect: a branch
# committed locally but NEVER pushed reads as ABSENT (the never-pushed case the MR
# probe misses), a pushed branch reads FOUND, an unreachable remote fails LOUD as
# UNREACHABLE (never silent-passes), and a repo with no remotes is NOREMOTE.
_bh_tmp="$(mktemp -d "${TMPDIR:-/tmp}/rfm-branch-XXXXXX")"
git init -q --bare "$_bh_tmp/remote.git"
git init -q "$_bh_tmp/work"
(
  cd "$_bh_tmp/work"
  git config user.email t@t; git config user.name t
  git commit -q --allow-empty -m init
  git remote add gitlab "$_bh_tmp/remote.git"     # active remote = a plain local path
  git checkout -q -b ABS-461-auto                 # story branch, committed but NOT pushed
  git commit -q --allow-empty -m feat
)
ORCH_STATE_ROOT_SAVE="${ORCH_STATE_ROOT:-}"
ORCH_STATE_ROOT="$_bh_tmp/work"

assert_eq "$(story_branch_remote_state ABS-461)" "ABSENT" \
    "local-only branch (never pushed) -> ABSENT (the ABS-461 never-pushed case)"

git -C "$_bh_tmp/work" push -q gitlab ABS-461-auto
assert_eq "$(story_branch_remote_state ABS-461)" "FOUND" \
    "once the branch is pushed to the active remote -> FOUND"

# Degraded connectivity: point the only remote at an unreachable URL. ls-remote
# errors (non-zero) -> no remote answered -> UNREACHABLE (fail-loud, not FOUND).
git -C "$_bh_tmp/work" remote set-url gitlab "file://$_bh_tmp/does-not-exist.git"
ORCH_REMOTE_PROBE_TIMEOUT=3 \
    assert_eq "$(story_branch_remote_state ABS-461)" "UNREACHABLE" \
    "unreachable remote -> UNREACHABLE (degraded connectivity fails loud, not silent-pass)"

git -C "$_bh_tmp/work" remote remove gitlab
assert_eq "$(story_branch_remote_state ABS-461)" "NOREMOTE" \
    "no git remote configured (placeholder) -> NOREMOTE (fail-open)"

ORCH_STATE_ROOT="$ORCH_STATE_ROOT_SAVE"
rm -rf "$_bh_tmp" 2>/dev/null || true
echo

# --- forge stub: story_pr_state calls `forge pr-state <ticket>`; return the
#     canned line in $STUB_PR_LINE (what a real $FORGE_CMD adapter would print).
STUB_PR_LINE=""
forge() { printf '%s\n' "$STUB_PR_LINE"; }

# --- branch-state stub: the gate calls story_branch_remote_state first (ABS-481).
#     Default FOUND so the MR-probe cases below exercise the ABS-454 half unchanged;
#     the ABS-481 gate-wiring cases set $STUB_BRANCH_STATE to ABSENT / UNREACHABLE.
STUB_BRANCH_STATE="FOUND"
story_branch_remote_state() { printf '%s' "$STUB_BRANCH_STATE"; }

# --- adapter + status-probe stubs (as station-guard / done-gate).
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

STUB_CALLS="$(mktemp "${TMPDIR:-/tmp}/rfm-calls-XXXXXX")"
ORCH_RUN_LOG="$(mktemp "${TMPDIR:-/tmp}/rfm-runlog-XXXXXX")"

# run_gate <ticket> <to> — run ready_for_merge_mr_gate, capturing stdout(intent) + rc.
run_gate() {
    : > "$STUB_CALLS"; : > "$ORCH_RUN_LOG"
    local rc=0 out
    out="$(ready_for_merge_mr_gate "$1" "$2" 2>/dev/null)" || rc=$?
    printf '%s\n%s' "$rc" "$out"
}

# =============================================================================
echo -e "${CYAN}AC1 — Ready for Merge with NO MR is detected, self-healed to Merging, audited (live)${NC}"
# =============================================================================
MODE="live"; FORGE_CMD="stub"; STUB_IN=0; STUB_PR_LINE="NONE"
res="$(run_gate "ABS-999" "Ready for Merge")"; rc="${res%%$'\n'*}"; out="${res#*$'\n'}"
assert_eq "$rc" "0" "gate INTERVENES (rc 0) on a Ready-for-Merge story with no MR"
assert_contains "$out" "INTENT READY-FOR-MERGE-NO-MR ticket=ABS-999 role=- to=Merging" "logs the no-MR self-heal intent redirecting to Merging"
calls="$(cat "$STUB_CALLS")"
assert_contains "$calls" "TRANSITION ABS-999 Merging" "re-transitions the ticket back to Merging (self-heal, not stall)"
assert_contains "$calls" "--expect-from Ready for Merge" "the redirect is guarded with --expect-from (lost race NOOPs, ABS-198)"
assert_contains "$calls" "COMMENT ABS-999 --kind gate-results --actor orchestrator" "posts a naming gate-results comment as the orchestrator"
assert_contains "$calls" "ABS-454" "audit comment cites ABS-454"
assert_contains "$calls" "RTE respawn" "comment names the self-heal: the RTE respawn creates the MR"
assert_contains "$(cat "$ORCH_RUN_LOG")" "INTENT-READY-FOR-MERGE-NO-MR	ABS-999" "writes an INTENT-READY-FOR-MERGE-NO-MR run.log event"

# =============================================================================
echo -e "\n${CYAN}AC2 — a MERGED MR passes unchanged (no false alarm, no writes)${NC}"
# =============================================================================
MODE="live"; FORGE_CMD="stub"; STUB_IN=0; STUB_PR_LINE="MERGED #700"
res="$(run_gate "ABS-998" "Ready for Merge")"; rc="${res%%$'\n'*}"; out="${res#*$'\n'}"
assert_eq "$rc" "1" "merged MR -> no-op (rc 1), the human merge gate keeps resting"
assert_not_contains "$out" "INTENT READY-FOR-MERGE-NO-MR" "no gate intent when the MR is merged"
assert_eq "$(cat "$STUB_CALLS")" "" "no adapter writes when the MR is merged"

# =============================================================================
echo -e "\n${CYAN}AC2 — an OPEN MR (docs_pr_gate merge-wait park) is left untouched${NC}"
# =============================================================================
# ABS-270 rests a green story with an OPEN, unmerged MR at Ready for Merge, waiting
# on the human. That is a LEGITIMATE rest — the gate must NOT redirect it (no false
# alarm), because an MR exists; only a NONE state is the defect.
MODE="live"; FORGE_CMD="stub"; STUB_IN=0; STUB_PR_LINE="OPEN #700"
res="$(run_gate "ABS-997" "Ready for Merge")"; rc="${res%%$'\n'*}"
assert_eq "$rc" "1" "open MR (merge-wait park) -> no-op (rc 1), not redirected"
assert_eq "$(cat "$STUB_CALLS")" "" "no writes for a legitimate open-MR merge-wait park (no false alarm)"

# =============================================================================
echo -e "\n${CYAN}Placeholder / guardrail — no \$FORGE_CMD fails OPEN${NC}"
# =============================================================================
MODE="live"; FORGE_CMD=""; STUB_IN=0; STUB_PR_LINE="NONE"
res="$(run_gate "ABS-996" "Ready for Merge")"; rc="${res%%$'\n'*}"
assert_eq "$rc" "1" "no \$FORGE_CMD (boilerplate placeholder) -> gate skipped (rc 1)"
assert_eq "$(cat "$STUB_CALLS")" "" "no writes when no forge platform is configured"

# =============================================================================
echo -e "\n${CYAN}Dry-run logs the intent but performs NO adapter writes${NC}"
# =============================================================================
MODE="dry-run"; FORGE_CMD="stub"; STUB_IN=0; STUB_PR_LINE="NONE"
res="$(run_gate "ABS-995" "Ready for Merge")"; rc="${res%%$'\n'*}"; out="${res#*$'\n'}"
assert_eq "$rc" "0" "dry-run still reports the intervention (rc 0)"
assert_contains "$out" "INTENT READY-FOR-MERGE-NO-MR ticket=ABS-995 role=- to=Merging" "dry-run logs the redirect intent"
assert_eq "$(cat "$STUB_CALLS")" "" "dry-run makes NO tracker comment/transition calls"
MODE="live"

# =============================================================================
echo -e "\n${CYAN}Scoping — non-Ready-for-Merge target and moved-on ticket are no-ops${NC}"
# =============================================================================
MODE="live"; FORGE_CMD="stub"; STUB_IN=0; STUB_PR_LINE="NONE"
res="$(run_gate "ABS-994" "Merging")"; assert_eq "${res%%$'\n'*}" "1" "to != Ready for Merge -> no-op (only guards the merge-gate rest)"
res="$(run_gate "ABS-993" "Done")";    assert_eq "${res%%$'\n'*}" "1" "to = Done -> no-op (done_pr_gate owns that landing)"
STUB_IN=1
res="$(run_gate "ABS-992" "Ready for Merge")"; assert_eq "${res%%$'\n'*}" "1" "ticket_still_in false (moved on) -> no-op, no stale write"
assert_eq "$(cat "$STUB_CALLS")" "" "no writes once the ticket has left Ready for Merge"

# =============================================================================
echo -e "\n${CYAN}ABS-481 AC1 — a local-only (never-pushed) branch is self-healed to Merging${NC}"
# =============================================================================
# The ABS-461 regression: branch committed but never pushed, so no remote branch
# and no MR. The gate must self-heal (redirect to Merging so the RTE re-pushes),
# INDEPENDENTLY of $FORGE_CMD — the never-pushed gap is checked before the MR probe.
MODE="live"; FORGE_CMD=""; STUB_IN=0; STUB_BRANCH_STATE="ABSENT"; STUB_PR_LINE="NONE"
res="$(run_gate "ABS-461" "Ready for Merge")"; rc="${res%%$'\n'*}"; out="${res#*$'\n'}"
assert_eq "$rc" "0" "local-only branch -> gate INTERVENES (rc 0) even with NO \$FORGE_CMD"
assert_contains "$out" "INTENT READY-FOR-MERGE-NO-BRANCH ticket=ABS-461 role=- to=Merging" "logs the no-branch self-heal intent redirecting to Merging"
calls="$(cat "$STUB_CALLS")"
assert_contains "$calls" "TRANSITION ABS-461 Merging" "re-transitions to Merging so the RTE respawn pushes the branch (not a silent NOOP)"
assert_contains "$calls" "--expect-from Ready for Merge" "the redirect is guarded with --expect-from (lost race NOOPs, ABS-198)"
assert_contains "$calls" "ABS-481" "audit comment cites ABS-481"
assert_contains "$calls" "never pushed" "comment names the never-pushed root cause"
assert_contains "$(cat "$ORCH_RUN_LOG")" "INTENT-READY-FOR-MERGE-NO-BRANCH	ABS-461" "writes an INTENT-READY-FOR-MERGE-NO-BRANCH run.log event"

# =============================================================================
echo -e "\n${CYAN}ABS-481 AC2 — degraded connectivity fails LOUD, never silent-passes${NC}"
# =============================================================================
# No remote answered: the gate cannot prove the branch is absent, so it must NOT
# self-heal (no thrash) and must NOT treat the gate as satisfied (no silent-pass).
# It surfaces the failure in the run log and rests (rc 1, no adapter writes).
MODE="live"; FORGE_CMD="stub"; STUB_IN=0; STUB_BRANCH_STATE="UNREACHABLE"; STUB_PR_LINE="NONE"
res="$(run_gate "ABS-461" "Ready for Merge")"; rc="${res%%$'\n'*}"; out="${res#*$'\n'}"
assert_eq "$rc" "1" "unreachable remote -> no-op (rc 1): does not self-heal on an unverifiable branch"
assert_not_contains "$out" "INTENT READY-FOR-MERGE" "no self-heal intent when the branch cannot be verified"
assert_eq "$(cat "$STUB_CALLS")" "" "no adapter writes on degraded connectivity (no thrash, no false transition)"
assert_contains "$(cat "$ORCH_RUN_LOG")" "READY-FOR-MERGE-GATE-UNREACHABLE	ABS-461" "fails LOUD: writes a READY-FOR-MERGE-GATE-UNREACHABLE run.log event"

# =============================================================================
echo -e "\n${CYAN}ABS-481 — a FOUND branch falls through to the ABS-454 MR-existence half${NC}"
# =============================================================================
# The branch is on the remote (FOUND) but MR-create failed (state NONE): the gate
# must still self-heal via the existing ABS-454 path — the two halves compose.
MODE="live"; FORGE_CMD="stub"; STUB_IN=0; STUB_BRANCH_STATE="FOUND"; STUB_PR_LINE="NONE"
res="$(run_gate "ABS-461" "Ready for Merge")"; rc="${res%%$'\n'*}"; out="${res#*$'\n'}"
assert_eq "$rc" "0" "FOUND branch + no MR -> falls through to the ABS-454 no-MR self-heal (rc 0)"
assert_contains "$out" "INTENT READY-FOR-MERGE-NO-MR ticket=ABS-461" "the ABS-454 MR half still fires when the branch exists but the MR does not"

# --- cleanup temp files -------------------------------------------------------
rm -f "$STUB_CALLS" "$ORCH_RUN_LOG" 2>/dev/null || true

# =============================================================================
echo -e "\n${CYAN}Wiring — the 'Ready for Merge' -> 'Merging' self-heal edge exists in statuses.yaml${NC}"
# =============================================================================
# AC1 requires the self-heal to ACTUALLY land (respawn, not stall). The redirect
# only lands if the adapter's transition table has the edge (same hole ABS-211's
# Done -> Merging redirect hit before ABS-270 added its edge). Assert the edge is
# present under `Ready for Merge` in the neutral source of truth.
rfm_next="$(awk '
    /^  - name: / { cur = substr($0, 11) }
    cur == "Ready for Merge" && /^    next:/ { innext = 1; next }
    innext && /^  - name: / { innext = 0 }
    innext && /^      - / { print substr($0, 9) }
' "$REPO_ROOT/profiles/neutral/adapters/statuses.yaml")"
if printf '%s\n' "$rfm_next" | grep -qxF "Merging"; then
    TOTAL=$((TOTAL + 1)); PASS=$((PASS + 1))
    echo -e "  ${GREEN}PASS${NC} statuses.yaml lists 'Merging' under 'Ready for Merge' next: (self-heal edge present)"
else
    TOTAL=$((TOTAL + 1)); FAIL=$((FAIL + 1))
    echo -e "  ${RED}FAIL${NC} statuses.yaml is missing the 'Ready for Merge' -> 'Merging' self-heal edge"
fi

# =============================================================================
echo -e "\n${CYAN}=== Test Results ===${NC}\n"
echo -e "  Total:  $TOTAL"
echo -e "  ${GREEN}Passed: $PASS${NC}"
if [ "$FAIL" -gt 0 ]; then
    echo -e "  ${RED}Failed: $FAIL${NC}"; exit 1
else
    echo -e "  Failed: 0"; echo -e "\n  ${GREEN}ALL TESTS PASSED${NC}\n"; exit 0
fi
