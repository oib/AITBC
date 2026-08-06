#!/bin/bash
# =============================================================================
# Test: Per-epic merge token (ABS-256 / ADR-A-0025)
# =============================================================================
# Two sibling stories of one epic touching the SAME file used to race the epic
# branch tip: the first merge invalidated the sibling's PR, the sibling was
# rebase-bounced to Ready for Development, and while it re-gated ANOTHER sibling
# merged and moved the tip again — the five-bounce livelock of the ABS-245
# consumer run.
#
# The fix has two halves and this suite pins BOTH, because the obvious half alone
# does not work:
#   1. SERIALIZE — at most one story per epic occupies the `Merging` seat.
#   2. HOLD ACROSS THE BOUNCE — the bounced holder KEEPS the token through its
#      re-gate walk, so the epic tip is frozen and its return rebase is clean.
# Half 1 without half 2 (a plain merge queue) still lets a sibling merge while the
# bounced story re-gates — the tip still moves under it and it bounces AGAIN. The
# `no double bounce` assertions below are what distinguish the two designs.
#
# AC2 -> "two stories, same file -> no double bounce"  (scenarios A, B)
# AC3 -> bounce telemetry shows the effect             (scenario C + unit tests)
#
# e2e sections drive the REAL runner (`--dry-run --once`) against the mock
# tracker; the pure-derivation unit tests SOURCE the runner and are kept LAST so
# redefining tracker()/helpers cannot leak into the e2e scenarios above.
#
# bash 3.2 + BSD tools only. Run from repo root: bash tests/test-merge-token.sh
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
        echo -e "  ${YELLOW}  Output:${NC}"; echo "$output" | grep -E '^INTENT' | head -10 | sed 's/^/    /'; FAIL=$((FAIL + 1)); fi
}
assert_not_contains() {
    local output="$1" expected="$2" label="$3"
    TOTAL=$((TOTAL + 1))
    if ! echo "$output" | grep -qF -- "$expected"; then echo -e "  ${GREEN}PASS${NC} $label"; PASS=$((PASS + 1))
    else echo -e "  ${RED}FAIL${NC} $label (did NOT expect: $expected)"
        echo -e "  ${YELLOW}  Output:${NC}"; echo "$output" | grep -E '^INTENT' | head -10 | sed 's/^/    /'; FAIL=$((FAIL + 1)); fi
}

new_env() {
    TEST_DIR="$(mktemp -d /tmp/merge-token-test-XXXXXX)"
    export MOCK_TRACKER_TICKETS_DIR="$TEST_DIR/work/tickets"
    export ORCH_STATE_DIR="$TEST_DIR/work/.orchestrator"
    export ORCH_STOP_FILE="$TEST_DIR/work/.orchestrator-stop"
    # Pin the adapter to the MOCK explicitly. $TRACKER_CMD defaults to the mock only
    # when UNSET — and an agent seat / live-run shell exports it (jira-tracker.sh),
    # which would otherwise make this suite drive the real tracker and assert against
    # whatever is on the live board. Same for the forge probe (done_pr_gate).
    export TRACKER_CMD="$TRACKER"
    unset FORGE_CMD ORCH_TARGET_REPO ORCH_RUN_LOG
    unset ORCH_MERGE_QUEUE ORCH_MERGE_TOPO ORCH_MAX_CONCURRENT ORCH_RECONCILE_ON_STARTUP
    export ORCH_BACKOFF_BASE_SECONDS=0 ORCH_OUTAGE_BURST=0
    export ORCH_SPAWN_CMD="$STUB"
    mkdir -p "$MOCK_TRACKER_TICKETS_DIR"
}
cleanup_env() { [ -n "${TEST_DIR:-}" ] && rm -rf "$TEST_DIR"; }

tracker() { bash "$TRACKER" "$@"; }
orch()    { bash "$ORCH" "$@"; }

