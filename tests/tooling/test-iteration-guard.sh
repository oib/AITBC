#!/bin/bash
# =============================================================================
# Test: Iteration Guard (ABS-12, counting model v2: ABS-115)
# =============================================================================
# Exercises scripts/hooks/iteration-guard.sh against the mock task-tracking
# adapter (scripts/mock-tracker.sh) with a temp ticket store.
# Run from repo root: bash tests/test-iteration-guard.sh
#
# v2 cases (ABS-115): informational APPROVE markers and quoted markers do NOT
# count (the ABS-107 false-positive fix); a real bounce = gate marker +
# backward transition; per-gate reset on forward progress; cumulative ticket
# budget cap; neutral Blocked/Needs-PO-Decision transitions. Plus the ABS-12
# base cases: caps from markers, fail-open, adapter shapes, hook mode, hygiene.
# =============================================================================

set -e
# PILOT-46: strip inherited backend/tracker env before any fixture runs (tests/sandbox-guard.sh).
# shellcheck source=tests/sandbox-guard.sh
. "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/sandbox-guard.sh"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
GUARD="$REPO_ROOT/scripts/hooks/iteration-guard.sh"
TRACKER="$REPO_ROOT/scripts/mock-tracker.sh"

# Test isolation (ABS-177): these cases drive the guard against the isolated
# mock-tracker fixture below via its default fallback. An inherited TRACKER_CMD /
# ITERATION_GUARD_ADAPTER (e.g. a live jira adapter exported in the operator
# shell) would override that fallback, sending the guard at the DEMO fixture
# tickets against the live tracker where they don't exist — it then fails open
# (exit 0) instead of blocking (exit 2). Neutralize both so the suite is
# deterministic however it is invoked. The precedence cases below set these
# vars inline per-invocation and are unaffected by this unset.
unset TRACKER_CMD ITERATION_GUARD_ADAPTER

TEST_DIR=$(mktemp -d /tmp/iteration-guard-test-XXXXXX)
trap "rm -rf $TEST_DIR" EXIT

export MOCK_TRACKER_TICKETS_DIR="$TEST_DIR/work/tickets"
export MOCK_TRACKER_STATUSES="$REPO_ROOT/profiles/neutral/adapters/statuses.yaml"

tracker() { bash "$TRACKER" "$@"; }
# Add a gate comment carrying the given marker body.
bounce()  { tracker comment "$1" --kind gate-results --actor qas --body "$2" >/dev/null; }
# Transition helper (legal edges only — the mock validates against statuses.yaml).
trans()   { tracker transition "$1" "$2" --actor test --reason "${3:-test}" >/dev/null; }
# Drive a fresh Backlog ticket to In Review (the canonical gate under test).
to_review() { trans "$1" "Ready for Development"; trans "$1" "In Progress"; trans "$1" "In Review"; }
# One REAL bounce at In Review that returns the ticket to In Review afterwards:
# gate marker comment + backward transition, then forward again to the gate.
real_bounce_at_review() {
    bounce "$1" "$2"
    trans "$1" "In Progress" "bounce"
    trans "$1" "In Review" "rework done"
}

PASS=0
FAIL=0
TOTAL=0
GREEN='\033[0;32m'; RED='\033[0;31m'; CYAN='\033[0;36m'; YELLOW='\033[1;33m'; NC='\033[0m'

# Run the guard on a ticket; capture exit code (never aborts under set -e).
guard_exit() {
    local ec=0
    bash "$GUARD" "$@" >/dev/null 2>&1 || ec=$?
    echo "$ec"
}

assert_exit() {
    local actual="$1" expected="$2" label="$3"
    TOTAL=$((TOTAL + 1))
    if [ "$actual" = "$expected" ]; then
        echo -e "  ${GREEN}PASS${NC} $label"
        PASS=$((PASS + 1))
    else
        echo -e "  ${RED}FAIL${NC} $label (expected exit $expected, got $actual)"
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
        echo -e "  ${YELLOW}  Output:${NC}"; echo "$output" | head -10 | sed 's/^/    /'
        FAIL=$((FAIL + 1))
    fi
}

assert_empty() {
    local output="$1" label="$2"
    TOTAL=$((TOTAL + 1))
    if [ -z "$output" ]; then
        echo -e "  ${GREEN}PASS${NC} $label"; PASS=$((PASS + 1))
    else
        echo -e "  ${RED}FAIL${NC} $label (expected empty, got: '$output')"; FAIL=$((FAIL + 1))
    fi
}

echo -e "${CYAN}=== Iteration Guard (ABS-12 / ABS-115 v2) ===${NC}\n"

# --- No comments: fresh ticket, nothing counts --------------------------------
echo -e "${CYAN}No comments (fresh ticket)${NC}"
T=$(tracker create --type ticket --title "fresh")
assert_exit "$(guard_exit "$T")" 0 "fresh ticket, no markers -> proceed"

# --- ABS-107 regression: markers WITHOUT backward transitions never count -----
echo -e "${CYAN}False-positive fix: markers without backward transitions (ABS-107)${NC}"
T=$(tracker create --type ticket --title "abs107")
to_review "$T"
bounce "$T" "APPROVE — Iteration 1 of 3 (no bounce)"
trans "$T" "In Test" "review passed"                       # forward: informational marker
bounce "$T" "APPROVE — Iteration 2 of 3 (no bounce)"        # (qas talking about its loop)
trans "$T" "Ready for Human Acceptance" "tests green"       # forward again
assert_exit "$(guard_exit "$T")" 0 "APPROVE markers + forward transitions -> no count, proceed"

