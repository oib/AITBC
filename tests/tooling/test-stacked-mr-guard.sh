#!/usr/bin/env bash
# =============================================================================
# Test: stacked-MR loss class — refusal + arrival-not-status gate (PILOT-21)
# =============================================================================
# v3-pilot #3 (2026-07-23, KRITISCH): the PILOT-13 seat opened !163 stacked on the
# SIBLING story branch PILOT-9-auto (not the epic integration branch) and merged it
# there. The later base-rebase of PILOT-9 dropped the stacked commits; !163 read
# state=merged, PILOT-13 stood at the merge gate — but its delivery (nosniff header
# + RFC-5987 filename) never reached the epic branch. Only an operator content
# check caught the silent loss. This suite pins the two mechanical defences:
#
#   AC1 — scripts/merge-target-guard.sh REFUSES a story/follow-up MR whose target is
#         a sibling story branch (`<ticket>-auto`), with a machine-greppable intent
#         line; it still ALLOWS the legitimate epic/* target and still REFUSES main.
#   AC2 — arrival, not MR-status, is authority: the forge-less merge probe
#         (story_git_merge_state) resolves the story's REAL target (epic child ->
#         epic integration branch, ABS-537) and gates on git ancestry INTO it, so a
#         branch "merged" onto a sibling story branch is OPEN (never arrived) and
#         merge_wait_release keeps it PARKED — it never reaches Docs/Done.
#   AC3 — happy path: the same branch merged into the CORRECT epic branch is MERGED
#         and released (no false park; no regression to the ABS-537 release path).
#   AC4 — determinism: re-evaluating the same (guard,target) and (gate,state) yields
#         the same verdict and does not double-transition.
#
# bash 3.2 + BSD tools only. Run from repo root: bash tests/test-stacked-mr-guard.sh
# =============================================================================
set -uo pipefail

# ABS-285: scrub ambient ORCH_* before sourcing/driving the runner.
unset "${!ORCH_@}" 2>/dev/null || true

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
GUARD="$REPO_ROOT/scripts/merge-target-guard.sh"

PASS=0; FAIL=0; TOTAL=0
GREEN='\033[0;32m'; RED='\033[0;31m'; CYAN='\033[0;36m'; YELLOW='\033[1;33m'; NC='\033[0m'

assert_rc() {
    local expected="$1" label="$2"; shift 2
    local rc=0
    "$@" >/dev/null 2>&1 || rc=$?
    TOTAL=$((TOTAL + 1))
    if [ "$rc" = "$expected" ]; then echo -e "  ${GREEN}PASS${NC} $label"; PASS=$((PASS + 1))
    else echo -e "  ${RED}FAIL${NC} $label (expected exit '$expected', got '$rc')"; FAIL=$((FAIL + 1)); fi
}
assert_eq() {
    local actual="$1" expected="$2" label="$3"
    TOTAL=$((TOTAL + 1))
    if [ "$actual" = "$expected" ]; then echo -e "  ${GREEN}PASS${NC} $label"; PASS=$((PASS + 1))
    else echo -e "  ${RED}FAIL${NC} $label (expected '$expected', got '$actual')"; FAIL=$((FAIL + 1)); fi
}
assert_contains() {
    local output="$1" expected="$2" label="$3"
    TOTAL=$((TOTAL + 1))
    if printf '%s' "$output" | grep -qF -- "$expected"; then echo -e "  ${GREEN}PASS${NC} $label"; PASS=$((PASS + 1))
    else echo -e "  ${RED}FAIL${NC} $label (expected to find: $expected)"
        echo -e "  ${YELLOW}  Output:${NC}"; printf '%s\n' "$output" | head -6 | sed 's/^/    /'; FAIL=$((FAIL + 1)); fi
}

# =============================================================================
echo -e "${CYAN}=== PILOT-21: stacked-MR guard + arrival-not-status gate ===${NC}\n"
echo -e "${CYAN}A. AC1 — merge-target-guard refuses a sibling story-branch target${NC}"
# =============================================================================
# The exact loss signature: MR target = PILOT-9-auto (a sibling story branch).
assert_rc 1 "target PILOT-9-auto (stacked sibling story branch) -> REFUSE (exit 1)" \
    bash "$GUARD" check PILOT-9-auto
