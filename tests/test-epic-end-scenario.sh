#!/usr/bin/env bash
# =============================================================================
# Test: epic-end 3-story shared-file sequential-merge scenario (ABS-399)
# =============================================================================
# EPIC ACCEPTANCE TEST for ABS-392. Reproduces the 2026-07-17 failure mode
# (ABS-352 / ABS-353 / ABS-348 each burned a full `Merging -> Ready for
# Development` conflict-bounce, ~1h each, because a late story's rebase conflict
# was only discovered AFTER it had entered Merging) and proves the epic's two
# levers eliminate it, together, in one end scenario:
#
#   lever (1) topological merge-token ordering        (child ABS-396)
#   lever (2) rebase-gate BEFORE Story Acceptance      (child ABS-397)
#             backed by the computed merge_readiness    (child ABS-395)
#             degraded git-only variant for jira/mock   (child ABS-398)
#
# The proof is split into three complementary facets of the SAME scenario:
#   Part 1 — topological token grant: a 3-story depends_on chain arriving in the
#            OPPOSITE (age) order still grants the token predecessor-first, so a
#            dependent never merges ahead of the branch it must rebase onto.
#            Driven through the REAL runner sweep against the mock tracker.
#   Part 2 — 3 stories touching ONE shared file, sequential merges: the
#            pre-acceptance rebase-gate catches every late story while it is still
#            AT Story Acceptance (never in Merging), the conflict is resolved by a
#            rebase BEFORE acceptance, and the subsequent epic-branch merge is
#            conflict-free. Asserts ZERO `Merging -> Ready for Development`
#            transitions across the whole scenario. A control merge proves the
#            conflict the gate prevents is real.
#   Part 3 — companion equivalence: the degraded git-only readiness (jira/mock)
#            maps 1:1 onto the native merge_readiness enum, so the shell-testable
#            path documents the native (Postgres) field's behaviour (AC3).
#
# Self-contained (own mktemp git repo + mock-tracker state, no fixed paths/ports).
# bash 3.2 + BSD tools only. Run from repo root: bash tests/test-epic-end-scenario.sh
# =============================================================================
set -uo pipefail
# PILOT-46: strip inherited backend/tracker env before any fixture runs (tests/sandbox-guard.sh).
# shellcheck source=tests/sandbox-guard.sh
. "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/sandbox-guard.sh"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
ORCH="$REPO_ROOT/scripts/orchestrator.sh"
TRACKER="$REPO_ROOT/scripts/mock-tracker.sh"
STUB="$REPO_ROOT/tests/fixtures/stub-claude.sh"
GATE="$REPO_ROOT/scripts/rebase-gate-check.sh"

PASS=0; FAIL=0; TOTAL=0
GREEN='\033[0;32m'; RED='\033[0;31m'; CYAN='\033[0;36m'; YELLOW='\033[1;33m'; NC='\033[0m'

assert_eq() {
    local actual="$1" expected="$2" label="$3"
    TOTAL=$((TOTAL + 1))
    if [ "$actual" = "$expected" ]; then echo -e "  ${GREEN}PASS${NC} $label"; PASS=$((PASS + 1))
    else echo -e "  ${RED}FAIL${NC} $label (expected '$expected', got '$actual')"; FAIL=$((FAIL + 1)); fi
}
assert_ne() {
    local actual="$1" unexpected="$2" label="$3"
    TOTAL=$((TOTAL + 1))
    if [ "$actual" != "$unexpected" ]; then echo -e "  ${GREEN}PASS${NC} $label"; PASS=$((PASS + 1))
    else echo -e "  ${RED}FAIL${NC} $label (did NOT expect '$unexpected')"; FAIL=$((FAIL + 1)); fi
}
assert_contains() {
    local output="$1" expected="$2" label="$3"
    TOTAL=$((TOTAL + 1))
    if echo "$output" | grep -qF -- "$expected"; then echo -e "  ${GREEN}PASS${NC} $label"; PASS=$((PASS + 1))
    else echo -e "  ${RED}FAIL${NC} $label (expected to find: $expected)"
        echo -e "  ${YELLOW}  Output:${NC}"; echo "$output" | grep -E '^INTENT' | head -12 | sed 's/^/    /'; FAIL=$((FAIL + 1)); fi
}

tracker() { bash "$TRACKER" "$@"; }
orch()    { bash "$ORCH" "$@"; }
status_of() { tracker get "$1" | awk -F': ' '/^status:/{print $2; exit}'; }

