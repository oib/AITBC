#!/bin/bash
# =============================================================================
# E2E exit gate: Workflow v3 full agent team (ABS-80)
# =============================================================================
# Re-runs the spec's S1-S16 acceptance scenarios (specs/ABS-69-workflow-v3-
# full-agent-team-spec.md §5), previously validated only as a spec-level
# Python simulation (tests/workflow-v2-sim.py), as deterministic bash
# dry/live-runs against the REAL scripts/orchestrator.sh + the mock
# task-tracking adapter (scripts/mock-tracker.sh) with a scratch ticket
# store and the STUB spawn command (tests/fixtures/stub-spawn.sh) -- no real
# `claude`, no live model. This is the epic's exit gate, mirroring
# tests/e2e-orchestrator-dryrun.sh (ABS-55, the v1/v2 exit gate).
#
# Reuse note: setup/teardown, the tracker()/orch() wrappers, baseline(), and
# the assert_contains/assert_not_contains/assert_eq helpers are copied
# verbatim from tests/e2e-orchestrator-dryrun.sh (same harness idiom used by
# tests/tooling/test-orchestrator.sh's 210 v1-v3 assertions) rather than sourcing that
# file, so this suite stays a single self-contained, independently-runnable
# script -- sourcing would couple its exit code / trap / PASS-FAIL globals to
# a file whose primary job is being its own standalone exit gate.
#
# Each S<N> section fabricates the scenario's ticket state via the mock
# tracker, drives scripts/orchestrator.sh (--dry-run or --live as the
# scenario requires) and asserts the emitted INTENT lines / ticket dumps
# match the spec's expected outcome for that scenario.
#
# ADR-gated exception: S5 ("Combination break") exercises RTE's sequential
# merge onto the epic's integration branch + a git-bisect over that branch's
# ticket-tagged commits (spec §3.5),
# which is intentionally NOT implemented in the orchestrator yet -- it is
# gated on human acceptance of ADR-A-0014 (a standalone agentic decision:
# the per-epic integration branch + gated auto-merge ONTO it, made within
# the unchanged ADR-A-0004/0005 human-only main boundaries -- main stays
# human-merge-only; ABS-89/90). Today `Merging` and `Epic Integration` are
# plain `SPAWN rte` rows with no rebase/CI/bisect logic in
# scripts/orchestrator.sh (that behavior belongs to the RTE agent itself,
# out of scope for the orchestrator and for this gate). S5 is reported as a
# clearly-labeled SKIP rather than silently omitted.
#
# Deterministic: uses --once / ORCH_MAX_CYCLES (no timers, no kill-switch
# race), backdated frontmatter timestamps instead of real sleeps. Runs on
# macOS bash 3.2 (no associative arrays, no `mapfile`).
#
# Run from repo root: bash tests/e2e-workflow-v3.sh
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
# ABS-111: this e2e asserts v3 WORKFLOW semantics under the deterministic
# synchronous scheduler (fixed same-cycle spawn counts, same-ticket sequences).
# The async scheduler + resume/gating features have their own section in
# tests/tooling/test-orchestrator.sh ("ABS-111").
export ORCH_ASYNC_SPAWNS=0
export ORCH_DEPENDS_GATING=0
export ORCH_SESSION_RESUME=0
export ORCH_WORKTREE_SPAWNS=0
# ABS-290: the scripted stage walks drive stub seats that hand off with NO
# declared target (HANDOFF-NOMOVE by construction), which the ADR-A-0018
# escalation budget (default 3 rounds) would escalate to Blocked mid-walk —
# a harness artifact, not the workflow under test. The budget mechanism has
# its own coverage in tests/tooling/test-orchestrator.sh (ABS-199/ABS-75 sections).
export ORCH_ESCALATION_BUDGET=999

PASS=0; FAIL=0; SKIP=0; TOTAL=0
GREEN='\033[0;32m'; RED='\033[0;31m'; CYAN='\033[0;36m'; YELLOW='\033[1;33m'; NC='\033[0m'

assert_contains() {
    local output="$1" expected="$2" label="$3"
    TOTAL=$((TOTAL + 1))
    if grep -qF -- "$expected" <<<"$output"; then
        echo -e "  ${GREEN}PASS${NC} $label"; PASS=$((PASS + 1))
    else
        echo -e "  ${RED}FAIL${NC} $label (expected to find: $expected)"
        echo -e "  ${YELLOW}  Output:${NC}"; head -30 <<<"$output" | sed 's/^/    /'
        FAIL=$((FAIL + 1))
    fi
}

assert_not_contains() {
    local output="$1" expected="$2" label="$3"
    TOTAL=$((TOTAL + 1))
    if ! grep -qF -- "$expected" <<<"$output"; then
        echo -e "  ${GREEN}PASS${NC} $label"; PASS=$((PASS + 1))
    else
        echo -e "  ${RED}FAIL${NC} $label (did NOT expect: $expected)"
        echo -e "  ${YELLOW}  Output:${NC}"; head -30 <<<"$output" | sed 's/^/    /'
        FAIL=$((FAIL + 1))
    fi
}

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

skip_scenario() {
    local label="$1" reason="$2"
    SKIP=$((SKIP + 1))
    echo -e "  ${YELLOW}SKIP${NC} $label -- $reason"
}

# Per-scenario isolated environment (mirrors test-orchestrator.sh's new_env):
# a fresh scratch ticket store + orchestrator state dir, all test-only knobs
# unset so no scenario inherits a prior one's env.
new_env() {
    TEST_DIR="$(mktemp -d /tmp/workflow-v3-e2e-XXXXXX)"
    export MOCK_TRACKER_TICKETS_DIR="$TEST_DIR/work/tickets"
    export ORCH_STATE_DIR="$TEST_DIR/work/.orchestrator"
    export ORCH_STOP_FILE="$TEST_DIR/work/.orchestrator-stop"
    unset ORCH_MAX_CONCURRENT ORCH_MAX_SPAWNS_PER_RUN ORCH_NOTIFY_TICKET
    unset ORCH_RECONCILE_ON_STARTUP ORCH_RECONCILE_EVERY_N_CYCLES STUB_RECORD_FILE
    unset STUB_FAIL STUB_HANG STUB_HANG_SECONDS STUB_NO_HANDOFF STUB_TRANSITION_TO
    unset ORCH_REWORK_LIMIT ORCH_CRASH_LIMIT ORCH_MAX_SPAWNS_PER_DAY ORCH_FOLLOWUP_BUDGET
    # ABS-118: scenarios assert retry-at-cadence recovery (S8 crash -> immediate
    # sweep re-derive); backoff/outage semantics are pinned in test-orchestrator.sh.
    export ORCH_BACKOFF_BASE_SECONDS=0 ORCH_OUTAGE_BURST=0
    export ORCH_SPAWN_CMD="$STUB"
    mkdir -p "$MOCK_TRACKER_TICKETS_DIR"
    # ABS-526: hermetic target repo. Without ORCH_TARGET_REPO the runner's
    # state root is the REAL checkout, and the ABS-270 docs merge-wait gate's
    # forge-less probe (story_git_merge_state) reads refs/heads/DEMO-*-auto
    # there — a stale DEMO-1-auto branch left by any earlier non-hermetic e2e
    # run then parks S-A1 at MERGE-WAIT instead of spawning the tech-writer.
    # A fresh scratch repo per scenario has no story branches, so the probe
    # reads NONE and fails open (Docs proceeds), exactly the clean-repo
    # behavior this suite pins. Explicit MOCK_TRACKER_TICKETS_DIR/
    # ORCH_STATE_DIR above still win over the target's work/ defaults.
    export ORCH_TARGET_REPO="$TEST_DIR/target-repo"
    mkdir -p "$ORCH_TARGET_REPO"
    git -C "$ORCH_TARGET_REPO" init -q
    git -C "$ORCH_TARGET_REPO" -c user.email=t@t -c user.name=t commit --allow-empty -m init -q
}
cleanup_env() { [ -n "${TEST_DIR:-}" ] && rm -rf "$TEST_DIR"; }

tracker() { bash "$TRACKER" "$@"; }
orch()    { bash "$ORCH" "$@"; }
# walk_to <ticket> <status> [transition args...] — idempotent transition for
# the scripted stage walks. Since ADR-A-0019 / handoff-transition the RUNNER
# itself may already have moved the ticket to the next stage when the stub
# seat handed off, so a strict re-transition would error with "already in"
# (ABS-290: previously masked by the suite aborting on the RfM->Docs edge).
walk_to() {
    local t="$1" s="$2"; shift 2
    tracker get "$t" | grep -q "^status: $s\$" && return 0
    tracker transition "$t" "$s" "$@" >/dev/null
}
# Baseline: consume creation events so the next --once sees only the
# transition we drive.
baseline() { ORCH_RECONCILE_ON_STARTUP=0 orch --dry-run --once >/dev/null 2>&1; }