# Walk a story up to Merging the legitimate way (station_guard reads the ticket's
# ACTUAL last transition, so the final `Story Acceptance -> Merging` hop is clean).
# actor=agent throughout, so none of these count as an `rte` merge-bounce.
walk_to_merging() {
    local t="$1" s
    for s in "Design" "Ready for Development" "In Progress" "In Review" "Security Review" \
             "Test Prep" "In Test" "Design Test" "Story Acceptance" "Merging"; do
        tracker transition "$t" "$s" --actor agent --reason walk >/dev/null 2>&1 || true
    done
}
status_of() { tracker get "$1" | awk -F': ' '/^status:/{print $2; exit}'; }
# Count the runner's intent lines of one action for one ticket.
count_intent() { echo "$1" | grep -cE "^INTENT $2 ticket=$3( |\$)" || true; }

sweep() { ORCH_RECONCILE_ON_STARTUP=1 orch --dry-run --once 2>/dev/null; }

echo -e "${CYAN}=== Per-epic merge token (ABS-256 / ADR-A-0025) ===${NC}\n"

# =============================================================================
echo -e "${CYAN}A. Serialization — two stories of one epic, only one merges${NC}"
# =============================================================================
new_env
E=$(tracker create --type epic --title "SPA epic")
S1=$(tracker create --type ticket --title "Story 1 (app.js)" --parent "$E" --role be-developer)
S2=$(tracker create --type ticket --title "Story 2 (app.js)" --parent "$E" --role be-developer)
walk_to_merging "$S1"
walk_to_merging "$S2"
assert_eq "$(status_of "$S1")" "Merging" "S1 walked to Merging"
assert_eq "$(status_of "$S2")" "Merging" "S2 walked to Merging"
tracker events >/dev/null 2>&1   # drain the walk events; reconcile re-derives

out=$(sweep)
rte_spawns=$(echo "$out" | grep -cE '^INTENT SPAWN .* role=rte to=Merging' || true)
waits=$(echo "$out" | grep -cE '^INTENT MERGE-QUEUE-WAIT' || true)
assert_eq "$rte_spawns" "1" "exactly ONE rte seat spawns for the epic (siblings serialized)"
assert_eq "$waits" "1" "the other sibling emits MERGE-QUEUE-WAIT instead of spawning"
assert_contains "$out" "INTENT MERGE-TOKEN-ACQUIRE" "the winner records the token acquisition"
assert_contains "$out" "epic=$E" "the token is keyed by the EPIC, not the ticket"
# The waiter must simply REST in Merging — the status is the queue (no new status).
if echo "$out" | grep -qE "^INTENT MERGE-QUEUE-WAIT ticket=$S1"; then WAITER="$S1"; HOLDER="$S2"; else WAITER="$S2"; HOLDER="$S1"; fi
assert_eq "$(status_of "$WAITER")" "Merging" "the waiting sibling rests in Merging (status is the queue)"
cleanup_env

# =============================================================================
echo -e "\n${CYAN}B. AC2 — the token is HELD across a merge-bounce (no double bounce)${NC}"
# =============================================================================
# THE load-bearing scenario. A plain merge queue passes section A and FAILS here.
new_env
E=$(tracker create --type epic --title "SPA epic")
S1=$(tracker create --type ticket --title "Story 1 (app.js)" --parent "$E" --role be-developer)
S2=$(tracker create --type ticket --title "Story 2 (app.js)" --parent "$E" --role be-developer)
walk_to_merging "$S1"
walk_to_merging "$S2"
tracker events >/dev/null 2>&1
out=$(sweep)
# Pin S1 as the holder deterministically: whoever won, re-cast the scenario around it.
if echo "$out" | grep -qE "^INTENT MERGE-QUEUE-WAIT ticket=$S1"; then TMP="$S1"; S1="$S2"; S2="$TMP"; fi
assert_contains "$out" "INTENT MERGE-TOKEN-ACQUIRE ticket=$S1" "S1 holds the epic's merge token"
assert_contains "$out" "INTENT MERGE-QUEUE-WAIT ticket=$S2" "S2 waits"

