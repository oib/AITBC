#!/bin/bash
# =============================================================================
# Test: Status-Machine Guard (ABS-136, Befund 6 / run ABS-126)
# =============================================================================
# A seat that jumps a MANDATORY chain station in one hop (the live Befund 6:
# qas In Test -> Done, skipping Story Acceptance / Merging / Docs) must be
# caught and redirected to the first skipped mandatory station with an audit
# comment + a run.log event. Legitimate ABS-84 SKIP-FORWARD jumps (over
# conditional-only stages) and backward review bounces stay untouched.
#
# The guard's decision logic (chain_status_at / first_skipped_mandatory /
# forward_skip_illegitimate / last_transition_pair) is pure, so this suite
# SOURCES scripts/orchestrator.sh (main is source-guarded) and exercises the
# functions directly. station_guard's redirect + audit + event side effects
# are driven with a stubbed `tracker` and `ticket_still_in` so no real adapter
# or model is touched.
#
# bash 3.2 + BSD tools only. Run from repo root: bash tests/test-station-guard.sh
# =============================================================================

set -euo pipefail

# ABS-285: scrub ambient ORCH_* before driving the real seam/runner. A seat
# exports ~37 of them; a non-empty one leaks into the code under test and makes
# the result a function of the calling seat instead of the commit. Prefix-unset
# covers vars added later. This test sets every ORCH_* it needs, below.
unset "${!ORCH_@}"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

PASS=0; FAIL=0; TOTAL=0
GREEN='\033[0;32m'; RED='\033[0;31m'; CYAN='\033[0;36m'; YELLOW='\033[1;33m'; NC='\033[0m'