# backdate_field <ticket-id> <field> <iso-value> -- rewrite one frontmatter
# timestamp in place (test fixture helper mirroring test-orchestrator.sh's
# ABS-62 stall-detection section; the adapter itself never backdates).
backdate_field() {
    local file="$MOCK_TRACKER_TICKETS_DIR/$1.md" field="$2" value="$3" tmp
    tmp="$file.bd.$$"
    awk -v k="$field" -v v="$value" '
        NR==1 && $0=="---" { fm=1; print; next }
        fm==1 && $0=="---" { fm=2; print; next }
        fm==1 && index($0, k ": ")==1 { print k ": " v; next }
        { print }
    ' "$file" > "$tmp" && mv "$tmp" "$file"
}

# epic_to_sif <epic-id> [child-id]... -- walk an epic through PO Triage ..
# Stories In Flight. Architecture Review is a plain SPAWN row (spec §1.1):
# the orchestrator itself never auto-releases children into Design -- that is
# the (simulated) system-architect's own action, mirrored here as the direct
# tracker transitions test-orchestrator.sh's v3 JOIN section performs.
epic_to_sif() {
    local epic="$1"; shift
    for s in "PO Triage" "Grooming" "Enrichment" "Ticket Review" "Architecture Review"; do
        tracker transition "$epic" "$s" --actor agent --reason walk >/dev/null
    done
    local child
    for child in "$@"; do
        tracker transition "$child" "Design" --actor system-architect --reason "released" >/dev/null 2>&1 || true
    done
    tracker transition "$epic" "Stories In Flight" --actor system-architect --reason "stories released" >/dev/null
}
# story_to_done <story-id> -- walk a (possibly flagged) story to Done. Flags
# absent on the ticket are transparently SKIP-FORWARDed by the live runner;
# this helper just drives the canonical chain and tolerates either path.
story_to_done() {
    local t="$1" cur seen_cur=0
    cur="$(tracker get "$t" | grep '^status:' | head -1 | sed 's/^status: //')"
    # If the ticket is not yet on the chain at all (e.g. still Backlog), walk
    # the full chain from Design. Otherwise skip every stage up to and
    # including the current one (e.g. already released to / past Design by a
    # prior system-architect step) so we don't attempt an illegal same-or-
    # backward transition.
    case "$cur" in
        "Design"|"Ready for Development"|"In Progress"|"In Review"|"Security Review"|\
        "Test Prep"|"In Test"|"Design Test"|"Story Acceptance"|"Merging"|"Docs") ;;
        *) cur="" ;;
    esac
    for s in "Design" "Ready for Development" "In Progress" "In Review" "Security Review" \
             "Test Prep" "In Test" "Design Test" "Story Acceptance" "Merging" "Docs" "Done"; do
        if [ -n "$cur" ] && [ "$seen_cur" = "0" ]; then
            if [ "$s" = "$cur" ]; then seen_cur=1; fi
            continue
        fi
        tracker transition "$t" "$s" --actor agent --reason walk >/dev/null
    done
}

echo -e "${CYAN}=== E2E exit gate: Workflow v3 (ABS-80) — S1-S16 + v3.1 intake S-A1..S-B3 vs the real orchestrator ===${NC}\n"

# =============================================================================
echo -e "${CYAN}S1 — Happy path: 3-story epic (1 design-flagged), single NOTIFY${NC}"
# =============================================================================
# Every stage spawns exactly once per story; JOIN fires after the last Done;
# human receives exactly one ready-to-test NOTIFY.
new_env
E=$(tracker create --type epic --title "S1 happy path epic")
S1A=$(tracker create --type ticket --title "S1 story A (design)" --parent "$E" --flag design)
S1B=$(tracker create --type ticket --title "S1 story B" --parent "$E")
S1C=$(tracker create --type ticket --title "S1 story C" --parent "$E")
baseline
export ORCH_MAX_CONCURRENT=10
epic_to_sif "$E" "$S1A" "$S1B" "$S1C"
out=$(ORCH_RECONCILE_ON_STARTUP=0 orch --live --once 2>/dev/null)
assert_contains "$out" "INTENT SPAWN ticket=$S1A role=ui-ux-design to=Design" "flagged story A: Design -> ui-ux-design spawns exactly once"
assert_contains "$out" "INTENT SKIP-FORWARD ticket=$S1B role=- to=Ready for Development" "unflagged story B SKIP-FORWARDs past Design (runner re-transitions itself)"
assert_contains "$out" "INTENT SKIP-FORWARD ticket=$S1C role=- to=Ready for Development" "unflagged story C SKIP-FORWARDs past Design (runner re-transitions itself)"
out=$(ORCH_RECONCILE_ON_STARTUP=0 orch --live --once 2>/dev/null)
assert_contains "$out" "INTENT SPAWN ticket=$S1B role=be-developer to=Ready for Development" "unflagged story B released to implementation"
assert_contains "$out" "INTENT SPAWN ticket=$S1C role=be-developer to=Ready for Development" "unflagged story C released to implementation"
story_to_done "$S1A"; story_to_done "$S1B"
tracker events >/dev/null 2>&1
out=$(ORCH_RECONCILE_ON_STARTUP=1 orch --dry-run --once 2>/dev/null)
assert_not_contains "$out" "ready-to-test" "JOIN does not fire before the last story reaches Done"
story_to_done "$S1C"
out=$(ORCH_RECONCILE_ON_STARTUP=0 orch --live --once 2>/dev/null)
assert_contains "$out" "INTENT JOIN ticket=$E role=- to=Epic Integration" "last child Done -> JOIN fires (S1A/B/C all Done)"
tracker transition "$E" "Ready for Epic Acceptance" --actor rte --reason "smoke passed" >/dev/null
out=$(ORCH_RECONCILE_ON_STARTUP=0 orch --dry-run --once 2>/dev/null)
notify_count=$(echo "$out" | grep -c "INTENT NOTIFY" || true)
assert_eq "$notify_count" "1" "S1: exactly one ready-to-test NOTIFY for the whole epic"
assert_contains "$out" "ready-to-test" "S1: the NOTIFY carries the ready-to-test text"
cleanup_env

# =============================================================================
echo -e "\n${CYAN}S2 — Design flaw in test: rework counter caps a design-fix loop${NC}"
# =============================================================================
# A design-fix bounce re-runs Design -> ... -> Design Test repeatedly; the
# rework counter (spec §3.2) reaches 3 -> Needs PO Decision, no budget blow-up.
new_env
E=$(tracker create --type epic --title "S2 design flaw epic")
S=$(tracker create --type ticket --title "S2 story" --parent "$E" --flag design)
baseline
for s in "Design" "Ready for Development" "In Progress" "In Review"; do
    tracker transition "$S" "$s" --actor agent --reason walk >/dev/null
done
tracker transition "$S" "Ready for Development" --actor qas-design --reason "design-fix bounce 1" >/dev/null
for s in "In Progress" "In Review" "Security Review" "Test Prep" "In Test" "Design Test"; do
    tracker transition "$S" "$s" --actor agent --reason walk >/dev/null
done
tracker transition "$S" "Ready for Development" --actor qas-design --reason "design-fix bounce 2" >/dev/null
for s in "In Progress" "In Review" "Security Review" "Test Prep" "In Test" "Design Test"; do
    tracker transition "$S" "$s" --actor agent --reason walk >/dev/null
done
tracker transition "$S" "Ready for Development" --actor qas-design --reason "design-fix bounce 3" >/dev/null
out=$(ORCH_RECONCILE_ON_STARTUP=0 orch --live --once 2>/dev/null)
assert_contains "$out" "INTENT REWORK-LIMIT ticket=$S" "S2: 3rd design-fix bounce -> REWORK-LIMIT, not another spawn"
assert_not_contains "$out" "INTENT SPAWN ticket=$S role=be-developer to=Ready for Development" "S2: no 4th implementer spawn"
dump=$(tracker get "$S")
assert_contains "$dump" "status: Needs PO Decision" "S2: story escalated to Needs PO Decision (no runaway spawn budget)"
cleanup_env

# =============================================================================
echo -e "\n${CYAN}S3 — Design-flagged test sequence: Design Test spawns / SKIP-FORWARDs${NC}"
# =============================================================================
new_env
E=$(tracker create --type epic --title "S3 epic")
FLAGGED=$(tracker create --type ticket --title "S3 flagged story" --parent "$E" --flag design)
PLAIN=$(tracker create --type ticket --title "S3 plain story" --parent "$E")
baseline
for s in "Design" "Ready for Development" "In Progress" "In Review" "Security Review" "Test Prep" "In Test"; do
    tracker transition "$FLAGGED" "$s" --actor agent --reason walk >/dev/null
