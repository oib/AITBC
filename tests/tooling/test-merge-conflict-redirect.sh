#!/bin/bash
# =============================================================================
# Test: Sweep-based MR-conflict detection at the merge gate (PILOT-18)
# =============================================================================
# merge_wait_release only asks "is the MR merged yet" (ancestry). It never asks
# "does the MR still merge cleanly". On 2026-07-22 (v3-pilot #3) MR !159 was broken
# by the merge of !158 (migration-number collision 015/015 + migrate.test.ts) and
# sat CONFLICTED at the human merge gate — invisible to the sweep; only the operator
# caught it and hand-redirected it with a resolution recipe.
#
# merge_conflict_redirect closes that wound: for every story resting at
# `Ready for Merge` it probes MERGEABILITY (story_mergeability — the adapter
# `mergeable` field with a forge, a `git merge-tree` dry-run without one) and, on
# CONFLICT, redirects to `Merging` with the PILOT-9 resolution recipe + a
# notification. AC2: a clean/undecidable MR causes NO action (no redirect, no log
# spam). AC3: the redirect fires ONCE per (MR-head, target-head) — the same conflict
# standstill is fingerprinted and skipped. AC4: merged-ness stays merge_wait_release's
# authority (a MERGED MR is never redirected; the release path is unchanged).
#
# The gate SOURCES scripts/orchestrator.sh (main is source-guarded) and exercises
# the function directly with stubbed `forge`, `tracker`, `ticket_still_in`, and the
# two probes — no real adapter, forge platform, git host, or model. The
# story_mergeability probe is ALSO exercised for real against a hermetic local git
# sandbox (no network) for both the conflicted and the clean case.
#
# bash 3.2 + BSD tools only. Run from repo root:
#   bash tests/test-merge-conflict-redirect.sh
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

echo -e "${CYAN}=== Sweep-based MR-conflict detection at the merge gate (PILOT-18) ===${NC}\n"

# =============================================================================
echo -e "${CYAN}story_mergeability — FORGE lane reads the adapter \`mergeable\` field${NC}"
# =============================================================================
# The git-host-adapter seam maps GitLab detailed_merge_status / Bitbucket mergeable
# onto ONE canonical `mergeable=BOOL` field (backend-forge.sh already prints it), so
# the orchestrator stays host-agnostic. false -> CONFLICT, true -> CLEAN, absent ->
# UNKNOWN (fail-open, never a false redirect).
STUB_PR_LINE=""
forge() { printf '%s\n' "$STUB_PR_LINE"; }

FORGE_CMD="stub"
STUB_PR_LINE="OPEN #159 ci=passed mergeable=false"
assert_eq "$(story_mergeability PILOT-9)" "CONFLICT" "mergeable=false -> CONFLICT (a foreign merge broke it)"
STUB_PR_LINE="OPEN #159 ci=passed mergeable=true"
assert_eq "$(story_mergeability PILOT-9)" "CLEAN" "mergeable=true -> CLEAN (legitimate merge-wait rest)"
STUB_PR_LINE="OPEN #159 ci=passed"
assert_eq "$(story_mergeability PILOT-9)" "UNKNOWN" "no mergeable field -> UNKNOWN (fail-open)"
STUB_PR_LINE="NONE"
assert_eq "$(story_mergeability PILOT-9)" "UNKNOWN" "no MR tracked -> UNKNOWN (fail-open)"
FORGE_CMD=""
echo

