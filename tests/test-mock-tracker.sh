#!/bin/bash
# =============================================================================
# Test: Mock Task-Tracking Adapter (blueprint §18)
# =============================================================================
# Conformance test for scripts/mock-tracker.sh against the task-tracking
# capability contract (profiles/neutral/adapters/task-tracking.md) and the
# canonical status machine (profiles/neutral/adapters/statuses.yaml).
# Run from repo root: bash tests/test-mock-tracker.sh
#
# Strategy: point the tracker at a temp ticket store via
# MOCK_TRACKER_TICKETS_DIR and exercise all nine operations end to end —
# including the full legal status walk, an illegal transition, the Blocked
# round-trip, and events polling.
# =============================================================================

set -e
# PILOT-46: strip inherited backend/tracker env before any fixture runs (tests/sandbox-guard.sh).
# shellcheck source=tests/sandbox-guard.sh
. "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/sandbox-guard.sh"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
TRACKER="$REPO_ROOT/scripts/mock-tracker.sh"

TEST_DIR=$(mktemp -d /tmp/mock-tracker-test-XXXXXX)
trap "rm -rf $TEST_DIR" EXIT

export MOCK_TRACKER_TICKETS_DIR="$TEST_DIR/work/tickets"
export MOCK_TRACKER_STATUSES="$REPO_ROOT/profiles/neutral/adapters/statuses.yaml"

tracker() {
    bash "$TRACKER" "$@"
}

PASS=0
FAIL=0
TOTAL=0

# Colors
GREEN='\033[0;32m'
RED='\033[0;31m'
CYAN='\033[0;36m'
YELLOW='\033[1;33m'
NC='\033[0m'

assert_eq() {
    local actual="$1"
    local expected="$2"
    local label="$3"
    TOTAL=$((TOTAL + 1))
    if [ "$actual" = "$expected" ]; then
        echo -e "  ${GREEN}PASS${NC} $label"
        PASS=$((PASS + 1))
    else
        echo -e "  ${RED}FAIL${NC} $label (expected: '$expected', got: '$actual')"
        FAIL=$((FAIL + 1))
    fi
}

assert_contains() {
    local output="$1"
    local expected="$2"
    local label="$3"
    TOTAL=$((TOTAL + 1))
    if echo "$output" | grep -qF -- "$expected"; then
        echo -e "  ${GREEN}PASS${NC} $label"
        PASS=$((PASS + 1))
    else
        echo -e "  ${RED}FAIL${NC} $label (expected to find: $expected)"
        echo -e "  ${YELLOW}  Output (first 20 lines):${NC}"
        echo "$output" | head -20 | sed 's/^/    /'
        FAIL=$((FAIL + 1))
    fi
}

assert_not_contains() {
    local output="$1"
    local expected="$2"
    local label="$3"
    TOTAL=$((TOTAL + 1))
    if ! echo "$output" | grep -qF -- "$expected"; then
        echo -e "  ${GREEN}PASS${NC} $label"
        PASS=$((PASS + 1))
    else
        echo -e "  ${RED}FAIL${NC} $label (did NOT expect to find: $expected)"
        FAIL=$((FAIL + 1))
    fi
}

assert_exit_code() {
    local actual="$1"
    local expected="$2"
    local label="$3"
    TOTAL=$((TOTAL + 1))
    if [ "$actual" -eq "$expected" ]; then
        echo -e "  ${GREEN}PASS${NC} $label"
        PASS=$((PASS + 1))
    else
        echo -e "  ${RED}FAIL${NC} $label (expected exit $expected, got $actual)"
        FAIL=$((FAIL + 1))
    fi
}

assert_nonzero_exit() {
    local actual="$1"
    local label="$2"
    TOTAL=$((TOTAL + 1))
    if [ "$actual" -ne 0 ]; then
        echo -e "  ${GREEN}PASS${NC} $label"
        PASS=$((PASS + 1))
    else
        echo -e "  ${RED}FAIL${NC} $label (expected non-zero exit, got 0)"
        FAIL=$((FAIL + 1))
    fi
}

assert_file_contains() {
    local file="$1"
    local expected="$2"
    local label="$3"
    TOTAL=$((TOTAL + 1))
    if [ -f "$file" ] && grep -qF -- "$expected" "$file"; then
        echo -e "  ${GREEN}PASS${NC} $label"
        PASS=$((PASS + 1))
    else
        echo -e "  ${RED}FAIL${NC} $label (expected file to contain: $expected)"
        if [ -f "$file" ]; then
            echo -e "  ${YELLOW}  File contents (first 20 lines):${NC}"
            head -20 "$file" | sed 's/^/    /'
        else
            echo -e "  ${YELLOW}  File does not exist: $file${NC}"
        fi
        FAIL=$((FAIL + 1))
    fi
}

assert_empty() {
    local output="$1"
    local label="$2"
    TOTAL=$((TOTAL + 1))
    if [ -z "$output" ]; then
        echo -e "  ${GREEN}PASS${NC} $label"
        PASS=$((PASS + 1))
    else
        echo -e "  ${RED}FAIL${NC} $label (expected empty output, got: $output)"
        FAIL=$((FAIL + 1))
    fi
}

# =============================================================================
echo -e "\n${CYAN}=== Test 0: Script syntax and help ===${NC}\n"
# =============================================================================
syntax_output=$(bash -n "$TRACKER" 2>&1)
assert_exit_code $? 0 "mock-tracker.sh has valid bash syntax"

help_output=$(tracker help)
assert_contains "$help_output" "transition" "help lists transition"
assert_contains "$help_output" "events" "help lists events"

# =============================================================================
echo -e "\n${CYAN}=== Test 1: create — epic + children, auto-incrementing ids ===${NC}\n"
# =============================================================================
EPIC=$(tracker create --type epic --title "Conformance demo epic")
assert_eq "$EPIC" "DEMO-1" "first created id is DEMO-1"

T1=$(tracker create --type ticket --title "First child ticket" --parent "$EPIC")
assert_eq "$T1" "DEMO-2" "id auto-increments to DEMO-2"