STACKED_OUT="$(bash "$GUARD" check PILOT-9-auto 2>/dev/null || true)"
assert_contains "$STACKED_OUT" "MERGE-GUARD-REFUSE" "stacked target prints the MERGE-GUARD-REFUSE intent line"
assert_contains "$STACKED_OUT" "reason=stacked-story-branch" "intent line names the stacked-story-branch reason"
assert_contains "$STACKED_OUT" "action=hitl-handoff" "intent line carries the hitl-handoff action token"
# refs/heads/ and remote-prefixed forms normalise to the bare story branch too.
assert_rc 1 "target origin/PILOT-9-auto -> REFUSE (normalised, exit 1)" \
    bash "$GUARD" check origin/PILOT-9-auto
assert_rc 1 "target refs/heads/PILOT-13-auto -> REFUSE (normalised, exit 1)" \
    bash "$GUARD" check refs/heads/PILOT-13-auto
# Legitimate targets are unaffected: epic/* ALLOWED, main still REFUSED (protected).
assert_rc 0 "target epic/PILOT-5-backend-jira-parity -> ALLOW (exit 0, epic integration branch)" \
    bash "$GUARD" check epic/PILOT-5-backend-jira-parity
assert_rc 1 "target main -> REFUSE (exit 1, protected — unchanged ABS-531 chokepoint)" \
    bash "$GUARD" check main
# An epic slug that itself ends in -auto is still ALLOWED (it has a '/', not a bare story branch).
assert_rc 0 "target epic/PILOT-7-auto-pilot -> ALLOW (slashed epic branch, not a story branch)" \
    bash "$GUARD" check epic/PILOT-7-auto-pilot

# =============================================================================
echo -e "\n${CYAN}A'. AC4 — guard verdict is deterministic on repeat${NC}"
# =============================================================================
r1=0; bash "$GUARD" check PILOT-9-auto >/dev/null 2>&1 || r1=$?
r2=0; bash "$GUARD" check PILOT-9-auto >/dev/null 2>&1 || r2=$?
assert_eq "$r1-$r2" "1-1" "repeat guard.check(PILOT-9-auto) -> same REFUSE verdict"

# =============================================================================
echo -e "\n${CYAN}B. AC2/AC3 — arrival gate: merged onto a sibling stays PARKED${NC}"
# =============================================================================
# Load the runner's functions without starting the poll loop.
source "$REPO_ROOT/scripts/orchestrator.sh" >/dev/null 2>&1

GX() { git -c user.email=t@t -c user.name=t -c commit.gpgsign=false "$@"; }
SANDBOX="$(mktemp -d "${TMPDIR:-/tmp}/stackmr21-XXXXXX")"
REMOTE="$SANDBOX/remote.git"; WORK="$SANDBOX/work"
GX init -q --bare "$REMOTE"
GX init -q "$WORK"
GX -C "$WORK" remote add origin "$REMOTE"
echo seed > "$WORK/README.md"; GX -C "$WORK" add -A; GX -C "$WORK" commit -q -m seed
GX -C "$WORK" branch -M main; GX -C "$WORK" push -q origin main

# Epic integration branch (ADR-A-0014), as epic-branch provisioning creates it.
EPIC_BR="epic/PILOT-5-backend-jira-parity"
GX -C "$WORK" checkout -q -b "$EPIC_BR" main
echo epic-seed > "$WORK/epic.txt"; GX -C "$WORK" add -A; GX -C "$WORK" commit -q -m "epic seed"
GX -C "$WORK" push -q origin "$EPIC_BR"
GX -C "$WORK" checkout -q main

mk_story_branch() {  # <ticket> <base>
    local br="$1-auto"
    GX -C "$WORK" checkout -q -b "$br" "$2"
    echo "$1 work" > "$WORK/$1.txt"; GX -C "$WORK" add -A; GX -C "$WORK" commit -q -m "$1 impl"
    GX -C "$WORK" push -q origin "$br"
    GX -C "$WORK" checkout -q main
}
human_merge() {  # <ticket> <target>
    local br="$1-auto" tgt="$2" merger="$SANDBOX/merger-$1-$2"
    GX clone -q "$REMOTE" "$merger"
    GX -C "$merger" checkout -q "$tgt"
    GX -C "$merger" merge -q --no-ff -m "Merge $br into $tgt" "origin/$br"
    GX -C "$merger" push -q origin "$tgt"
    rm -rf "$merger"
}

# Pilot lane: NO forge, active remote = origin (offline git-ancestry probe).
MODE="live"; FORGE_CMD=""
ORCH_STATE_ROOT="$WORK"; ORCH_LOCAL_MAIN_BRANCH="main"; ORCH_MAIN_REMOTE="origin"
ORCH_REMOTE_PROBE_TIMEOUT="12"