# =============================================================================
echo -e "${CYAN}story_mergeability — PILOT lane (no forge) via a hermetic git merge-tree${NC}"
# =============================================================================
# Build a real local sandbox (no network): a base commit on main pushed to a bare
# "remote", then a story branch and a foreign change on main that either conflict
# (same file, divergent edits) or do not (different files).
_mt_tmp="$(mktemp -d "${TMPDIR:-/tmp}/mcr-mergetree-XXXXXX")"
git init -q --bare "$_mt_tmp/remote.git"
git init -q "$_mt_tmp/work"
(
  cd "$_mt_tmp/work"
  git config user.email t@t; git config user.name t
  printf 'base\n' > f.txt; git add f.txt; git commit -q -m base
  git branch -m main
  git remote add origin "$_mt_tmp/remote.git"
  git push -q -u origin main

  # Conflicting story: edits the SAME file the foreign merge will also edit.
  # Its commit carries the SAFe `[<ticket>]` tag every real story commit follows —
  # that tag is what marks the branch as genuinely THIS story's (ABS-225 guard).
  git checkout -q -b PILOT-CONFLICT-auto
  printf 'story-change\n' > f.txt; git add f.txt; git commit -q -m 'feat: story [PILOT-CONFLICT]'

  # Clean story: from main tip, edits a DIFFERENT file.
  git checkout -q main
  git checkout -q -b PILOT-CLEAN-auto
  printf 'other\n' > g.txt; git add g.txt; git commit -q -m 'feat: clean [PILOT-CLEAN]'

  # Already-merged story: its head IS on main.
  git checkout -q main
  git checkout -q -b PILOT-MERGED-auto
  git checkout -q main

  # ABS-225 collision: a foreign branch that merely SHARES the `<id>-auto` name
  # (from unrelated work — its commit is tagged with a DIFFERENT ticket) and
  # conflicts on the same file. It is NOT this story's branch, so it must NOT
  # trigger a CONFLICT redirect. Mirrors the real gitlab/DEMO-1-auto (an ABS-225
  # branch) that collided with test ticket ids and broke the epic gate.
  git checkout -q main
  git checkout -q -b PILOT-FOREIGN-auto
  printf 'foreign-unrelated\n' > f.txt; git add f.txt; git commit -q -m 'feat: unrelated [ABS-225]'
  git checkout -q main

  # Foreign merge lands on main: same file, divergent from the story edit.
  git checkout -q main
  printf 'foreign-change\n' > f.txt; git add f.txt; git commit -q -m foreign
  git push -q origin main
  git fetch -q origin
) >/dev/null 2>&1

ORCH_STATE_ROOT_SAVE="${ORCH_STATE_ROOT:-}"; ORCH_STATE_ROOT="$_mt_tmp/work"
ORCH_LOCAL_MAIN_BRANCH="main"; ORCH_MAIN_REMOTE="origin"
# Parentless story -> target is main; stub away the tracker lookup.
story_merge_target_branch() { printf 'main'; }
FORGE_CMD=""

assert_eq "$(story_mergeability PILOT-CONFLICT)" "CONFLICT" \
    "story branch conflicts with the foreign merge on the target -> CONFLICT (the !159 case)"
assert_eq "$(story_mergeability PILOT-CLEAN)" "CLEAN" \
    "story branch touches a different file -> CLEAN (no false alarm)"
assert_eq "$(story_mergeability PILOT-MERGED)" "CLEAN" \
    "already-merged story head (ancestor of target) -> CLEAN (merged-ness is not a conflict)"
assert_eq "$(story_mergeability PILOT-FOREIGN)" "UNKNOWN" \
    "ABS-225: a conflicting <id>-auto branch that carries NO [<ticket>] tag is a foreign name-collision, not this story -> UNKNOWN (no false redirect)"
assert_eq "$(story_mergeability PILOT-NOBRANCH)" "UNKNOWN" \
    "no story branch anywhere -> UNKNOWN (fail-open, nothing to judge)"

ORCH_STATE_ROOT="$ORCH_STATE_ROOT_SAVE"
rm -rf "$_mt_tmp" 2>/dev/null || true
unset -f story_merge_target_branch
echo

# =============================================================================
# --- gate wiring stubs -------------------------------------------------------
# =============================================================================
STUB_CALLS=""; STUB_IN=0; STUB_MERGEABILITY="CONFLICT"; STUB_FP="mrHEAD:tgtHEAD"; STUB_TRC=0
tracker() {
    case "$1" in
        comment)    shift; printf 'COMMENT %s\n' "$*" >> "$STUB_CALLS" ;;
        transition) shift; printf 'TRANSITION %s\n' "$*" >> "$STUB_CALLS"; return "$STUB_TRC" ;;
        *)          : ;;
    esac
}
ticket_still_in() { return "$STUB_IN"; }
story_mergeability() { printf '%s' "$STUB_MERGEABILITY"; }
merge_conflict_fp() { printf '%s' "$STUB_FP"; }