assert_true() {  # <cmd...> -- last arg is the label
    local label="${!#}"; set -- "${@:1:$(($#-1))}"
    TOTAL=$((TOTAL + 1))
    if "$@"; then echo -e "  ${GREEN}PASS${NC} $label"; PASS=$((PASS + 1))
    else echo -e "  ${RED}FAIL${NC} $label (expected true, got false)"; FAIL=$((FAIL + 1)); fi
}
assert_false() {
    local label="${!#}"; set -- "${@:1:$(($#-1))}"
    TOTAL=$((TOTAL + 1))
    if "$@"; then echo -e "  ${RED}FAIL${NC} $label (expected false, got true)"; FAIL=$((FAIL + 1))
    else echo -e "  ${GREEN}PASS${NC} $label"; PASS=$((PASS + 1)); fi
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

echo -e "${CYAN}=== Status-Machine Guard (ABS-136) ===${NC}\n"

# =============================================================================
echo -e "${CYAN}chain_status_at is the inverse of chain_index (bijection)${NC}"
# =============================================================================
ok=1
for s in "Design" "Ready for Development" "In Progress" "In Review" "Security Review" \
         "Test Prep" "In Test" "Design Test" "Story Acceptance" "Merging" "Docs" "Done" \
         "PO Triage" "Grooming" "Enrichment" "Ticket Review" "Architecture Review" \
         "Stories In Flight" "Epic Integration" "Ready for Epic Acceptance" "Epic Done"; do
    [ "$(chain_status_at "$(chain_index "$s")")" = "$s" ] || ok=0
done
assert_eq "$ok" "1" "round-trips every canonical chain status"
assert_eq "$(chain_status_at 0)" "" "index 0 (off-chain) maps back to empty"

# =============================================================================
echo -e "\n${CYAN}first_skipped_mandatory — conditional stages are transparent${NC}"
# =============================================================================
assert_eq "$(first_skipped_mandatory 7 12)" "Story Acceptance" "In Test..Done -> first mandatory skipped is Story Acceptance"
assert_eq "$(first_skipped_mandatory 9 12)" "Merging" "Story Acceptance..Done -> Merging"
assert_eq "$(first_skipped_mandatory 10 12)" "Docs" "Merging..Done -> Docs"
assert_eq "$(first_skipped_mandatory 4 7)" "" "In Review..In Test spans only conditional Sec Review/Test Prep -> none"
assert_eq "$(first_skipped_mandatory 7 9)" "" "In Test..Story Acceptance spans only conditional Design Test -> none"

# =============================================================================
echo -e "\n${CYAN}AC1/AC2 forward_skip_illegitimate — mandatory skips flagged, SKIP-FORWARD green${NC}"
# =============================================================================
# --- ILLEGITIMATE forward skips of a mandatory seat (the Befund-6 class) ------
assert_true  forward_skip_illegitimate "In Test" "Done"              "In Test -> Done (skips Story Acceptance/Merging/Docs) -> flagged"
assert_true  forward_skip_illegitimate "In Review" "Story Acceptance" "In Review -> Story Acceptance (skips mandatory In Test) -> flagged"
assert_true  forward_skip_illegitimate "Story Acceptance" "Done"      "Story Acceptance -> Done (skips Merging/Docs) -> flagged"
assert_true  forward_skip_illegitimate "Merging" "Done"              "Merging -> Done (skips Docs) -> flagged"
assert_true  forward_skip_illegitimate "Grooming" "Epic Done"        "epic-range Grooming -> Epic Done (skips mandatory) -> flagged"

# --- LEGITIMATE SKIP-FORWARD (ABS-84): every skipped stage is conditional -----
assert_false forward_skip_illegitimate "In Review" "Test Prep"        "In Review -> Test Prep (skips conditional Sec Review) -> green"
assert_false forward_skip_illegitimate "In Review" "In Test"          "In Review -> In Test (skips conditional Sec Review + Test Prep) -> green"
assert_false forward_skip_illegitimate "Security Review" "In Test"    "Security Review -> In Test (skips conditional Test Prep) -> green"
assert_false forward_skip_illegitimate "In Test" "Story Acceptance"   "In Test -> Story Acceptance (skips conditional Design Test) -> green"
assert_false forward_skip_illegitimate "In Review" "Security Review"  "In Review -> Security Review (ABS-124 gate-skip, adjacent) -> green"
assert_false forward_skip_illegitimate "In Test" "Design Test"        "In Test -> Design Test (ABS-124 gate-skip, adjacent) -> green"
assert_false forward_skip_illegitimate "Design" "Ready for Development" "Design -> Ready for Development (adjacent SKIP-FORWARD target) -> green"

# --- AC3 BACKWARD transitions (review bounces) are always allowed -------------
assert_false forward_skip_illegitimate "In Review" "In Progress"        "In Review -> In Progress (bounce) -> allowed"
assert_false forward_skip_illegitimate "Story Acceptance" "Ready for Development" "Story Acceptance -> Ready for Development (reject bounce) -> allowed"
assert_false forward_skip_illegitimate "In Test" "Ready for Development" "In Test -> Ready for Development (test-fail bounce) -> allowed"
assert_false forward_skip_illegitimate "Done" "Story Acceptance"        "Done -> Story Acceptance (guard's own redirect) -> allowed (idempotent)"

# --- Off-chain / cross-range are exempt ---------------------------------------
assert_false forward_skip_illegitimate "Backlog" "Design"               "off-chain 'from' (Backlog) is exempt"
assert_false forward_skip_illegitimate "In Progress" "Epic Integration"  "story-range -> epic-range never compared (disjoint tickets)"

# =============================================================================
echo -e "\n${CYAN}ABS-216 — 'Ready for Human Acceptance' (out-of-chain) folds Story Acceptance${NC}"
# =============================================================================
# RfHA has no canonical chain_index (v2 human gate, index 0) — guard_chain_index
# maps it to 10 (functionally between Story Acceptance/9 and Merging/10) for skip
# detection ONLY, so an 'In Test -> RfHA' hop that folds mandatory Story Acceptance
# is caught while the canonical chain_index stays 0.
assert_eq "$(chain_index "Ready for Human Acceptance")" "0" "canonical chain_index for RfHA stays 0 (bounce counting untouched)"
assert_eq "$(guard_chain_index "Ready for Human Acceptance")" "10" "guard_chain_index supplements RfHA to 10 for skip detection"
assert_eq "$(guard_chain_index "In Test")" "$(chain_index "In Test")" "guard_chain_index is a pass-through for canonical chain statuses"
# AC1: the Befund class — In Test -> RfHA folds the mandatory Story Acceptance seat.
assert_true  forward_skip_illegitimate "In Test" "Ready for Human Acceptance"   "In Test -> RfHA (folds mandatory Story Acceptance) -> flagged"
assert_eq "$(first_skipped_mandatory "$(guard_chain_index "In Test")" "$(guard_chain_index "Ready for Human Acceptance")")" "Story Acceptance" \
    "In Test -> RfHA redirect target is Story Acceptance"
assert_true  forward_skip_illegitimate "Design Test" "Ready for Human Acceptance" "Design Test -> RfHA (folds mandatory Story Acceptance) -> flagged"
# AC2: legal paths around RfHA stay green.
assert_false forward_skip_illegitimate "Story Acceptance" "Ready for Human Acceptance" "Story Acceptance -> RfHA (legal human gate) -> green"
assert_false forward_skip_illegitimate "Ready for Human Acceptance" "Merging"        "RfHA -> Merging (same guard slot) -> green"
assert_false forward_skip_illegitimate "Ready for Human Acceptance" "Ready for Merge" "RfHA -> Ready for Merge (off-chain target, the legal exit) -> green"

# =============================================================================
echo -e "\n${CYAN}ABS-247 — flag-conditional stations are enforced (pure logic)${NC}"
# =============================================================================
# chain_station_mandatory: a conditional station is mandatory ONLY when its gating
# flag is in the active-flag set; unconditional stations are always mandatory.
assert_true  chain_station_mandatory "Story Acceptance" ""        "Story Acceptance (unconditional) -> mandatory regardless of flags"
assert_false chain_station_mandatory "Design Test" ""             "Design Test unflagged -> skippable"
assert_true  chain_station_mandatory "Design Test" "design"       "Design Test with design flag -> mandatory (ABS-247)"
assert_false chain_station_mandatory "Security Review" "design"   "Security Review with only design flag -> still skippable"
assert_true  chain_station_mandatory "Security Review" "security" "Security Review with security flag -> mandatory"
assert_true  chain_station_mandatory "Test Prep" "data"           "Test Prep with data flag -> mandatory"
assert_true  chain_station_mandatory "Test Prep" "design security data" "Test Prep with full flag set -> mandatory"

# first_skipped_mandatory becomes flag-aware via the optional 3rd arg.
assert_eq "$(first_skipped_mandatory 7 9 "design")" "Design Test" "AC1: In Test..Story Acceptance with design flag -> Design Test is now mandatory"
assert_eq "$(first_skipped_mandatory 7 9 "")"       ""            "AC2: In Test..Story Acceptance unflagged -> still transparent (unchanged)"
assert_eq "$(first_skipped_mandatory 4 6 "security")" "Security Review" "AC3: In Review..Test Prep with security flag -> Security Review mandatory"
assert_eq "$(first_skipped_mandatory 5 7 "data")"   "Test Prep"   "AC3: Security Review..In Test with data flag -> Test Prep mandatory"
assert_eq "$(first_skipped_mandatory 4 7 "data")"   "Test Prep"   "AC3: In Review..In Test with data flag -> first mandatory is Test Prep (Sec Review still skippable)"
assert_eq "$(first_skipped_mandatory 4 7 "")"       ""            "AC2: In Review..In Test unflagged -> transparent (unchanged)"

# forward_skip_illegitimate becomes flag-aware via the optional 3rd arg.
assert_true  forward_skip_illegitimate "In Test" "Story Acceptance" "design"   "AC1: In Test -> Story Acceptance with design flag -> flagged (folds Design Test)"
assert_false forward_skip_illegitimate "In Test" "Story Acceptance" ""         "AC2: In Test -> Story Acceptance unflagged -> green (SKIP-FORWARD legit)"
assert_false forward_skip_illegitimate "In Test" "Story Acceptance" "security" "AC2: In Test -> Story Acceptance with unrelated security flag -> green"
assert_true  forward_skip_illegitimate "In Review" "In Test" "security"        "AC3: In Review -> In Test with security flag -> flagged (folds Security Review)"
assert_true  forward_skip_illegitimate "In Review" "In Test" "data"            "AC3: In Review -> In Test with data flag -> flagged (folds Test Prep)"
assert_false forward_skip_illegitimate "In Review" "In Test" ""                "AC2: In Review -> In Test unflagged -> green"

# =============================================================================
echo -e "\n${CYAN}last_transition_pair — parses the ACTUAL last transition (not net event)${NC}"
# =============================================================================
DUMP_MULTI="$(printf 'status: Done\n\n### t1 | kind: transition-reason | actor: x\n\nTransition: In Review -> In Test. Reason: review passed\n\n### t2 | kind: transition-reason | actor: qas\n\nTransition: In Test -> Done. Reason: tests green\n')"
assert_eq "$(last_transition_pair "$DUMP_MULTI")" "$(printf 'In Test\tDone')" "returns the LAST transition pair across a multi-step history"
assert_eq "$(last_transition_pair "$(printf 'status: Backlog\n\nno transitions yet\n')")" "" "no transition comment -> empty"

# =============================================================================
# station_guard side effects — stub the adapter + status probe.
# =============================================================================
STUB_CALLS=""      # file capturing tracker comment/transition invocations
STUB_DUMP=""       # what `tracker get` returns
STUB_IN=0          # ticket_still_in exit code

tracker() {
    case "$1" in
        get)        printf '%s' "$STUB_DUMP" ;;
        comment)    shift; printf 'COMMENT %s\n' "$*" >> "$STUB_CALLS" ;;
        transition) shift; printf 'TRANSITION %s\n' "$*" >> "$STUB_CALLS" ;;
        *)          : ;;
    esac
}
ticket_still_in() { return "$STUB_IN"; }