done
out=$(ORCH_RECONCILE_ON_STARTUP=0 orch --dry-run --once 2>/dev/null)
assert_contains "$out" "INTENT SPAWN ticket=$FLAGGED role=qas to=In Test" "S3: In Test pass spawns qas"
tracker transition "$FLAGGED" "Design Test" --actor qas --reason "passed, design review next" >/dev/null
out=$(ORCH_RECONCILE_ON_STARTUP=0 orch --dry-run --once 2>/dev/null)
assert_contains "$out" "INTENT SPAWN ticket=$FLAGGED role=qas-design to=Design Test" "S3: design-flagged story spawns qas-design at Design Test"
for s in "Design" "Ready for Development" "In Progress" "In Review" "Security Review" "Test Prep" "In Test"; do
    tracker transition "$PLAIN" "$s" --actor agent --reason walk >/dev/null 2>&1 || true
done
out=$(ORCH_RECONCILE_ON_STARTUP=0 orch --live --once 2>/dev/null)
assert_contains "$out" "INTENT SPAWN ticket=$PLAIN role=qas to=In Test" "S3: unflagged story also spawns qas at In Test"
tracker transition "$PLAIN" "Design Test" --actor qas --reason "passed" >/dev/null
out=$(ORCH_RECONCILE_ON_STARTUP=0 orch --live --once 2>/dev/null)
assert_contains "$out" "INTENT SKIP-FORWARD ticket=$PLAIN role=- to=Story Acceptance" "S3: unflagged story SKIP-FORWARDs past Design Test"
assert_not_contains "$out" "INTENT SPAWN ticket=$PLAIN role=qas-design" "S3: unflagged story never spawns qas-design"
dump=$(tracker get "$PLAIN")
assert_contains "$dump" "kind: skip | actor: orchestrator" "S3: SKIP-FORWARD leaves an audit comment"
cleanup_env

# =============================================================================
echo -e "\n${CYAN}S4 — Plain story: all three conditional stages skip, 5 story spawns${NC}"
# =============================================================================
# No flags: Security Review, Test Prep, Design Test all SKIP-FORWARD; total
# spawns for the story = 5 (implement, review, qas, acceptance, merge) plus a
# separate tech-writer spawn at Docs.
new_env
E=$(tracker create --type epic --title "S4 epic")
P=$(tracker create --type ticket --title "S4 plain story" --parent "$E")
baseline
STUB_RECORD_FILE="$TEST_DIR/s4-spawns.txt"; export STUB_RECORD_FILE
: > "$STUB_RECORD_FILE"
tracker transition "$P" "Design" --actor system-architect --reason "released" >/dev/null
out=$(ORCH_POLL_INTERVAL=0 ORCH_MAX_CYCLES=6 ORCH_RECONCILE_EVERY_N_CYCLES=0 ORCH_RECONCILE_ON_STARTUP=0 orch --live 2>/dev/null)
assert_contains "$out" "INTENT SKIP-FORWARD ticket=$P role=- to=Ready for Development" "S4: unflagged Design skips"
assert_contains "$out" "INTENT SPAWN ticket=$P role=be-developer to=Ready for Development" "S4: Ready for Development spawns the implementer"
tracker transition "$P" "In Progress" --actor be-developer --reason start >/dev/null
tracker transition "$P" "In Review" --actor be-developer --reason handoff >/dev/null
out1b=$(ORCH_RECONCILE_ON_STARTUP=0 orch --live --once 2>/dev/null)
assert_contains "$out1b" "INTENT SPAWN ticket=$P role=system-architect to=In Review" "S4: In Review spawns system-architect"
tracker transition "$P" "Security Review" --actor system-architect --reason reviewed >/dev/null
out2=$(ORCH_POLL_INTERVAL=0 ORCH_MAX_CYCLES=3 ORCH_RECONCILE_EVERY_N_CYCLES=0 ORCH_RECONCILE_ON_STARTUP=0 orch --live 2>/dev/null)
assert_contains "$out2" "INTENT SKIP-FORWARD ticket=$P role=- to=Test Prep" "S4: unflagged Security Review skips"
assert_contains "$out2" "INTENT SKIP-FORWARD ticket=$P role=- to=In Test" "S4: unflagged Test Prep skips"
assert_contains "$out2" "INTENT SPAWN ticket=$P role=qas to=In Test" "S4: chain lands at In Test -> qas spawns"
tracker transition "$P" "Design Test" --actor qas --reason passed >/dev/null
out3=$(ORCH_POLL_INTERVAL=0 ORCH_MAX_CYCLES=2 ORCH_RECONCILE_EVERY_N_CYCLES=0 ORCH_RECONCILE_ON_STARTUP=0 orch --live 2>/dev/null)
assert_contains "$out3" "INTENT SKIP-FORWARD ticket=$P role=- to=Story Acceptance" "S4: unflagged Design Test skips"
assert_contains "$out3" "INTENT SPAWN ticket=$P role=po-agent to=Story Acceptance" "S4: Story Acceptance spawns po-agent"
tracker transition "$P" "Merging" --actor po-agent --reason accepted >/dev/null
out4=$(ORCH_RECONCILE_ON_STARTUP=0 orch --live --once 2>/dev/null)
assert_contains "$out4" "INTENT SPAWN ticket=$P role=rte to=Merging" "S4: Merging spawns rte"
tracker transition "$P" "Docs" --actor rte --reason merged >/dev/null
out5=$(ORCH_RECONCILE_ON_STARTUP=0 orch --live --once 2>/dev/null)
assert_contains "$out5" "INTENT SPAWN ticket=$P role=tech-writer to=Docs" "S4: Docs spawns tech-writer"
# Count the story-owned role spawns actually recorded by the stub: be-developer
# (Ready for Development), system-architect (In Review), qas (In Test),
# po-agent (Story Acceptance), rte (Merging) = 5, tech-writer at Docs is the
# 6th and separate seat named explicitly in the spec's "+ tech-writer" clause.
story_spawns=$(grep -c "	$P$" "$STUB_RECORD_FILE" || true)
assert_eq "$story_spawns" "6" "S4: total recorded spawns for the story = 5 canonical + 1 tech-writer (Docs)"
cleanup_env

# =============================================================================
echo -e "\n${CYAN}S5 — Combination break: sequential merge conflict onto epic branch / bisect reopen${NC}"
# =============================================================================
skip_scenario "S5 Combination break (sequential merge conflict onto epic branch / bisect reopen)" \
    "pending ADR-A-0014 / ABS-89/90 -- orchestrator.sh maps 'Merging' and 'Epic Integration' to a plain SPAWN rte with no rebase/CI/bisect logic; sequential merge onto the epic integration branch + bisect is RTE agent behavior, not yet implemented and gated on human ADR acceptance (main stays human-merge-only regardless)"

# =============================================================================
echo -e "\n${CYAN}S6 — Blocked on credentials: TDM once per entry, escalation, resume${NC}"
# =============================================================================
new_env
E=$(tracker create --type epic --title "S6 epic")
S=$(tracker create --type ticket --title "S6 story" --parent "$E")
baseline
tracker transition "$S" "Ready for Development" --actor po --reason go >/dev/null
tracker transition "$S" "In Progress" --actor be-developer --reason start >/dev/null
tracker transition "$S" "Blocked" --actor be-developer --reason "credentials missing" >/dev/null
out=$(ORCH_RECONCILE_ON_STARTUP=0 orch --live --once 2>/dev/null)
assert_contains "$out" "INTENT SPAWN ticket=$S role=tdm to=Blocked" "S6: Blocked -> SPAWN tdm exactly once (not po-agent)"
dump=$(tracker get "$S")
assert_contains "$dump" "BLOCKED-FROM=In Progress (orchestrator)" "S6: pre-blocked status (In Progress) recorded"
# A second sweep must NOT re-spawn tdm for the same Blocked entry.
out2=$(ORCH_RECONCILE_ON_STARTUP=1 orch --live --once 2>/dev/null)
assert_not_contains "$out2" "INTENT SPAWN ticket=$S role=tdm" "S6: second sweep does not re-spawn tdm (once-per-entry guard)"
# TDM classifies human-only (credentials) -> escalation NOTIFY already fired at
# the Blocked spawn per docs/sop/ORCHESTRATOR_SOP.md; TDM resumes the ticket to
# the recorded pre-blocked status once the human unblocks it. Since ADR-A-0019
# the RUNNER itself resumes a target-less tdm handoff to the recorded
# BLOCKED-FROM origin, so the stub seat's sweep above may already have moved
# the ticket — only transition manually when it still rests in Blocked
# (ABS-290: this was masked by the suite aborting on the RfM->Docs edge).
if tracker get "$S" | grep -q '^status: Blocked'; then
    tracker transition "$S" "In Progress" --actor tdm --reason "Blocker resolved (credentials provisioned): resuming to origin In Progress" >/dev/null