T=$(tracker create --type ticket --title "quoted")
to_review "$T"
tracker comment "$T" --kind decision --actor operator \
    --body "Operator note: earlier comment said 'Iteration 2 of 3', investigating" >/dev/null
tracker comment "$T" --kind notification --actor orchestrator \
    --body "FYI Iteration 3 of 3 was quoted upstream" >/dev/null
assert_exit "$(guard_exit "$T")" 0 "quoted markers in decision/notification comments -> no count"

T=$(tracker create --type ticket --title "markers-only")
bounce "$T" "Iteration 1 of 3"; bounce "$T" "Iteration 2 of 3"; bounce "$T" "Iteration 3 of 3"
assert_exit "$(guard_exit "$T")" 0 "marker-only history (no transitions at all) -> proceed"

# --- Real bounces count: gate marker + backward transition --------------------
echo -e "${CYAN}Real bounces${NC}"
T=$(tracker create --type ticket --title "realbounce")
to_review "$T"
real_bounce_at_review "$T" "Iteration 1 of 3 — code failure, back to implementer"
assert_exit "$(guard_exit "$T")" 0 "1 real bounce, gate cap 3 -> proceed"
real_bounce_at_review "$T" "Iteration 2 of 3 — second miss"
assert_exit "$(guard_exit "$T")" 2 "2 real bounces at gate, cap 3 -> block (N=3 forbidden)"
stderr=$(bash "$GUARD" "$T" 2>&1 >/dev/null || true)
assert_contains "$stderr" "In Review" "block message names the gate"

# --- Per-gate reset on forward progress; cumulative counter never resets ------
echo -e "${CYAN}Per-gate reset + cumulative budget${NC}"
T=$(tracker create --type ticket --title "gatereset")
to_review "$T"
real_bounce_at_review "$T" "Iteration 1 of 3"
real_bounce_at_review "$T" "Iteration 2 of 3"
# At cap at In Review right now; forward progress over the gate resets ONLY
# its own counter…
trans "$T" "In Test" "review finally passed"
trans "$T" "In Progress" "tests failed"        # backward but NO marker -> not a bounce
trans "$T" "In Review" "fix pushed"            # back at the SAME gate
assert_exit "$(guard_exit "$T")" 0 "forward over gate resets it; later fall-back counts fresh -> proceed"
# …but the cumulative ticket counter kept both bounces: with a tight budget
# cap of 3 the next bounce (total would be 3) is refused even at a fresh gate.
ec=0; stderr=$(ITERATION_GUARD_TICKET_CAP=3 bash "$GUARD" "$T" 2>&1 >/dev/null) || ec=$?
assert_exit "$ec" 2 "cumulative counter survived the gate reset -> ticket budget cap blocks"
assert_contains "$stderr" "cumulative" "cumulative block message says cumulative budget"

# Other gates are untouched by a busy gate.
T=$(tracker create --type ticket --title "othergate")
to_review "$T"
real_bounce_at_review "$T" "Iteration 1 of 3"
real_bounce_at_review "$T" "Iteration 2 of 3"
trans "$T" "In Test" "review passed"           # now at a DIFFERENT gate
assert_exit "$(guard_exit "$T")" 0 "at-cap gate does not block a different gate"

# --- Cumulative cap: env-tunable, 0 disables ----------------------------------
echo -e "${CYAN}Cumulative ticket budget cap (ITERATION_GUARD_TICKET_CAP)${NC}"
T=$(tracker create --type ticket --title "budget")
to_review "$T"
real_bounce_at_review "$T" "Iteration 1 of 3"
ec=0; ITERATION_GUARD_TICKET_CAP=2 bash "$GUARD" "$T" >/dev/null 2>&1 || ec=$?
assert_exit "$ec" 2 "budget cap 2: 1 real bounce -> next total 2 -> block"
ec=0; ITERATION_GUARD_TICKET_CAP=0 bash "$GUARD" "$T" >/dev/null 2>&1 || ec=$?
assert_exit "$ec" 0 "budget cap 0 disables the cumulative level"

# --- Neutral transitions: Blocked / Needs PO Decision --------------------------
echo -e "${CYAN}Neutral transitions (Blocked / Needs PO Decision)${NC}"
T=$(tracker create --type ticket --title "neutral")
to_review "$T"
bounce "$T" "Iteration 1 of 3 — blocked on env"
trans "$T" "Blocked" "environment down"        # neutral: closes the marker window
trans "$T" "In Review" "environment back"      # neutral return
bounce "$T" "Iteration 1 of 3 — PO question"
trans "$T" "Needs PO Decision" "scope question"
assert_exit "$(guard_exit "$T")" 0 "Blocked/NPD detours neither count nor reset -> proceed"

# --- Malformed markers do not count -------------------------------------------
echo -e "${CYAN}Malformed markers${NC}"
T=$(tracker create --type ticket --title "malformed")
to_review "$T"
bounce "$T" "Iteration two of three — spelled out, not a valid marker"
trans "$T" "In Progress" "bounce without valid marker"
trans "$T" "In Review" "back"
assert_exit "$(guard_exit "$T")" 0 "non-numeric marker + backward transition -> not a bounce"

# --- Custom cap read from the marker (of 5), not hardcoded ---------------------
echo -e "${CYAN}Custom cap from marker${NC}"
T=$(tracker create --type ticket --title "customcap")
to_review "$T"
real_bounce_at_review "$T" "Iteration 1 of 5"
real_bounce_at_review "$T" "Iteration 2 of 5"
real_bounce_at_review "$T" "Iteration 3 of 5"
assert_exit "$(guard_exit "$T")" 0 "3 real bounces, cap 5 -> proceed (cap read from marker)"