# Capture files live in the PARENT shell so writes made inside station_guard's
# command-substitution subshell (tracker/runlog append to these paths) survive.
STUB_CALLS="$(mktemp /tmp/sg-calls-XXXXXX)"
ORCH_RUN_LOG="$(mktemp /tmp/sg-runlog-XXXXXX)"

# run_guard <ticket> <to> — run station_guard, capturing stdout(intent) + rc.
# Prints "rc\nstdout". Truncates the capture files first so each call is clean.
run_guard() {
    : > "$STUB_CALLS"; : > "$ORCH_RUN_LOG"
    local rc=0 out
    out="$(station_guard "$1" "$2" 2>/dev/null)" || rc=$?
    printf '%s\n%s' "$rc" "$out"
}

# =============================================================================
echo -e "\n${CYAN}AC1 — In Test -> Done is caught, redirected, and audited (live)${NC}"
# =============================================================================
MODE="live"
STUB_IN=0
STUB_DUMP="$(printf 'status: Done\n\n### t | kind: transition-reason | actor: qas\n\nTransition: In Test -> Done. Reason: tests green\n')"
res="$(run_guard "ABS-999" "Done")"; rc="${res%%$'\n'*}"; out="${res#*$'\n'}"
assert_eq "$rc" "0" "guard INTERVENES (rc 0) on the illegitimate In Test -> Done skip"
assert_contains "$out" "INTENT STATION-GUARD ticket=ABS-999 role=- to=Story Acceptance" "logs the STATION-GUARD intent redirecting to Story Acceptance"
calls="$(cat "$STUB_CALLS")"
assert_contains "$calls" "TRANSITION ABS-999 Story Acceptance" "re-transitions the ticket to the first skipped mandatory station"
assert_contains "$calls" "COMMENT ABS-999 --kind skip --actor orchestrator" "posts a kind:skip audit comment as the orchestrator"
assert_contains "$calls" "ABS-136" "audit comment cites ABS-136"
# AC4: a run.log event is written for the intervention.
assert_contains "$(cat "$ORCH_RUN_LOG")" "INTENT-STATION-GUARD	ABS-999" "writes an INTENT-STATION-GUARD run.log event (AC4)"