fi
dump=$(tracker get "$S")
assert_contains "$dump" "status: In Progress" "S6: human unblock -> tdm resumes the ticket to its recorded origin"
# Sweep sees the ticket resting In Progress (a NOOP status per the story map --
# the implementer subagent, not the runner, would drive it onward from here;
# assert no spurious re-spawn / no crash). ABS-290: when the RUNNER performed
# the resume (ADR-A-0019) the In Progress event was consumed by that earlier
# live sweep, so no fresh INTENT line exists to grep — assert the absence of a
# spurious spawn plus the resting status instead of a NOOP intent line.
out3=$(ORCH_RECONCILE_ON_STARTUP=1 orch --dry-run --once 2>/dev/null)
assert_not_contains "$out3" "INTENT SPAWN ticket=$S" "S6: resumed ticket rests at In Progress (no spurious re-spawn)"
assert_contains "$(tracker get "$S")" "status: In Progress" "S6: resumed ticket still rests at its recorded origin after the sweep"
cleanup_env

# =============================================================================
echo -e "\n${CYAN}S7 — Follow-up storm: 6 follow-ups, 5 out-of-epic + 1 budget overflow${NC}"
# =============================================================================
new_env
export ORCH_MAX_CONCURRENT=10
E=$(tracker create --type epic --title "S7 epic")
A=$(tracker create --type ticket --title "S7 story w/ follow-up storm" --parent "$E")
baseline
for i in 1 2 3 4 5 6; do
    tracker comment "$A" --kind follow-up --actor qas --body "S7 finding $i" >/dev/null
done
out=$(ORCH_RECONCILE_ON_STARTUP=1 orch --live --once 2>/dev/null)
spawn_count=$(printf '%s\n' "$out" | grep -c "INTENT SPAWN ticket=$A role=bsa" || true)
assert_eq "$spawn_count" "5" "S7: 5 of the 6 follow-ups spawn bsa (created outside the epic by default)"
assert_contains "$out" "INTENT FOLLOWUP-BUDGET ticket=$E role=- to=Needs PO Decision" "S7: 6th follow-up -> Needs PO Decision (budget overflow), not a 6th spawn"
dump=$(tracker get "$E")
assert_contains "$dump" "status: Needs PO Decision" "S7: epic escalated on follow-up budget overflow"
cleanup_env
# JOIN is unaffected by a follow-up NOT marked AC-blocking: a second epic with
# a single plain story and its own follow-up storm still reaches Epic
# Integration once the storm is answered/contained.
new_env
export ORCH_MAX_CONCURRENT=10
E2=$(tracker create --type epic --title "S7 JOIN-unaffected epic")
S2=$(tracker create --type ticket --title "S7 story" --parent "$E2")
baseline
epic_to_sif "$E2"
story_to_done "$S2"
tracker comment "$S2" --kind follow-up --actor qas --body "S7 non-AC-blocking finding" >/dev/null
tracker events >/dev/null 2>&1
out=$(ORCH_RECONCILE_ON_STARTUP=1 orch --live --once 2>/dev/null)
assert_contains "$out" "INTENT JOIN-WAIT ticket=$E2" "S7: JOIN waits while the follow-up is unprocessed (quiescence)"
tracker comment "$S2" --kind bsa-decision --actor bsa --body "Decision: create outside the epic (not AC-blocking)." >/dev/null
out=$(ORCH_RECONCILE_ON_STARTUP=1 orch --live --once 2>/dev/null)
assert_contains "$out" "INTENT JOIN ticket=$E2 role=- to=Epic Integration" "S7: once answered (not AC-blocking) JOIN proceeds unaffected"
cleanup_env

# =============================================================================
echo -e "\n${CYAN}S8 — Crash + rejection: reconcile recovery, forward-fix rejection${NC}"
# =============================================================================
new_env
export STUB_FAIL=1
STUB_RECORD_FILE="$TEST_DIR/s8-spawns.txt"; export STUB_RECORD_FILE
: > "$STUB_RECORD_FILE"
E=$(tracker create --type epic --title "S8 epic")
baseline
for s in "PO Triage" "Grooming" "Enrichment" "Ticket Review"; do
    tracker transition "$E" "$s" --actor agent --reason walk >/dev/null
done
tracker transition "$E" "Architecture Review" --actor qas --reason "DoR passed" >/dev/null
tracker events >/dev/null 2>&1
out=$(ORCH_RECONCILE_ON_STARTUP=1 orch --live --once 2>/dev/null)
assert_contains "$out" "INTENT SPAWN-CRASH ticket=$E" "S8: killed spawn mid-Architecture-Review recorded as a crash marker"
dump=$(tracker get "$E")
assert_contains "$dump" "status: Architecture Review" "S8: crash leaves the epic RESTING in Architecture Review"
# Recovery: a fresh runner (no crash injection) re-derives via reconcile sweep
# and succeeds, releasing the (zero, in this scaffold) stories forward.
unset STUB_FAIL
tracker events >/dev/null 2>&1
out2=$(ORCH_RECONCILE_ON_STARTUP=1 orch --live --once 2>&1)
assert_contains "$out2" "reconciliation sweep" "S8: fresh runner's reconciliation sweep runs"
assert_contains "$out2" "INTENT SPAWN ticket=$E role=system-architect to=Architecture Review" "S8: crashed spawn recovered by reconcile sweep"
# Human epic rejection: forward-fix routes feedback to Grooming; main/mainline
# state (here: the epic's own children so far) is never reverted, only added to.
tracker transition "$E" "Stories In Flight" --actor system-architect --reason "stories released (none in this scaffold)" >/dev/null
tracker transition "$E" "Epic Integration" --actor orchestrator --reason "JOIN (no children to wait on)" >/dev/null
tracker transition "$E" "Ready for Epic Acceptance" --actor rte --reason "smoke passed" >/dev/null
tracker transition "$E" "Grooming" --actor human --reason "rejected: needs one more story for edge case X" >/dev/null
out3=$(ORCH_RECONCILE_ON_STARTUP=0 orch --dry-run --once 2>/dev/null)
assert_contains "$out3" "INTENT SPAWN ticket=$E role=bsa to=Grooming" "S8: human rejection routes to Grooming (forward-fix, bsa re-spawned)"
assert_not_contains "$out3" "revert" "S8: no revert intent is ever emitted"
cleanup_env

# =============================================================================
echo -e "\n${CYAN}S9 — Concurrent epics: JOINs, notifies, follow-up budgets isolated${NC}"
# =============================================================================
new_env
export ORCH_MAX_CONCURRENT=10
EA=$(tracker create --type epic --title "S9 epic A")
EB=$(tracker create --type epic --title "S9 epic B")
SA1=$(tracker create --type ticket --title "S9 A story 1" --parent "$EA")
SA2=$(tracker create --type ticket --title "S9 A story 2" --parent "$EA")
SB1=$(tracker create --type ticket --title "S9 B story 1" --parent "$EB")
baseline
epic_to_sif "$EA"; epic_to_sif "$EB"
story_to_done "$SA1"
tracker comment "$SA1" --kind follow-up --actor qas --body "S9 A-only follow-up storm 1" >/dev/null
for i in 2 3 4 5 6; do
    tracker comment "$SA1" --kind follow-up --actor qas --body "S9 A-only follow-up storm $i" >/dev/null
done
story_to_done "$SA2"
story_to_done "$SB1"
tracker events >/dev/null 2>&1
out=$(ORCH_RECONCILE_ON_STARTUP=1 orch --live --once 2>/dev/null)
assert_contains "$out" "INTENT FOLLOWUP-BUDGET ticket=$EA role=- to=Needs PO Decision" "S9: epic A's own follow-up storm overflows its own budget"
assert_not_contains "$out" "INTENT FOLLOWUP-BUDGET ticket=$EB" "S9: epic B's budget is untouched by epic A's storm"
dump_b=$(tracker get "$EB")
assert_contains "$dump_b" "status: Epic Integration" "S9: epic B still JOINs normally despite epic A's escalation"
dump_a=$(tracker get "$EA")
assert_contains "$dump_a" "status: Needs PO Decision" "S9: epic A escalated on its own follow-up budget"
cleanup_env

# =============================================================================
echo -e "\n${CYAN}S10 — Empty epic: zero children -> Needs PO Decision, no vacuous NOTIFY${NC}"
# =============================================================================
new_env
E=$(tracker create --type epic --title "S10 empty epic")
baseline
epic_to_sif "$E"
tracker events >/dev/null 2>&1
out=$(ORCH_RECONCILE_ON_STARTUP=1 orch --live --once 2>/dev/null)
assert_contains "$out" "INTENT JOIN-EMPTY ticket=$E role=- to=Needs PO Decision" "S10: zero-children epic hits the empty-epic guard"
assert_not_contains "$out" "ready-to-test" "S10: no vacuous ready-to-test NOTIFY fires for an empty epic"
dump=$(tracker get "$E")
assert_contains "$dump" "status: Needs PO Decision" "S10: empty epic escalated instead of integrating nothing"
cleanup_env