# --- PILOT-64: a marker may only RAISE the cap, never LOWER it -------------------
# The cap FLOOR is configuration (ITERATION_GUARD_DEFAULT_CAP=3); a marker in a
# comment may push it higher but can never pull it below the floor. An agent must
# not be able to shrink its own budget with a small "of M" and deadlock already-
# approved work (the PILOT-32 class). ADR-A-0026: control state in typed config,
# not parsed prose.
echo -e "${CYAN}PILOT-64: markers may only raise the cap, never lower it${NC}"
# AC4 falsification fixture: an APPROVE gate comment carrying "Iteration 1 of 1"
# at ZERO real bounces must NOT block (old code set cap=1 and blocked at 0 bounces).
T=$(tracker create --type ticket --title "pilot64 approve of 1")
to_review "$T"
bounce "$T" "QAS Gate Results — PILOT-64 APPROVED (Iteration 1 of 1)"
assert_exit "$(guard_exit "$T")" 0 "AC4: APPROVE 'Iteration 1 of 1' at 0 bounces -> no block (cap floored at 3)"

# AC2: a low "of 1" marker on a real reject cannot pull the cap below the floor —
# 1 real bounce under floor 3 still proceeds (old code would cap at 1 and block).
T=$(tracker create --type ticket --title "pilot64 low marker")
to_review "$T"
real_bounce_at_review "$T" "Iteration 1 of 1 — real reject, agent wrote a shrinking cap"
assert_exit "$(guard_exit "$T")" 0 "AC2: 'of 1' marker cannot lower the cap below floor 3 -> 1 bounce proceeds"

# AC2: once RAISED (marker of 5), a later low "of 1" cannot pull it back down —
# the max marker wins. With 2 real bounces the next (3) is under 5 -> proceed;
# a regression flooring back to 3 would block here (next 3 >= 3).
T=$(tracker create --type ticket --title "pilot64 raise then low")
to_review "$T"
real_bounce_at_review "$T" "Iteration 1 of 5"
real_bounce_at_review "$T" "Iteration 2 of 5"
bounce "$T" "APPROVE — Iteration 1 of 1 (no bounce) shrink attempt"   # low marker, no backward transition
assert_exit "$(guard_exit "$T")" 0 "AC2: later 'of 1' does not lower a cap already raised to 5 (max wins)"

# AC3: the block message names the cap SOURCE (config floor vs marker-raised) plus
# the functional-vs-abort split, so the operator need not hand-diagnose the cap.
T=$(tracker create --type ticket --title "pilot64 provenance")
to_review "$T"
real_bounce_at_review "$T" "Iteration 1 of 3"
real_bounce_at_review "$T" "Iteration 2 of 3"
stderr=$(bash "$GUARD" "$T" 2>&1 >/dev/null || true)
assert_contains "$stderr" "configured floor" "AC3: block message names the cap source (configured floor)"
assert_contains "$stderr" "FUNCTIONAL" "AC3: block message names the functional bounce count"

# --- Single comment with two markers counts as ONE bounce ----------------------
echo -e "${CYAN}Single comment with two markers${NC}"
T=$(tracker create --type ticket --title "doublecount")
to_review "$T"
bounce "$T" "Previous attempt was Iteration 1 of 3; this is Iteration 2 of 3"
trans "$T" "In Progress" "bounce"
trans "$T" "In Review" "back"
assert_exit "$(guard_exit "$T")" 0 "single comment w/ two markers = 1 bounce, cap 3 -> proceed"

# --- Tracker unreachable -> fail-open ------------------------------------------
echo -e "${CYAN}Fail-open: tracker unreachable${NC}"
T=$(tracker create --type ticket --title "failopen")
to_review "$T"
real_bounce_at_review "$T" "Iteration 1 of 3"
real_bounce_at_review "$T" "Iteration 2 of 3"   # would block if reachable
ec=0; out=$(ITERATION_GUARD_ADAPTER="$TEST_DIR/does-not-exist.sh" bash "$GUARD" "$T" 2>&1 >/dev/null) || ec=$?
assert_exit "$ec" 0 "missing adapter -> fail-open (exit 0)"
assert_contains "$out" "WARN" "fail-open emits a stderr warning"

# --- Unknown ticket id -> fail-open --------------------------------------------
echo -e "${CYAN}Fail-open: unknown ticket${NC}"
assert_exit "$(guard_exit "NOPE-999")" 0 "unknown ticket -> fail-open (exit 0)"

# --- Output hygiene on block: stdout empty, stderr labelled + names ticket -----
echo -e "${CYAN}Output hygiene on block${NC}"
T=$(tracker create --type ticket --title "hygiene")
to_review "$T"
real_bounce_at_review "$T" "Iteration 1 of 3"
real_bounce_at_review "$T" "Iteration 2 of 3"
stdout=$(bash "$GUARD" "$T" 2>/dev/null || true)
stderr=$(bash "$GUARD" "$T" 2>&1 >/dev/null || true)
assert_empty "$stdout" "stdout is empty on block"
assert_contains "$stderr" "BLOCK" "stderr carries the BLOCK label"
assert_contains "$stderr" "$T" "block message names the ticket"