new_env() {
    TEST_DIR="$(mktemp -d "${TMPDIR:-/tmp}/epic-end-XXXXXX")"
    export MOCK_TRACKER_TICKETS_DIR="$TEST_DIR/work/tickets"
    export ORCH_STATE_DIR="$TEST_DIR/work/.orchestrator"
    export ORCH_STOP_FILE="$TEST_DIR/work/.orchestrator-stop"
    export TRACKER_CMD="$TRACKER"          # pin the adapter to the MOCK explicitly
    unset FORGE_CMD ORCH_TARGET_REPO ORCH_RUN_LOG
    unset ORCH_MERGE_QUEUE ORCH_MERGE_TOPO ORCH_MAX_CONCURRENT ORCH_RECONCILE_ON_STARTUP
    export ORCH_BACKOFF_BASE_SECONDS=0 ORCH_OUTAGE_BURST=0
    export ORCH_SPAWN_CMD="$STUB"
    mkdir -p "$MOCK_TRACKER_TICKETS_DIR"
}
cleanup_env() { [ -n "${TEST_DIR:-}" ] && rm -rf "$TEST_DIR"; }

# Walk a story up the v3 pipeline to (and including) $target. actor=agent, so none
# of these hops count as an `rte` merge-bounce.
walk_to() {
    local t="$1" target="$2" s
    for s in "Design" "Ready for Development" "In Progress" "In Review" "Security Review" \
             "Test Prep" "In Test" "Design Test" "Story Acceptance" "Merging"; do
        tracker transition "$t" "$s" --actor agent --reason walk >/dev/null 2>&1 || true
        [ "$s" = "$target" ] && break
    done
}
sweep() { ORCH_RECONCILE_ON_STARTUP=1 orch --dry-run --once 2>/dev/null; }

echo -e "${CYAN}=== epic-end 3-story shared-file sequential-merge scenario (ABS-399) ===${NC}\n"

# =============================================================================
echo -e "${CYAN}Part 1. Topological merge-token grant — 3-story depends_on chain (lever 1, ABS-396)${NC}"
# =============================================================================
# Chain S1 <- S2 <- S3 (S2 depends_on S1, S3 depends_on S2). Create in the OPPOSITE
# (age) order — S3 first, S1 last — so a plain FIFO/age grant would pick the wrong
# story. Topological ordering must still grant the token to the ROOT predecessor
# S1, deferring S2 and S3, so no dependent merges ahead of what it must rebase onto.
new_env
E=$(tracker create --type epic --title "Epic-end scenario")
S3=$(tracker create --type ticket --title "Story 3 (shared.txt)" --parent "$E" --role be-developer)
S2=$(tracker create --type ticket --title "Story 2 (shared.txt)" --parent "$E" --role be-developer)
S1=$(tracker create --type ticket --title "Story 1 (shared.txt)" --parent "$E" --role be-developer)
tracker link "$S2" "$S1" depends-on >/dev/null   # S2 depends_on S1
tracker link "$S3" "$S2" depends-on >/dev/null   # S3 depends_on S2
walk_to "$S3" "Merging"; walk_to "$S2" "Merging"; walk_to "$S1" "Merging"
assert_eq "$(status_of "$S1")" "Merging" "S1 walked to Merging"
assert_eq "$(status_of "$S2")" "Merging" "S2 walked to Merging"
assert_eq "$(status_of "$S3")" "Merging" "S3 walked to Merging"
tracker events >/dev/null 2>&1
out=$(sweep)
assert_contains "$out" "INTENT MERGE-TOKEN-ACQUIRE ticket=$S1" "the ROOT predecessor S1 takes the token first, despite being created LAST"
assert_contains "$out" "INTENT MERGE-QUEUE-WAIT ticket=$S2" "S2 defers to its predecessor S1"
assert_contains "$out" "INTENT MERGE-QUEUE-WAIT ticket=$S3" "S3 defers to its predecessor S2"
assert_contains "$out" "topo=depends_on" "the deferral is topological (depends_on), not FIFO"
rte_spawns=$(echo "$out" | grep -cE '^INTENT SPAWN .* role=rte to=Merging' || true)
assert_eq "$rte_spawns" "1" "single-holder invariant — exactly ONE rte merge seat (human merge-to-main untouched, ADR-A-0005)"
cleanup_env