# =============================================================================
echo -e "\n${CYAN}ABS-216 — In Test -> Ready for Human Acceptance is caught end-to-end${NC}"
# =============================================================================
# The v2.24.0 smoke-gate Befund: qas jumped In Test -> RfHA, folding Story
# Acceptance. RfHA is off-chain (chain_index 0) so the guard used to no-op at its
# landing check; guard_chain_index now supplements it to slot 10 so the guard fires.
MODE="live"
STUB_IN=0
STUB_DUMP="$(printf 'status: Ready for Human Acceptance\n\n### t | kind: transition-reason | actor: qas\n\nTransition: In Test -> Ready for Human Acceptance. Reason: In Test gate passed\n')"
res="$(run_guard "ABS-216" "Ready for Human Acceptance")"; rc="${res%%$'\n'*}"; out="${res#*$'\n'}"
assert_eq "$rc" "0" "guard INTERVENES (rc 0) on the In Test -> RfHA skip that folds Story Acceptance"
assert_contains "$out" "INTENT STATION-GUARD ticket=ABS-216 role=- to=Story Acceptance" "redirects the RfHA landing to Story Acceptance"
calls="$(cat "$STUB_CALLS")"
assert_contains "$calls" "TRANSITION ABS-216 Story Acceptance" "re-transitions RfHA -> Story Acceptance so the folded seat runs"
assert_contains "$calls" "COMMENT ABS-216 --kind skip --actor orchestrator" "posts a kind:skip audit comment for the RfHA fold"

# =============================================================================
echo -e "\n${CYAN}Dry-run logs the intent but performs NO adapter writes${NC}"
# =============================================================================
MODE="dry-run"
STUB_IN=0
STUB_DUMP="$(printf 'status: Done\n\nTransition: In Test -> Done. Reason: tests green\n')"
res="$(run_guard "ABS-999" "Done")"; rc="${res%%$'\n'*}"; out="${res#*$'\n'}"
assert_eq "$rc" "0" "dry-run still reports the intervention (rc 0)"
assert_contains "$out" "INTENT STATION-GUARD ticket=ABS-999 role=- to=Story Acceptance" "dry-run logs the redirect intent"
assert_eq "$(cat "$STUB_CALLS")" "" "dry-run makes NO tracker comment/transition calls"
MODE="live"

# =============================================================================
echo -e "\n${CYAN}AC2 — legitimate SKIP-FORWARD landing is a silent no-op${NC}"
# =============================================================================
STUB_IN=0
STUB_DUMP="$(printf 'status: In Test\n\nTransition: In Review -> In Test. Reason: review passed, unflagged conditional stages skip-forwarded\n')"
res="$(run_guard "ABS-998" "In Test")"; rc="${res%%$'\n'*}"; out="${res#*$'\n'}"
assert_eq "$rc" "1" "In Review -> In Test (all skipped stages conditional) -> no-op (rc 1)"
assert_not_contains "$out" "INTENT STATION-GUARD" "no guard intent on a legitimate SKIP-FORWARD"
assert_eq "$(cat "$STUB_CALLS")" "" "no adapter writes on a legitimate SKIP-FORWARD"

# =============================================================================
echo -e "\n${CYAN}AC3 — a backward review bounce is never guarded${NC}"
# =============================================================================
STUB_IN=0
STUB_DUMP="$(printf 'status: In Progress\n\nTransition: In Review -> In Progress. Reason: blocking review findings\n')"
res="$(run_guard "ABS-997" "In Progress")"; rc="${res%%$'\n'*}"; out="${res#*$'\n'}"
assert_eq "$rc" "1" "In Review -> In Progress bounce -> no-op (rc 1)"
assert_not_contains "$out" "INTENT STATION-GUARD" "no guard intent on a backward bounce"

