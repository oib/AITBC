#!/bin/bash
# =============================================================================
# Test: Docs merge-wait + auto-resume in the PILOT lane (no forge) — PILOT-4
# =============================================================================
# ABS-494 (v3-pilot finding): the ABS-270 merge-wait park+resume only fired when a
# $FORGE_CMD was configured (Jira lane). The pilot lane runs no forge, so a
# pipeline-green story reaching `Docs` with an UNMERGED branch spawned the
# tech-writer, who could only refuse the Done transition and rest — which the runner
# misread as an ABS-132 stuck loop and escalated to the PO (2 futile respawns + a
# false escalation + a PO Blocked-park for a plain human-merge wait).
#
# PILOT-4 gives the pilot lane a forge-LESS merge probe (story_git_merge_state:
# `merge-base --is-ancestor` against the active push remote — the docs-station /
# ABS-457 + PILOT-3 check) and wires it into docs_pr_gate / merge_wait_release so
# BOTH human-gated wait postures auto-resume with no operator action:
#   posture 1 — Docs + unmerged branch -> park at `Ready for Merge`; resume Docs
#               when the branch becomes an ancestor of remote main.
#   posture 2 — Merging-origin rest at `Ready for Merge` + already-merged branch
#               -> auto-advance to `Docs` (operator scope-append; PILOT-2 sat 3h
#               there because the pilot lane had no merge-detection).
#
# Unlike tests/test-merge-wait.sh (which stubs the forge line), this drives the REAL
# git-ancestry probe against a live sandbox: a bare "remote" + a working repo with a
# story branch, and "the human merge" is a real merge pushed to that remote. Only
# `tracker` / `ticket_still_in` are stubbed — no real adapter, model, or network.
#
# bash 3.2 + BSD tools only. Run from repo root: bash tests/test-docs-merge-wait-pilot.sh
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
assert_not_contains() {
    local output="$1" expected="$2" label="$3"
    TOTAL=$((TOTAL + 1))
    if ! echo "$output" | grep -qF -- "$expected"; then echo -e "  ${GREEN}PASS${NC} $label"; PASS=$((PASS + 1))
    else echo -e "  ${RED}FAIL${NC} $label (did NOT expect: $expected)"; FAIL=$((FAIL + 1)); fi
}

# Load the runner's functions without starting the poll loop.
source "$REPO_ROOT/scripts/orchestrator.sh" >/dev/null 2>&1

echo -e "${CYAN}=== PILOT-4: Docs merge-wait + auto-resume in the pilot lane (no forge) ===${NC}\n"

# --- git sandbox: a bare "remote" + a working repo (the runner's ORCH_STATE_ROOT) --
GX() { git -c user.email=t@t -c user.name=t -c commit.gpgsign=false "$@"; }
SANDBOX="$(mktemp -d /tmp/pilot4-XXXXXX)"
REMOTE="$SANDBOX/remote.git"; WORK="$SANDBOX/work"
GX init -q --bare "$REMOTE"
GX init -q "$WORK"
GX -C "$WORK" remote add origin "$REMOTE"
echo seed > "$WORK/README.md"; GX -C "$WORK" add -A; GX -C "$WORK" commit -q -m seed
GX -C "$WORK" branch -M main; GX -C "$WORK" push -q origin main
# The story branch <ticket>-auto with an unmerged commit (as the pilot runner leaves it).
mk_story_branch() {
    local br="$1-auto"
    GX -C "$WORK" checkout -q -b "$br" main
    echo "$1 work" > "$WORK/$1.txt"; GX -C "$WORK" add -A; GX -C "$WORK" commit -q -m "$1 impl"
    GX -C "$WORK" push -q origin "$br"
    GX -C "$WORK" checkout -q main
}
# "The human merges": merge the story branch into main and push it to the remote,
# from a SEPARATE clone (the runner's WORK never runs the merge itself).
human_merge() {
    local br="$1-auto" merger="$SANDBOX/merger-$1"
    GX clone -q "$REMOTE" "$merger"
    GX -C "$merger" checkout -q main
    GX -C "$merger" merge -q --no-ff -m "Merge $br (pull request)" "origin/$br"
    GX -C "$merger" push -q origin main
}

# The pilot lane: NO forge, active remote resolved to origin (offline).
MODE="live"; FORGE_CMD=""
ORCH_STATE_ROOT="$WORK"; ORCH_LOCAL_MAIN_BRANCH="main"; ORCH_MAIN_REMOTE="origin"
ORCH_REMOTE_PROBE_TIMEOUT="12"

# --- stubs: tracker records calls + serves the dump; ticket_still_in is settable ---
STUB_CALLS="$(mktemp /tmp/p4-calls-XXXXXX)"
ORCH_RUN_LOG="$(mktemp /tmp/p4-runlog-XXXXXX)"
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