T2=$(tracker create --type ticket --title "Second child ticket" --parent "$EPIC")
assert_eq "$T2" "DEMO-3" "id auto-increments to DEMO-3"

OTHER=$(tracker create --type subtask --title "Other prefix" --prefix TEST)
assert_eq "$OTHER" "TEST-1" "ids auto-increment per prefix (TEST-1)"

ec=0
tracker create --type nonsense --title "bad" >/dev/null 2>&1 || ec=$?
assert_nonzero_exit "$ec" "create rejects invalid type"

ec=0
tracker create --type ticket --title "orphan" --parent NOPE-99 >/dev/null 2>&1 || ec=$?
assert_nonzero_exit "$ec" "create rejects unknown parent"

# =============================================================================
echo -e "\n${CYAN}=== Test 1b: create --role — optional implementer-role hint (ABS-36 §2.2) ===${NC}\n"
# =============================================================================
# Absent --role -> no role: line at all (optional field; other adapters unaffected).
NOROLE=$(tracker create --type ticket --title "No role hint")
out=$(tracker get "$NOROLE")
assert_not_contains "$out" "role:" "create without --role emits no role frontmatter line"

# Present --role -> round-trips through get, one accepted value per role.
WITHROLE=$(tracker create --type ticket --title "Backend role" --role be-developer)
out=$(tracker get "$WITHROLE")
assert_contains "$out" "role: be-developer" "create --role be-developer surfaces via get"

FEROLE=$(tracker create --type ticket --title "Frontend role" --role fe-developer)
out=$(tracker get "$FEROLE")
assert_contains "$out" "role: fe-developer" "create --role fe-developer surfaces via get"

DEROLE=$(tracker create --type ticket --title "Data role" --role data-engineer)
out=$(tracker get "$DEROLE")
assert_contains "$out" "role: data-engineer" "create --role data-engineer surfaces via get"

ec=0
tracker create --type ticket --title "bad role" --role qas >/dev/null 2>&1 || ec=$?
assert_nonzero_exit "$ec" "create rejects invalid role value"

ec=0
tracker create --type ticket --title "role no value" --role >/dev/null 2>&1 || ec=$?
assert_nonzero_exit "$ec" "create rejects --role without a value"

# =============================================================================
echo -e "\n${CYAN}=== Test 1c: create --body-file — enriched body persists via adapter (ABS-60) ===${NC}\n"
# =============================================================================
# Absent --body-file -> the _TBD_ template body (default behavior unchanged).
DEFBODY=$(tracker create --type ticket --title "Default body")
out=$(tracker get "$DEFBODY")
assert_contains "$out" "_TBD_" "create without --body-file keeps the _TBD_ template"

# Present --body-file -> the file contents become the ticket body, no _TBD_.
BODY_FIXTURE="$TEST_DIR/enriched-child.md"
printf '## Goal\n\nShip the enriched child.\n\n## Scope\n\n**In scope:**\n\n- The one enriched unit\n\n## Acceptance Criteria\n\n- [ ] Enriched AC holds\n' > "$BODY_FIXTURE"
ENRICHED=$(tracker create --type ticket --title "Enriched child" --body-file "$BODY_FIXTURE")
out=$(tracker get "$ENRICHED")
assert_contains "$out" "Ship the enriched child." "create --body-file seeds the ticket body from the file"
assert_contains "$out" "Enriched AC holds" "create --body-file persists enriched acceptance criteria"
assert_not_contains "$out" "_TBD_" "create --body-file replaces the _TBD_ template entirely"

# A comment still appends cleanly even though the body omits '## Comments'.
tracker comment "$ENRICHED" --kind understanding --actor po-agent --body "first comment on enriched child" >/dev/null
out=$(tracker get "$ENRICHED")
assert_contains "$out" "first comment on enriched child" "comment self-heals '## Comments' on a custom body"

# A missing --body-file path is rejected.
ec=0
tracker create --type ticket --title "bad body file" --body-file "$TEST_DIR/does-not-exist.md" >/dev/null 2>&1 || ec=$?
assert_nonzero_exit "$ec" "create rejects a --body-file that does not exist"

# =============================================================================
echo -e "\n${CYAN}=== Test 2: get — full canonical ticket ===${NC}\n"
# =============================================================================
out=$(tracker get "$EPIC")
assert_contains "$out" "id: DEMO-1" "get returns frontmatter id"
assert_contains "$out" "type: epic" "get returns type"
assert_contains "$out" "status: Backlog" "get returns initial status Backlog"
assert_contains "$out" "title: Conformance demo epic" "get returns title"
assert_contains "$out" "## Goal" "ticket body has Goal section"
assert_contains "$out" "## Acceptance Criteria" "ticket body has Acceptance Criteria section"
assert_contains "$out" "## Definition of Done" "ticket body has Definition of Done section"
assert_contains "$out" "## Test Plan" "ticket body has Test Plan section"
assert_contains "$out" "## ADR Context" "ticket body has ADR Context section"

ec=0
tracker get NOPE-1 >/dev/null 2>&1 || ec=$?
assert_nonzero_exit "$ec" "get rejects unknown ticket"

# =============================================================================
echo -e "\n${CYAN}=== Test 3: children + search ===${NC}\n"
# =============================================================================
out=$(tracker children "$EPIC")
assert_contains "$out" "DEMO-2" "children lists DEMO-2"
assert_contains "$out" "DEMO-3" "children lists DEMO-3"
assert_contains "$out" "[Backlog]" "children includes status summary"
assert_not_contains "$out" "TEST-1" "children excludes non-children"

out=$(tracker search --status Backlog)
assert_contains "$out" "DEMO-1" "search by status finds DEMO-1"
assert_contains "$out" "DEMO-3" "search by status finds DEMO-3"

out=$(tracker search --type epic)
assert_contains "$out" "DEMO-1" "search by type finds the epic"
assert_not_contains "$out" "DEMO-2" "search by type excludes tickets"

out=$(tracker search --parent "$EPIC" --type ticket)
assert_contains "$out" "DEMO-2" "search by parent+type finds children"
assert_not_contains "$out" "DEMO-1" "search by parent excludes the epic itself"