# =============================================================================
echo -e "\n${CYAN}ABS-247 AC1 — design-flagged In Test -> Story Acceptance is caught end-to-end${NC}"
# =============================================================================
# The consumer Befund: a design-flagged ticket jumped In Test -> Story Acceptance,
# silently folding the mandatory-for-this-ticket Design Test gate. The flag-aware
# guard reads the ticket flags (which it already dumps) and intervenes.
MODE="live"
STUB_IN=0
STUB_DUMP="$(printf -- '---\nstatus: Story Acceptance\nflags: [design]\n---\n\n### t | kind: transition-reason | actor: qas\n\nTransition: In Test -> Story Acceptance. Reason: In Test gate passed\n')"
res="$(run_guard "ABS-247D" "Story Acceptance")"; rc="${res%%$'\n'*}"; out="${res#*$'\n'}"
assert_eq "$rc" "0" "guard INTERVENES (rc 0) on the design-flagged In Test -> Story Acceptance skip"
assert_contains "$out" "INTENT STATION-GUARD ticket=ABS-247D role=- to=Design Test" "redirects the design-flagged landing to Design Test"
calls="$(cat "$STUB_CALLS")"
assert_contains "$calls" "TRANSITION ABS-247D Design Test" "re-transitions the ticket to the folded Design Test seat"
assert_contains "$calls" "COMMENT ABS-247D --kind skip --actor orchestrator" "posts a kind:skip audit comment"
assert_contains "$calls" "design" "audit comment names the 'design' flag that made Design Test mandatory"
assert_contains "$calls" "ABS-247" "audit comment cites ABS-247 (flag-conditional enforcement)"

# =============================================================================
echo -e "\n${CYAN}ABS-247 AC2 — the SAME hop UNFLAGGED stays a silent no-op${NC}"
# =============================================================================
# SKIP-FORWARD legitimacy is preserved: without the design flag, In Test ->
# Story Acceptance folds only the (now legitimately skippable) Design Test.
MODE="live"
STUB_IN=0
STUB_DUMP="$(printf -- '---\nstatus: Story Acceptance\nflags: []\n---\n\nTransition: In Test -> Story Acceptance. Reason: unflagged conditional Design Test skip-forwarded\n')"
res="$(run_guard "ABS-247U" "Story Acceptance")"; rc="${res%%$'\n'*}"; out="${res#*$'\n'}"
assert_eq "$rc" "1" "unflagged In Test -> Story Acceptance -> no-op (rc 1), SKIP-FORWARD preserved"
assert_not_contains "$out" "INTENT STATION-GUARD" "no guard intent on the unflagged SKIP-FORWARD"
assert_eq "$(cat "$STUB_CALLS")" "" "no adapter writes on the unflagged SKIP-FORWARD"

# =============================================================================
echo -e "\n${CYAN}ABS-247 AC3 — security-flagged In Review -> In Test is caught end-to-end${NC}"
# =============================================================================
MODE="live"
STUB_IN=0
STUB_DUMP="$(printf -- '---\nstatus: In Test\nflags: [security]\n---\n\nTransition: In Review -> In Test. Reason: review passed\n')"
res="$(run_guard "ABS-247S" "In Test")"; rc="${res%%$'\n'*}"; out="${res#*$'\n'}"
assert_eq "$rc" "0" "guard INTERVENES on the security-flagged In Review -> In Test skip"
assert_contains "$out" "INTENT STATION-GUARD ticket=ABS-247S role=- to=Security Review" "redirects the security-flagged landing to Security Review"
calls="$(cat "$STUB_CALLS")"
assert_contains "$calls" "TRANSITION ABS-247S Security Review" "re-transitions the ticket to the folded Security Review seat"
assert_contains "$calls" "security" "audit comment names the 'security' flag that made Security Review mandatory"

# =============================================================================
echo -e "\n${CYAN}ABS-247 AC3 — data-flagged In Review -> In Test redirects to Test Prep${NC}"
# =============================================================================
MODE="live"
STUB_IN=0
STUB_DUMP="$(printf -- '---\nstatus: In Test\nflags: [data]\n---\n\nTransition: In Review -> In Test. Reason: review passed\n')"
res="$(run_guard "ABS-247T" "In Test")"; rc="${res%%$'\n'*}"; out="${res#*$'\n'}"
assert_eq "$rc" "0" "guard INTERVENES on the data-flagged In Review -> In Test skip"
assert_contains "$out" "INTENT STATION-GUARD ticket=ABS-247T role=- to=Test Prep" "redirects the data-flagged landing to Test Prep"