# --- Hook mode: pipe JSON, correct ticket extracted -----------------------------
echo -e "${CYAN}Hook mode: ticket extracted from command${NC}"
T=$(tracker create --type ticket --title "hooktest")
to_review "$T"
real_bounce_at_review "$T" "Iteration 1 of 3"   # 1 prior real bounce -> next allowed
json_input="{\"tool_name\":\"Bash\",\"tool_input\":{\"command\":\"bash scripts/mock-tracker.sh comment $T --kind gate-results --actor qas --body \\\"Iteration 2 of 3 test\\\"\"}}"
ec=0
bash "$GUARD" <<< "$json_input" >/dev/null 2>&1 || ec=$?
assert_exit "$ec" 0 "hook mode: 1 prior real bounce -> extract $T and proceed"

# --- Hook mode: at cap -> block, command-derived ticket wins over branch --------
echo -e "${CYAN}Hook mode: at cap -> block${NC}"
T=$(tracker create --type ticket --title "hookblock")
to_review "$T"
real_bounce_at_review "$T" "Iteration 1 of 3"
real_bounce_at_review "$T" "Iteration 2 of 3"
json_input="{\"tool_name\":\"Bash\",\"tool_input\":{\"command\":\"bash scripts/mock-tracker.sh comment $T --kind gate-results --actor qas --body \\\"Iteration 3 of 3\\\"\"}}"
ec=0
stderr=$(bash "$GUARD" <<< "$json_input" 2>&1 >/dev/null) || ec=$?
assert_exit "$ec" 2 "hook mode: 2 real bounces, cap 3 -> block (exit 2)"
assert_contains "$stderr" "BLOCK" "hook-mode block carries the BLOCK label"
assert_contains "$stderr" "$T" "hook-mode block names the command-derived ticket (not the branch)"

# --- Hook mode: non-bounce command with marker substring -> no false block ------
echo -e "${CYAN}Hook mode: non-bounce command with marker substring${NC}"
json_input='{"tool_name":"Bash","tool_input":{"command":"git commit -m \"note Iteration 2 of 3\""}}'
ec=0
stderr=$(bash "$GUARD" <<< "$json_input" 2>&1 >/dev/null) || ec=$?
assert_exit "$ec" 0 "hook mode: git commit with marker substring -> allow (exit 0)"
assert_empty "$stderr" "hook mode: non-bounce -> no stderr"

# --- Hook mode: compound command with decoy ticket -> block ---------------------
echo -e "${CYAN}Hook mode: decoy ticket in compound command${NC}"
T=$(tracker create --type ticket --title "decoy")
DECOY=$(tracker create --type ticket --title "decoy-target")
to_review "$T"
real_bounce_at_review "$T" "Iteration 1 of 3"
real_bounce_at_review "$T" "Iteration 2 of 3"
json_input="{\"tool_name\":\"Bash\",\"tool_input\":{\"command\":\"bash scripts/mock-tracker.sh comment $DECOY --kind gate-results --actor qas --body decoy && bash scripts/mock-tracker.sh comment $T --kind gate-results --actor qas --body \\\"Iteration 3 of 3\\\"\"}}"
ec=0
stderr=$(bash "$GUARD" <<< "$json_input" 2>&1 >/dev/null) || ec=$?
assert_exit "$ec" 2 "hook mode: decoy + capped bounce in one command -> block (exit 2)"
assert_contains "$stderr" "BLOCK" "decoy compound block carries BLOCK label"
assert_contains "$stderr" "ambiguous" "decoy compound names ambiguous multi-target"

# --- Hook mode: gate-results without literal marker (body indirection) ----------
echo -e "${CYAN}Hook mode: gate-results without literal marker in command${NC}"
T=$(tracker create --type ticket --title "bodyvar")
to_review "$T"
real_bounce_at_review "$T" "Iteration 1 of 3"
real_bounce_at_review "$T" "Iteration 2 of 3"
json_input="{\"tool_name\":\"Bash\",\"tool_input\":{\"command\":\"bash scripts/mock-tracker.sh comment $T --kind gate-results --actor qas --body \\\"\\$BODY\\\"\"}}"
ec=0
stderr=$(bash "$GUARD" <<< "$json_input" 2>&1 >/dev/null) || ec=$?
assert_exit "$ec" 2 "hook mode: gate-results at cap without literal marker -> block (exit 2)"
assert_contains "$stderr" "BLOCK" "body-var bounce block carries BLOCK label"

# --- Hook mode: gate bounce but tracker unreachable -> fail-open ----------------
echo -e "${CYAN}Hook mode: fail-open when tracker unreachable${NC}"
T=$(tracker create --type ticket --title "hook-failopen")
to_review "$T"
real_bounce_at_review "$T" "Iteration 1 of 3"
real_bounce_at_review "$T" "Iteration 2 of 3"
json_input="{\"tool_name\":\"Bash\",\"tool_input\":{\"command\":\"bash scripts/mock-tracker.sh comment $T --kind gate-results --actor qas --body \\\"Iteration 3 of 3\\\"\"}}"
ec=0
out=$(ITERATION_GUARD_ADAPTER="$TEST_DIR/does-not-exist.sh" bash "$GUARD" <<< "$json_input" 2>&1 >/dev/null) || ec=$?
assert_exit "$ec" 0 "hook mode: bounce at cap but tracker missing -> fail-open (exit 0)"
assert_contains "$out" "WARN" "hook-mode tracker fail-open emits WARN"