# =============================================================================
echo -e "\n${CYAN}=== Test 3b: search --text — full-text over title and body ===${NC}\n"
# =============================================================================
out=$(tracker search --text "conformance")
assert_contains "$out" "DEMO-1" "text search matches in title"
assert_not_contains "$out" "DEMO-2" "text search excludes non-matching tickets"

out=$(tracker search --text "CONFORMANCE Demo")
assert_contains "$out" "DEMO-1" "text search is case-insensitive"

# Seed distinctive body text via a comment (comments live in the ticket body).
tracker comment "$T2" --kind decision --actor dedup-gate --body "Dedup marker: zanzibar rollout" >/dev/null
out=$(tracker search --text "ZANZIBAR")
assert_contains "$out" "DEMO-3" "text search matches in body, case-insensitively"
assert_not_contains "$out" "DEMO-1" "body match excludes tickets without the text"

out=$(tracker search --text "unobtainium-flux-capacitor")
assert_empty "$out" "text search with no match returns nothing"

out=$(tracker search --type epic --text "conformance")
assert_contains "$out" "DEMO-1" "text search combines with structural filters"

ec=0
tracker search --text >/dev/null 2>&1 || ec=$?
assert_nonzero_exit "$ec" "search rejects --text without a value"

# =============================================================================
echo -e "\n${CYAN}=== Test 3c: search row ordering — priority ASC, created ASC (ABS-389) ===${NC}\n"
# =============================================================================
# Canonical cross-adapter contract (profiles/neutral/adapters/task-tracking.md):
# rows sort by priority band hotfix>high>normal>low, then created oldest-first
# within a band. Fence a fixture under one epic, CREATE it in scrambled order so
# a pass proves real sorting (not insertion order). The `sleep 1` gives the two
# normals distinct (second-granularity) created stamps so the within-band
# age-ASC tiebreak is deterministic regardless of on-disk id order.
OE=$(tracker create --type epic --title "ordering fixture epic")
ON1=$(tracker create --type ticket --parent "$OE" --title "ord normal old"   --priority normal)
sleep 1
OH=$(tracker create  --type ticket --parent "$OE" --title "ord hotfix"       --priority hotfix)
OL=$(tracker create  --type ticket --parent "$OE" --title "ord low"          --priority low)
OHI=$(tracker create --type ticket --parent "$OE" --title "ord high"         --priority high)
ON2=$(tracker create --type ticket --parent "$OE" --title "ord normal young" --priority normal)
ord_actual=$(tracker search --parent "$OE" | cut -f1 | tr '\n' ' ')
assert_eq "$ord_actual" "$OH $OHI $ON1 $ON2 $OL " \
  "search orders priority ASC then created ASC (hotfix>high>normal[old>young]>low), not insertion order"

# =============================================================================
echo -e "\n${CYAN}=== Test 4: comment — timestamped, with kind and actor ===${NC}\n"
# =============================================================================
tracker comment "$T1" --kind understanding --actor po-agent --body "PO understanding recorded." >/dev/null
T1_FILE="$MOCK_TRACKER_TICKETS_DIR/$T1.md"
assert_file_contains "$T1_FILE" "kind: understanding | actor: po-agent" "comment records kind and actor"
assert_file_contains "$T1_FILE" "PO understanding recorded." "comment records the body"
assert_file_contains "$T1_FILE" "## Comments" "comments live under the Comments section"

ec=0
tracker comment "$T1" --kind bogus --actor x --body y >/dev/null 2>&1 || ec=$?
assert_nonzero_exit "$ec" "comment rejects invalid kind"

# =============================================================================
echo -e "\n${CYAN}=== Test 5: events — baseline poll ===${NC}\n"
# =============================================================================
out=$(tracker events)
assert_contains "$out" "{ticket_id: DEMO-1, from: null, to: Backlog" "first poll surfaces DEMO-1 creation"
assert_contains "$out" "{ticket_id: TEST-1, from: null, to: Backlog" "first poll surfaces TEST-1 creation"

out=$(tracker events)
assert_empty "$out" "second poll with no changes is empty"

# =============================================================================
echo -e "\n${CYAN}=== Test 6: transition — full legal walk Backlog -> ... -> Done ===${NC}\n"
# =============================================================================
ec=0
walk_out=$(
    for status in "Ready for Development" "In Progress" "In Review" "In Test" \
                  "Ready for Human Acceptance" "Ready for Merge" "Done"; do
        tracker transition "$T1" "$status" --actor coordinator --reason "walk: advancing to $status" || exit $?
    done
) || ec=$?
assert_exit_code "$ec" 0 "full legal walk succeeds"
assert_contains "$walk_out" "DEMO-2: Backlog -> Ready for Development" "walk reports first hop"
assert_contains "$walk_out" "DEMO-2: Ready for Merge -> Done" "walk reports final hop"

assert_file_contains "$T1_FILE" "status: Done" "frontmatter status updated to Done"
assert_file_contains "$T1_FILE" "kind: transition-reason | actor: coordinator" "transition comment records actor"
assert_file_contains "$T1_FILE" "Transition: Backlog -> Ready for Development. Reason: walk: advancing to Ready for Development" "transition comment records from/to and reason"
assert_file_contains "$T1_FILE" "Transition: Ready for Merge -> Done. Reason: walk: advancing to Done" "final transition comment recorded"

# updated field must have been rewritten alongside the status
updated_line=$(grep -c '^updated: ' "$T1_FILE")
assert_eq "$updated_line" "1" "exactly one updated field in frontmatter"

# =============================================================================
echo -e "\n${CYAN}=== Test 7: transition — illegal transitions rejected ===${NC}\n"
# =============================================================================
ec=0
out=$(tracker transition "$T2" "In Test" --actor coordinator --reason "skipping ahead" 2>&1) || ec=$?
assert_nonzero_exit "$ec" "Backlog -> In Test rejected with non-zero exit"
assert_contains "$out" "illegal transition" "rejection message names the illegal transition"
assert_file_contains "$MOCK_TRACKER_TICKETS_DIR/$T2.md" "status: Backlog" "status unchanged after rejected transition"