# =============================================================================
echo -e "\n${CYAN}ABS-266 — the MERGE BOUNDARY: a Docs landing is never dragged backward${NC}"
# =============================================================================
# ABS-234: a PO-accepted, QAS-green, HITL-merged story was released to Docs by the
# RTE; the move was recorded 'In Progress -> Docs', the guard read it as an
# implementation-stage skip of mandatory In Review and pulled the MERGED story
# backward — which re-spawns an implementer to rebuild already-merged code.
# `Docs` carries entered_when "Story merged" (statuses.yaml), so any landing there
# is post-merge and exempt from the pre-merge station-order check.

# --- pure logic: every landing in Docs is exempt, whatever it skipped ----------
assert_false forward_skip_illegitimate "In Progress" "Docs"  "AC1: In Progress -> Docs (the ABS-234 hop) -> exempt, merged story never dragged back"
assert_false forward_skip_illegitimate "In Test" "Docs"      "In Test -> Docs (post-merge landing) -> exempt"
assert_false forward_skip_illegitimate "Design" "Docs"       "Design -> Docs (skips the whole implementation range) -> still exempt (merge boundary)"
assert_false forward_skip_illegitimate "In Progress" "Docs" "design security data" "merge boundary beats a full flag set — a merged story is never rebuilt"

# --- the boundary is NARROW: Done landings stay guarded (ABS-136 Befund 6) -----
assert_true  forward_skip_illegitimate "In Test" "Done"      "regression: In Test -> Done STILL flagged (Befund 6 intact — Docs is the only exemption)"
assert_true  forward_skip_illegitimate "Merging" "Done"      "regression: Merging -> Done STILL flagged (skips the Docs seat)"

# --- end-to-end: the exact ABS-234 replay is a silent no-op --------------------
MODE="live"
STUB_IN=0
STUB_DUMP="$(printf 'status: Docs\n\n### t | kind: transition-reason | actor: rte\n\nTransition: In Progress -> Docs. Reason: PR #184 merged (ef7d01f), releasing to Docs\n')"
res="$(run_guard "ABS-234" "Docs")"; rc="${res%%$'\n'*}"; out="${res#*$'\n'}"
assert_eq "$rc" "1" "AC1: merged story released to Docs -> guard no-ops (rc 1), story STAYS at Docs"
assert_not_contains "$out" "INTENT STATION-GUARD" "no guard intent on the post-merge Docs landing"
assert_eq "$(cat "$STUB_CALLS")" "" "AC1: NO adapter writes — the merged story is not transitioned backward"

# =============================================================================
echo -e "\n${CYAN}Idempotency + guards on the landing it actually observes${NC}"
# =============================================================================
# After the guard's own redirect the last transition is BACKWARD -> never re-fires.
STUB_IN=0
STUB_DUMP="$(printf 'status: Story Acceptance\n\nTransition: In Test -> Done. Reason: tests green\n\nTransition: Done -> Story Acceptance. Reason: STATION-GUARD redirect\n')"
res="$(run_guard "ABS-996" "Story Acceptance")"; rc="${res%%$'\n'*}"
assert_eq "${res%%$'\n'*}" "1" "after redirect (last hop Done -> Story Acceptance is backward) -> no re-fire"

# `to` no longer matches the last observed landing (ticket moved on): no-op.
STUB_IN=0
STUB_DUMP="$(printf 'status: In Test\n\nTransition: In Review -> In Test. Reason: passed\n')"
res="$(run_guard "ABS-995" "Done")"; rc="${res%%$'\n'*}"
assert_eq "${res%%$'\n'*}" "1" "last transition landed elsewhere than <to> -> no-op"

# ticket no longer rests in `to` (moved since the event) -> no-op, no stale write.
STUB_IN=1
STUB_DUMP="$(printf 'status: Story Acceptance\n\nTransition: In Test -> Done. Reason: tests green\n')"
res="$(run_guard "ABS-994" "Done")"; rc="${res%%$'\n'*}"
assert_eq "${res%%$'\n'*}" "1" "ticket_still_in false (already moved on) -> no-op"

# --- cleanup temp files -------------------------------------------------------
rm -f "$STUB_CALLS" "$ORCH_RUN_LOG" 2>/dev/null || true

# =============================================================================
echo -e "\n${CYAN}ABS-165 extract_usage_note — cache-token fields surfaced${NC}"
# =============================================================================
# A cache-heavy CLI result JSON: the real input volume is in the cache_* fields
# (input_tokens is tiny — the ABS-165 bug read tokens_in=2 and dropped the rest).
usage_json='{"type":"result","total_cost_usd":0.7123,"usage":{"input_tokens":2,"cache_creation_input_tokens":18000,"cache_read_input_tokens":250000,"output_tokens":1234}}'
note="$(extract_usage_note "$usage_json")"
assert_eq "$note" "tokens_in=2 cache_read=250000 cache_create=18000 tokens_out=1234 cost_usd=0.7123" \
    "parser extracts all five fields (input never collides with cache_*_input_tokens)"