# --- Hook mode: no marker in input -> exit 0 silently ---------------------------
echo -e "${CYAN}Hook mode: no marker in command${NC}"
json_input='{"tool_name":"Bash","tool_input":{"command":"bash scripts/mock-tracker.sh update some-id status SomeStatus"}}'
ec=0
stderr=$(bash "$GUARD" <<< "$json_input" 2>&1 >/dev/null) || ec=$?
assert_exit "$ec" 0 "hook mode: no marker in input -> exit 0"
assert_empty "$stderr" "hook mode: no marker -> no stderr output"

# --- TRACKER_CMD as a PATH command ----------------------------------------------
echo -e "${CYAN}Adapter as PATH command${NC}"
TEST_BIN="$TEST_DIR/bin"
mkdir -p "$TEST_BIN"
# Unquoted heredoc bakes the absolute REPO_ROOT path (\$@ stays literal) so the
# fake command works without REPO_ROOT being exported into its environment.
cat > "$TEST_BIN/fake-tracker" << FAKE_TRACKER
#!/usr/bin/env bash
exec bash "$REPO_ROOT/scripts/mock-tracker.sh" "\$@"
FAKE_TRACKER
chmod +x "$TEST_BIN/fake-tracker"

T=$(tracker create --type ticket --title "path-cmd-test")
to_review "$T"
real_bounce_at_review "$T" "Iteration 1 of 3"
real_bounce_at_review "$T" "Iteration 2 of 3"

# NOTE: the env prefix must apply to the guard itself — not to assert_exit with
# guard_exit in a command substitution (the substitution runs before the prefix
# takes effect, so the guard would never see TRACKER_CMD).
ec=0
PATH="$TEST_BIN:$PATH" ITERATION_GUARD_ADAPTER="" TRACKER_CMD="fake-tracker" \
    bash "$GUARD" "$T" >/dev/null 2>&1 || ec=$?
assert_exit "$ec" 2 "TRACKER_CMD as PATH command at cap -> block (exit 2)"

# --- TRACKER_CMD as a command with arguments -------------------------------------
echo -e "${CYAN}Adapter as command with arguments${NC}"
T=$(tracker create --type ticket --title "cmd-with-args-test")
to_review "$T"
real_bounce_at_review "$T" "Iteration 1 of 3"
real_bounce_at_review "$T" "Iteration 2 of 3"

ec=0
ITERATION_GUARD_ADAPTER="" TRACKER_CMD="bash $REPO_ROOT/scripts/mock-tracker.sh" \
    bash "$GUARD" "$T" >/dev/null 2>&1 || ec=$?
assert_exit "$ec" 2 "TRACKER_CMD with args at cap -> block (exit 2)"

# --- Nonexistent command: fail-open ----------------------------------------------
echo -e "${CYAN}Adapter as nonexistent command (fail-open)${NC}"
T=$(tracker create --type ticket --title "nonexistent-cmd-test")
to_review "$T"
real_bounce_at_review "$T" "Iteration 1 of 3"
real_bounce_at_review "$T" "Iteration 2 of 3"

ec=0
out=$(ITERATION_GUARD_ADAPTER="" TRACKER_CMD="definitely-not-a-real-cmd-xyz" bash "$GUARD" "$T" 2>&1 >/dev/null) || ec=$?
assert_exit "$ec" 0 "nonexistent TRACKER_CMD -> fail-open (exit 0)"
assert_contains "$out" "WARN" "nonexistent command fail-open emits WARN"

# --- Parser tolerates a header with no blank line before the body ----------------
# An adapter that renders "### header\n<body>" (no blank separator) must still
# have its bounces counted. Emulate such an adapter via a fixed dump that
# carries two real bounces at In Review and rests at In Review.
echo -e "${CYAN}Adapter without blank line after comment header${NC}"
NOBLANK="$TEST_DIR/noblank-tracker.sh"
cat > "$NOBLANK" << 'NOBLANK_ADAPTER'
#!/usr/bin/env bash
# Renders a ticket whose comment headers are immediately followed by the body,
# with NO blank line in between (a valid adapter shape the guard must handle).
printf '%s\n' \
    "---" \
    "id: ABS-NOBLANK" \
    "status: In Review" \
    "---" \
    "## Comments" \
    "### 2026-07-03 | kind: gate-results | actor: qas" \
    "Iteration 1 of 3 — first bounce" \
    "### 2026-07-03 | kind: transition-reason | actor: qas" \
    "Transition: In Review -> In Progress. Reason: bounce" \
    "### 2026-07-03 | kind: transition-reason | actor: be-developer" \
    "Transition: In Progress -> In Review. Reason: rework done" \
    "### 2026-07-03 | kind: gate-results | actor: qas" \
    "Iteration 2 of 3 — second bounce" \
    "### 2026-07-03 | kind: transition-reason | actor: qas" \
    "Transition: In Review -> In Progress. Reason: bounce" \
    "### 2026-07-03 | kind: transition-reason | actor: be-developer" \
    "Transition: In Progress -> In Review. Reason: rework done"
NOBLANK_ADAPTER
chmod +x "$NOBLANK"
ec=0
ITERATION_GUARD_ADAPTER="$NOBLANK" bash "$GUARD" "ABS-NOBLANK" >/dev/null 2>&1 || ec=$?
assert_exit "$ec" 2 "no blank line after header: 2 real bounces counted -> block (exit 2)"