ec=0
out=$(tracker transition "$T2" "Nonexistent Status" --actor coordinator --reason "typo" 2>&1) || ec=$?
assert_nonzero_exit "$ec" "unknown target status rejected"
assert_contains "$out" "unknown status" "rejection message flags unknown status"

# Done's ONLY sanctioned exit is Ready for Development (bisect reopen, ABS-90 —
# exercised in the v3 section below); every other exit stays rejected.
ec=0
out=$(tracker transition "$T1" "In Progress" --actor coordinator --reason "resurrect" 2>&1) || ec=$?
assert_nonzero_exit "$ec" "Done -> In Progress rejected (only the bisect-reopen edge leaves Done)"

# =============================================================================
echo -e "\n${CYAN}=== Test 8: transition — Blocked round-trip ===${NC}\n"
# =============================================================================
tracker transition "$T2" "Ready for Development" --actor coordinator --reason "prioritized" >/dev/null
tracker transition "$T2" "In Progress" --actor coordinator --reason "subagent started" >/dev/null

ec=0
tracker transition "$T2" "Blocked" --actor be-developer --reason "missing credentials" >/dev/null 2>&1 || ec=$?
assert_exit_code "$ec" 0 "In Progress -> Blocked allowed"
assert_file_contains "$MOCK_TRACKER_TICKETS_DIR/$T2.md" "status: Blocked" "status is Blocked"

ec=0
tracker transition "$T2" "In Progress" --actor po-agent --reason "unblocked: credentials provided" >/dev/null 2>&1 || ec=$?
assert_exit_code "$ec" 0 "Blocked -> In Progress allowed (round-trip)"
assert_file_contains "$MOCK_TRACKER_TICKETS_DIR/$T2.md" "status: In Progress" "status back to In Progress"
assert_file_contains "$MOCK_TRACKER_TICKETS_DIR/$T2.md" "Transition: In Progress -> Blocked. Reason: missing credentials" "block reason recorded"

# =============================================================================
echo -e "\n${CYAN}=== Test 8b: transition --expect-from compare-and-set (ABS-198) ===${NC}\n"
# =============================================================================
# A dedicated ticket (does not perturb T1/T2, which later tests depend on).
CAS=$(tracker create --type ticket --title "compare-and-set path")
CAS_FILE="$MOCK_TRACKER_TICKETS_DIR/$CAS.md"
tracker transition "$CAS" "Ready for Development" --actor coordinator --reason "prioritized" >/dev/null
tracker transition "$CAS" "In Progress" --actor be-developer --reason "started" >/dev/null

# Mismatch: the ticket has moved away from the expected FROM -> NOOP, exit 0,
# no transition, status untouched (the actor-overwrite race is defused).
ec=0
out=$(tracker transition "$CAS" "In Review" --actor coordinator --reason "cas mismatch" --expect-from "Blocked" 2>&1) || ec=$?
assert_exit_code "$ec" 0 "compare-and-set mismatch exits 0 (lost race is not an error)"
assert_contains "$out" "NOOP compare-and-set expect-from=Blocked actual=In Progress" "mismatch logs a NOOP naming expected + actual"
assert_file_contains "$CAS_FILE" "status: In Progress" "status unchanged after compare-and-set NOOP"
assert_not_contains "$(cat "$CAS_FILE")" "Transition: In Progress -> In Review" "no transition comment written on NOOP"

# Match: expected FROM equals the current status -> the transition is applied.
ec=0
out=$(tracker transition "$CAS" "In Review" --actor coordinator --reason "cas match" --expect-from "In Progress" 2>&1) || ec=$?
assert_exit_code "$ec" 0 "compare-and-set match succeeds"
assert_contains "$out" "$CAS: In Progress -> In Review" "matching compare-and-set performs the transition"
assert_file_contains "$CAS_FILE" "status: In Review" "status advanced after matching compare-and-set"

# =============================================================================
echo -e "\n${CYAN}=== Test 8c: Needs PO Decision — post-merge forward exit (ABS-266) ===${NC}\n"
# =============================================================================
# ABS-234: a story escalated to Needs PO Decision from a POST-MERGE stage was
# un-routable forward — every sanctioned exit led backward into re-implementation
# (destructive: the code is already merged), so the PO-Agent had to launder it
# through Blocked purely because Blocked's resume-to-origin next: list happens to
# contain Docs. `Docs` is now a first-class exit from Needs PO Decision.
PME=$(tracker create --type ticket --title "post-merge escalation path")
PME_FILE="$MOCK_TRACKER_TICKETS_DIR/$PME.md"
tracker transition "$PME" "Needs PO Decision" --actor orchestrator --reason "escalated from a post-merge stage" >/dev/null

ec=0
out=$(tracker transition "$PME" "Docs" --actor po-agent --reason "PO accept: story is merged, resume at Docs" 2>&1) || ec=$?
assert_exit_code "$ec" 0 "AC3: Needs PO Decision -> Docs is a LEGAL transition (statuses.yaml next-table)"
assert_contains "$out" "$PME: Needs PO Decision -> Docs" "AC4: post-merge escalation routes FORWARD to Docs"
assert_file_contains "$PME_FILE" "status: Docs" "escalated story resumes at Docs, not re-implementation"
assert_not_contains "$(cat "$PME_FILE")" "-> Blocked" "AC4: routed forward WITHOUT ever laundering through Blocked (no Blocked hop in the history)"

# =============================================================================
echo -e "\n${CYAN}=== Test 9: link + update ===${NC}\n"
# =============================================================================
tracker link "$T2" "$T1" depends-on >/dev/null
assert_file_contains "$MOCK_TRACKER_TICKETS_DIR/$T2.md" "links: [depends-on:DEMO-2]" "link recorded in links"
assert_file_contains "$MOCK_TRACKER_TICKETS_DIR/$T2.md" "depends_on: [DEMO-2]" "depends-on link mirrored into depends_on"

