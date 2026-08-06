#!/bin/bash
# =============================================================================
# Test: Three-way intake classification at the orchestrator head (ABS-104)
# =============================================================================
# Covers the Story-2 acceptance criteria for spec ABS-103 §4:
#   1. the two new adapter reads (`parent` / `child-count`) return correct values
#      via scripts/mock-tracker.sh (the reference adapter, spec §9-2);
#   2. scripts/orchestrator.sh classifies each admitted top-level Backlog ticket
#      into exactly one of empty-epic / epic-with-children / parentless-ticket
#      (plus the child-of-epic no-op) and logs an INTENT INTAKE-CLASSIFY routing
#      the ticket to the correct pipeline head — bash-only, no LLM;
#   3. a --live --once run emits the kind:gate-results audit comment naming the
#      chosen path exactly once (idempotent across sweeps).
#
# Drives the runner against the mock adapter with a temp ticket store and the
# STUB spawn (tests/fixtures/stub-spawn.sh) — never a real model.
# Run from repo root: bash tests/test-intake-classification.sh
# =============================================================================

set -e
# PILOT-46: strip inherited backend/tracker env before any fixture runs (tests/sandbox-guard.sh).
# shellcheck source=tests/sandbox-guard.sh
. "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/sandbox-guard.sh"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
ORCH="$REPO_ROOT/scripts/orchestrator.sh"
TRACKER="$REPO_ROOT/scripts/mock-tracker.sh"
STUB="$REPO_ROOT/tests/fixtures/stub-spawn.sh"

export MOCK_TRACKER_STATUSES="$REPO_ROOT/profiles/neutral/adapters/statuses.yaml"
export TRACKER_CMD="$TRACKER"

PASS=0; FAIL=0; TOTAL=0
GREEN='\033[0;32m'; RED='\033[0;31m'; CYAN='\033[0;36m'; YELLOW='\033[1;33m'; NC='\033[0m'

assert_eq() {
    local actual="$1" expected="$2" label="$3"
    TOTAL=$((TOTAL + 1))
    if [ "$actual" = "$expected" ]; then
        echo -e "  ${GREEN}PASS${NC} $label"; PASS=$((PASS + 1))
    else
        echo -e "  ${RED}FAIL${NC} $label (expected '$expected', got '$actual')"
        FAIL=$((FAIL + 1))
    fi
}

assert_contains() {
    local output="$1" expected="$2" label="$3"
    TOTAL=$((TOTAL + 1))
    if echo "$output" | grep -qF -- "$expected"; then
        echo -e "  ${GREEN}PASS${NC} $label"; PASS=$((PASS + 1))
    else
        echo -e "  ${RED}FAIL${NC} $label (expected to find: $expected)"
        echo -e "  ${YELLOW}  Output:${NC}"; echo "$output" | head -30 | sed 's/^/    /'
        FAIL=$((FAIL + 1))
    fi
}

assert_not_contains() {
    local output="$1" expected="$2" label="$3"
    TOTAL=$((TOTAL + 1))
    if ! echo "$output" | grep -qF -- "$expected"; then
        echo -e "  ${GREEN}PASS${NC} $label"; PASS=$((PASS + 1))
    else
        echo -e "  ${RED}FAIL${NC} $label (did NOT expect: $expected)"
        echo -e "  ${YELLOW}  Output:${NC}"; echo "$output" | head -30 | sed 's/^/    /'
        FAIL=$((FAIL + 1))
    fi
}

new_env() {
    TEST_DIR="$(mktemp -d /tmp/intake-class-test-XXXXXX)"
    export MOCK_TRACKER_TICKETS_DIR="$TEST_DIR/work/tickets"
    export ORCH_STATE_DIR="$TEST_DIR/work/.orchestrator"
    export ORCH_STOP_FILE="$TEST_DIR/work/.orchestrator-stop"
    unset ORCH_MAX_CONCURRENT ORCH_MAX_SPAWNS_PER_RUN ORCH_NOTIFY_TICKET
    unset ORCH_RECONCILE_ON_STARTUP ORCH_RECONCILE_EVERY_N_CYCLES STUB_RECORD_FILE
    unset STUB_FAIL STUB_HANG STUB_NO_HANDOFF STUB_TRANSITION_TO
    export ORCH_SPAWN_CMD="$STUB"
    mkdir -p "$MOCK_TRACKER_TICKETS_DIR"
}
cleanup_env() { [ -n "${TEST_DIR:-}" ] && rm -rf "$TEST_DIR"; }

tracker() { bash "$TRACKER" "$@"; }
orch()    { bash "$ORCH" "$@"; }
# current status from the adapter dump's frontmatter (ABS-271 assertions)
fm_status() { tracker get "$1" | awk -F': ' '/^status: /{print $2; exit}'; }

