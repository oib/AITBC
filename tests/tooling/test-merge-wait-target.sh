#!/bin/bash
# =============================================================================
# Test: merge-wait release probes the MR TARGET branch, not hardcoded main — ABS-537
# =============================================================================
# v3-pilot #3 finding: the ABS-270/494 merge-wait release (story_git_merge_state)
# ran `merge-base --is-ancestor <story-head> <active-main>` unconditionally. For
# a parentless story (MR target = main) that is correct; for an EPIC-LANE story
# the MR targets the epic integration branch epic/<parent>-* (ADR-A-0014), so its
# merged head is an ancestor of epic/* only — the main probe read it as OPEN
# forever and all 5 PILOT-5 stories sat a whole night in `Ready for Merge` after
# their MRs were human-merged.
#
# ABS-537 derives the target from the story CONTEXT (story_merge_target_branch):
# parent set in the tracker -> epic integration branch (ABS-119 lexicographic
# pick, local heads + active-remote tracking refs); parentless -> main. Ancestry
# into main stays accepted for an epic child (integrated-epic fallback).
#
# Same fixture shape as tests/test-docs-merge-wait-pilot.sh: a bare "remote" + a
# working repo drive the REAL git-ancestry probe; only `tracker` /
# `ticket_still_in` / `notify` are stubbed — no adapter, forge, model, network.
#
# bash 3.2 + BSD tools only. Run from repo root: bash tests/test-merge-wait-target.sh
# =============================================================================

set -euo pipefail

# ABS-285: scrub ambient ORCH_* before driving the runner.
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
    if echo "$output" | grep -qF -- "$expected"; then echo -e "  ${GREEN}PASS${NC} $label"; PASS=$((PASS + 1))
    else echo -e "  ${RED}FAIL${NC} $label (expected to find: $expected)"
        echo -e "  ${YELLOW}  Output:${NC}"; echo "$output" | head -8 | sed 's/^/    /'; FAIL=$((FAIL + 1)); fi
}

# Load the runner's functions without starting the poll loop.
source "$REPO_ROOT/scripts/orchestrator.sh" >/dev/null 2>&1

echo -e "${CYAN}=== ABS-537: merge-wait release resolves the MR target branch ===${NC}\n"

# --- git sandbox: bare "remote" + working repo (the runner's ORCH_STATE_ROOT) -----
GX() { git -c user.email=t@t -c user.name=t -c commit.gpgsign=false "$@"; }
SANDBOX="$(mktemp -d /tmp/mwt537-XXXXXX)"
REMOTE="$SANDBOX/remote.git"; WORK="$SANDBOX/work"
GX init -q --bare "$REMOTE"
GX init -q "$WORK"
GX -C "$WORK" remote add origin "$REMOTE"
echo seed > "$WORK/README.md"; GX -C "$WORK" add -A; GX -C "$WORK" commit -q -m seed
GX -C "$WORK" branch -M main; GX -C "$WORK" push -q origin main

# The epic integration branch (ADR-A-0014 lane), as the epic-branch provisioning
# creates it: epic/<epic-id>-<slug>, based on main, pushed to the remote.
EPIC_BR="epic/PILOT-5-backend-jira-parity"
GX -C "$WORK" checkout -q -b "$EPIC_BR" main
echo epic-seed > "$WORK/epic.txt"; GX -C "$WORK" add -A; GX -C "$WORK" commit -q -m "epic seed"
GX -C "$WORK" push -q origin "$EPIC_BR"
GX -C "$WORK" checkout -q main

# mk_story_branch <ticket> <base> — the story branch <ticket>-auto with an
# unmerged commit, based on <base> (epic children base on the epic branch).
mk_story_branch() {
    local br="$1-auto"
    GX -C "$WORK" checkout -q -b "$br" "$2"
    echo "$1 work" > "$WORK/$1.txt"; GX -C "$WORK" add -A; GX -C "$WORK" commit -q -m "$1 impl"
    GX -C "$WORK" push -q origin "$br"
    GX -C "$WORK" checkout -q main
}
# human_merge <ticket> <target> — "the human merges the MR": merge the story
# branch into <target> and push, from a SEPARATE clone (never the runner's WORK).
human_merge() {
    local br="$1-auto" tgt="$2" merger="$SANDBOX/merger-$1"
    GX clone -q "$REMOTE" "$merger"
    GX -C "$merger" checkout -q "$tgt"
    GX -C "$merger" merge -q --no-ff -m "Merge $br into $tgt (merge request)" "origin/$br"
    GX -C "$merger" push -q origin "$tgt"
    rm -rf "$merger"
}