# --- rte bounces the holder: rebase conflict -> Ready for Development ---------
tracker transition "$S1" "Ready for Development" --actor rte \
    --reason "Merging: rebase onto the epic tip CONFLICTED on app.js — bounce" >/dev/null
tracker events >/dev/null 2>&1

out=$(sweep)
# The bounced holder re-gates (implementer spawns) — and KEEPS the token.
assert_contains "$out" "INTENT SPAWN ticket=$S1 role=be-developer to=Ready for Development" "the bounced story re-gates (implementer respawns)"
assert_not_contains "$out" "INTENT MERGE-TOKEN-RELEASE ticket=$S1" "the bounce does NOT release the token (ADR-A-0025 §3)"
# *** The assertion the whole ADR turns on ***: the sibling STILL cannot merge, so
# the epic tip cannot move under the story that is fixing its rebase against it.
assert_contains "$out" "INTENT MERGE-QUEUE-WAIT ticket=$S2" "S2 STILL waits while the bounced holder re-gates (tip frozen)"
assert_not_contains "$out" "INTENT SPAWN ticket=$S2 role=rte to=Merging" "S2 does NOT merge during the bounce — this is what kills the livelock"

# --- the holder re-gates back to Merging: same tip, clean rebase, re-entry ----
walk_to_merging "$S1"
tracker events >/dev/null 2>&1
out=$(sweep)
assert_contains "$out" "INTENT MERGE-TOKEN-HOLD ticket=$S1" "the returning holder RE-ENTERS its own token (no re-acquire race)"
assert_contains "$out" "INTENT SPAWN ticket=$S1 role=rte to=Merging" "the returning holder gets the rte seat"
assert_contains "$out" "bounces=1" "AC3: the holder's bounce count is reported (1)"
assert_not_contains "$out" "bounces=2" "AC2: it never takes a SECOND bounce — the tip never moved"
assert_contains "$out" "INTENT MERGE-QUEUE-WAIT ticket=$S2" "S2 is still queued behind the holder"

# --- the holder merges (Docs) -> token released -> the sibling may now merge ---
tracker transition "$S1" "Docs" --actor rte --reason "merged onto the epic branch" >/dev/null
tracker events >/dev/null 2>&1
out=$(sweep)
assert_contains "$out" "INTENT MERGE-TOKEN-RELEASE ticket=$S1" "reaching Docs (merged) releases the token"
assert_contains "$out" "INTENT SPAWN ticket=$S2 role=rte to=Merging" "the freed token lets the queued sibling merge — exactly one at a time"
assert_contains "$out" "INTENT MERGE-TOKEN-ACQUIRE ticket=$S2" "the sibling takes the token in its turn"
# S2 rebases onto a tip that moved exactly ONCE, by exactly ONE sibling merge.
assert_eq "$(count_intent "$out" "MERGE-QUEUE-WAIT" "$S2")" "0" "S2 no longer waits once the token is free"
cleanup_env

# =============================================================================
echo -e "\n${CYAN}C. AC3 — bounce telemetry is reported on every Merging dispatch${NC}"
# =============================================================================
new_env
E=$(tracker create --type epic --title "SPA epic")
S1=$(tracker create --type ticket --title "Solo story" --parent "$E" --role be-developer)
walk_to_merging "$S1"
tracker events >/dev/null 2>&1
out=$(sweep)
assert_contains "$out" "bounces=0" "a never-bounced story reports bounces=0"
# Two rte bounces (the pre-fix cascade signature) must be counted as such.
tracker transition "$S1" "Ready for Development" --actor rte --reason "rebase conflict" >/dev/null
walk_to_merging "$S1"
tracker transition "$S1" "Ready for Development" --actor rte --reason "rebase conflict again" >/dev/null
walk_to_merging "$S1"
tracker events >/dev/null 2>&1
out=$(sweep)
assert_contains "$out" "bounces=2" "the counter derives BOTH rte merge-bounces from the transition history"
cleanup_env