echo -e "${CYAN}=== Intake classification (ABS-104) ===${NC}\n"

# =============================================================================
echo -e "${CYAN}AC6 — adapter parent + child-count reads (mock reference adapter)${NC}"
# =============================================================================
new_env
EE=$(tracker create --type epic   --title "Empty epic"        --label orchestrator-ready)
EC=$(tracker create --type epic   --title "Epic w/ children"  --label orchestrator-ready)
CH=$(tracker create --type ticket --title "Child story"       --parent "$EC" --label orchestrator-ready)
PT=$(tracker create --type ticket --title "Parentless ticket" --label orchestrator-ready)

assert_eq "$(tracker parent "$PT")"       ""     "parent of a seeded parentless ticket is empty"
assert_eq "$(tracker parent "$CH")"       "$EC"  "parent of a seeded child story is its epic"
assert_eq "$(tracker child-count "$EC")"  "1"    "child-count of a seeded epic-with-children is 1"
assert_eq "$(tracker child-count "$EE")"  "0"    "child-count of a seeded empty epic is 0"
assert_eq "$(tracker child-count "$PT")"  "0"    "child-count of a parentless ticket is 0"

# arity guards mirror the other subcommands
if bash "$TRACKER" parent >/dev/null 2>&1; then
    assert_eq "guarded" "died" "parent with no id must error (arity guard)"
else
    assert_eq "guarded" "guarded" "parent with no id errors (arity guard)"
fi
cleanup_env

# =============================================================================
echo -e "\n${CYAN}AC1-5 — classifier routes each admitted ticket to exactly one head${NC}"
# =============================================================================
# All four tickets are labelled orchestrator-ready so they pass the Backlog
# opt-in gate and reach the classifier. A single --dry-run --once poll surfaces
# the four creation events; classification is bash-only (no spawn, dry-run).
new_env
EE=$(tracker create --type epic   --title "Empty epic"        --label orchestrator-ready)
EC=$(tracker create --type epic   --title "Epic w/ children"  --label orchestrator-ready)
CH=$(tracker create --type ticket --title "Child story"       --parent "$EC" --label orchestrator-ready)
PT=$(tracker create --type ticket --title "Parentless ticket" --label orchestrator-ready)
out=$(ORCH_RECONCILE_ON_STARTUP=0 orch --dry-run --once 2>/dev/null)

# AC2: empty epic -> empty-epic -> unchanged v3.0 Grooming path
assert_contains "$out" "INTENT INTAKE-CLASSIFY ticket=$EE role=- to=v3.0 Grooming path note=class=empty-epic" \
    "empty epic -> class=empty-epic, head=v3.0 Grooming path"
# AC3: epic with >=1 child -> epic-with-children -> its DoR gate (ABS-271: the head
# names the station the epic actually owes; it used to read "Path-B entry gate", a
# head no status edge led to).
assert_contains "$out" "INTENT INTAKE-CLASSIFY ticket=$EC role=- to=Ticket Review (DoR gate) note=class=epic-with-children" \
    "epic with children -> class=epic-with-children, head=Ticket Review (DoR gate)"
# AC4: parentless story/bug -> parentless-ticket -> Path-A head
assert_contains "$out" "INTENT INTAKE-CLASSIFY ticket=$PT role=- to=Path-A head note=class=parentless-ticket" \
    "parentless ticket -> class=parentless-ticket, head=Path-A head"
# AC5: a story WITH a parent-epic link is a normal child story, NOT misclassified
assert_contains "$out" "INTENT INTAKE-CLASSIFY ticket=$CH role=- to=normal child story note=class=child-of-epic" \
    "child story (has parent) -> class=child-of-epic (no misclassification)"
assert_not_contains "$out" "ticket=$CH role=- to=Path-A head note=class=parentless-ticket" \
    "child story is never classified parentless-ticket"

# AC1: each admitted ticket yields exactly one classification line
for t in "$EE" "$EC" "$PT" "$CH"; do
    n=$(echo "$out" | grep -c "INTENT INTAKE-CLASSIFY ticket=$t " || true)
    assert_eq "$n" "1" "exactly one classification line for $t"
done

# AC7 (bash-only, no LLM): dry-run classification invokes no spawn.
assert_not_contains "$out" "INTENT HANDOFF" "classification spawns no LLM (dry-run posts no handoff)"

# Additivity: the empty-epic / parentless heads still fall through to the
# existing Backlog PO-Triage dispatch (SPAWN po-agent) — routing is additive.
assert_contains "$out" "INTENT SPAWN ticket=$PT role=po-agent to=Backlog" \
    "additive: classification does not replace the Backlog SPAWN po-agent"
cleanup_env