# =============================================================================
echo -e "\n${CYAN}Part 2. Pre-acceptance rebase-gate — shared file, sequential merges, ZERO bounce (levers 1+2)${NC}"
# =============================================================================
# A REAL throwaway git repo: an epic branch and three story branches that ALL
# rewrite the SAME line of ONE shared file. The mock tracker carries each story's
# status so a `Merging -> Ready for Development` conflict-bounce would be a real,
# recorded transition. The seat runs the degraded rebase-gate (jira/mock, ABS-398 —
# the git-only stand-in for the native merge_readiness guard) at Story Acceptance
# and only enters Merging on a clean/ACCEPT outcome.
new_env
git init -q "$TEST_DIR/repo"
cd "$TEST_DIR/repo" || exit 1
git config user.email t@t.t; git config user.name t; git config commit.gpgsign false
git config advice.detachedHead false
EPIC="epic/ABS-392-integration"
git checkout -q -b "$EPIC"
echo "shared" > shared.txt; git add shared.txt; git commit -qm "base: shared file"   # epic tip @ base
# All three story branches fork from the SAME base commit (the epic-end setup).
git checkout -q -b s1 "$EPIC"; echo "shared s1" > shared.txt; git commit -qam "s1 edits shared line"
git checkout -q -b s2 "$EPIC"; echo "shared s2" > shared.txt; git commit -qam "s2 edits shared line"
git checkout -q -b s3 "$EPIC"; echo "shared s3" > shared.txt; git commit -qam "s3 edits shared line"
git checkout -q "$EPIC"

# Mock-tracker tickets, all walked to Story Acceptance (post-QAS, pre-Merging).
EP=$(tracker create --type epic --title "Epic ABS-392")
T1=$(tracker create --type ticket --title "Story 1" --parent "$EP" --role be-developer)
T2=$(tracker create --type ticket --title "Story 2" --parent "$EP" --role be-developer)
T3=$(tracker create --type ticket --title "Story 3" --parent "$EP" --role be-developer)
walk_to "$T1" "Story Acceptance"; walk_to "$T2" "Story Acceptance"; walk_to "$T3" "Story Acceptance"

EPICUNION="shared"          # tracks the epic-branch shared.txt as merges land
REJECTED_PREACCEPT=""       # stories the gate caught BEFORE acceptance
ACCEPTED_CLEAN=""           # stories that were already clean

# process_story <git-branch> <token> <ticket>
# Runs the pre-acceptance gate; on rebase-needed it rebases (resolving the shared
# line) BEFORE moving to Merging, so the story never enters Merging dirty and never
# bounces back to Ready for Development.
process_story() {
    local branch="$1" token="$2" ticket="$3"
    git checkout -q "$branch"
    local reason="accepted, ready to merge" rc=0
    bash "$GATE" gate "$EPIC" "$branch" "$reason" >/dev/null 2>&1 || rc=$?
    if [ "$rc" -ne 0 ]; then
        REJECTED_PREACCEPT="$REJECTED_PREACCEPT $ticket"
        # CONTROL: prove the conflict the gate prevents is REAL — a merge WITHOUT
        # the rebase (the pre-2026-07-17 behaviour) conflicts on the shared line.
        git checkout -q -b "_trial_$ticket" "$EPIC"
        local trc=0; git merge --no-edit "$branch" >/dev/null 2>&1 || trc=$?
        git merge --abort >/dev/null 2>&1 || true
        git checkout -q "$branch"; git branch -qD "_trial_$ticket"
        assert_ne "$trc" "0" "$ticket: WITHOUT the gate, the pre-rebase merge WOULD conflict (the bounce the gate prevents)"
        # Seat rebases onto the epic tip, resolving the shared-line conflict.
        if ! git rebase -q "$EPIC" >/dev/null 2>&1; then
            printf '%s %s\n' "$EPICUNION" "$token" > shared.txt
            git add shared.txt
            GIT_EDITOR=true git rebase --continue >/dev/null 2>&1
        fi
        reason="rebased onto the epic tip; shared.txt conflict resolved before acceptance"
        rc=0; bash "$GATE" gate "$EPIC" "$branch" "$reason" >/dev/null 2>&1 || rc=$?
        assert_eq "$rc" "0" "$ticket: gate ACCEPTs after the documented rebase"
    else
        ACCEPTED_CLEAN="$ACCEPTED_CLEAN $ticket"
    fi
    # ACCEPT path — ONLY NOW does the story enter Merging (never a dirty entry).
    LEDGER="$LEDGER
$(tracker transition "$ticket" "Merging" --actor rte --reason "$reason")"
    # Merge onto the epic branch — conflict-free because the rebase already ran at the gate.
    git checkout -q "$EPIC"
    local mrc=0; git merge -q --no-edit "$branch" >/dev/null 2>&1 || mrc=$?
    assert_eq "$mrc" "0" "$ticket: epic-branch merge is CONFLICT-FREE (resolved pre-acceptance)"
    assert_eq "$(grep -c '^<<<<<<<' shared.txt 2>/dev/null || true)" "0" "$ticket: merged shared.txt has no conflict markers"
    EPICUNION="$(cat shared.txt)"
    LEDGER="$LEDGER
$(tracker transition "$ticket" "Docs" --actor rte --reason "merged onto the epic branch")"
}