# =============================================================================
echo -e "\n${CYAN}S11 — AC-blocking follow-up: JOIN waits for it (quiescence)${NC}"
# =============================================================================
new_env
E=$(tracker create --type epic --title "S11 epic")
A=$(tracker create --type ticket --title "S11 story" --parent "$E")
baseline
epic_to_sif "$E"
story_to_done "$A"
tracker comment "$A" --kind follow-up --actor qas \
    --body "Follow-up: found a gap while testing; recommend a hardening story." >/dev/null
tracker events >/dev/null 2>&1
out=$(ORCH_RECONCILE_ON_STARTUP=1 orch --live --once 2>/dev/null)
assert_contains "$out" "INTENT JOIN-WAIT ticket=$E" "S11: JOIN waits for the unprocessed follow-up (no race)"
assert_not_contains "$out" "INTENT JOIN ticket=$E role=- to=Epic Integration" "S11: epic does not integrate before the follow-up is triaged"
# BSA marks it AC-blocking and attaches a child; the JOIN rule counts it and
# only fires once that child is also Done.
tracker comment "$A" --kind bsa-decision --actor bsa \
    --body "Decision: AC-blocking, attach to this epic." >/dev/null
FU=$(tracker create --type ticket --title "S11 AC-blocking follow-up story" --parent "$E" --ac-blocking)
out=$(ORCH_RECONCILE_ON_STARTUP=1 orch --live --once 2>/dev/null)
assert_not_contains "$out" "INTENT JOIN ticket=$E role=- to=Epic Integration" "S11: JOIN still waits -- the AC-blocking child is not Done yet"
story_to_done "$FU"
tracker events >/dev/null 2>&1
out=$(ORCH_RECONCILE_ON_STARTUP=1 orch --live --once 2>/dev/null)
assert_contains "$out" "INTENT JOIN ticket=$E role=- to=Epic Integration" "S11: epic integrates only after the AC-blocking child reaches Done"
cleanup_env

# =============================================================================
echo -e "\n${CYAN}S12 — Cross-stage rework: 3 different reviewers bounce once each${NC}"
# =============================================================================
new_env
E=$(tracker create --type epic --title "S12 epic")
S=$(tracker create --type ticket --title "S12 bouncy story" --parent "$E" \
    --role be-developer --flag security --flag design)
baseline
for s in "Design" "Ready for Development" "In Progress" "In Review"; do
    tracker transition "$S" "$s" --actor agent --reason walk >/dev/null
done
tracker transition "$S" "Ready for Development" --actor system-architect --reason "rework: findings" >/dev/null
for s in "In Progress" "In Review" "Security Review"; do
    tracker transition "$S" "$s" --actor agent --reason walk >/dev/null
done
tracker transition "$S" "Ready for Development" --actor security-engineer --reason "rework: vuln" >/dev/null
for s in "In Progress" "In Review" "Security Review" "Test Prep" "In Test"; do
    tracker transition "$S" "$s" --actor agent --reason walk >/dev/null
done
tracker transition "$S" "Ready for Development" --actor qas --reason "rework: test fail" >/dev/null
out=$(ORCH_RECONCILE_ON_STARTUP=0 orch --live --once 2>/dev/null)
assert_contains "$out" "INTENT REWORK-LIMIT ticket=$S" "S12: single per-ticket counter reaches 3 across THREE different reviewers"
dump=$(tracker get "$S")
assert_contains "$dump" "status: Needs PO Decision" "S12: escalated -- would be invisible to a pairwise-only guard"
cleanup_env

# =============================================================================
echo -e "\n${CYAN}S13 — Max-flag story: design+security+data runs all 10 stages${NC}"
# =============================================================================
# 10 story spawns; 16 spawns total to NOTIFY including the Ticket-Review gate
# (upper cost pin per story, spec §5).
new_env
STUB_RECORD_FILE="$TEST_DIR/s13-spawns.txt"; export STUB_RECORD_FILE
: > "$STUB_RECORD_FILE"
E=$(tracker create --type epic --title "S13 epic")
S=$(tracker create --type ticket --title "S13 max-flag story" --parent "$E" \
    --role fe-developer --flag design --flag security --flag data)
baseline
# Drive the epic pipeline itself THROUGH the orchestrator (one hop per --once)
# so each epic-owned seat is actually dispatched and recorded by the stub:
# PO Triage, Grooming, Enrichment, Ticket Review, Architecture Review = 5 so
# far; Epic Integration (the 6th) fires later via JOIN once the story is Done.
for s in "PO Triage" "Grooming" "Enrichment" "Ticket Review" "Architecture Review"; do
    walk_to "$E" "$s" --actor agent --reason "walk to $s"
    out=$(ORCH_RECONCILE_ON_STARTUP=0 orch --live --once 2>/dev/null)
done
# The system-architect (simulated) releases the max-flag story into Design,
# then rests the epic in Stories In Flight (spec §1.1).
tracker transition "$S" "Design" --actor system-architect --reason "released" >/dev/null
tracker transition "$E" "Stories In Flight" --actor system-architect --reason "stories released" >/dev/null
out=$(ORCH_RECONCILE_ON_STARTUP=0 orch --live --once 2>/dev/null)
assert_contains "$out" "INTENT SPAWN ticket=$S role=ui-ux-design to=Design" "S13: Design (flagged) spawns ui-ux-design"
for s in "Ready for Development" "In Progress" "In Review" "Security Review" \
         "Test Prep" "In Test" "Design Test" "Story Acceptance" "Merging" "Docs"; do
    walk_to "$S" "$s" --actor agent --reason "walk to $s"
    out=$(ORCH_RECONCILE_ON_STARTUP=0 orch --live --once 2>/dev/null)
done
story_spawn_lines=$(grep -c "	$S$" "$STUB_RECORD_FILE" || true)
assert_eq "$story_spawn_lines" "10" "S13: all 10 story-pipeline stages spawn exactly once (max-flag story)"
for role in ui-ux-design security-engineer data-provisioning-eng qas qas-design; do
    assert_contains "$(cat "$STUB_RECORD_FILE")" "$role	$S" "S13: conditional seat '$role' spawned for the max-flag story"
done
# Docs->Done completes the (only) story; the JOIN fires on that dispatch
# (transitioning the epic, role=- -- JOIN itself never spawns); the FOLLOWING
# poll picks up the fresh Epic Integration event and dispatches the epic's
# 6th spawn (SPAWN rte).
tracker transition "$S" "Done" --actor tech-writer --reason "docs done" >/dev/null
out=$(ORCH_RECONCILE_ON_STARTUP=0 orch --live --once 2>/dev/null)
assert_contains "$out" "INTENT JOIN ticket=$E role=- to=Epic Integration" "S13: only-story Done -> JOIN fires -> Epic Integration"
out=$(ORCH_RECONCILE_ON_STARTUP=0 orch --live --once 2>/dev/null)
assert_contains "$out" "INTENT SPAWN ticket=$E role=rte to=Epic Integration" "S13: Epic Integration (post-JOIN) spawns rte"
epic_spawn_lines=$(grep -c "	$E$" "$STUB_RECORD_FILE" || true)
assert_eq "$epic_spawn_lines" "6" "S13: epic-pipeline seats spawn 6 times (PO Triage/Grooming/Enrichment/Ticket Review/Arch Review/Epic Integration)"
total_spawns=$(wc -l < "$STUB_RECORD_FILE" | tr -d ' ')
assert_eq "$total_spawns" "16" "S13: 16 total spawns to NOTIFY (10 story + 6 epic incl. the Ticket-Review DoR gate)"
cleanup_env

# =============================================================================
echo -e "\n${CYAN}S14 — Epic-level Blocked: BSA blocks during Grooming${NC}"
# =============================================================================
new_env
E=$(tracker create --type epic --title "S14 epic")
baseline
tracker transition "$E" "PO Triage" --actor po-agent --reason triage >/dev/null
tracker transition "$E" "Grooming" --actor po-agent --reason groom >/dev/null
tracker transition "$E" "Blocked" --actor bsa --reason "missing domain input" >/dev/null
out=$(ORCH_RECONCILE_ON_STARTUP=0 orch --live --once 2>/dev/null)
assert_contains "$out" "INTENT SPAWN ticket=$E role=tdm to=Blocked" "S14: epic-level Blocked also spawns tdm once"
dump=$(tracker get "$E")
assert_contains "$dump" "BLOCKED-FROM=Grooming (orchestrator)" "S14: pre-blocked status recorded as Grooming (epic pipeline, spec §3.7)"
# Second sweep must not re-spawn tdm for the same entry.
out2=$(ORCH_RECONCILE_ON_STARTUP=1 orch --live --once 2>/dev/null)
assert_not_contains "$out2" "INTENT SPAWN ticket=$E role=tdm" "S14: no double tdm spawn for the same Blocked entry"
# Runner may already have resumed the epic to its BLOCKED-FROM origin
# (ADR-A-0019, same as S6) — only transition manually when still Blocked.
if tracker get "$E" | grep -q '^status: Blocked'; then
    tracker transition "$E" "Grooming" --actor tdm --reason "Blocker resolved (domain input provided): resuming to origin Grooming" >/dev/null