# The pilot lane: NO forge, active remote resolved to origin (offline).
MODE="live"; FORGE_CMD=""
ORCH_STATE_ROOT="$WORK"; ORCH_LOCAL_MAIN_BRANCH="main"; ORCH_MAIN_REMOTE="origin"
ORCH_REMOTE_PROBE_TIMEOUT="12"

# --- stubs: tracker serves a per-ticket dump + records writes ---------------------
STUB_CALLS="$(mktemp /tmp/mwt537-calls-XXXXXX)"
ORCH_RUN_LOG="$(mktemp /tmp/mwt537-runlog-XXXXXX)"
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

run_gate() {
    : > "$STUB_CALLS"; : > "$ORCH_RUN_LOG"
    local rc=0 out fn="$1"
    out="$("$fn" "$2" "$3" 2>/dev/null)" || rc=$?
    printf '%s\n%s' "$rc" "$out"
}

# Tracker dumps: an epic child carries `parent:`; a parentless story does not.
EPIC_CHILD_DUMP="$(cat <<'EOF'
---
id: PILOT-6
type: ticket
status: Ready for Merge
parent: PILOT-5
---
Transition: Docs -> Ready for Merge. Reason: MERGE-WAIT waiting on human merge (ABS-270)
EOF
)"
PARENTLESS_DUMP="$(cat <<'EOF'
---
id: PILOT-9
type: ticket
status: Ready for Merge
---
Transition: Docs -> Ready for Merge. Reason: MERGE-WAIT waiting on human merge (ABS-270)
EOF
)"

# =============================================================================
echo -e "${CYAN}Target resolution — epic child -> epic/*, parentless -> main${NC}"
# =============================================================================
STUB_DUMP="$EPIC_CHILD_DUMP"
assert_eq "$(story_merge_target_branch PILOT-6 origin)" "$EPIC_BR" "epic child (parent: PILOT-5) resolves to the epic integration branch"
STUB_DUMP="$PARENTLESS_DUMP"
assert_eq "$(story_merge_target_branch PILOT-9 origin)" "main" "parentless story resolves to main"
STUB_DUMP="$(printf '%s\n' 'parent: NOPE-99')"
assert_eq "$(story_merge_target_branch PILOT-Z origin)" "main" "parent with NO matching epic/* branch falls back to main (fail-open)"

# =============================================================================
echo -e "\n${CYAN}Epic lane, unmerged — the wait posture HOLDS (no premature advance)${NC}"
# =============================================================================
mk_story_branch "PILOT-6" "$EPIC_BR"
STUB_DUMP="$EPIC_CHILD_DUMP"
state="$(story_git_merge_state PILOT-6 | awk -F'\t' '{print $1}')"
assert_eq "$state" "OPEN" "epic-lane branch not merged anywhere -> OPEN"
res="$(run_gate merge_wait_release "PILOT-6" "Ready for Merge")"
assert_eq "${res%%$'\n'*}" "1" "unmerged epic-lane story keeps resting at the merge gate"
assert_eq "$(cat "$STUB_CALLS")" "" "zero adapter writes while the MR is unmerged"

# =============================================================================
echo -e "\n${CYAN}Epic lane, human-merged into epic/* — released within ONE sweep${NC}"
# =============================================================================
# The exact PILOT-5 night: the MR (target epic/*) is human-merged; the head is an
# ancestor of the EPIC branch only, never of main. The old main-probe read this
# as OPEN forever.
human_merge "PILOT-6" "$EPIC_BR"
STUB_DUMP="$EPIC_CHILD_DUMP"
pair="$(story_git_merge_state PILOT-6)"
assert_eq "${pair%%$'\t'*}" "MERGED" "head merged into epic/* (NOT main) -> MERGED against the resolved target"
res="$(run_gate merge_wait_release "PILOT-6" "Ready for Merge")"; rc="${res%%$'\n'*}"; out="${res#*$'\n'}"
assert_eq "$rc" "0" "ONE sweep after the human merge the epic-lane story is RELEASED (the all-night stall)"
assert_contains "$out" "INTENT MERGE-WAIT-RELEASE ticket=PILOT-6 role=- to=Docs" "release intent targets the Docs seat"
assert_contains "$(cat "$STUB_CALLS")" "TRANSITION PILOT-6 Docs" "transitions Ready for Merge -> Docs, no operator step"