tracker link "$T2" "https://github.com/example/repo/pull/42" pr >/dev/null
assert_file_contains "$MOCK_TRACKER_TICKETS_DIR/$T2.md" "pr:https://github.com/example/repo/pull/42" "pr link appended"

ec=0
tracker link "$T2" "$T1" friend-of >/dev/null 2>&1 || ec=$?
assert_nonzero_exit "$ec" "invalid link type rejected"

# PILOT-8: `relates` — symmetric soft link, one-sided persist, not a dependency.
tracker link "$T1" "$T2" relates >/dev/null
assert_file_contains "$MOCK_TRACKER_TICKETS_DIR/$T1.md" "relates:$T2" "relates link recorded in links facet"
assert_file_contains "$MOCK_TRACKER_TICKETS_DIR/$T1.md" "depends_on: []" "relates is NOT mirrored into depends_on"
ec=0
out=$(tracker link "$T1" "$T2" relates 2>&1) || ec=$?
assert_contains "$out" "already linked" "replayed relates link is idempotent (already linked)"

tracker update "$T2" title "Second child ticket (renamed)" >/dev/null
assert_file_contains "$MOCK_TRACKER_TICKETS_DIR/$T2.md" "title: Second child ticket (renamed)" "update rewrites title"

ec=0
tracker update "$T2" status "Done" >/dev/null 2>&1 || ec=$?
assert_nonzero_exit "$ec" "update refuses to touch status (must use transition)"

# =============================================================================
echo -e "\n${CYAN}=== Test 10: events — polling detects transitions exactly once ===${NC}\n"
# =============================================================================
out=$(tracker events)
assert_contains "$out" "{ticket_id: DEMO-2, from: Backlog, to: Done" "poll reports DEMO-2 net status change"
assert_contains "$out" "{ticket_id: DEMO-3, from: Backlog, to: In Progress" "poll reports DEMO-3 net status change"
assert_not_contains "$out" "TEST-1" "unchanged ticket produces no event"

out=$(tracker events)
assert_empty "$out" "second poll is empty (each change delivered exactly once)"

# One more single transition: detected on the next poll, and only that one.
tracker transition "$T2" "In Review" --actor coordinator --reason "handoff complete" >/dev/null
out=$(tracker events)
assert_contains "$out" "{ticket_id: DEMO-3, from: In Progress, to: In Review" "new transition surfaces on next poll"
assert_not_contains "$out" "DEMO-2" "already-delivered changes are not repeated"

out=$(tracker events)
assert_empty "$out" "and is delivered exactly once"

# =============================================================================
echo -e "\n${CYAN}=== Test 11: transition — Needs PO Decision (ABS-61) ===${NC}\n"
# =============================================================================
# The tenth canonical status: reachable from any active status, and routing out
# to Backlog / Ready for Development / Blocked once the PO-Agent has decided.
NPD=$(tracker create --type ticket --title "PO decision path")
NPD_FILE="$MOCK_TRACKER_TICKETS_DIR/$NPD.md"
tracker transition "$NPD" "Ready for Development" --actor po-agent --reason "prioritized" >/dev/null
tracker transition "$NPD" "In Progress" --actor be-developer --reason "started" >/dev/null

# TO Needs PO Decision is valid from an active status (here: In Progress).
ec=0
tracker transition "$NPD" "Needs PO Decision" --actor be-developer --reason "scope question for PO" >/dev/null 2>&1 || ec=$?
assert_exit_code "$ec" 0 "active status (In Progress) -> Needs PO Decision allowed"
assert_file_contains "$NPD_FILE" "status: Needs PO Decision" "status is Needs PO Decision"

# FROM Needs PO Decision -> Ready for Development is valid (PO decided, proceed).
ec=0
tracker transition "$NPD" "Ready for Development" --actor po-agent --reason "decided: proceed" >/dev/null 2>&1 || ec=$?
assert_exit_code "$ec" 0 "Needs PO Decision -> Ready for Development allowed"

# FROM Needs PO Decision -> an out-of-table target (In Test) is rejected.
tracker transition "$NPD" "Needs PO Decision" --actor po-agent --reason "another question" >/dev/null
ec=0
out=$(tracker transition "$NPD" "In Test" --actor po-agent --reason "skip ahead" 2>&1) || ec=$?
assert_nonzero_exit "$ec" "Needs PO Decision -> In Test rejected (not in its next set)"
assert_contains "$out" "illegal transition" "rejection names the illegal transition"

# TO Needs PO Decision is rejected FROM the terminal Done status.
DONE=$(tracker create --type ticket --title "Done ticket")
for s in "Ready for Development" "In Progress" "In Review" "In Test" \
         "Ready for Human Acceptance" "Ready for Merge" "Done"; do
    tracker transition "$DONE" "$s" --actor agent --reason "walk to $s" >/dev/null
done
ec=0
out=$(tracker transition "$DONE" "Needs PO Decision" --actor po-agent --reason "too late" 2>&1) || ec=$?
assert_nonzero_exit "$ec" "Done -> Needs PO Decision rejected (Done is terminal, not active)"
assert_file_contains "$MOCK_TRACKER_TICKETS_DIR/$DONE.md" "status: Done" "Done ticket status unchanged after rejected transition"

# =============================================================================
# v3 statuses + flags (ABS-70 / ABS-81 / ABS-82)
# =============================================================================
echo -e "\n${CYAN}--- v3: epic pipeline walk (ABS-81 executed AC) ---${NC}"

V3E=$(tracker create --type epic --title "v3 epic pipeline walk")
ec=0
for s in "PO Triage" "Grooming" "Enrichment" "Ticket Review" "Architecture Review" \
         "Stories In Flight" "Epic Integration" "Ready for Epic Acceptance" "Epic Done"; do
    tracker transition "$V3E" "$s" --actor agent --reason "walk to $s" >/dev/null 2>&1 || ec=$?
done
assert_exit_code "$ec" 0 "epic walks Backlog -> PO Triage -> ... -> Epic Done (all 9 epic statuses)"
assert_file_contains "$MOCK_TRACKER_TICKETS_DIR/$V3E.md" "status: Epic Done" "epic rests in Epic Done"