STUB_CALLS="$(mktemp "${TMPDIR:-/tmp}/mcr-calls-XXXXXX")"
ORCH_RUN_LOG="$(mktemp "${TMPDIR:-/tmp}/mcr-runlog-XXXXXX")"
ORCH_STATE_DIR="$(mktemp -d "${TMPDIR:-/tmp}/mcr-state-XXXXXX")"

# run_gate <ticket> <to> — run merge_conflict_redirect, capturing stdout(intent) + rc.
run_gate() {
    : > "$STUB_CALLS"; : > "$ORCH_RUN_LOG"
    local rc=0 out
    out="$(merge_conflict_redirect "$1" "$2" 2>/dev/null)" || rc=$?
    printf '%s\n%s' "$rc" "$out"
}

# =============================================================================
echo -e "${CYAN}AC1 — a conflicted open MR is detected, redirected to Merging, audited (live)${NC}"
# =============================================================================
MODE="live"; STUB_IN=0; STUB_MERGEABILITY="CONFLICT"; STUB_FP="mrA:tgtA"; STUB_TRC=0
rm -f "$(merge_conflict_marker PILOT-18)"
res="$(run_gate "PILOT-18" "Ready for Merge")"; rc="${res%%$'\n'*}"; out="${res#*$'\n'}"
assert_eq "$rc" "0" "gate INTERVENES (rc 0) on a conflicted merge-wait story"
assert_contains "$out" "INTENT MERGE-CONFLICT-REDIRECT ticket=PILOT-18 role=- to=Merging" "logs the merge-conflict redirect intent to Merging"
calls="$(cat "$STUB_CALLS")"
assert_contains "$calls" "TRANSITION PILOT-18 Merging" "re-transitions the ticket back to Merging (auto-redirect)"
assert_contains "$calls" "--expect-from Ready for Merge" "the redirect is guarded with --expect-from (lost race NOOPs, ABS-198)"
assert_contains "$calls" "COMMENT PILOT-18 --kind gate-results --actor orchestrator" "posts a gate-results comment as the orchestrator"
assert_contains "$calls" "scripts/next-migration-number.sh" "reason carries the PILOT-9 recipe: re-draw migration numbers, never guess"
assert_contains "$calls" "--force-with-lease" "reason names the --force-with-lease push after rebase+resolve"
assert_contains "$calls" "PILOT-18" "audit cites PILOT-18"
assert_contains "$calls" "--kind notification" "fires a notification event so the operator SEES it (no action needed)"
assert_contains "$out" "INTENT NOTIFY ticket=PILOT-18" "emits the NOTIFY intent line"
assert_contains "$(cat "$ORCH_RUN_LOG")" "INTENT-MERGE-CONFLICT-REDIRECT	PILOT-18" "writes an INTENT-MERGE-CONFLICT-REDIRECT run.log event"

# =============================================================================
echo -e "\n${CYAN}AC2 — a CLEAN waiting MR causes NO action (no redirect, no log spam)${NC}"
# =============================================================================
MODE="live"; STUB_IN=0; STUB_MERGEABILITY="CLEAN"; STUB_FP="mrB:tgtB"
res="$(run_gate "PILOT-20" "Ready for Merge")"; rc="${res%%$'\n'*}"; out="${res#*$'\n'}"
assert_eq "$rc" "1" "clean MR -> no-op (rc 1), the human merge gate keeps resting"
assert_not_contains "$out" "INTENT MERGE-CONFLICT-REDIRECT" "no gate intent when the MR merges cleanly (no log spam)"
assert_eq "$(cat "$STUB_CALLS")" "" "no adapter writes for a clean waiting MR"