# =============================================================================
echo -e "${CYAN}Probe — story_git_merge_state reads the REAL merge state with no forge${NC}"
# =============================================================================
mk_story_branch "PILOT-T1"
state="$(story_git_merge_state PILOT-T1 | awk -F'\t' '{print $1}')"
assert_eq "$state" "OPEN" "unmerged story branch -> OPEN (merge still owed by a human)"
state="$(story_git_merge_state PILOT-XX | awk -F'\t' '{print $1}')"
assert_eq "$state" "NONE" "no story branch -> NONE (fail-open, the gate proceeds as before)"

# =============================================================================
echo -e "\n${CYAN}AC1 — posture 1: Docs + unmerged branch parks, NOBODY spawned${NC}"
# =============================================================================
STUB_IN=0
res="$(run_gate docs_pr_gate "PILOT-T1" "Docs")"; rc="${res%%$'\n'*}"; out="${res#*$'\n'}"
assert_eq "$rc" "0" "gate INTERVENES on a Docs landing whose branch is unmerged (pilot lane, no forge)"
assert_contains "$out" "INTENT MERGE-WAIT ticket=PILOT-T1 role=- to=Ready for Merge" "parks to 'Ready for Merge' — no SPAWN"
assert_not_contains "$out" "SPAWN" "no tech-writer spawn intent for the parked story"
calls="$(cat "$STUB_CALLS")"
assert_contains "$calls" "TRANSITION PILOT-T1 Ready for Merge" "rests the story at the human-owned merge gate"
assert_contains "$calls" "waiting on human merge" "the transition reason names a human merge wait, not a stall"

# =============================================================================
echo -e "\n${CYAN}AC1 — the park rests: human-gated standstill accounting, zero respawns${NC}"
# =============================================================================
# These three predicates ARE the standstill mechanism (same as test-merge-wait.sh):
# a NOOP + non-reconcilable + legit-rest status cannot feed the ABS-132 no-move
# counter, so a parked story respawns nobody and is accounted human-gated.
assert_eq "$(map_action 'Ready for Merge')" "NOOP -" "AC1: 'Ready for Merge' maps to NOOP — no seat spawned there"
if is_reconcilable_status "Ready for Merge"; then rr="reconcilable"; else rr="rests"; fi
assert_eq "$rr" "rests" "AC1: 'Ready for Merge' is NOT reconcilable — no sweep re-derive, no no-move respawn"
if is_legit_rest_status "Ready for Merge"; then lr="legit-rest"; else lr="stuck-candidate"; fi
assert_eq "$lr" "legit-rest" "AC1: the stuck detector treats the merge gate as a legitimate rest"

# The reconcile-sweep release hook over 3 sweeps while the branch stays unmerged:
# every sweep is a no-op (zero writes) — no tech-writer respawn, no escalation.
PARKED_DOCS_DUMP="$(printf '%s\n%s\n' 'Transition: Merging -> Docs. Reason: pipeline green' 'Transition: Docs -> Ready for Merge. Reason: MERGE-WAIT waiting on human merge (ABS-270)')"
STUB_DUMP="$PARKED_DOCS_DUMP"
zero_writes=1
for sweep in 1 2 3; do
    res="$(run_gate merge_wait_release "PILOT-T1" "Ready for Merge")"
    [ "${res%%$'\n'*}" = "1" ] || zero_writes=0
    [ -s "$STUB_CALLS" ] && zero_writes=0
done
assert_eq "$zero_writes" "1" "AC1/AC2: 3 sweeps with an unmerged branch -> zero transitions, zero respawns, zero escalations"

# =============================================================================
echo -e "\n${CYAN}AC2 — no ABS-132 escalation ever fires on this path${NC}"
# =============================================================================
# The park/release path writes only Ready for Merge <-> Docs; it never routes to the
# PO escalation bucket. Assert across the whole call history of posture 1.
: > "$STUB_CALLS"
docs_pr_gate "PILOT-T1" "Docs" >/dev/null 2>&1 || true
STUB_DUMP="$PARKED_DOCS_DUMP"; merge_wait_release "PILOT-T1" "Ready for Merge" >/dev/null 2>&1 || true
allcalls="$(cat "$STUB_CALLS")"
assert_not_contains "$allcalls" "Needs PO Decision" "AC2: a human-merge wait is never escalated to the PO (ADR-A-0005)"
assert_not_contains "$allcalls" "SPAWN" "AC2: no seat is ever spawned on the merge-wait path"