fi
dump=$(tracker get "$E")
assert_contains "$dump" "status: Grooming" "S14: resume-to-origin returns the epic to Grooming (not a fixed stage)"
cleanup_env

# =============================================================================
echo -e "\n${CYAN}S15 — Deterministic crash: 3 consecutive crashes -> Needs PO Decision${NC}"
# =============================================================================
new_env
export STUB_FAIL=1
STUB_RECORD_FILE="$TEST_DIR/s15-spawns.txt"; export STUB_RECORD_FILE
: > "$STUB_RECORD_FILE"
T=$(tracker create --type ticket --title "S15 crasher" --role be-developer)
baseline
tracker transition "$T" "Ready for Development" --actor po-agent --reason go >/dev/null
tracker events >/dev/null 2>&1
out1=$(ORCH_RECONCILE_ON_STARTUP=1 orch --live --once 2>/dev/null)
assert_contains "$out1" "INTENT SPAWN-CRASH ticket=$T" "S15: crash run 1 -> SPAWN-CRASH marker, no escalation yet"
assert_not_contains "$out1" "INTENT CRASH-LIMIT ticket=$T" "S15: below limit after run 1"
out2=$(ORCH_RECONCILE_ON_STARTUP=1 orch --live --once 2>/dev/null)
assert_contains "$out2" "INTENT SPAWN-CRASH ticket=$T" "S15: crash run 2 (fresh process re-derives + crashes again)"
assert_not_contains "$out2" "INTENT CRASH-LIMIT ticket=$T" "S15: still below limit after run 2"
out3=$(ORCH_RECONCILE_ON_STARTUP=1 orch --live --once 2>/dev/null)
assert_contains "$out3" "INTENT CRASH-LIMIT ticket=$T" "S15: 3rd consecutive crash -> CRASH-LIMIT, no infinite retry loop"
dump=$(tracker get "$T")
assert_contains "$dump" "status: Needs PO Decision" "S15: deterministic crasher escalated instead of retried forever"
cleanup_env

# =============================================================================
echo -e "\n${CYAN}S16 — DoR gate: un-ready tickets bounce; no story released early${NC}"
# =============================================================================
new_env
E=$(tracker create --type epic --title "S16 epic")
baseline
for s in "PO Triage" "Grooming" "Enrichment" "Ticket Review"; do
    tracker transition "$E" "$s" --actor agent --reason walk >/dev/null
done
out=$(ORCH_RECONCILE_ON_STARTUP=0 orch --dry-run --once 2>/dev/null)
assert_not_contains "$out" "INTENT SPAWN ticket=$E role=system-architect" "S16: no story released before the DoR gate passes"
tracker transition "$E" "Grooming" --actor qas --reason "DoR bounce 1: untestable AC on story 2" >/dev/null
for s in "Enrichment" "Ticket Review"; do
    tracker transition "$E" "$s" --actor agent --reason walk >/dev/null
done
tracker transition "$E" "Grooming" --actor qas --reason "DoR bounce 2: still missing coverage mapping" >/dev/null
for s in "Enrichment" "Ticket Review"; do
    tracker transition "$E" "$s" --actor agent --reason walk >/dev/null
done
tracker transition "$E" "Grooming" --actor qas --reason "DoR bounce 3: unresolved blind-spot" >/dev/null
out=$(ORCH_RECONCILE_ON_STARTUP=0 orch --live --once 2>/dev/null)
assert_contains "$out" "INTENT REWORK-LIMIT ticket=$E" "S16: 3rd DoR bounce trips the epic ticket's rework counter (§3.2 reused, no new mechanic)"
dump=$(tracker get "$E")
assert_contains "$dump" "status: Needs PO Decision" "S16: DoR-gate rework-limit escalates the epic to Needs PO Decision"
assert_not_contains "$out" "INTENT SPAWN ticket=$E role=system-architect" "S16: Architecture Review (and therefore any story) never released"
cleanup_env

# =============================================================================
# Workflow v3.1 — flexible intake (ABS-102, spec ABS-103): the two new intake
# heads and the empty-epic regression, driven against the SAME real
# orchestrator.sh + mock adapter as S1-S16. Path-A / Path-B are entry ROUTES
# onto the existing pipeline (no new stages), so each scenario reuses the story-
# and epic-pipeline seat mappings verbatim and asserts the runner's INTENT lines.
# =============================================================================

# =============================================================================
echo -e "\n${CYAN}S-A1 — Path-A: parentless bug walks intake → triage/DoR → fix → test → RTE-PR-to-main${NC}"
# =============================================================================
# A seeded PARENTLESS bug is classified onto the Path-A head, runs the reused
# v3.0 story pipeline (conditional stages SKIP-FORWARD), and ends at an RTE
# PR-to-main (SPAWN rte at Merging). DoD: ZERO epic-level statuses entered and
# NO auto-merge (the epic JOIN → Epic Integration path never fires). Spec §5.1/§5.2/§7.
new_env
export ORCH_MAX_CONCURRENT=10
PB=$(tracker create --type ticket --title "S-A1 parentless bug" --role be-developer --label orchestrator-ready)
allout=""
# Intake + triage/DoR head: classify parentless -> Path-A; Backlog still SPAWNs
# po-agent (the triage+DoR head in single-ticket mode, spec §3).
o=$(ORCH_RECONCILE_ON_STARTUP=0 orch --live --once 2>/dev/null); allout="$allout$o"
assert_contains "$o" "INTENT INTAKE-CLASSIFY ticket=$PB role=- to=Path-A head note=class=parentless-ticket" "S-A1: parentless bug classified onto the Path-A head (intake)"
assert_contains "$o" "INTENT SPAWN ticket=$PB role=po-agent to=Backlog" "S-A1: triage+DoR head spawns (po-agent, single-ticket mode)"
# ready head outcome -> Design (story-pipeline head); walk the reused pipeline.
tracker transition "$PB" "Design" --actor po-agent --reason "Path-A triage: ready" >/dev/null
o=$(ORCH_POLL_INTERVAL=0 ORCH_MAX_CYCLES=6 ORCH_RECONCILE_EVERY_N_CYCLES=0 ORCH_RECONCILE_ON_STARTUP=0 orch --live 2>/dev/null); allout="$allout$o"
assert_contains "$o" "INTENT SKIP-FORWARD ticket=$PB role=- to=Ready for Development" "S-A1: unflagged Design SKIP-FORWARDs (no spawn)"
assert_contains "$o" "INTENT SPAWN ticket=$PB role=be-developer to=Ready for Development" "S-A1: fix — implementer spawns (be-developer)"
tracker transition "$PB" "In Progress" --actor be-developer --reason start >/dev/null
tracker transition "$PB" "In Review" --actor be-developer --reason handoff >/dev/null
o=$(ORCH_RECONCILE_ON_STARTUP=0 orch --live --once 2>/dev/null); allout="$allout$o"
assert_contains "$o" "INTENT SPAWN ticket=$PB role=system-architect to=In Review" "S-A1: code review spawns (system-architect)"
tracker transition "$PB" "Security Review" --actor system-architect --reason reviewed >/dev/null
o=$(ORCH_POLL_INTERVAL=0 ORCH_MAX_CYCLES=3 ORCH_RECONCILE_EVERY_N_CYCLES=0 ORCH_RECONCILE_ON_STARTUP=0 orch --live 2>/dev/null); allout="$allout$o"
assert_contains "$o" "INTENT SPAWN ticket=$PB role=qas to=In Test" "S-A1: test — qas spawns at In Test"
tracker transition "$PB" "Design Test" --actor qas --reason passed >/dev/null
o=$(ORCH_POLL_INTERVAL=0 ORCH_MAX_CYCLES=2 ORCH_RECONCILE_EVERY_N_CYCLES=0 ORCH_RECONCILE_ON_STARTUP=0 orch --live 2>/dev/null); allout="$allout$o"
assert_contains "$o" "INTENT SPAWN ticket=$PB role=po-agent to=Story Acceptance" "S-A1: story acceptance spawns (po-agent)"
tracker transition "$PB" "Merging" --actor po-agent --reason accepted >/dev/null
o=$(ORCH_RECONCILE_ON_STARTUP=0 orch --live --once 2>/dev/null); allout="$allout$o"
assert_contains "$o" "INTENT SPAWN ticket=$PB role=rte to=Merging" "S-A1: RTE-opens-PR-to-main — Merging spawns rte"
tracker transition "$PB" "Docs" --actor rte --reason "PR opened to main" >/dev/null
o=$(ORCH_RECONCILE_ON_STARTUP=0 orch --live --once 2>/dev/null); allout="$allout$o"
assert_contains "$o" "INTENT SPAWN ticket=$PB role=tech-writer to=Docs" "S-A1: Docs spawns tech-writer"
# DoD: ZERO epic-level statuses ever entered for the parentless ticket.
pblog=$(tracker get "$PB")
for st in "PO Triage" "Grooming" "Enrichment" "Ticket Review" "Architecture Review" "Epic Integration"; do
    n=$(echo "$pblog" | grep -c -- "-> $st\." || true)
    assert_eq "$n" "0" "S-A1: transition log never enters epic status '$st'"