LEDGER=""
# Sequential merges in topological order (the order Part 1 proved the token grants).
process_story s1 s1 "$T1"
process_story s2 s2 "$T2"
process_story s3 s3 "$T3"

echo -e "  ${CYAN}-- gate outcomes --${NC}"
assert_contains "$ACCEPTED_CLEAN" "$T1" "S1 was already clean (forked at the current tip) — no rebase, straight ACCEPT"
assert_contains "$REJECTED_PREACCEPT" "$T2" "S2 rebase-needed was caught AT Story Acceptance (pre-Merging)"
assert_contains "$REJECTED_PREACCEPT" "$T3" "S3 rebase-needed was caught AT Story Acceptance (pre-Merging)"

echo -e "  ${CYAN}-- ZERO conflict-bounce (the epic's headline AC) --${NC}"
bounce_ledger=$(echo "$LEDGER" | grep -c "Merging -> Ready for Development" || true)
assert_eq "$bounce_ledger" "0" "no Merging -> Ready for Development in the driven transition ledger"
bounce_recorded=$(grep -rl "Transition: Merging -> Ready for Development" "$MOCK_TRACKER_TICKETS_DIR" 2>/dev/null | wc -l | tr -d ' ')
assert_eq "$bounce_recorded" "0" "no Merging -> Ready for Development recorded on ANY ticket (real tracker state)"
assert_eq "$(status_of "$T1")" "Docs" "S1 finished at Docs (merged, never bounced)"
assert_eq "$(status_of "$T2")" "Docs" "S2 finished at Docs (merged, never bounced)"
assert_eq "$(status_of "$T3")" "Docs" "S3 finished at Docs (merged, never bounced)"

echo -e "  ${CYAN}-- the shared file carries every story's change --${NC}"
assert_eq "$(cat "$TEST_DIR/repo/shared.txt")" "shared s1 s2 s3" "epic shared.txt is the clean union of all three stories"
cd "$REPO_ROOT" || exit 1
cleanup_env

# =============================================================================
echo -e "\n${CYAN}Part 3. Companion equivalence — degraded readiness <-> native merge_readiness (AC3)${NC}"
# =============================================================================
# The native profile computes merge_readiness (ABS-395) from pr_mirror base_sha vs
# the epic tip; the jira/mock profile has no computed field and runs the git-only
# check (ABS-398). Both reduce to the SAME predicate — `git merge-base --is-ancestor
# <epic-tip> <story>` — so the degraded outcomes documented here stand in 1:1 for
# the native enum, closing AC3 for the mock/jira variant.
new_env
git init -q "$TEST_DIR/repo3"
cd "$TEST_DIR/repo3" || exit 1
git config user.email t@t.t; git config user.name t; git config commit.gpgsign false
git config advice.detachedHead false
EPIC="epic/ABS-392-integration"
git checkout -q -b "$EPIC"
echo base > f.txt; git add f.txt; git commit -qm base
git checkout -q -b stale "$EPIC"; echo w > w.txt; git add w.txt; git commit -qm stale-work
git checkout -q "$EPIC"; echo more >> f.txt; git commit -qam advance   # tip moves past `stale`
git checkout -q -b fresh "$EPIC"; echo x > x.txt; git add x.txt; git commit -qm fresh-work

rc=0; bash "$GATE" readiness "$EPIC" fresh >/dev/null 2>&1 || rc=$?
assert_eq "$rc" "0" "degraded readiness=0 (clean) === native merge_readiness 'clean' (story contains the epic tip)"
rc=0; bash "$GATE" readiness "$EPIC" stale >/dev/null 2>&1 || rc=$?
assert_eq "$rc" "1" "degraded readiness=1 (rebase-needed) === native merge_readiness 'rebase-needed' (epic advanced past the story)"
cd "$REPO_ROOT" || exit 1
cleanup_env

# =============================================================================
echo -e "\n${CYAN}=== Results ===${NC}"
echo -e "  Total:  $TOTAL"
echo -e "  ${GREEN}Passed: $PASS${NC}"
[ "$FAIL" -gt 0 ] && echo -e "  ${RED}Failed: $FAIL${NC}" || echo -e "  Failed: 0"
[ "$FAIL" -eq 0 ] || exit 1
echo -e "\n${GREEN}All epic-end scenario tests passed.${NC}"