# Epic Done is terminal.
ec=0
tracker transition "$V3E" "Grooming" --actor agent --reason "no way back" >/dev/null 2>&1 || ec=$?
assert_nonzero_exit "$ec" "Epic Done is terminal (no outgoing transitions)"

# Ticket Review may bounce to Grooming (DoR rework, spec §3.10).
V3E2=$(tracker create --type epic --title "v3 DoR bounce epic")
for s in "PO Triage" "Grooming" "Enrichment" "Ticket Review"; do
    tracker transition "$V3E2" "$s" --actor agent --reason "walk" >/dev/null
done
ec=0
tracker transition "$V3E2" "Grooming" --actor qas --reason "DoR rework verdict" >/dev/null 2>&1 || ec=$?
assert_exit_code "$ec" 0 "Ticket Review -> Grooming bounce allowed (DoR rework)"

# Epic Integration may bounce back to Stories In Flight (bisect reopen path).
for s in "Enrichment" "Ticket Review" "Architecture Review" "Stories In Flight" "Epic Integration"; do
    tracker transition "$V3E2" "$s" --actor agent --reason "walk" >/dev/null
done
ec=0
tracker transition "$V3E2" "Stories In Flight" --actor rte --reason "bisect reopened a story" >/dev/null 2>&1 || ec=$?
assert_exit_code "$ec" 0 "Epic Integration -> Stories In Flight allowed (bisect reopen)"

echo -e "\n${CYAN}--- v3: story pipeline walk + flags round-trip (ABS-82 executed AC) ---${NC}"

V3S=$(tracker create --type ticket --title "v3 flagged story" --parent "$V3E" \
      --role fe-developer --flag design --flag security --flag data --ac-blocking)
out=$(tracker get "$V3S")
assert_contains "$out" "flags: [design, security, data]" "create --flag (repeatable) round-trips via get"
assert_contains "$out" "ac_blocking: true" "create --ac-blocking round-trips via get"
assert_contains "$out" "role: fe-developer" "role hint coexists with flags"

ec=0
for s in "Design" "Ready for Development" "In Progress" "In Review" "Security Review" \
         "Test Prep" "In Test" "Design Test" "Story Acceptance" "Merging" "Docs" "Done"; do
    tracker transition "$V3S" "$s" --actor agent --reason "walk to $s" >/dev/null 2>&1 || ec=$?
done
assert_exit_code "$ec" 0 "story walks Backlog -> Design -> ... -> Docs -> Done (full v3 story chain)"

# Done -> Ready for Development: the single sanctioned reopen edge (bisect, ABS-90).
ec=0
tracker transition "$V3S" "Ready for Development" --actor rte --reason "bisect isolated this story" >/dev/null 2>&1 || ec=$?
assert_exit_code "$ec" 0 "Done -> Ready for Development allowed (bisect reopen, sole sanctioned exit from Done)"

# v3 bounce edges: In Review / In Test / Design Test -> fresh implementer or Design.
V3B=$(tracker create --type ticket --title "v3 bounce edges" --flag design)
for s in "Design" "Ready for Development" "In Progress" "In Review"; do
    tracker transition "$V3B" "$s" --actor agent --reason walk >/dev/null
done
ec=0
tracker transition "$V3B" "Ready for Development" --actor system-architect --reason "review bounce" >/dev/null 2>&1 || ec=$?
assert_exit_code "$ec" 0 "In Review -> Ready for Development bounce allowed (fresh implementer)"
for s in "In Progress" "In Review" "Security Review" "Test Prep" "In Test" "Design Test"; do
    tracker transition "$V3B" "$s" --actor agent --reason walk >/dev/null
done
ec=0
tracker transition "$V3B" "Design" --actor qas-design --reason "design-fix bounce" >/dev/null 2>&1 || ec=$?
assert_exit_code "$ec" 0 "Design Test -> Design bounce allowed (design-fix)"

echo -e "\n${CYAN}--- v3: flag validation + update contract (ABS-82) ---${NC}"

# Invalid flag rejected on create.
ec=0
out=$(tracker create --type ticket --title "bad flag" --flag bogus 2>&1) || ec=$?
assert_nonzero_exit "$ec" "create --flag bogus rejected"
assert_contains "$out" "invalid flag" "rejection names the invalid flag"

# update flags: replace-whole-set on a ticket that HAD flags.
tracker update "$V3S" flags "[data]" >/dev/null
out=$(tracker get "$V3S")
assert_contains "$out" "flags: [data]" "update flags replaces the whole set"

# update flags: insert path on a ticket created WITHOUT flags.
V3P=$(tracker create --type ticket --title "v3 plain story")
tracker update "$V3P" flags "[security]" >/dev/null
out=$(tracker get "$V3P")
assert_contains "$out" "flags: [security]" "update flags inserts frontmatter on a flag-less ticket"

# update ac_blocking: insert + flip.
tracker update "$V3P" ac_blocking true >/dev/null
out=$(tracker get "$V3P")
assert_contains "$out" "ac_blocking: true" "update ac_blocking true inserts the marker"
tracker update "$V3P" ac_blocking false >/dev/null
out=$(tracker get "$V3P")
assert_contains "$out" "ac_blocking: false" "update ac_blocking false flips the marker"

# Invalid update values rejected.
ec=0
tracker update "$V3P" flags "design" >/dev/null 2>&1 || ec=$?
assert_nonzero_exit "$ec" "update flags without [list] shape rejected"
ec=0
tracker update "$V3P" flags "[bogus]" >/dev/null 2>&1 || ec=$?
assert_nonzero_exit "$ec" "update flags with invalid member rejected"
ec=0
tracker update "$V3P" ac_blocking maybe >/dev/null 2>&1 || ec=$?
assert_nonzero_exit "$ec" "update ac_blocking with non-boolean rejected"

echo -e "\n${CYAN}--- ABS-101: free-form labels + orchestrator-ready gate ---${NC}"