done
# DoD: NO auto-merge — the epic JOIN / Epic-Integration path never fires on Path-A.
assert_not_contains "$allout" "INTENT JOIN" "S-A1: no auto-merge — JOIN rule never evaluates (parentless)"
assert_not_contains "$allout" "to=Epic Integration" "S-A1: no auto-merge — Epic Integration never entered"
cleanup_env

# =============================================================================
echo -e "\n${CYAN}S-B1 — Path-B: pre-populated epic, conformant children → Architecture Review, no story gen${NC}"
# =============================================================================
# An epic authored WITH children skips Grooming decomposition and runs the DoR
# gate as its ENTRY gate; a conformant (ready) verdict routes straight to
# Architecture Review with NO story generation — transition-log assertion:
# never enters Grooming/Enrichment, no bsa/issue-enrichment spawn, child-count
# unchanged. Spec §6.
new_env
export ORCH_MAX_CONCURRENT=10
E=$(tracker create --type epic --title "S-B1 pre-populated epic" --label orchestrator-ready)
C1=$(tracker create --type ticket --title "S-B1 conformant child 1" --parent "$E")
C2=$(tracker create --type ticket --title "S-B1 conformant child 2" --parent "$E")
allout=""
# Intake: classify epic-with-children -> the Path-B entry gate, named "Ticket
# Review (DoR gate)" since ABS-271 (on the Backlog poll).
# ABS-290: asserted on a DRY-RUN sweep — a live sweep would spawn the po-agent
# triage stub whose target-less handoff lets the runner EPIC-JOIN-REST the epic
# straight to Stories In Flight, preempting the scripted DoR-gate walk below.
o=$(ORCH_RECONCILE_ON_STARTUP=0 orch --dry-run --once 2>/dev/null); allout="$allout$o"
assert_contains "$o" "INTENT INTAKE-CLASSIFY ticket=$E role=- to=Ticket Review (DoR gate) note=class=epic-with-children" "S-B1: epic-with-children classified onto the Path-B entry gate (Ticket Review, ABS-271)"
# Path-B skips Grooming DECOMPOSITION: the epic walks to the DoR entry gate
# without ever RESTING for a bsa decomposition spawn. The machine's linear epic
# statuses are traversed, but because no orchestrator poll lands on Grooming /
# Enrichment those events are SKIP-STALE by poll time — no decomposition seat is
# dispatched (SOP: "no Grooming SPAWN entry precedes the Ticket Review gate").
for s in "PO Triage" "Grooming" "Enrichment" "Ticket Review"; do
    tracker transition "$E" "$s" --actor orchestrator --reason "Path-B: walk to DoR entry gate over pre-existing children" >/dev/null
done
o=$(ORCH_RECONCILE_ON_STARTUP=0 orch --live --once 2>/dev/null); allout="$allout$o"
assert_contains "$o" "INTENT SPAWN ticket=$E role=qas to=Ticket Review" "S-B1: the DoR entry gate spawns qas (Ticket Review)"
assert_not_contains "$allout" "INTENT SPAWN ticket=$E role=bsa" "S-B1: NO BSA decomposition spawn precedes the DoR gate (Grooming decomposition skipped)"
assert_not_contains "$allout" "INTENT SPAWN ticket=$E role=issue-enrichment" "S-B1: NO Enrichment child-creation spawn (no story generation)"
# ready verdict -> straight to Architecture Review (no rework bounce to Grooming).
tracker transition "$E" "Architecture Review" --actor qas --reason "DoR ready: all children conformant" >/dev/null
o=$(ORCH_RECONCILE_ON_STARTUP=0 orch --live --once 2>/dev/null); allout="$allout$o"
assert_contains "$o" "INTENT SPAWN ticket=$E role=system-architect to=Architecture Review" "S-B1: ready -> Architecture Review (architect reviews complete tickets)"
elog=$(tracker get "$E")
assert_contains "$elog" "-> Architecture Review." "S-B1: transition log — the DoR gate routed straight to Architecture Review"
nbounce=$(echo "$elog" | grep -c -- "Ticket Review -> Grooming\." || true)
assert_eq "$nbounce" "0" "S-B1: no DoR rework bounce (Ticket Review never bounced to Grooming)"
assert_eq "$(tracker child-count "$E")" "2" "S-B1: child-count unchanged at 2 — no new stories generated"
cleanup_env

# =============================================================================
echo -e "\n${CYAN}S-B2 — Path-B: auto-fix rework pass, substance-gap open question, 3-bounce cap${NC}"
# =============================================================================
# Three seeded sub-cases against the auto-fix rework loop (spec §6, ABS-108):
#   (a) a mechanical bounce auto-fixes below the cap -> gate pass -> epic starts;
#   (b) a substance gap yields an open question -> Needs PO Decision;
#   (c) a 3-bounce case trips the epic's rework counter (§3.2) -> Needs PO Decision.

# (a) non-conformant → mechanical auto-fix (below the 3-cap) → gate pass → starts.
new_env
export ORCH_MAX_CONCURRENT=10
E=$(tracker create --type epic --title "S-B2a non-conformant (mechanical)" --label orchestrator-ready)
C=$(tracker create --type ticket --title "S-B2a child (fixable flag)" --parent "$E")
# ABS-290: dry-run for the classify assert (same as S-B1) — a live sweep would
# let the runner EPIC-JOIN-REST the epic and preempt the scripted gate walk.
o=$(ORCH_RECONCILE_ON_STARTUP=0 orch --dry-run --once 2>/dev/null)
assert_contains "$o" "INTENT INTAKE-CLASSIFY ticket=$E role=- to=Ticket Review (DoR gate) note=class=epic-with-children" "S-B2a: epic-with-children -> Path-B entry gate (Ticket Review, ABS-271)"
for s in "PO Triage" "Grooming" "Enrichment" "Ticket Review"; do
    tracker transition "$E" "$s" --actor orchestrator --reason "Path-B walk to entry gate" >/dev/null
done
# rework verdict: ONE mechanical bounce Ticket Review -> Grooming (auto-normalize
# the existing child at child granularity), the 1st of the capped loop.
tracker transition "$E" "Grooming" --actor qas --reason "rework: mechanical fix — missing design flag on child" >/dev/null
o=$(ORCH_RECONCILE_ON_STARTUP=0 orch --live --once 2>/dev/null)
assert_not_contains "$o" "INTENT REWORK-LIMIT ticket=$E" "S-B2a: a single mechanical bounce does NOT escalate (below the 3-cap)"
# re-enter the gate (fixed) and pass -> Architecture Review: the epic STARTS.
for s in "Enrichment" "Ticket Review" "Architecture Review"; do
    tracker transition "$E" "$s" --actor issue-enrichment --reason "child normalized, gate pass" >/dev/null
done
o=$(ORCH_RECONCILE_ON_STARTUP=0 orch --live --once 2>/dev/null)
assert_contains "$o" "INTENT SPAWN ticket=$E role=system-architect to=Architecture Review" "S-B2a: auto-fix reaches a gate pass and the epic starts (Architecture Review)"
assert_contains "$(tracker get "$E")" "status: Architecture Review" "S-B2a: epic rests at Architecture Review after a passing auto-fix loop"
cleanup_env

# (b) substance gap in one child → open question → Needs PO Decision.
new_env
export ORCH_MAX_CONCURRENT=10
E=$(tracker create --type epic --title "S-B2b substance gap" --label orchestrator-ready)
C=$(tracker create --type ticket --title "S-B2b child (untestable AC)" --parent "$E")
# ABS-290: dry-run for the classify assert (same as S-B1) — a live sweep would
# let the runner EPIC-JOIN-REST the epic and preempt the scripted gate walk.
o=$(ORCH_RECONCILE_ON_STARTUP=0 orch --dry-run --once 2>/dev/null)
assert_contains "$o" "INTENT INTAKE-CLASSIFY ticket=$E role=- to=Ticket Review (DoR gate) note=class=epic-with-children" "S-B2b: epic-with-children -> Path-B entry gate (Ticket Review, ABS-271)"
for s in "PO Triage" "Grooming" "Enrichment" "Ticket Review"; do
    tracker transition "$E" "$s" --actor orchestrator --reason "Path-B walk to entry gate" >/dev/null