# =============================================================================
echo -e "\n${CYAN}Parentless lane — conformance against main is UNCHANGED${NC}"
# =============================================================================
mk_story_branch "PILOT-9" "main"
STUB_DUMP="$PARENTLESS_DUMP"
state="$(story_git_merge_state PILOT-9 | awk -F'\t' '{print $1}')"
assert_eq "$state" "OPEN" "parentless unmerged branch -> OPEN (waits on the human merge)"
res="$(run_gate merge_wait_release "PILOT-9" "Ready for Merge")"
assert_eq "${res%%$'\n'*}" "1" "unmerged parentless story keeps resting"
human_merge "PILOT-9" "main"
STUB_DUMP="$PARENTLESS_DUMP"
state="$(story_git_merge_state PILOT-9 | awk -F'\t' '{print $1}')"
assert_eq "$state" "MERGED" "parentless branch merged into main -> MERGED"
res="$(run_gate merge_wait_release "PILOT-9" "Ready for Merge")"; rc="${res%%$'\n'*}"
assert_eq "$rc" "0" "merged parentless story is released within one sweep (regression guard)"
assert_contains "$(cat "$STUB_CALLS")" "TRANSITION PILOT-9 Docs" "parentless release still lands at Docs"

# =============================================================================
echo -e "\n${CYAN}PILOT-67 AC1/AC5 — PARENTLESS story merged into an epic branch => MERGED + released${NC}"
# =============================================================================
# The exact PILOT-34 defect: a story with NO parent field was merged (MR !196)
# into epic/PILOT-28-poll-to-push, not main. story_merge_target_branch says 'main'
# (parentless), so the old single-target probe read it OPEN for up to 20 min after
# the merge, fired a false MERGE-CONFLICT-REDIRECT, and bounced three operator
# releases. PILOT-67 probes EVERY candidate (main AND every epic branch), so the
# parentless-into-epic head is MERGED and the merge-wait release fires.
PL34_DUMP="$(cat <<'EOF'
---
id: PILOT-34
type: ticket
status: Ready for Merge
---
Transition: Docs -> Ready for Merge. Reason: MERGE-WAIT waiting on human merge (ABS-270)
EOF
)"
mk_story_branch "PILOT-34" "$EPIC_BR"
STUB_DUMP="$PL34_DUMP"
state="$(story_git_merge_state PILOT-34 | awk -F'\t' '{print $1}')"
assert_eq "$state" "OPEN" "parentless-into-epic branch not yet merged -> OPEN (wait holds)"
human_merge "PILOT-34" "$EPIC_BR"
STUB_DUMP="$PL34_DUMP"
state="$(story_git_merge_state PILOT-34 | awk -F'\t' '{print $1}')"
assert_eq "$state" "MERGED" "AC1: parentless story merged into epic/* -> MERGED (declared target is main!)"
res="$(run_gate merge_wait_release "PILOT-34" "Ready for Merge")"; rc="${res%%$'\n'*}"; out="${res#*$'\n'}"
assert_eq "$rc" "0" "AC5: MERGE-WAIT-RELEASE fires for the parentless-into-epic story"
assert_contains "$out" "INTENT MERGE-WAIT-RELEASE ticket=PILOT-34 role=- to=Docs" "AC5: release intent targets Docs"
assert_contains "$(cat "$STUB_CALLS")" "TRANSITION PILOT-34 Docs" "AC5: released Ready for Merge -> Docs, no operator step"

# =============================================================================
echo -e "\n${CYAN}PILOT-67 AC2 — a STALE/absent local epic tracking ref does not hide the target${NC}"
# =============================================================================
# Drop the runner's local tracking ref for the epic branch; the resolver must
# FETCH it back before listing (old behavior fell silently through to main only).
GX -C "$WORK" update-ref -d "refs/remotes/origin/$EPIC_BR" 2>/dev/null || true
STUB_DUMP="$PL34_DUMP"
branches="$(story_merge_target_branches PILOT-34 origin)"
assert_contains "$branches" "$EPIC_BR" "AC2: epic branch is (re-)fetched and listed even with the local tracking ref deleted"
state="$(story_git_merge_state PILOT-34 | awk -F'\t' '{print $1}')"
assert_eq "$state" "MERGED" "AC2: merged-ness still resolves after the stale-ref fetch"