# =============================================================================
echo -e "\n${CYAN}D. Kill-switch + non-epic safety${NC}"
# =============================================================================
new_env
E=$(tracker create --type epic --title "SPA epic")
S1=$(tracker create --type ticket --title "Story 1" --parent "$E" --role be-developer)
S2=$(tracker create --type ticket --title "Story 2" --parent "$E" --role be-developer)
walk_to_merging "$S1"; walk_to_merging "$S2"
tracker events >/dev/null 2>&1
out=$(ORCH_MERGE_QUEUE=0 ORCH_RECONCILE_ON_STARTUP=1 orch --dry-run --once 2>/dev/null)
rte_spawns=$(echo "$out" | grep -cE '^INTENT SPAWN .* role=rte to=Merging' || true)
assert_eq "$rte_spawns" "2" "ORCH_MERGE_QUEUE=0 restores the unserialized behavior (both spawn)"
assert_not_contains "$out" "INTENT MERGE-QUEUE-WAIT" "kill-switch off -> no queueing at all"
cleanup_env

# A parentless story has no epic branch to serialize on — it must never be gated.
new_env
P=$(tracker create --type ticket --title "Parentless story" --role be-developer)
walk_to_merging "$P"
tracker events >/dev/null 2>&1
out=$(sweep)
assert_contains "$out" "INTENT SPAWN ticket=$P role=rte to=Merging" "a parentless story merges ungated (no epic, nothing to serialize)"
assert_not_contains "$out" "INTENT MERGE-QUEUE-WAIT" "a parentless story never queues"
cleanup_env

# =============================================================================
echo -e "\n${CYAN}E. Stale-token reclaim — liveness, not a wall clock${NC}"
# =============================================================================
# A legitimate hold spans a whole re-gate walk, so a TTL reclaim would steal the
# token mid-fix and reopen the cascade. Staleness is therefore the HOLDER'S status:
# a holder parked off the merge path (human -> Blocked) releases its grip.
new_env
E=$(tracker create --type epic --title "SPA epic")
S1=$(tracker create --type ticket --title "Story 1" --parent "$E" --role be-developer)
S2=$(tracker create --type ticket --title "Story 2" --parent "$E" --role be-developer)
walk_to_merging "$S1"; walk_to_merging "$S2"
tracker events >/dev/null 2>&1
out=$(sweep)
if echo "$out" | grep -qE "^INTENT MERGE-QUEUE-WAIT ticket=$S1"; then TMP="$S1"; S1="$S2"; S2="$TMP"; fi
# A human parks the holder OFF the merge path; its token must not wedge the epic.
tracker transition "$S1" "Blocked" --actor human --reason "parked by a human" >/dev/null
tracker events >/dev/null 2>&1
out=$(sweep)
assert_contains "$out" "INTENT MERGE-TOKEN-ACQUIRE ticket=$S2" "a holder parked off the merge path is reclaimed — the epic never wedges"
assert_contains "$out" "INTENT SPAWN ticket=$S2 role=rte to=Merging" "the sibling proceeds after the reclaim"
cleanup_env

# =============================================================================
echo -e "\n${CYAN}F. merge_bounce_count derivation (unit — sourced, kept LAST)${NC}"
# =============================================================================
export ORCH_STATE_DIR="$(mktemp -d /tmp/merge-token-unit-XXXXXX)"
# shellcheck disable=SC1090
source "$ORCH" >/dev/null 2>&1

dump_with() { printf '%s\n' "$1"; }

# An `rte` bounce out of Merging is THE merge-bounce.
D='### 2026-07-13T10:00:00Z | kind: transition-reason | actor: rte

Transition: Merging -> Ready for Development. Reason: rebase conflict on app.js.'
assert_eq "$(merge_bounce_count "$(dump_with "$D")")" "1" "rte: Merging -> Ready for Development counts as a bounce"