done
# open question: a substance gap (untestable AC) the loop cannot mechanically fix
# -> Needs PO Decision (the po-agent that triaged the epic decides), spec §6.
tracker transition "$E" "Needs PO Decision" --actor qas --reason "open question: untestable AC on child — substance gap, not auto-fixable" >/dev/null
assert_contains "$(tracker get "$E")" "status: Needs PO Decision" "S-B2b: a substance-gap open question routes the epic to Needs PO Decision"
o=$(ORCH_RECONCILE_ON_STARTUP=0 orch --live --once 2>/dev/null)
assert_contains "$o" "INTENT SPAWN ticket=$E role=po-agent to=Needs PO Decision" "S-B2b: Needs PO Decision spawns the po-agent (product authority decides)"
cleanup_env

# (c) 3-bounce case → the epic rework counter caps out → Needs PO Decision.
new_env
export ORCH_MAX_CONCURRENT=10
E=$(tracker create --type epic --title "S-B2c 3-bounce cap" --label orchestrator-ready)
C=$(tracker create --type ticket --title "S-B2c child" --parent "$E")
# ABS-290: dry-run for the classify assert (same as S-B1) — a live sweep would
# let the runner EPIC-JOIN-REST the epic and preempt the scripted gate walk.
o=$(ORCH_RECONCILE_ON_STARTUP=0 orch --dry-run --once 2>/dev/null)
assert_contains "$o" "INTENT INTAKE-CLASSIFY ticket=$E role=- to=Ticket Review (DoR gate) note=class=epic-with-children" "S-B2c: epic-with-children -> Path-B entry gate (Ticket Review, ABS-271)"
for s in "PO Triage" "Grooming" "Enrichment" "Ticket Review"; do
    tracker transition "$E" "$s" --actor orchestrator --reason "Path-B walk to entry gate" >/dev/null
done
# three Ticket Review -> Grooming bounces trip the epic ticket's rework counter (§3.2).
tracker transition "$E" "Grooming"       --actor qas              --reason "rework bounce 1" >/dev/null
tracker transition "$E" "Enrichment"     --actor issue-enrichment --reason "re-enter 1" >/dev/null
tracker transition "$E" "Ticket Review"  --actor issue-enrichment --reason "re-enter gate 1" >/dev/null
tracker transition "$E" "Grooming"       --actor qas              --reason "rework bounce 2" >/dev/null
tracker transition "$E" "Enrichment"     --actor issue-enrichment --reason "re-enter 2" >/dev/null
tracker transition "$E" "Ticket Review"  --actor issue-enrichment --reason "re-enter gate 2" >/dev/null
tracker transition "$E" "Grooming"       --actor qas              --reason "rework bounce 3" >/dev/null
o=$(ORCH_RECONCILE_ON_STARTUP=0 orch --live --once 2>/dev/null)
assert_contains "$o" "INTENT REWORK-LIMIT ticket=$E" "S-B2c: 3rd Path-B rework bounce trips the epic rework counter (§3.2, no new mechanic)"
assert_contains "$(tracker get "$E")" "status: Needs PO Decision" "S-B2c: the 3-bounce cap escalates the epic to Needs PO Decision"
cleanup_env

# =============================================================================
echo -e "\n${CYAN}S-B3 — regression: empty epic still takes the unchanged v3.0 generate-stories Grooming path${NC}"
# =============================================================================
# Additivity guard: an empty epic (no children) must NOT be misclassified onto
# either new head — it classifies to the unchanged v3.0 Grooming path and still
# spawns bsa at Grooming (story generation). Spec §4 (row 1).
new_env
export ORCH_MAX_CONCURRENT=10
E=$(tracker create --type epic --title "S-B3 empty epic" --label orchestrator-ready)
o=$(ORCH_RECONCILE_ON_STARTUP=0 orch --live --once 2>/dev/null)
assert_contains "$o" "INTENT INTAKE-CLASSIFY ticket=$E role=- to=v3.0 Grooming path note=class=empty-epic" "S-B3: empty epic classified onto the UNCHANGED v3.0 Grooming path"
assert_not_contains "$o" "ticket=$E role=- to=Ticket Review (DoR gate)" "S-B3: empty epic NOT misclassified as epic-with-children (Path-B)"
assert_not_contains "$o" "ticket=$E role=- to=Path-A head" "S-B3: empty epic NOT misclassified as parentless (Path-A)"
# v3.0 generate-stories path: PO Triage -> Grooming spawns bsa (story drafts).
tracker transition "$E" "PO Triage" --actor po-agent --reason triage >/dev/null
tracker transition "$E" "Grooming"  --actor po-agent --reason groom >/dev/null
o=$(ORCH_RECONCILE_ON_STARTUP=0 orch --live --once 2>/dev/null)
assert_contains "$o" "INTENT SPAWN ticket=$E role=bsa to=Grooming" "S-B3: empty epic still takes the v3.0 generate-stories Grooming path (SPAWN bsa)"
cleanup_env

# =============================================================================
echo -e "\n${CYAN}Mutation check — disabling the intake classifier breaks S-A1 / S-B1 / S-B3${NC}"
# =============================================================================
# Proves the three intake-bound scenarios assert the NEW behavior (not incidental
# passes): a test-only orchestrator copy with the sole route_intake call neutered
# emits NO INTAKE-CLASSIFY line, so each scenario's intake assertion would fail.
# A positive control confirms the UNMUTATED runner still classifies all three.
new_env
export ORCH_MAX_CONCURRENT=10
# Build the mutant: the one route_intake call site -> a no-op (:). Self-contained
# in $TEST_DIR (the missing hooks/ dir is harmless — iteration_guard_blocks is a
# no-op when its script is absent). Standard mutation-testing idiom; the real
# scripts/orchestrator.sh is never modified.
MUT_ORCH="$TEST_DIR/orchestrator-noclassifier.sh"
sed 's/^[[:space:]]*route_intake .*/    :/' "$ORCH" > "$MUT_ORCH"
mut_orch() { bash "$MUT_ORCH" "$@"; }
subs=$(grep -c '^[[:space:]]*route_intake ' "$ORCH" || true)
assert_eq "$subs" "1" "mutation: exactly one route_intake call site is neutered"
PB=$(tracker create --type ticket --title "MUT parentless (S-A1)" --role be-developer --label orchestrator-ready)
EB=$(tracker create --type epic   --title "MUT epic-with-children (S-B1)" --label orchestrator-ready)
CB=$(tracker create --type ticket --title "MUT child" --parent "$EB")
EE=$(tracker create --type epic   --title "MUT empty-epic (S-B3)" --label orchestrator-ready)
# positive control: the UNMUTATED runner DOES classify all three.
ctl=$(ORCH_RECONCILE_ON_STARTUP=0 orch --dry-run --once 2>/dev/null)
assert_contains "$ctl" "INTENT INTAKE-CLASSIFY ticket=$PB role=- to=Path-A head note=class=parentless-ticket" "mutation control: unmutated runner classifies the S-A1 parentless ticket"
assert_contains "$ctl" "INTENT INTAKE-CLASSIFY ticket=$EB role=- to=Ticket Review (DoR gate) note=class=epic-with-children" "mutation control: unmutated runner classifies the S-B1 epic-with-children"
assert_contains "$ctl" "INTENT INTAKE-CLASSIFY ticket=$EE role=- to=v3.0 Grooming path note=class=empty-epic" "mutation control: unmutated runner classifies the S-B3 empty epic"
# mutation: with route_intake disabled the reconcile sweep re-derives the same
# resting Backlog tickets but emits NO classify line for any of the three.
mut=$(ORCH_RECONCILE_ON_STARTUP=1 mut_orch --dry-run --once 2>/dev/null)
# guard the mutation check itself: the mutant must still RUN (only classification
# removed), else assert_not_contains would pass on an empty/crashed output.
assert_contains "$mut" "INTENT SPAWN ticket=$PB role=po-agent to=Backlog" "mutation: the mutant still runs its non-classifier work (Backlog dispatch intact)"
assert_not_contains "$mut" "INTENT INTAKE-CLASSIFY ticket=$PB" "mutation: S-A1 intake assertion FAILS when the classifier is disabled"
assert_not_contains "$mut" "INTENT INTAKE-CLASSIFY ticket=$EB" "mutation: S-B1 intake assertion FAILS when the classifier is disabled"
assert_not_contains "$mut" "INTENT INTAKE-CLASSIFY ticket=$EE" "mutation: S-B3 intake assertion FAILS when the classifier is disabled"
cleanup_env

# =============================================================================
echo -e "\n${CYAN}=== Test Results ===${NC}\n"
echo -e "  Total:   $TOTAL"
echo -e "  ${GREEN}Passed:  $PASS${NC}"
echo -e "  ${YELLOW}Skipped: $SKIP${NC} (scenario(s) pending ADR-A-0014 / ABS-89/90)"
if [ "$FAIL" -gt 0 ]; then
    echo -e "  ${RED}Failed:  $FAIL${NC}"
    echo -e "\n  ${RED}FAILED${NC}\n"
    exit 1
else
    echo -e "  Failed:  0"
    echo -e "\n  ${GREEN}ALL RUNNABLE SCENARIOS PASSED${NC} ($PASS passed, $SKIP skipped)\n"
    exit 0
fi