STUB_CALLS="$(mktemp "${TMPDIR:-/tmp}/stackmr21-calls-XXXXXX")"
ORCH_RUN_LOG="$(mktemp "${TMPDIR:-/tmp}/stackmr21-runlog-XXXXXX")"
STUB_DUMP=""; STUB_IN=0
tracker() {
    case "$1" in
        get)        printf '%s\n' "$STUB_DUMP" ;;
        comment)    shift; printf 'COMMENT %s\n' "$*" >> "$STUB_CALLS" ;;
        transition) shift; printf 'TRANSITION %s\n' "$*" >> "$STUB_CALLS" ;;
        *)          : ;;
    esac
}
ticket_still_in() { return "$STUB_IN"; }
notify() { :; }

# PILOT-13 is an epic child of PILOT-5 (its MR must target the epic branch).
CHILD_DUMP="$(cat <<'EOF'
---
id: PILOT-13
type: ticket
status: Ready for Merge
parent: PILOT-5
---
Transition: Docs -> Ready for Merge. Reason: MERGE-WAIT waiting on human merge (ABS-270)
EOF
)"
STUB_DUMP="$CHILD_DUMP"

# The epic child's target resolves to the epic integration branch (ABS-537).
assert_eq "$(story_merge_target_branch PILOT-13 origin)" "$EPIC_BR" "epic child (parent: PILOT-5) targets the epic integration branch"

# Build PILOT-13-auto off the epic branch, and a sibling PILOT-9-auto off main.
mk_story_branch "PILOT-13" "$EPIC_BR"
mk_story_branch "PILOT-9" "main"

# THE DEFECT: PILOT-13-auto is stacked-merged onto the SIBLING PILOT-9-auto, NOT
# onto the epic branch. Its head lives in PILOT-9-auto only.
human_merge "PILOT-13" "PILOT-9-auto"
state="$(story_git_merge_state PILOT-13 | awk -F'\t' '{print $1}')"
assert_eq "$state" "OPEN" "merged onto a SIBLING story branch (not the epic) -> OPEN (never arrived) [AC2]"
: > "$STUB_CALLS"
rc=0; merge_wait_release PILOT-13 "Ready for Merge" >/dev/null 2>&1 || rc=$?
assert_eq "$rc" "1" "stacked-merged story keeps PARKED at the merge gate (no release) [AC2]"
assert_eq "$(cat "$STUB_CALLS")" "" "zero adapter writes — the story never advances toward Done [AC2]"

# AC4: re-evaluating the same not-arrived state is stable (still OPEN, still parked).
state2="$(story_git_merge_state PILOT-13 | awk -F'\t' '{print $1}')"
assert_eq "$state2" "OPEN" "repeat probe of the not-arrived story -> still OPEN (deterministic) [AC4]"
: > "$STUB_CALLS"
rc=0; merge_wait_release PILOT-13 "Ready for Merge" >/dev/null 2>&1 || rc=$?
assert_eq "$rc" "1" "repeat gate on the not-arrived story -> still parked, no double-transition [AC4]"
assert_eq "$(cat "$STUB_CALLS")" "" "repeat gate emits no adapter writes either [AC4]"

# =============================================================================
echo -e "\n${CYAN}C. AC3 — happy path: merged into the CORRECT epic branch is released${NC}"
# =============================================================================
human_merge "PILOT-13" "$EPIC_BR"
state="$(story_git_merge_state PILOT-13 | awk -F'\t' '{print $1}')"
assert_eq "$state" "MERGED" "same branch merged into the epic integration branch -> MERGED (arrived) [AC3]"
: > "$STUB_CALLS"
rc=0; out="$(merge_wait_release PILOT-13 "Ready for Merge" 2>/dev/null)" || rc=$?
assert_eq "$rc" "0" "arrived story is RELEASED within one sweep (no false park) [AC3]"
assert_contains "$out" "INTENT MERGE-WAIT-RELEASE ticket=PILOT-13 role=- to=Docs" "release intent targets the Docs seat [AC3]"
assert_contains "$(cat "$STUB_CALLS")" "TRANSITION PILOT-13 Docs" "arrived story transitions Ready for Merge -> Docs [AC3]"

rm -rf "$SANDBOX" 2>/dev/null || true
rm -f "$STUB_CALLS" "$ORCH_RUN_LOG" 2>/dev/null || true

# =============================================================================
echo -e "\n${CYAN}=== Results ===${NC}"
echo -e "  Total:  $TOTAL"
echo -e "  ${GREEN}Passed: $PASS${NC}"
[ "$FAIL" -gt 0 ] && echo -e "  ${RED}Failed: $FAIL${NC}" || echo -e "  Failed: 0"
[ "$FAIL" -eq 0 ] || exit 1
echo -e "\n${GREEN}All stacked-MR-guard tests passed.${NC}"