# The FORWARD exits are merges, not bounces.
D='### 2026-07-13T10:00:00Z | kind: transition-reason | actor: rte

Transition: Merging -> Docs. Reason: merged onto the epic branch.'
assert_eq "$(merge_bounce_count "$(dump_with "$D")")" "0" "rte: Merging -> Docs (a successful merge) is NOT a bounce"

D='### 2026-07-13T10:00:00Z | kind: transition-reason | actor: rte

Transition: Merging -> Done. Reason: merged.'
assert_eq "$(merge_bounce_count "$(dump_with "$D")")" "0" "rte: Merging -> Done is NOT a bounce"

# Only the rte seat bounces a MERGE; other seats' backward moves are plain rework.
D='### 2026-07-13T10:00:00Z | kind: transition-reason | actor: qas

Transition: Merging -> Ready for Development. Reason: not an rte merge-bounce.'
assert_eq "$(merge_bounce_count "$(dump_with "$D")")" "0" "a non-rte actor is not a merge-bounce (rework_count already owns that)"

# Bounces accumulate; unrelated transitions are ignored.
D='### 2026-07-13T10:00:00Z | kind: transition-reason | actor: rte

Transition: Merging -> Ready for Development. Reason: rebase conflict.

### 2026-07-13T11:00:00Z | kind: transition-reason | actor: po-agent

Transition: Story Acceptance -> Merging. Reason: accepted.

### 2026-07-13T12:00:00Z | kind: transition-reason | actor: rte

Transition: Merging -> Ready for Development. Reason: CI red.'
assert_eq "$(merge_bounce_count "$(dump_with "$D")")" "2" "two rte bounces accumulate; the forward Story Acceptance -> Merging hop is ignored"
assert_eq "$(merge_bounce_count "")" "0" "an empty dump yields 0"

rm -rf "$ORCH_STATE_DIR"

# =============================================================================
echo -e "\n${CYAN}G. ABS-396 — merge token granted in depends_on TOPOLOGICAL order${NC}"
# =============================================================================
# ADR-A-0014's queue grants the token to whichever contender the sweep reaches
# first (arrival/FIFO). When a predecessor and a dependent both rest in Merging,
# the dependent must rebase onto the predecessor's MERGED tip — so the predecessor
# must take the token first, whatever the arrival order.

# --- AC1: dependent ARRIVES FIRST, predecessor still wins the token ------------
# The sweep processes rows in `created` ASC order, so creating the DEPENDENT first
# makes it the first contender the sweep reaches — the exact "opposite order" case.
new_env
E=$(tracker create --type epic --title "Topo epic")
DEP=$(tracker create --type ticket --title "Dependent story" --parent "$E" --role be-developer)
PRE=$(tracker create --type ticket --title "Predecessor story" --parent "$E" --role be-developer)
tracker link "$DEP" "$PRE" depends-on >/dev/null   # DEP depends_on PRE
walk_to_merging "$DEP"
walk_to_merging "$PRE"
assert_eq "$(status_of "$DEP")" "Merging" "dependent walked to Merging"
assert_eq "$(status_of "$PRE")" "Merging" "predecessor walked to Merging"
tracker events >/dev/null 2>&1
out=$(sweep)
assert_contains "$out" "INTENT MERGE-TOKEN-ACQUIRE ticket=$PRE" "the PREDECESSOR takes the token first, despite arriving second"
assert_contains "$out" "INTENT MERGE-QUEUE-WAIT ticket=$DEP" "the dependent DEFERS even though the sweep reaches it first"
assert_contains "$out" "predecessor=$PRE topo=depends_on" "the wait names the topological predecessor"
assert_not_contains "$out" "INTENT MERGE-TOKEN-ACQUIRE ticket=$DEP" "the dependent never grabs the free token out of topo-order"
# AC3 invariant: single-holder + human-merge boundary unchanged — exactly ONE rte
# seat spawns (the holder opens the PR; humans still merge the epic PR to main).
rte_spawns=$(echo "$out" | grep -cE '^INTENT SPAWN .* role=rte to=Merging' || true)
assert_eq "$rte_spawns" "1" "single-holder invariant holds — exactly one rte merge seat (human merge-to-main untouched)"
assert_contains "$out" "INTENT SPAWN ticket=$PRE role=rte to=Merging" "the predecessor (token holder) gets the rte seat"