# create --label (repeatable) round-trips via get.
LBL=$(tracker create --type ticket --title "labelled" --label orchestrator-ready --label triage)
out=$(tracker get "$LBL")
assert_contains "$out" "labels: [orchestrator-ready, triage]" "create --label (repeatable) round-trips via get"

# search --label matches EXACTLY (no substring false-positive).
out=$(tracker search --label orchestrator-ready)
assert_contains "$out" "$LBL" "search --label finds the labelled ticket"
out=$(tracker search --label ready)
assert_not_contains "$out" "$LBL" "search --label ready does NOT match 'orchestrator-ready' (exact, not substring)"

# create dedupe is exact-token too: a label that is a substring of an earlier
# one must still be added, while an exact repeat is dropped.
LBLSUB=$(tracker create --type ticket --title "substring labels" --label orchestrator-ready --label ready --label ready)
out=$(tracker get "$LBLSUB")
assert_contains "$out" "labels: [orchestrator-ready, ready]" "create --label keeps a label nested inside an earlier one, drops exact repeats"

# update labels: insert path on a ticket created WITHOUT labels.
LBL2=$(tracker create --type ticket --title "plain then labelled")
tracker update "$LBL2" labels "[orchestrator-ready]" >/dev/null
out=$(tracker get "$LBL2")
assert_contains "$out" "labels: [orchestrator-ready]" "update labels inserts frontmatter on a label-less ticket"

# Invalid label rejected on create and update.
ec=0
tracker create --type ticket --title "bad label" --label "has space" >/dev/null 2>&1 || ec=$?
assert_nonzero_exit "$ec" "create --label with an illegal char is rejected"
ec=0
tracker update "$LBL2" labels "bare" >/dev/null 2>&1 || ec=$?
assert_nonzero_exit "$ec" "update labels without [list] shape rejected"

# Labels coexist with flags/role without clobbering (independent frontmatter).
LBL3=$(tracker create --type ticket --title "labels + flags" --role fe-developer --flag design --label orchestrator-ready)
out=$(tracker get "$LBL3")
assert_contains "$out" "flags: [design]" "flags survive alongside labels"
assert_contains "$out" "labels: [orchestrator-ready]" "labels survive alongside flags"

echo -e "\n${CYAN}--- lane: first-class fastlane field (ABS-319) ---${NC}"

# AC1: default lane is normal; --lane fastlane surfaces via get.
LANE_DEF=$(tracker create --type ticket --title "default lane")
out=$(tracker get "$LANE_DEF")
assert_contains "$out" "lane: normal" "create without --lane yields lane: normal"
LANE_FAST=$(tracker create --type ticket --title "fast lane" --lane fastlane)
out=$(tracker get "$LANE_FAST")
assert_contains "$out" "lane: fastlane" "create --lane fastlane surfaces via get"

# AC4: lane is a real frontmatter field, NOT stored as a lane:<x> label.
assert_not_contains "$out" "labels:" "lane fastlane ticket carries no labels list"
assert_not_contains "$out" "lane:fastlane" "lane is a field, not a lane:<x> label token"

# AC2: update flips the field both ways.
out=$(tracker update "$LANE_DEF" lane fastlane)
assert_eq "$out" "$LANE_DEF: lane updated" "update lane prints the canonical success line"
assert_contains "$(tracker get "$LANE_DEF")" "lane: fastlane" "update lane fastlane flips the field"
tracker update "$LANE_DEF" lane normal >/dev/null
assert_contains "$(tracker get "$LANE_DEF")" "lane: normal" "update lane normal flips it back"

# AC3: search --lane fastlane returns exactly the fastlane tickets.
out=$(tracker search --lane fastlane)
assert_contains "$out" "$LANE_FAST" "search --lane fastlane includes the fastlane ticket"
assert_not_contains "$out" "$LANE_DEF" "search --lane fastlane excludes a normal-lane ticket"

# lane coexists with role/flags/labels without clobbering.
LANE_MIX=$(tracker create --type ticket --title "lane + flags" --lane fastlane --role fe-developer --flag design --label orchestrator-ready)
out=$(tracker get "$LANE_MIX")
assert_contains "$out" "lane: fastlane" "lane survives alongside role/flags/labels"
assert_contains "$out" "flags: [design]" "flags survive alongside lane"
assert_contains "$out" "labels: [orchestrator-ready]" "labels survive alongside lane"

# AC5: invalid lane values rejected on create and update, non-zero exit.
ec=0
tracker create --type ticket --title "bad lane" --lane express >/dev/null 2>&1 || ec=$?
assert_nonzero_exit "$ec" "create --lane with an invalid value is rejected"
ec=0
tracker update "$LANE_DEF" lane express >/dev/null 2>&1 || ec=$?
assert_nonzero_exit "$ec" "update lane with an invalid value is rejected"

echo -e "\n${CYAN}--- update body / body-file (ABS-252) ---${NC}"

# AC-rework after enrichment: the body is REWRITTEN in place; frontmatter and
# every existing comment survive. Both adapters implement this identically
# (parity contract; jira side asserted in tests/test-jira-tracker.sh).
BDY=$(tracker create --type ticket --title "body rewrite")
tracker comment "$BDY" --kind understanding --actor bsa --body "Original understanding." >/dev/null

NEWBODY="$TEST_DIR/newbody.md"
printf '## Goal\n\nReworked goal.\n\n## Acceptance Criteria\n\n- [ ] AC1: reworked\n' > "$NEWBODY"
out=$(tracker update "$BDY" body-file "$NEWBODY")
assert_eq "$out" "$BDY: body updated" "update body-file prints the canonical success line"
out=$(tracker get "$BDY")
assert_contains "$out" "- [ ] AC1: reworked" "update body-file rewrites the ticket body"
assert_not_contains "$out" "_TBD_" "update body-file replaces the old body (no _TBD_ template left)"
assert_contains "$out" "Original understanding." "update body-file preserves existing comments"
assert_contains "$out" "title: body rewrite" "update body-file preserves the frontmatter"
assert_contains "$out" "## Comments" "update body-file keeps the comments heading"