# =============================================================================
echo -e "\n${CYAN}AC1 — posture 1 resume: the human merges -> runner resumes Docs${NC}"
# =============================================================================
human_merge "PILOT-T1"
state="$(story_git_merge_state PILOT-T1 | awk -F'\t' '{print $1}')"
assert_eq "$state" "MERGED" "after the human merge lands on remote main -> MERGED (merge-base --is-ancestor)"
STUB_DUMP="$PARKED_DOCS_DUMP"; STUB_IN=0
res="$(run_gate merge_wait_release "PILOT-T1" "Ready for Merge")"; rc="${res%%$'\n'*}"; out="${res#*$'\n'}"
assert_eq "$rc" "0" "merged branch -> the sweep RELEASES the parked story (no operator action)"
assert_contains "$out" "INTENT MERGE-WAIT-RELEASE ticket=PILOT-T1 role=- to=Docs" "resumes the story at the Docs seat"
calls="$(cat "$STUB_CALLS")"
assert_contains "$calls" "TRANSITION PILOT-T1 Docs" "AC1: transitions Ready for Merge -> Docs — the tech-writer then reaches Done"
assert_contains "$calls" "--expect-from Ready for Merge" "compare-and-set: a lost race with a human is a NOOP (ABS-198)"
# The re-entered Docs landing now PASSES the gate (branch merged) -> tech-writer spawns.
: > "$STUB_CALLS"
res="$(run_gate docs_pr_gate "PILOT-T1" "Docs")"
assert_eq "${res%%$'\n'*}" "1" "AC1: the re-entered Docs landing passes (branch merged) -> Docs proceeds to Done"
assert_eq "$(cat "$STUB_CALLS")" "" "AC1: no park/release ping-pong once the branch is merged"

# =============================================================================
echo -e "\n${CYAN}AC (scope-append) — posture 2: Merging-origin rest + merged -> Docs${NC}"
# =============================================================================
# The PILOT-2 posture: a story that rested at `Ready for Merge` straight from
# `Merging` (auto-merge off / wait_state_repair), never through Docs, and sat there
# after the human merged because the pilot lane had no merge-detection.
mk_story_branch "PILOT-T2"
MERGING_ORIGIN_DUMP="$(printf '%s\n' 'Transition: Merging -> Ready for Merge. Reason: auto-merge off, resting at the human merge gate (ABS-133)')"
STUB_DUMP="$MERGING_ORIGIN_DUMP"; STUB_IN=0
# Before the merge: it correctly keeps resting (no premature advance).
res="$(run_gate merge_wait_release "PILOT-T2" "Ready for Merge")"
assert_eq "${res%%$'\n'*}" "1" "posture 2: before the merge the Merging-origin rest keeps resting (no premature advance)"
assert_eq "$(cat "$STUB_CALLS")" "" "posture 2: zero writes while the branch is unmerged"
# The human merges -> auto-advance to Docs, no operator step.
human_merge "PILOT-T2"
STUB_DUMP="$MERGING_ORIGIN_DUMP"
res="$(run_gate merge_wait_release "PILOT-T2" "Ready for Merge")"; rc="${res%%$'\n'*}"; out="${res#*$'\n'}"
assert_eq "$rc" "0" "posture 2: merged branch -> Merging-origin rest auto-advances (kills the PILOT-2 3h stall)"
assert_contains "$out" "INTENT MERGE-WAIT-RELEASE ticket=PILOT-T2 role=- to=Docs" "posture 2: advances to the Docs seat"
assert_contains "$(cat "$STUB_CALLS")" "TRANSITION PILOT-T2 Docs" "posture 2: transitions Ready for Merge -> Docs automatically"

# =============================================================================
echo -e "\n${CYAN}Scoping — ABS-537 arming on every RfM entry; non-merge-gate tickets untouched${NC}"
# =============================================================================
# ABS-537 (retro finding #7): RfM entry arms the wait posture on EVERY path —
# the old Docs/Merging origin filter (which the MERGE-TOKEN-RELEASE path never
# armed) is gone, so a Path-A / foreign-origin rest with a merged branch is
# released too instead of resting forever.
STUB_DUMP="$(printf '%s\n' 'Transition: Ready for Human Acceptance -> Ready for Merge. Reason: PO accepted')"
res="$(run_gate merge_wait_release "PILOT-T2" "Ready for Merge")"
assert_eq "${res%%$'\n'*}" "0" "ABS-537: Path-A (RfHA origin) rest with a merged branch IS released to Docs"
STUB_DUMP="$MERGING_ORIGIN_DUMP"
res="$(run_gate merge_wait_release "PILOT-T2" "In Test")"
assert_eq "${res%%$'\n'*}" "1" "a ticket not at the merge gate is never touched"
STUB_IN=1
res="$(run_gate docs_pr_gate "PILOT-T1" "Docs")"
assert_eq "${res%%$'\n'*}" "1" "docs_pr_gate no-ops once the ticket has left Docs"
STUB_IN=0