# --- TRACKER_CMD as a NON-executable script file WITH args ------------------------
# A script path plus args, with the +x bit unset, must resolve (run via bash),
# not fail open. Under the old resolver this fell through to command -v and
# fail-opened.
echo -e "${CYAN}Adapter as non-executable script file with args${NC}"
WRAPPER="$TEST_DIR/wrapper-tracker.sh"   # deliberately NOT chmod +x
cat > "$WRAPPER" << WRAPPER_ADAPTER
#!/usr/bin/env bash
[ "\$1" = "--flag" ] && shift
exec bash "$REPO_ROOT/scripts/mock-tracker.sh" "\$@"
WRAPPER_ADAPTER
T=$(tracker create --type ticket --title "script-with-args-test")
to_review "$T"
real_bounce_at_review "$T" "Iteration 1 of 3"
real_bounce_at_review "$T" "Iteration 2 of 3"
ec=0
ITERATION_GUARD_ADAPTER="" TRACKER_CMD="$WRAPPER --flag" bash "$GUARD" "$T" >/dev/null 2>&1 || ec=$?
assert_exit "$ec" 2 "non-executable script file + args at cap -> block (exit 2)"

# --- Hook mode: approve-at-cap edge (spec §3.2) -----------------------------------
# A gate approving on its final allowed iteration says "no bounce"; the hook
# (which cannot see the coming forward transition) must let it through.
echo -e "${CYAN}Hook mode: approve-at-cap ('no bounce' convention)${NC}"
T=$(tracker create --type ticket --title "approve-at-cap")
to_review "$T"
real_bounce_at_review "$T" "Iteration 1 of 3"
real_bounce_at_review "$T" "Iteration 2 of 3"
json_input="{\"tool_name\":\"Bash\",\"tool_input\":{\"command\":\"bash scripts/mock-tracker.sh comment $T --kind gate-results --actor qas --body \\\"APPROVE — Iteration 3 of 3 (no bounce)\\\"\"}}"
ec=0
bash "$GUARD" <<< "$json_input" >/dev/null 2>&1 || ec=$?
assert_exit "$ec" 0 "hook mode: at cap but 'no bounce' body -> allow (approve-at-cap)"

# --- ABS-305: PO release out of Needs PO Decision resets the gate counters ---------
# The trap: gate[G] reset required a FORWARD transition from G, but the runner
# enforcement blocks the dispatch INTO G — at the cap, the only seat that could
# produce that forward transition is refused, and every sanctioned PO exit
# routes back through the capped gate. The reset key was locked inside the room.
echo -e "${CYAN}ABS-305: ticket at cap -> Needs PO Decision -> release -> dispatchable again${NC}"
T=$(tracker create --type ticket --title "abs305 trap")
to_review "$T"
real_bounce_at_review "$T" "Iteration 1 of 3: findings"
real_bounce_at_review "$T" "Iteration 2 of 3: findings"
assert_exit "$(guard_exit "$T")" 2 "at cap: 2 prior real bounces, next would be 3 of 3 -> block"
# Escalate to the PO (neutral transition: counters unchanged, still blocked
# conceptually) and have the PO release it back into the loop.
trans "$T" "Needs PO Decision" "loop cap escalation"
trans "$T" "Ready for Development" "PO release: scope clarified, continue the loop"
trans "$T" "In Progress" "fresh implementer"
trans "$T" "In Review" "rework done after PO release"
assert_exit "$(guard_exit "$T")" 0 "after PO release: gate counter reset, the gate is enterable again"
# The reset sanctions a FRESH loop, not a free pass: two new real bounces
# reach the cap again.
real_bounce_at_review "$T" "Iteration 1 of 3: new findings"
real_bounce_at_review "$T" "Iteration 2 of 3: new findings"
assert_exit "$(guard_exit "$T")" 2 "the re-armed loop caps again after fresh real bounces"

# --- ABS-305 control: the cumulative ticket budget is NOT reset by a PO release ----
echo -e "${CYAN}ABS-305 control: cumulative ticket cap survives a PO release${NC}"
T=$(tracker create --type ticket --title "abs305 cumulative")
to_review "$T"
real_bounce_at_review "$T" "Iteration 1 of 3"
real_bounce_at_review "$T" "Iteration 2 of 3"
trans "$T" "Needs PO Decision" "escalate"
trans "$T" "Ready for Development" "PO release"
trans "$T" "In Progress" "fresh implementer"
trans "$T" "In Review" "back at gate"
ec=$(ITERATION_GUARD_TICKET_CAP=3 bash "$GUARD" "$T" >/dev/null 2>&1; echo $?)
assert_exit "$ec" 2 "cumulative budget (2 lifetime bounces, cap 3) still blocks — PO release cannot widen ADR-A-0009"

# --- Drift test: guard rank lists vs statuses.yaml document order ------------------
# The guard embeds the chain order (spec §2); statuses.yaml's `- name:` document
# order is the canonical source. Blocked / Needs PO Decision are cross-cutting
# (neutral) and excluded on both sides.
echo -e "${CYAN}Drift test: embedded ranks == statuses.yaml order${NC}"
yaml_order="$(grep -E '^  - name: ' "$MOCK_TRACKER_STATUSES" \
    | sed 's/^  - name: //' \
    | grep -v -e '^Blocked$' -e '^Needs PO Decision$')"
guard_order="$(sed -n '/story pipeline (statuses.yaml/,/for (s in eranks)/p' "$GUARD" \
    | grep -oE '(ranks|eranks)\["[^"]+"\]' \
    | sed -E 's/^e?ranks\["//; s/"\]$//')"
# statuses.yaml lists the story pipeline with the v1/v2 human statuses BEFORE
# Done; the guard ranks them identically. Epic statuses follow in both.
TOTAL=$((TOTAL + 1))
if [ "$yaml_order" = "$guard_order" ]; then
    echo -e "  ${GREEN}PASS${NC} guard rank lists match statuses.yaml document order"
    PASS=$((PASS + 1))