# =============================================================================
echo -e "\n${CYAN}AC7 — live run emits the audit comment naming the path, exactly once${NC}"
# =============================================================================
new_env
PT=$(tracker create --type ticket --title "Parentless ticket" --label orchestrator-ready)
out=$(ORCH_RECONCILE_ON_STARTUP=0 orch --live --once 2>/dev/null)
assert_contains "$out" "INTENT INTAKE-CLASSIFY ticket=$PT role=- to=Path-A head note=class=parentless-ticket" \
    "live: classifies the parentless ticket"
dump=$(tracker get "$PT")
n=$(echo "$dump" | grep -c "INTAKE-CLASS=parentless-ticket" || true)
assert_eq "$n" "1" "live: exactly one INTAKE-CLASS audit comment naming the path"
# the audit comment is a kind:gate-results / actor:orchestrator block
kind=$(echo "$dump" | grep -B2 "INTAKE-CLASS=parentless-ticket" | grep -c "kind: gate-results | actor: orchestrator" || true)
assert_eq "$kind" "1" "live: the audit comment is a kind:gate-results orchestrator block"

# Idempotency: a second sweep (reconcile re-derives the labelled Backlog ticket)
# must NOT repost the audit comment.
ORCH_RECONCILE_ON_STARTUP=1 orch --live --once >/dev/null 2>&1 || true
n2=$(tracker get "$PT" | grep -c "INTAKE-CLASS=parentless-ticket" || true)
assert_eq "$n2" "1" "idempotent: a second sweep does not repost the audit comment"
cleanup_env

# =============================================================================
echo -e "\n${CYAN}ABS-271 — a PRE-FILLED epic reaches its own DoR gate (STATION-GUARD)${NC}"
# =============================================================================
# Reproduces the live hole verified on epic ABS-278 (2026-07-13T22:03:05Z): a
# pre-filled epic went `Backlog -> Stories In Flight` in ONE hop -- past the DoR
# gate at `Ticket Review` -- and released 14 children to Ready for Development.
# STATION-GUARD could not see it: `Backlog` is chain_index 0 and index-0 sources are
# exempt. The epic's own DoR gate was therefore mechanically unreachable.
#
# Note the hop needs NO lenient seat to occur: the RUNNER performs it. A pre-filled
# epic gets no forward move out of Backlog from the po-agent, so ABS-214's
# epic_join_rest_complete parks it in its JOIN state (INTENT EPIC-JOIN-REST ->
# Stories In Flight, children=2) -- straight past the gate. The fixture below drives
# exactly that: it seeds the epic and lets the runner do the rest.
new_env
EC=$(tracker create --type epic   --title "Pre-filled epic" --label orchestrator-ready)
tracker create --type ticket --title "Child WITH testable ACs" --parent "$EC" --label orchestrator-ready >/dev/null
# AC3 negative fixture: a child that violates the DoR (no testable ACs). It must not
# be waved through -- the epic must still be made to stop at the gate that reviews it.
tracker create --type ticket --title "Child WITHOUT testable ACs (DoR violation)" \
    --parent "$EC" --label orchestrator-ready >/dev/null

# Sweep 1: intake classification, po-agent spawn, and the ABS-214 JOIN-rest park
# that carries the epic past its gate -- the hop this story has to catch.
out1=$(ORCH_RECONCILE_ON_STARTUP=0 orch --live --once 2>/dev/null)
assert_contains "$out1" "INTENT EPIC-JOIN-REST ticket=$EC role=po-agent to=Stories In Flight" \
    "the runner itself parks the pre-filled epic past its DoR gate (the hole, ABS-214 edge)"
assert_eq "$(fm_status "$EC")" "Stories In Flight" "the epic lands past the gate, unreviewed"

# AC2: the audit comment describes what ACTUALLY happens -- it must not claim a
# routing the mechanism never performs.
dump=$(tracker get "$EC")
assert_contains "$dump" "INTAKE-CLASS=epic-with-children" "AC2: pre-filled epic is classified at intake"
assert_contains "$dump" "does NOT transition the epic there" \
    "AC2: audit comment states the classification does not route (honest)"
assert_contains "$dump" "STATION-GUARD enforces it" \
    "AC2: audit comment names the mechanism that DOES enforce the gate"
assert_not_contains "$dump" "routed $EC to 'Path-B entry gate'" \
    "AC2: no claim of a 'Path-B entry gate' routing that never happens"

# Sweep 2: the guard observes the landing and redirects to the skipped DoR gate.
out=$(ORCH_RECONCILE_ON_STARTUP=0 orch --live --once 2>/dev/null)
assert_contains "$out" "INTENT STATION-GUARD ticket=$EC role=- to=Ticket Review" \
    "AC1: STATION-GUARD catches the pre-filled epic landing past its DoR gate"
assert_eq "$(fm_status "$EC")" "Ticket Review" \
    "AC1: the epic is redirected to Ticket Review (the DoR gate it owed)"