# =============================================================================
echo -e "\n${CYAN}AC2 — an UNDECIDABLE (UNKNOWN) MR fails open: no action${NC}"
# =============================================================================
MODE="live"; STUB_IN=0; STUB_MERGEABILITY="UNKNOWN"; STUB_FP="mrC:tgtC"
res="$(run_gate "PILOT-21" "Ready for Merge")"; rc="${res%%$'\n'*}"
assert_eq "$rc" "1" "unknown mergeability -> no-op (rc 1): degraded host never triggers a false redirect"
assert_eq "$(cat "$STUB_CALLS")" "" "no writes when mergeability cannot be determined"

# =============================================================================
echo -e "\n${CYAN}AC3 — the SAME conflict standstill redirects only ONCE (flapping guard)${NC}"
# =============================================================================
MODE="live"; STUB_IN=0; STUB_MERGEABILITY="CONFLICT"; STUB_FP="mrD:tgtD"; STUB_TRC=0
rm -f "$(merge_conflict_marker PILOT-22)"
res="$(run_gate "PILOT-22" "Ready for Merge")"; assert_eq "${res%%$'\n'*}" "0" "first CONFLICT at (mrD,tgtD) -> redirects (rc 0)"
res="$(run_gate "PILOT-22" "Ready for Merge")"; rc="${res%%$'\n'*}"
assert_eq "$rc" "1" "same (MR-head,target-head) again -> no re-redirect (rc 1), no spam"
assert_eq "$(cat "$STUB_CALLS")" "" "no writes on the repeat of an unchanged conflict standstill"
# A NEW foreign merge (target moves) or a rebase (MR head moves) is a fresh fingerprint.
STUB_FP="mrD:tgtE"
res="$(run_gate "PILOT-22" "Ready for Merge")"; rc="${res%%$'\n'*}"
assert_eq "$rc" "0" "a changed fingerprint (new target head) -> redirects again (rc 0)"

# =============================================================================
echo -e "\n${CYAN}AC4 — a MERGED MR is left to merge_wait_release (no conflict redirect)${NC}"
# =============================================================================
# A merged MR reads CLEAN from story_mergeability (ancestry short-circuit), so the
# conflict gate no-ops and the ancestor/merged-ness release path stays authoritative.
MODE="live"; STUB_IN=0; STUB_MERGEABILITY="CLEAN"; STUB_FP="mrF:tgtF"
res="$(run_gate "PILOT-23" "Ready for Merge")"; assert_eq "${res%%$'\n'*}" "1" "merged/clean MR -> conflict gate no-ops (merge_wait_release keeps authority)"
# merge_wait_release still releases a MERGED story unchanged (regression).
story_merge_state() { printf 'MERGED\t#900'; }
: > "$STUB_CALLS"
mw_rc=0; mw_out="$(merge_wait_release "PILOT-23" "Ready for Merge" 2>/dev/null)" || mw_rc=$?
assert_eq "$mw_rc" "0" "merge_wait_release still releases a MERGED story (rc 0) — release path untouched by PILOT-18"
assert_contains "$mw_out" "INTENT MERGE-WAIT-RELEASE ticket=PILOT-23 role=- to=Docs" "merge_wait_release still routes a merged story to Docs"
assert_contains "$(cat "$STUB_CALLS")" "TRANSITION PILOT-23 Docs" "the ancestor/merged-ness release still transitions to Docs"
unset -f story_merge_state

# =============================================================================
echo -e "\n${CYAN}Dry-run logs the intent but performs NO adapter writes${NC}"
# =============================================================================
MODE="dry-run"; STUB_IN=0; STUB_MERGEABILITY="CONFLICT"; STUB_FP="mrG:tgtG"
rm -f "$(merge_conflict_marker PILOT-24)"
res="$(run_gate "PILOT-24" "Ready for Merge")"; rc="${res%%$'\n'*}"; out="${res#*$'\n'}"
assert_eq "$rc" "0" "dry-run still reports the intervention (rc 0)"
assert_contains "$out" "INTENT MERGE-CONFLICT-REDIRECT ticket=PILOT-24 role=- to=Merging" "dry-run logs the redirect intent"
assert_eq "$(cat "$STUB_CALLS")" "" "dry-run makes NO tracker comment/transition/notify calls"
MODE="live"