# Missing usage object -> every field degrades to empty, line still shaped.
assert_eq "$(extract_usage_note '{"result":"ok"}')" \
    "tokens_in= cache_read= cache_create= tokens_out= cost_usd=" \
    "missing usage degrades to empty fields (pipeline never breaks)"

# =============================================================================
echo -e "\n${CYAN}ABS-165 emit_run_usage_rollup — per-ticket/per-role summation${NC}"
# =============================================================================
ROLLUP_LOG="$(mktemp)"
ORCH_RUN_LOG="$ROLLUP_LOG"
# Two SPAWN-USAGE lines for one ticket/role + a crashed (empty) one -> 0.
printf '%s\tSPAWN-USAGE\tABS-1\tbe-developer\tIn Progress\ttokens_in=10 cache_read=100 cache_create=5 tokens_out=20 cost_usd=0.10\n' "$(timestamp)" >> "$ROLLUP_LOG"
printf '%s\tSPAWN-USAGE\tABS-1\tbe-developer\tIn Review\ttokens_in=30 cache_read=900 cache_create=15 tokens_out=80 cost_usd=0.40\n' "$(timestamp)" >> "$ROLLUP_LOG"
printf '%s\tSPAWN-USAGE\tABS-1\tbe-developer\tIn Review\ttokens_in= cache_read= cache_create= tokens_out= cost_usd=\n' "$(timestamp)" >> "$ROLLUP_LOG"
emit_run_usage_rollup
rollup_ticket="$(grep 'RUN-USAGE' "$ROLLUP_LOG" | grep 'ABS-1' | head -1)"
assert_contains "$rollup_ticket" "spawns=3 tokens_in=40 cache_read=1000 cache_create=20 tokens_out=100 cost_usd=0.5000" \
    "rollup sums three spawns per ticket (empty crash line counts as 0)"
rollup_role="$(grep 'RUN-USAGE' "$ROLLUP_LOG" | grep 'be-developer' | head -1)"
assert_contains "$rollup_role" "spawns=3 tokens_in=40 cache_read=1000 cache_create=20 tokens_out=100 cost_usd=0.5000" \
    "rollup sums per role"
# Re-running does not double-count (RUN-USAGE lines are ignored by the aggregation).
emit_run_usage_rollup
assert_contains "$(grep 'RUN-USAGE' "$ROLLUP_LOG" | grep 'ABS-1' | tail -1)" "spawns=3 tokens_in=40" \
    "re-emitting the rollup never double-counts (RUN-USAGE lines are transparent)"
rm -f "$ROLLUP_LOG" 2>/dev/null || true

# =============================================================================
echo -e "\n${CYAN}ABS-271 — the guard on the EPIC chain (pre-filled vs decomposed)${NC}"
# =============================================================================
# Both epic classes have children, so "has children" CANNOT tell them apart. The
# discriminator is Grooming: it is the station that CREATES children, so only a
# DECOMPOSED epic has ever visited it. Getting this wrong is not cosmetic — a
# clamp that fires on the decomposed class makes the guard forgive mandatory
# `Enrichment`, i.e. it weakens ABS-136/ABS-247 exactly where they must hold.
#
# These cases need `tracker child-count`, which the stub above does not answer;
# extend it here (the guard reads the count only for epics).
STUB_CHILDREN=2
tracker() {
    case "$1" in
        get)         printf '%s' "$STUB_DUMP" ;;
        child-count) printf '%s' "$STUB_CHILDREN" ;;
        comment)     shift; printf 'COMMENT %s\n' "$*" >> "$STUB_CALLS" ;;
        transition)  shift; printf 'TRANSITION %s\n' "$*" >> "$STUB_CALLS" ;;
        *)           : ;;
    esac
}
# An epic dump needs the `---` frontmatter fence: prefilled_epic_entry_index reads
# `type` via fm_field, which only parses BETWEEN the fences. An unfenced fixture
# silently reports type="", the clamp never arms, and the test passes vacuously.
epic_dump() {  # <status> <transition-history...>
    local status="$1"; shift
    printf -- '---\nid: E\ntype: epic\nstatus: %s\n---\n\n' "$status"
    printf '### t | kind: transition-reason | actor: x\n\n%s\n\n' "$@"
}
MODE="live"
STUB_IN=0

# AC1: the pre-filled epic's ABS-214 JOIN-rest park lands PAST the DoR gate.
STUB_DUMP="$(epic_dump "Stories In Flight" \
    "Transition: Backlog -> Stories In Flight. Reason: epic_join_rest_complete")"
res="$(run_guard "ABS-271-PRE" "Stories In Flight")"; rc="${res%%$'\n'*}"; out="${res#*$'\n'}"
assert_eq "$rc" "0" "AC1: pre-filled epic parked Backlog -> Stories In Flight is caught"
assert_contains "$out" "INTENT STATION-GUARD ticket=ABS-271-PRE role=- to=Ticket Review" \
    "AC1: redirected to the DoR gate it never ran (Backlog is index 0, so only the clamp can see this hop)"