# =============================================================================
echo -e "\n${CYAN}ABS-596 — MR merged, SOURCE BRANCH DELETED post-merge => MERGED (story continues)${NC}"
# =============================================================================
# Pilot 8 (PILOT-76): the MR was merged into the epic branch and GitLab then
# auto-deleted the source branch. The old probe could only answer via the branch
# head (ancestry), so with the head gone it read 'not merged' and parked the story
# at the human-owned merge gate for ~4h. The fix reads the merge from a
# branch-INDEPENDENT source: the merge commit left in the TARGET that names the
# source branch. (AC1: at least one non-branch source evaluated. AC2: this test.)
mk_story_branch "PILOT-DEL"
human_merge "PILOT-DEL"                               # merges into main, "Merge PILOT-DEL-auto (pull request)"
GX -C "$WORK" push -q origin --delete "PILOT-DEL-auto"   # GitLab post-merge cleanup: source branch gone
GX -C "$WORK" branch -q -D "PILOT-DEL-auto"              # runner's local ref also gone (worst case)
pair="$(story_git_merge_state PILOT-DEL)"
assert_eq "${pair%%$'\t'*}" "MERGED" "AC1/AC2: merged MR with a DELETED source branch reads MERGED (via the merge commit in the target)"
assert_contains "$pair" "merge commit for PILOT-DEL-auto" "AC4: the REF names WHAT the decision rests on (which commit, which source)"
# AC2: the story then CONTINUES — the merge-wait release fires and it advances to Docs.
STUB_DUMP="$PARKED_DOCS_DUMP"; STUB_IN=0
res="$(run_gate merge_wait_release "PILOT-DEL" "Ready for Merge")"; rc="${res%%$'\n'*}"
assert_eq "$rc" "0" "AC2: a merged story with a deleted source branch is RELEASED, not stuck at the human gate"
assert_contains "$(cat "$STUB_CALLS")" "TRANSITION PILOT-DEL Docs" "AC2: released Ready for Merge -> Docs — the story runs on"

# =============================================================================
echo -e "\n${CYAN}ABS-596 AC3 — evidence source UNREACHABLE => named UNKNOWN, not silent 'not merged'${NC}"
# =============================================================================
# When NO target ref on the active remote can be reached, the probe cannot decide.
# It must report a NAMED 'merge-state unknown' that names the missing source — never
# the silent OPEN ('not merged') that disguises itself as a human merge gate.
UREMOTE="$SANDBOX/uremote.git"; UWORK="$SANDBOX/uwork"
GX init -q --bare "$UREMOTE"                          # an EMPTY remote: no main, no epic branches
GX init -q "$UWORK"; GX -C "$UWORK" remote add origin "$UREMOTE"
GX -C "$UWORK" checkout -q -b "PILOT-UNK-auto"        # a story branch exists locally...
echo unk > "$UWORK/unk.txt"; GX -C "$UWORK" add -A; GX -C "$UWORK" commit -q -m "PILOT-UNK impl"
SAVED_STATE_ROOT="$ORCH_STATE_ROOT"; ORCH_STATE_ROOT="$UWORK"; STUB_DUMP=""; STUB_IN=0
pair="$(story_git_merge_state PILOT-UNK)"
assert_eq "${pair%%$'\t'*}" "UNKNOWN" "AC3: no reachable target ref -> UNKNOWN (even WITH a branch present — not silent OPEN)"
assert_contains "$pair" "no target ref reachable" "AC3/AC4: the UNKNOWN state names the missing evidence source"
# docs_pr_gate on UNKNOWN: honest named message + rest, never the 'waiting on human merge' false wording.
res="$(run_gate docs_pr_gate "PILOT-UNK" "Docs")"; rc="${res%%$'\n'*}"; out="${res#*$'\n'}"
assert_eq "$rc" "0" "AC3: docs_pr_gate rests an UNKNOWN story at the merge gate (re-probes; done_pr_gate backstops)"
assert_contains "$out" "INTENT MERGE-WAIT-UNKNOWN ticket=PILOT-UNK" "AC3: the intent is the named UNKNOWN, not a plain MERGE-WAIT"
calls="$(cat "$STUB_CALLS")"
assert_contains "$calls" "MERGE-STATE UNKNOWN" "AC3/AC4: the ticket message says UNKNOWN and names the missing source"
assert_not_contains "$calls" "WAITING ON A HUMAN MERGE" "AC3: it does NOT masquerade as a settled human merge wait ('not merged')"
ORCH_STATE_ROOT="$SAVED_STATE_ROOT"

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