# AC1/AC3: the gate is not merely reached -- the DoR review actually runs.
out3=$(ORCH_RECONCILE_ON_STARTUP=0 orch --live --once 2>/dev/null)
assert_contains "$out3" "INTENT SPAWN ticket=$EC role=qas to=Ticket Review" \
    "AC1/AC3: the DoR batch review (qas) is spawned over the children -- incl. the DoR-violating one"

# The guard must not re-fire once the epic rests at the gate (idempotent).
assert_not_contains "$out3" "INTENT STATION-GUARD ticket=$EC" \
    "AC1: the guard does not re-fire after the redirect (idempotent)"
cleanup_env

# =============================================================================
echo -e "\n${CYAN}AC4 — the decomposed (Branch-B) path Enrichment -> Ticket Review is unchanged${NC}"
# =============================================================================
# The epic that DECOMPOSES normally reaches the same gate the long way round. Its
# children exist by the time it leaves Enrichment, so it meets the pre-filled
# predicate's child-count test -- the guard must still leave it alone, because
# Enrichment -> Ticket Review skips nothing. (Asserted here rather than via
# e2e-workflow-v3.sh, which aborts in the STORY pipeline on the unrelated
# `Ready for Merge -> Docs` next-table defect, ABS-290, before it reaches the epic
# sections.)
new_env
EB=$(tracker create --type epic   --title "Decomposed epic (Branch B)" --label orchestrator-ready)
tracker create --type ticket --title "Child drafted by enrichment" --parent "$EB" --label orchestrator-ready >/dev/null
for hop in "PO Triage" "Grooming" "Enrichment" "Ticket Review"; do
    tracker transition "$EB" "$hop" --actor issue-enrichment --reason "v3 decomposition hop" >/dev/null
done
out=$(ORCH_RECONCILE_ON_STARTUP=0 orch --live --once 2>/dev/null)
assert_not_contains "$out" "INTENT STATION-GUARD ticket=$EB" \
    "AC4: Enrichment -> Ticket Review is not flagged (it skips nothing)"
assert_contains "$out" "INTENT SPAWN ticket=$EB role=qas to=Ticket Review" \
    "AC4: the decomposed epic still spawns the qas DoR review at the gate"
assert_eq "$(fm_status "$EB")" "Ticket Review" "AC4: it rests at the gate, as before"
cleanup_env

# =============================================================================
echo -e "\n${CYAN}AC4 — no false positives: an epic that ALREADY passed the gate${NC}"
# =============================================================================
# ABS-214's `Backlog -> Stories In Flight` JOIN-rest edge must survive: a DECOMPOSED
# epic that already ran the DoR gate and later re-enters Stories In Flight from
# Backlog must NOT be dragged back to it. Path: PO Triage -> Grooming -> Enrichment
# -> Ticket Review (gate runs) -> Needs PO Decision -> Backlog -> Stories In Flight.
#
# The hops go through Grooming/Enrichment because that is how a decomposed epic
# ACTUALLY reaches the gate. There is deliberately no seat edge that jumps straight
# into `Ticket Review`: this fixture used to take one, which is how a dead edge in
# statuses.yaml stayed alive -- exercised only by the test that needed it.
new_env
ED=$(tracker create --type epic   --title "Decomposed epic (gate already run)" --label orchestrator-ready)
tracker create --type ticket --title "Child story" --parent "$ED" --label orchestrator-ready >/dev/null
# Give it a history in which the DoR gate HAS run, then return it to Backlog --
# seeded before the first sweep, so the runner's own JOIN-rest park is what carries
# it into Stories In Flight (the exact ABS-214 edge the guard must not fight).
for hop in "PO Triage" "Grooming" "Enrichment" "Ticket Review" "Needs PO Decision" "Backlog"; do
    tracker transition "$ED" "$hop" --actor po-agent --reason "fixture hop" >/dev/null
done
ORCH_RECONCILE_ON_STARTUP=0 orch --live --once >/dev/null 2>&1 || true   # JOIN-rest park
assert_eq "$(fm_status "$ED")" "Stories In Flight" "AC4: the gate-passed epic reaches its JOIN state"
out=$(ORCH_RECONCILE_ON_STARTUP=0 orch --live --once 2>/dev/null)        # guard evaluates the landing
assert_not_contains "$out" "INTENT STATION-GUARD ticket=$ED" \
    "AC4: an epic that already passed the DoR gate is NOT dragged back (ABS-214 JOIN-rest intact)"
assert_eq "$(fm_status "$ED")" "Stories In Flight" \
    "AC4: it rests in its JOIN state, untouched by the guard"
cleanup_env

# =============================================================================
echo -e "\n${CYAN}=== Results ===${NC}"
echo -e "Total: $TOTAL  ${GREEN}Pass: $PASS${NC}  ${RED}Fail: $FAIL${NC}"
[ "$FAIL" -eq 0 ] || exit 1