# --- the predecessor merges (Docs) -> token released -> dependent may merge -----
tracker transition "$PRE" "Docs" --actor rte --reason "merged onto the epic branch" >/dev/null
tracker events >/dev/null 2>&1
out=$(sweep)
# The token transfers to the dependent once the predecessor leaves Merging. (The
# age-first dependent is swept before the predecessor's Docs row, so it takes the
# now-off-path token via the stale-reclaim edge rather than an explicit RELEASE;
# the RELEASE edge itself is pinned in section B. Either way the token moves once.)
assert_contains "$out" "INTENT MERGE-TOKEN-ACQUIRE ticket=$DEP" "the dependent takes the token once its predecessor has merged"
assert_eq "$(count_intent "$out" "MERGE-QUEUE-WAIT" "$DEP")" "0" "the dependent no longer waits once the predecessor left Merging"
cleanup_env

# --- AC2: independent siblings keep a DETERMINISTIC tiebreak (age order) --------
# No depends_on relation -> topo never fires; the token goes to the age-first
# sibling (prioritize_rows: canonical priority, then adapter `created` ASC).
new_env
E=$(tracker create --type epic --title "Independent epic")
I1=$(tracker create --type ticket --title "Independent A (first)" --parent "$E" --role be-developer)
I2=$(tracker create --type ticket --title "Independent B (second)" --parent "$E" --role be-developer)
walk_to_merging "$I1"; walk_to_merging "$I2"
tracker events >/dev/null 2>&1
out=$(sweep)
assert_contains "$out" "INTENT MERGE-TOKEN-ACQUIRE ticket=$I1" "independent set: the age-first sibling wins the token (documented tiebreak)"
assert_contains "$out" "INTENT MERGE-QUEUE-WAIT ticket=$I2" "the age-second sibling waits"
assert_not_contains "$out" "topo=depends_on" "no topological deferral fires for an independent set (FIFO tiebreak preserved)"
cleanup_env

# --- kill-switch: ORCH_MERGE_TOPO=0 restores plain FIFO ------------------------
new_env
E=$(tracker create --type epic --title "Topo killswitch epic")
DEP=$(tracker create --type ticket --title "Dependent story" --parent "$E" --role be-developer)
PRE=$(tracker create --type ticket --title "Predecessor story" --parent "$E" --role be-developer)
tracker link "$DEP" "$PRE" depends-on >/dev/null
walk_to_merging "$DEP"; walk_to_merging "$PRE"
tracker events >/dev/null 2>&1
out=$(ORCH_MERGE_TOPO=0 ORCH_RECONCILE_ON_STARTUP=1 orch --dry-run --once 2>/dev/null)
assert_not_contains "$out" "topo=depends_on" "ORCH_MERGE_TOPO=0 -> no topological deferral (plain FIFO grant)"
assert_contains "$out" "INTENT MERGE-TOKEN-ACQUIRE ticket=$DEP" "FIFO: the age-first (dependent) contender takes the token when topo is off"
cleanup_env

# =============================================================================
echo -e "\n${CYAN}=== Results ===${NC}"
echo -e "  Total:  $TOTAL"
echo -e "  ${GREEN}Passed: $PASS${NC}"
[ "$FAIL" -gt 0 ] && echo -e "  ${RED}Failed: $FAIL${NC}" || echo -e "  Failed: 0"
[ "$FAIL" -eq 0 ] || exit 1
echo -e "\n${GREEN}All merge-token tests passed.${NC}"