# =============================================================================
echo -e "\n${CYAN}PILOT-67 AC3 — resolve_active_main_ref never hardcodes origin${NC}"
# =============================================================================
# origin is Bitbucket (down / no epic branches); the active push remote is the
# only source. With no ORCH_MAIN_REMOTE and no @{push}, resolution comes from
# remote.pushDefault, else the sole remote — never a blind 'origin/main'.
AC3A="$SANDBOX/ac3-pushdefault"; GX init -q "$AC3A"
GX -C "$AC3A" remote add origin http://bitbucket/x    # present but NOT the active remote
GX -C "$AC3A" remote add gitlab http://gitlab/x
GX -C "$AC3A" config remote.pushDefault gitlab
out="$( (unset ORCH_MAIN_REMOTE; resolve_active_main_ref main "$AC3A") )"
assert_eq "$out" "gitlab/main" "AC3: pushDefault=gitlab resolves to gitlab/main, NOT the hardcoded origin/main"
AC3B="$SANDBOX/ac3-sole"; GX init -q "$AC3B"
GX -C "$AC3B" remote add bitbucket http://bitbucket/x  # a single, non-origin remote
out="$( (unset ORCH_MAIN_REMOTE; resolve_active_main_ref main "$AC3B") )"
assert_eq "$out" "bitbucket/main" "AC3: the sole configured remote is used, never a hardcoded origin"

# =============================================================================
echo -e "\n${CYAN}PILOT-67 AC4 — a manual operator release is surfaced, not silently re-parked${NC}"
# =============================================================================
# docs_pr_gate must NOT re-park a story an operator manually released from the
# merge gate when its own probe still reads OPEN: it posts a visible conflict
# comment and lets Docs proceed (done_pr_gate stays the Done backstop).
OP_RELEASE_DUMP="$(cat <<'EOF'
---
id: PILOT-77
type: ticket
status: Docs
---
### 2026-07-26T13:00:00Z | kind: transition-reason | actor: orchestrator

Transition: Merging -> Ready for Merge. Reason: MERGE-WAIT (ABS-270)

### 2026-07-26T14:00:00Z | kind: transition-reason | actor: operator

Transition: Ready for Merge -> Docs. Reason: manual operator release — MR merged
EOF
)"
assert_eq "$(operator_released_from_merge_gate "$OP_RELEASE_DUMP"; echo $?)" "0" "AC4: operator release out of Ready for Merge is detected"
assert_eq "$(operator_released_from_merge_gate "$PL34_DUMP"; echo $?)" "1" "AC4: an orchestrator-only history is NOT an operator release"
# Drive docs_pr_gate: unmerged story (OPEN) + operator-release history -> no re-park.
mk_story_branch "PILOT-77" "main"
STUB_DUMP="$OP_RELEASE_DUMP"
res="$(run_gate docs_pr_gate "PILOT-77" "Docs")"; rc="${res%%$'\n'*}"; out="${res#*$'\n'}"
assert_eq "$rc" "1" "AC4: docs_pr_gate does NOT intervene — the operator release stands, Docs proceeds"
assert_contains "$out" "INTENT MERGE-WAIT-CONFLICT ticket=PILOT-77" "AC4: the disagreement is logged as a MERGE-WAIT-CONFLICT"
assert_contains "$(cat "$STUB_CALLS")" "COMMENT PILOT-77" "AC4: a visible conflict comment is posted"
if grep -q "TRANSITION PILOT-77 Ready for Merge" "$STUB_CALLS"; then
    assert_eq "re-parked" "not-re-parked" "AC4: the story must NOT be re-parked to Ready for Merge"
else
    assert_eq "not-re-parked" "not-re-parked" "AC4: no silent re-park transition to Ready for Merge"
fi

# =============================================================================
echo -e "\n${CYAN}Integrated-epic fallback — epic/* merged to main and deleted: still MERGED${NC}"
# =============================================================================
# After the epic JOIN the integration branch is merged to main and eventually
# deleted; the story head is then an ancestor of MAIN. The epic child must not
# regress to OPEN just because its epic/* ref is gone from the remote.
merger="$SANDBOX/merger-epic"
GX clone -q "$REMOTE" "$merger"
GX -C "$merger" checkout -q main
GX -C "$merger" merge -q --no-ff -m "Merge $EPIC_BR (epic MR)" "origin/$EPIC_BR"
GX -C "$merger" push -q origin main
GX -C "$merger" push -q origin --delete "$EPIC_BR"
rm -rf "$merger"
# Drop the runner's stale local knowledge of the epic branch so ONLY the main
# fallback can answer (the deleted-remote-branch worst case).
GX -C "$WORK" update-ref -d "refs/remotes/origin/$EPIC_BR" 2>/dev/null || true
GX -C "$WORK" branch -q -D "$EPIC_BR" 2>/dev/null || true
STUB_DUMP="$EPIC_CHILD_DUMP"
state="$(story_git_merge_state PILOT-6 | awk -F'\t' '{print $1}')"
assert_eq "$state" "MERGED" "epic child whose epic/* is integrated to main + deleted -> MERGED via the main fallback"

rm -rf "$SANDBOX" 2>/dev/null || true
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