# Inline form (same write, text on the command line).
out=$(tracker update "$BDY" body "Inline body text.")
assert_eq "$out" "$BDY: body updated" "update body prints the canonical success line"
out=$(tracker get "$BDY")
assert_contains "$out" "Inline body text." "update body rewrites the body from inline text"
assert_not_contains "$out" "AC1: reworked" "update body replaces the previous body (not appended)"
assert_contains "$out" "Original understanding." "update body preserves existing comments"

# Frontmatter stays intact: exactly one updated: field, and it was refreshed.
updated_count=$(grep -c '^updated: ' "$MOCK_TRACKER_TICKETS_DIR/$BDY.md")
assert_eq "$updated_count" "1" "body rewrite leaves exactly one updated: field"

# Comments still append after a body rewrite (comments section intact).
tracker comment "$BDY" --kind gate-results --actor qas --body "Gate: PASS." >/dev/null
out=$(tracker get "$BDY")
assert_contains "$out" "Gate: PASS." "comments still append after a body rewrite"
assert_contains "$out" "Inline body text." "the rewritten body survives the new comment"

# Missing body-file path rejected.
ec=0
tracker update "$BDY" body-file "$TEST_DIR/does-not-exist.md" >/dev/null 2>&1 || ec=$?
assert_nonzero_exit "$ec" "update body-file with a missing path rejected"

# search --text finds the rewritten body (body writes are searchable).
out=$(tracker search --text "Inline body text")
assert_contains "$out" "$BDY" "search --text matches the rewritten body"

# search still lists v3-status tickets (search has no status whitelist).
out=$(tracker search --status "Epic Done")
assert_contains "$out" "$V3E" "search --status 'Epic Done' finds the epic"

echo -e "\n${CYAN}--- v3: follow-up comment kinds (ABS-75/ABS-82) ---${NC}"

ec=0
tracker comment "$V3P" --kind follow-up --actor qas --body "Follow-up: add a regression test for X." >/dev/null 2>&1 || ec=$?
assert_exit_code "$ec" 0 "kind: follow-up accepted"
ec=0
tracker comment "$V3P" --kind bsa-decision --actor bsa --body "Decision: create outside the epic." >/dev/null 2>&1 || ec=$?
assert_exit_code "$ec" 0 "kind: bsa-decision accepted"
ec=0
# ABS-182: claim kind accepted (orchestrator stakes a distributed ticket claim).
tracker comment "$V3P" --kind claim --actor orchestrator --body "Staking claim." >/dev/null 2>&1 || ec=$?
assert_exit_code "$ec" 0 "kind: claim accepted"
ec=0
tracker comment "$V3P" --kind made-up-kind --actor x --body "nope" >/dev/null 2>&1 || ec=$?
assert_nonzero_exit "$ec" "invalid comment kind still rejected"

# Migration blind-spot check (ABS-81 DoR amendment): a ticket resting in a v2
# status BEFORE the extension still gets/transitions correctly after it — the
# tickets created at the top of this suite (pre-v3 sections) already prove
# `get`; prove a v2 ticket can still take a v2 transition here.
ec=0
tracker transition "$NPD" "Backlog" --actor po-agent --reason "park (v2 flow intact)" >/dev/null 2>&1 || ec=$?
assert_exit_code "$ec" 0 "pre-existing v2 ticket still transitions after the v3 extension"

# =============================================================================
echo -e "\n${CYAN}--- assign: set and get assignee (ABS-126) ---${NC}"
# =============================================================================
ASGN=$(tracker create --type ticket --title "assign test ticket")
out=$(tracker assign "$ASGN" "user-account-123")
assert_eq "$out" "$ASGN: assignee set to user-account-123" "assign prints the success line"
out=$(tracker get "$ASGN")
assert_contains "$out" "assignee: user-account-123" "assign sets the assignee: frontmatter field"

tracker assign "$ASGN" "user-account-456" >/dev/null
out=$(tracker get "$ASGN")
assert_contains "$out" "assignee: user-account-456" "re-assign overwrites the previous assignee"
assert_not_contains "$out" "user-account-123" "previous assignee value no longer present"

ec=0
out=$(tracker assign "$ASGN" 2>&1) || ec=$?
assert_nonzero_exit "$ec" "assign without accountId fails (arity)"
assert_contains "$out" "usage: assign" "assign arity error mentions usage"

ec=0
tracker assign NOPE-99 some-acct >/dev/null 2>&1 || ec=$?
assert_nonzero_exit "$ec" "assign on unknown ticket fails"

# SA Bug 2 regression: ticket whose frontmatter has no depends_on: field.
# The awk insert-before block must fall back to the closing --- fence so the
# assignee: field is still written (silent no-op was the pre-fix behaviour).
ASGN_NODEP=$(tracker create --type ticket --title "assign test no-depends_on")
ASGN_NODEP_FILE="$TEST_DIR/work/tickets/$ASGN_NODEP.md"
_tmp_nodep="$TEST_DIR/no-dep-tmp.md"
grep -v "^depends_on:" "$ASGN_NODEP_FILE" > "$_tmp_nodep" && mv "$_tmp_nodep" "$ASGN_NODEP_FILE"
out=$(tracker assign "$ASGN_NODEP" "user-account-789")
assert_eq "$out" "$ASGN_NODEP: assignee set to user-account-789" "assign on ticket without depends_on: prints success"
out=$(tracker get "$ASGN_NODEP")
assert_contains "$out" "assignee: user-account-789" "assign on ticket without depends_on: sets the field (SA Bug 2 regression)"

# =============================================================================
# Summary
# =============================================================================
echo -e "\n${CYAN}=== Test Results ===${NC}\n"
echo -e "  Total:  $TOTAL"
echo -e "  ${GREEN}Passed: $PASS${NC}"
if [ $FAIL -gt 0 ]; then
    echo -e "  ${RED}Failed: $FAIL${NC}"
    exit 1
else
    echo -e "  Failed: 0"
    echo -e "\n  ${GREEN}ALL TESTS PASSED${NC}\n"
    exit 0
fi