else
    echo -e "  ${RED}FAIL${NC} guard rank lists drifted from statuses.yaml"
    echo "--- statuses.yaml ---"; echo "$yaml_order"
    echo "--- guard ---"; echo "$guard_order"
    FAIL=$((FAIL + 1))
fi

# --- ABS-305: a PO release out of Needs PO Decision reopens the capped gate ----
# The trap: a gate at its bounce cap can never re-enter — the only reset is a
# forward transition FROM the gate, which needs the very seat the cap blocks, and
# every sanctioned PO exit routes back through the capped gate. A fresh PO
# adjudication (release OUT of "Needs PO Decision") must clear the per-gate
# counters so the ticket gets one clean re-entry.
echo -e "\n${CYAN}ABS-305: PO release reopens a gate parked at its cap${NC}"
T=$(tracker create --type ticket --title "abs305 locked room")
to_review "$T"
real_bounce_at_review "$T" "Iteration 1 of 3 — first miss"
real_bounce_at_review "$T" "Iteration 2 of 3 — second miss"
assert_exit "$(guard_exit "$T")" 2 "ABS-305: gate 'In Review' at cap 3 -> blocked (the locked room)"
# Sanctioned PO route: In Review -> Needs PO Decision -> Ready for Development,
# then the implementer chain walks the ticket back to the capped gate.
trans "$T" "Needs PO Decision" "escalate for product decision"
trans "$T" "Ready for Development" "PO release: try again"
trans "$T" "In Progress"; trans "$T" "In Review" "rework"
assert_exit "$(guard_exit "$T")" 0 "ABS-305: after a PO release the ticket re-enters 'In Review' (gate reset)"
# Off-switch: with the reset disabled, the trap persists (today's behaviour).
ITERATION_GUARD_PO_RELEASE_RESET=0 assert_exit \
    "$(ITERATION_GUARD_PO_RELEASE_RESET=0 guard_exit "$T")" 2 \
    "ABS-305: ITERATION_GUARD_PO_RELEASE_RESET=0 keeps the ticket blocked (off-switch)"

# --- ABS-305: the PO release does NOT reset the cumulative ticket budget -------
# The per-gate reset must not become a free reset of the ADR-A-0009 budget brake:
# a ticket that keeps bouncing across PO releases is still stopped by the
# cumulative cap. Cap the ticket budget low and prove it still fires post-release.
T=$(tracker create --type ticket --title "abs305 budget intact")
to_review "$T"
real_bounce_at_review "$T" "Iteration 1 of 9 — miss"
real_bounce_at_review "$T" "Iteration 2 of 9 — miss"
trans "$T" "Needs PO Decision" "escalate"
trans "$T" "Ready for Development" "PO release"
trans "$T" "In Progress"; trans "$T" "In Review" "rework"
# Gate is reset (2 gate bounces < cap 9 anyway), but total bounces = 2. With the
# cumulative cap set to 3, the NEXT bounce (total 3) must still block.
assert_exit "$(ITERATION_GUARD_TICKET_CAP=3 guard_exit "$T")" 2 \
    "ABS-305: PO release does not reset the cumulative ticket budget (ADR-A-0009 brake intact)"

# --- PILOT-49 / ABS-555: infrastructure aborts do NOT count; real rejects do ----
# A seat that dies from an infrastructure cause (error_max_turns, crash, timeout,
# rate-limit, session-poison) — or the orchestrator's own CRASH-REPAIR /
# INPROGRESS-HEAL / spawn-crashed backward route — renders NO functional verdict.
# Its backward transition must NOT consume an iteration, even with a gate marker
# pending. The classifier keys off the transition REASON.
echo -e "\n${CYAN}PILOT-49: infrastructure aborts are excluded from the iteration counter${NC}"
# One infra abort at In Review: a gate marker is posted (e.g. QAS approved), then
# the seat dies and the orchestrator routes the ticket back via CRASH-REPAIR.
infra_abort_at_review() {
    bounce "$1" "$2"
    trans "$1" "In Progress" "CRASH-REPAIR: own SPAWN-CRASH marker proves seat is dead; routing back to In Review (ABS-295)"
    trans "$1" "In Review" "fresh seat re-derived"
}
T=$(tracker create --type ticket --title "pilot49 infra")
to_review "$T"
infra_abort_at_review "$T" "Iteration 1 of 3 — QAS approved, then seat died (error_max_turns)"
infra_abort_at_review "$T" "Iteration 2 of 3 — seat died again on the prefix ceiling"
# Two infra aborts would have tripped gate cap 3 had they counted; they must not.
assert_exit "$(guard_exit "$T")" 0 "2 infra aborts at gate -> counter unchanged, proceed (AC1/AC2)"
# …and they consume no cumulative budget either (the deadlock class).
assert_exit "$(ITERATION_GUARD_TICKET_CAP=3 guard_exit "$T")" 0 \
    "infra aborts do not consume the cumulative budget (AC1) — no spurious deadlock"

# Control (AC4): the SAME gate+backward shape but with a FUNCTIONAL reject reason
# DOES count — one iteration per real QAS reject.
T=$(tracker create --type ticket --title "pilot49 real reject")
to_review "$T"
real_bounce_at_review "$T" "Iteration 1 of 3 — real QAS reject: AC3 not met"
real_bounce_at_review "$T" "Iteration 2 of 3 — real QAS reject: AC5 not met"
assert_exit "$(guard_exit "$T")" 2 "2 real QAS rejects -> +1 each -> block at cap 3 (AC4 control)"