# =============================================================================
echo -e "\n${CYAN}Scoping — non-Ready-for-Merge target and a moved-on ticket are no-ops${NC}"
# =============================================================================
MODE="live"; STUB_IN=0; STUB_MERGEABILITY="CONFLICT"; STUB_FP="mrH:tgtH"
res="$(run_gate "PILOT-25" "Merging")"; assert_eq "${res%%$'\n'*}" "1" "to != Ready for Merge -> no-op (only guards the merge-gate rest)"
res="$(run_gate "PILOT-26" "Docs")";    assert_eq "${res%%$'\n'*}" "1" "to = Docs -> no-op"
STUB_IN=1
res="$(run_gate "PILOT-27" "Ready for Merge")"; assert_eq "${res%%$'\n'*}" "1" "ticket_still_in false (moved on) -> no-op, no stale write"
assert_eq "$(cat "$STUB_CALLS")" "" "no writes once the ticket has left Ready for Merge"

# =============================================================================
echo -e "\n${CYAN}Fail-LOUD — a rejected 'Ready for Merge' -> 'Merging' edge surfaces, not silent${NC}"
# =============================================================================
MODE="live"; STUB_IN=0; STUB_MERGEABILITY="CONFLICT"; STUB_FP="mrI:tgtI"; STUB_TRC=1
rm -f "$(merge_conflict_marker PILOT-28)"
res="$(run_gate "PILOT-28" "Ready for Merge")"; rc="${res%%$'\n'*}"
assert_eq "$rc" "1" "rejected redirect -> returns 1 (does not report a phantom intervention)"
assert_contains "$(cat "$ORCH_RUN_LOG")" "MERGE-CONFLICT-REDIRECT-REJECTED	PILOT-28" "writes a REJECTED run.log event (fail-loud, not silent stall)"
STUB_TRC=0

# =============================================================================
echo -e "\n${CYAN}Wiring — the 'Ready for Merge' -> 'Merging' redirect edge exists in statuses.yaml${NC}"
# =============================================================================
# The redirect only lands if the adapter's transition table has the edge (shared
# with ABS-454/ABS-481). Assert it is present under `Ready for Merge` next:.
rfm_next="$(awk '
    /^  - name: / { cur = substr($0, 11) }
    cur == "Ready for Merge" && /^    next:/ { innext = 1; next }
    innext && /^  - name: / { innext = 0 }
    innext && /^      - / { print substr($0, 9) }
' "$REPO_ROOT/profiles/neutral/adapters/statuses.yaml")"
if printf '%s\n' "$rfm_next" | grep -qxF "Merging"; then
    TOTAL=$((TOTAL + 1)); PASS=$((PASS + 1))
    echo -e "  ${GREEN}PASS${NC} statuses.yaml lists 'Merging' under 'Ready for Merge' next: (redirect edge present)"
else
    TOTAL=$((TOTAL + 1)); FAIL=$((FAIL + 1))
    echo -e "  ${RED}FAIL${NC} statuses.yaml is missing the 'Ready for Merge' -> 'Merging' redirect edge"
fi

# --- cleanup temp files -------------------------------------------------------
rm -f "$STUB_CALLS" "$ORCH_RUN_LOG" 2>/dev/null || true
rm -rf "$ORCH_STATE_DIR" 2>/dev/null || true

# =============================================================================
echo -e "\n${CYAN}=== Test Results ===${NC}\n"
echo -e "  Total:  $TOTAL"
echo -e "  ${GREEN}Passed: $PASS${NC}"
if [ "$FAIL" -gt 0 ]; then
    echo -e "  ${RED}Failed: $FAIL${NC}"; exit 1
else
    echo -e "  Failed: 0"; echo -e "\n  ${GREEN}ALL TESTS PASSED${NC}\n"; exit 0
fi