assert_contains "$(cat "$STUB_CALLS")" "TRANSITION ABS-271-PRE Ticket Review" \
    "AC1: re-transitioned to Ticket Review, where the qas DoR batch review spawns"

# REGRESSION (guard logic): a DECOMPOSED epic (bsa created its children in
# Grooming) skips mandatory Enrichment. It must be redirected to ENRICHMENT — not
# to Ticket Review, which would forgive the skipped station. Absent this case, the
# clamp misfiring on the decomposed class ships green (it did).
#
# NOTE this exact hop is not adapter-reachable: statuses.yaml allows only
# Enrichment/Blocked/Needs PO Decision out of Grooming, so no seat can produce it.
# It is asserted at the guard's decision layer, where the clamp lives. The
# adapter-REACHABLE form of the same defect is the next case.
STUB_DUMP="$(epic_dump "Architecture Review" \
    "Transition: PO Triage -> Grooming. Reason: decompose" \
    "Transition: Grooming -> Architecture Review. Reason: stories drafted")"
res="$(run_guard "ABS-271-DEC" "Architecture Review")"; rc="${res%%$'\n'*}"; out="${res#*$'\n'}"
assert_eq "$rc" "0" "decomposed epic skipping Enrichment is caught"
assert_contains "$out" "INTENT STATION-GUARD ticket=ABS-271-DEC role=- to=Enrichment" \
    "decomposed epic is redirected to the skipped mandatory ENRICHMENT (not waved on to Ticket Review)"

# REGRESSION (adapter-reachable): a decomposed epic can legally be parked
# Grooming -> Needs PO Decision -> Backlog, and once its children are Done the
# ABS-214 JOIN-rest edge carries it Backlog -> Stories In Flight. Without the
# Grooming discriminator the clamp fires here too and the guard drags a decomposed
# epic — whose children are all DONE — backwards to a DoR gate it does not owe.
# It must stay silent: `Backlog` is index 0, the guard's normal exemption.
STUB_DUMP="$(epic_dump "Stories In Flight" \
    "Transition: PO Triage -> Grooming. Reason: decompose" \
    "Transition: Grooming -> Needs PO Decision. Reason: PO question" \
    "Transition: Needs PO Decision -> Backlog. Reason: deprioritized" \
    "Transition: Backlog -> Stories In Flight. Reason: epic_join_rest_complete")"
res="$(run_guard "ABS-271-PARK" "Stories In Flight")"
assert_eq "${res%%$'\n'*}" "1" \
    "decomposed epic JOIN-resting via Backlog is NOT clamped (not dragged to a gate it does not owe)"

# AC4: the legitimate Enrichment -> Ticket Review hop stays untouched.
STUB_DUMP="$(epic_dump "Ticket Review" \
    "Transition: Grooming -> Enrichment. Reason: drafted" \
    "Transition: Enrichment -> Ticket Review. Reason: enriched")"
res="$(run_guard "ABS-271-OK" "Ticket Review")"; rc="${res%%$'\n'*}"
assert_eq "${res%%$'\n'*}" "1" "AC4: the legal Enrichment -> Ticket Review hop is NOT touched"

# ABS-214 intact: an epic that ALREADY passed the gate re-enters Stories In Flight
# from Backlog to rest. It must not be dragged back to a gate it has run.
STUB_DUMP="$(epic_dump "Stories In Flight" \
    "Transition: Enrichment -> Ticket Review. Reason: gate passed" \
    "Transition: Backlog -> Stories In Flight. Reason: epic_join_rest_complete")"
res="$(run_guard "ABS-271-REST" "Stories In Flight")"
assert_eq "${res%%$'\n'*}" "1" "ABS-214: a gate-passed epic resting in Stories In Flight is NOT dragged back"

# The discriminator itself, stated as a unit fact.
assert_true  epic_visited_grooming "$(printf 'Transition: PO Triage -> Grooming. Reason: x\n')" \
    "epic_visited_grooming: true for an epic transitioned INTO Grooming (decomposed)"
assert_false epic_visited_grooming "$(printf 'Transition: Backlog -> Stories In Flight. Reason: x\n')" \
    "epic_visited_grooming: false for an epic that never visited Grooming (pre-filled)"
assert_false epic_visited_grooming "$(printf 'prose that merely mentions Grooming in passing\n')" \
    "epic_visited_grooming: prose naming Grooming does not arm it (anchored to the Transition: line)"

# =============================================================================
echo -e "\n${CYAN}=== Test Results ===${NC}\n"
echo -e "  Total:  $TOTAL"
echo -e "  ${GREEN}Passed: $PASS${NC}"
if [ "$FAIL" -gt 0 ]; then
    echo -e "  ${RED}Failed: $FAIL${NC}"; exit 1
else
    echo -e "  Failed: 0"; echo -e "\n  ${GREEN}ALL TESTS PASSED${NC}\n"; exit 0
fi