# Mixed history + observability (AC5): the block reason names functional vs abort.
T=$(tracker create --type ticket --title "pilot49 observability")
to_review "$T"
infra_abort_at_review "$T" "Iteration 1 of 3 — seat died (timeout)"
real_bounce_at_review "$T" "Iteration 1 of 3 — real reject"
real_bounce_at_review "$T" "Iteration 2 of 3 — real reject"
assert_exit "$(guard_exit "$T")" 2 "1 abort + 2 functional bounces -> cap hit on the functional 2 (AC4)"
stderr=$(bash "$GUARD" "$T" 2>&1 >/dev/null || true)
assert_contains "$stderr" "infrastructure abort" "block reason names the excluded infra aborts (AC5)"
assert_contains "$stderr" "FUNCTIONAL" "block reason names the functional bounce count (AC5)"

# --- PILOT-77 / ADR-A-0026 P1: typed iteration_cap field is authoritative -------
# Control state lives in a typed FIELD, not comment prose. When the field is
# present the dispatch reads it directly and comment markers no longer influence
# the cap. When the field is ABSENT the guard falls back to the legacy marker
# behavior (fail-soft) so unmigrated tickets are unaffected.
echo -e "${CYAN}PILOT-77: typed iteration_cap field${NC}"

# Field RAISES the cap: iteration_cap=5, two real bounces -> next (3) < 5 -> proceed
# (with no field and no marker the floor-3 default would block at the 3rd here).
T=$(tracker create --type ticket --title "pilot77 field raises")
tracker update "$T" iteration_cap 5 >/dev/null
to_review "$T"
real_bounce_at_review "$T" "Iteration 1 of 1 — routine QAS note, must be ignored"
real_bounce_at_review "$T" "Iteration 2 of 1 — routine QAS note, must be ignored"
assert_exit "$(guard_exit "$T")" 0 "typed field cap=5 wins; low 'of 1' markers ignored -> 2 bounces proceed"

# The self-renewing defect from PILOT-64: operator raised the cap, then a routine
# 'Iteration 1 of 1' comment used to pull it back to 1. With the typed field the
# marker is inert — cap stays 5 and the block message NAMES the field as source.
T=$(tracker create --type ticket --title "pilot77 field provenance")
tracker update "$T" iteration_cap 5 >/dev/null
to_review "$T"
real_bounce_at_review "$T" "Iteration 1 of 5"
real_bounce_at_review "$T" "Iteration 2 of 5"
real_bounce_at_review "$T" "Iteration 3 of 5"
bounce "$T" "APPROVE — Iteration 1 of 1 (no bounce) shrink attempt"   # inert under the field
assert_exit "$(guard_exit "$T")" 0 "typed field cap=5: 3 bounces + shrinking marker -> still proceed"
# Drive it to the cap to read the provenance line.
real_bounce_at_review "$T" "Iteration 4 of 5"
stderr=$(bash "$GUARD" "$T" 2>&1 >/dev/null || true)
assert_exit "$(guard_exit "$T")" 2 "typed field cap=5: 4 bounces -> next 5 >= 5 -> block"
assert_contains "$stderr" "typed field iteration_cap=5" "block message names the typed field as cap source"

# Field can LOWER below the floor — a deliberate, audited operator choice (unlike
# agent prose). iteration_cap=2, one real bounce -> next (2) >= 2 -> block, where
# the floor-3 default (or a marker) would still proceed.
T=$(tracker create --type ticket --title "pilot77 field lowers")
tracker update "$T" iteration_cap 2 >/dev/null
to_review "$T"
real_bounce_at_review "$T" "Iteration 1 of 3 — marker says 3 but field says 2"
assert_exit "$(guard_exit "$T")" 2 "typed field cap=2 is authoritative below the floor -> 1 bounce blocks"

# FAIL-SOFT (AC3): no iteration_cap field -> legacy marker behavior is preserved.
T=$(tracker create --type ticket --title "pilot77 failsoft no field")
to_review "$T"
real_bounce_at_review "$T" "Iteration 1 of 5"
real_bounce_at_review "$T" "Iteration 2 of 5"
real_bounce_at_review "$T" "Iteration 3 of 5"
assert_exit "$(guard_exit "$T")" 0 "no field present -> marker 'of 5' still read (fail-soft), 3 bounces proceed"

# FAIL-SOFT (AC3): the mock rejects a malformed field write, so a bad value can
# never reach the frontmatter; the guard then reads no field and falls back.
T=$(tracker create --type ticket --title "pilot77 failsoft bad field")
ec=0; tracker update "$T" iteration_cap "abc" >/dev/null 2>&1 || ec=$?
assert_exit "$ec" 1 "mock rejects a non-integer iteration_cap (validated at the adapter)"
to_review "$T"
real_bounce_at_review "$T" "Iteration 1 of 3"
assert_exit "$(guard_exit "$T")" 0 "no valid field written -> floor-3 default, 1 bounce proceeds (fail-soft)"

# =============================================================================
echo -e "\n${CYAN}=== Test Results ===${NC}\n"
echo -e "  Total:  $TOTAL"
echo -e "  ${GREEN}Passed: $PASS${NC}"
if [ $FAIL -gt 0 ]; then
    echo -e "  ${RED}Failed: $FAIL${NC}"; exit 1
else
    echo -e "  Failed: 0"; echo -e "\n  ${GREEN}ALL TESTS PASSED${NC}\n"; exit 0
fi
