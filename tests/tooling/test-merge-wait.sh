#!/bin/bash
# =============================================================================
# Test: merge-wait rest — "story correct, PR open, waiting on a human" (ABS-270)
# =============================================================================
# The ABS-211 done-gate refuses a Done whose PR is unmerged. The state that gate
# NECESSARILY produces — pipeline green, PR open, merge owed by a human — had no
# resting place: the story sat in `Docs`, a SPAWN-triggering station. The
# tech-writer correctly refused Done and rested; the runner read the no-move
# respawns as an ABS-132 stuck loop and escalated to `Needs PO Decision` — routing
# a human merge wait to the PO, who has no merge authority (ADR-A-0005). Measured
# on ABS-253 (PR #173): 2 tech-writer spawns + 1 po-agent spawn burnt to discover
# that nobody had clicked merge.
#
# docs_pr_gate rests such a story at `Ready for Merge` (the human-owned merge gate
# that already exists) and spawns NOBODY; merge_wait_release returns it to `Docs`
# once the PR is merged, so it reaches Done with no manual step.
#
# Same test shape as tests/test-done-gate.sh (its sibling gate): SOURCE the runner
# (main is source-guarded) and exercise the functions directly with a stubbed
# `forge`, `tracker` and `ticket_still_in` — no real adapter, forge, or model. The
# statuses.yaml edges are additionally driven through the REAL mock tracker, since
# a park the adapter rejects would be a no-op in production.
#
# bash 3.2 + BSD tools only. Run from repo root: bash tests/tooling/test-merge-wait.sh
# =============================================================================

set -euo pipefail
# PILOT-46: strip inherited backend/tracker env before any fixture runs (tests/sandbox-guard.sh).
# shellcheck source=tests/sandbox-guard.sh
. "$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)/sandbox-guard.sh"

# ABS-285: scrub ambient ORCH_* before driving the runner — a seat exports ~37 of
# them and a leaked value would make the result a function of the calling seat.
unset "${!ORCH_@}"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"

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

echo -e "${CYAN}=== Merge-wait rest: PR open, waiting on a human (ABS-270) ===${NC}\n"

# --- stubs (as test-done-gate.sh): forge line + adapter call recorder ---------
STUB_PR_LINE=""
forge() { printf '%s\n' "$STUB_PR_LINE"; }

STUB_CALLS=""; STUB_IN=0; STUB_DUMP=""
tracker() {
    case "$1" in
        get)        printf '%s\n' "$STUB_DUMP" ;;
        comment)    shift; printf 'COMMENT %s\n' "$*" >> "$STUB_CALLS" ;;
        transition) shift; printf 'TRANSITION %s\n' "$*" >> "$STUB_CALLS" ;;
        *)          : ;;
    esac
}
ticket_still_in() { return "$STUB_IN"; }
# PILOT-4: with no $FORGE_CMD the gates fall back to the forge-less git-ancestry
# probe. Stub it to NONE here so the placeholder (no-forge) assertions stay
# hermetic — the real git-ancestry path is exercised end-to-end against a live
# sandbox repo in tests/test-docs-merge-wait-pilot.sh.
story_git_merge_state() { printf 'NONE\t'; }

STUB_CALLS="$(mktemp /tmp/mw-calls-XXXXXX)"
ORCH_RUN_LOG="$(mktemp /tmp/mw-runlog-XXXXXX)"

# run_gate <fn> <arg1> <arg2> — run a gate, capturing rc + stdout(intent).
run_gate() {
    : > "$STUB_CALLS"; : > "$ORCH_RUN_LOG"
    local rc=0 out fn="$1"
    out="$("$fn" "$2" "$3" 2>/dev/null)" || rc=$?
    printf '%s\n%s' "$rc" "$out"
}

# The dump of a story the gate parked (last transition into the gate is from Docs).
PARKED_DUMP="$(cat <<'EOF'
### 2026-07-13T10:00:00Z | kind: transition-reason | actor: rte
Transition: Merging -> Docs. Reason: PR opened
### 2026-07-13T11:00:00Z | kind: transition-reason | actor: orchestrator
Transition: Docs -> Ready for Merge. Reason: MERGE-WAIT: implementation PR #173 not merged (OPEN) — waiting on human merge (ABS-270)
EOF
)"

# =============================================================================
echo -e "${CYAN}AC1/AC2/AC6 — Docs landing with an OPEN PR: parked, audited, NOBODY spawned${NC}"
# =============================================================================
MODE="live"; FORGE_CMD="stub"; STUB_IN=0; STUB_PR_LINE="OPEN #173"
res="$(run_gate docs_pr_gate "ABS-253" "Docs")"; rc="${res%%$'\n'*}"; out="${res#*$'\n'}"
assert_eq "$rc" "0" "gate INTERVENES (rc 0) on a Docs landing whose PR is still open"
assert_contains "$out" "INTENT MERGE-WAIT ticket=ABS-253 role=- to=Ready for Merge" "AC2: intent is a PARK to 'Ready for Merge' — no SPAWN of the tech-writer"
assert_not_contains "$out" "SPAWN" "AC2: no spawn intent is emitted for the parked story"
calls="$(cat "$STUB_CALLS")"
assert_contains "$calls" "TRANSITION ABS-253 Ready for Merge" "rests the story at the human-owned merge gate"
assert_contains "$calls" "COMMENT ABS-253 --kind gate-results --actor orchestrator" "posts a naming gate-results comment as the orchestrator"
assert_contains "$calls" "#173" "the audit comment NAMES the PR that is not merged (#173)"
assert_contains "$calls" "waiting on human merge" "AC6: the transition REASON names the wait as a human merge, not a stall"
assert_contains "$calls" "--kind notification" "AC6/option-3-half: notifies the human who owes the merge"
assert_not_contains "$calls" "Needs PO Decision" "AC1: never routes a human merge wait to the PO (no merge authority, ADR-A-0005)"
assert_contains "$(cat "$ORCH_RUN_LOG")" "INTENT-MERGE-WAIT	ABS-253" "writes an INTENT-MERGE-WAIT run.log event"

# =============================================================================
echo -e "\n${CYAN}AC1 — the parked story rests: no re-derive, no respawn, no stuck flag${NC}"
# =============================================================================
# The escalation this ticket kills is ABS-132 (consecutive NO-MOVE RESPAWNS at a
# station). Resting at `Ready for Merge` cannot feed that counter, because the
# runner never spawns there and reconcile never re-derives it — the three
# predicates that decide this are asserted directly, since they ARE the mechanism.
assert_eq "$(map_action 'Ready for Merge')" "NOOP -" "AC2: 'Ready for Merge' maps to NOOP — no seat is spawned there, ever"
if is_reconcilable_status "Ready for Merge"; then rr="reconcilable"; else rr="rests"; fi
assert_eq "$rr" "rests" "AC1: 'Ready for Merge' is NOT reconcilable — no sweep re-derive, so no no-move respawn to count"
if is_legit_rest_status "Ready for Merge"; then lr="legit-rest"; else lr="stuck-candidate"; fi
assert_eq "$lr" "legit-rest" "AC1: the stuck detector treats the merge gate as a legitimate rest (no false STUCK)"

# ≥2 sweeps over the parked story with the PR still open: still no move, no escalation.
MODE="live"; FORGE_CMD="stub"; STUB_PR_LINE="OPEN #173"; STUB_DUMP="$PARKED_DUMP"
for sweep in 1 2 3; do
    res="$(run_gate merge_wait_release "ABS-253" "Ready for Merge")"
    assert_eq "${res%%$'\n'*}" "1" "sweep $sweep: PR still open -> release is a no-op (the story keeps resting)"
done
assert_eq "$(cat "$STUB_CALLS")" "" "AC1/AC2: over 3 sweeps with an open PR: zero transitions, zero spawns, zero PO escalations"

# =============================================================================
echo -e "\n${CYAN}AC4 — the merge lands: the story resumes to Done with NO manual step${NC}"
# =============================================================================
MODE="live"; FORGE_CMD="stub"; STUB_PR_LINE="MERGED #173"; STUB_DUMP="$PARKED_DUMP"
res="$(run_gate merge_wait_release "ABS-253" "Ready for Merge")"; rc="${res%%$'\n'*}"; out="${res#*$'\n'}"
assert_eq "$rc" "0" "merged PR -> the sweep RELEASES the parked story (rc 0)"
assert_contains "$out" "INTENT MERGE-WAIT-RELEASE ticket=ABS-253 role=- to=Docs" "releases the story back to the Docs seat"
calls="$(cat "$STUB_CALLS")"
assert_contains "$calls" "TRANSITION ABS-253 Docs" "AC4: transitions Ready for Merge -> Docs (tech-writer then takes it to Done)"
assert_contains "$calls" "--expect-from Ready for Merge" "compare-and-set: a lost race with a human is a NOOP, not an overwrite (ABS-198)"

# And the Docs landing it produces now PASSES the gate (the PR is merged), so the
# tech-writer really is spawned — the release cannot bounce back into the park.
STUB_IN=0
res="$(run_gate docs_pr_gate "ABS-253" "Docs")"
assert_eq "${res%%$'\n'*}" "1" "AC4: the re-entered Docs landing passes the gate (PR merged) -> tech-writer spawns as normal"
assert_eq "$(cat "$STUB_CALLS")" "" "AC4: no writes on the passing Docs landing (no park/release ping-pong)"

# =============================================================================
echo -e "\n${CYAN}AC3 — the Done gate is INTACT: an unmerged PR still cannot reach Done${NC}"
# =============================================================================
# ABS-192 regression: a Done with an open PR poisons the epic JOIN. The merge-wait
# park must not weaken that backstop — done_pr_gate still bounces such a Done.
MODE="live"; FORGE_CMD="stub"; STUB_IN=0; STUB_PR_LINE="OPEN #133"
res="$(run_gate done_pr_gate "ABS-192" "Done")"; rc="${res%%$'\n'*}"
assert_eq "$rc" "0" "AC3: Done with an unmerged PR is STILL refused (done_pr_gate untouched)"
assert_contains "$(cat "$STUB_CALLS")" "TRANSITION ABS-192 Merging" "AC3: still redirected to Merging — the epic JOIN cannot fire on a false signal"

# =============================================================================
echo -e "\n${CYAN}PILOT-20 — a DECLINED story PR gets a distinct human escalation (once)${NC}"
# =============================================================================
# ABS-270 covers the OPEN (rest) and MERGED (auto-resume) branches. The terminal
# DECLINED / closed-without-merge branch it did NOT cover: merge_wait_release fires
# only on MERGED and ready_for_merge_mr_gate only when NO MR exists, so a declined
# PR rests at `Ready for Merge` forever. merge_wait_declined_gate emits ONE human
# notification naming the declined PR.

# AC1 — DECLINED -> a distinct escalation fires exactly once (kind: notification).
MODE="live"; FORGE_CMD="stub"; STUB_PR_LINE="DECLINED #173"; STUB_DUMP=""
res="$(run_gate merge_wait_declined_gate "ABS-253" "Ready for Merge")"; rc="${res%%$'\n'*}"; out="${res#*$'\n'}"
assert_eq "$rc" "0" "AC1: a declined PR at the merge gate ESCALATES (rc 0)"
assert_contains "$out" "INTENT MERGE-WAIT-DECLINED ticket=ABS-253 role=- to=Ready for Merge" "AC1: intent is a distinct DECLINED escalation, not a release/self-heal"
calls="$(cat "$STUB_CALLS")"
assert_contains "$calls" "COMMENT ABS-253 --kind notification --actor orchestrator" "AC1: emits a kind: notification comment to the human"
assert_contains "$calls" "#173" "AC1: the notification NAMES the declined PR ref (#173)"
assert_contains "$calls" "DECLINED" "AC1: the notification identifies the PR as DECLINED / closed-without-merge"
assert_not_contains "$calls" "TRANSITION" "AC1 (option-a default): the story keeps resting at the human-owned gate — no transition"

# AC2 — OPEN -> no escalation, the story keeps resting (ABS-270 preserved).
MODE="live"; FORGE_CMD="stub"; STUB_PR_LINE="OPEN #173"; STUB_DUMP=""
res="$(run_gate merge_wait_declined_gate "ABS-253" "Ready for Merge")"; rc="${res%%$'\n'*}"; out="${res#*$'\n'}"
assert_eq "$rc" "1" "AC2: an OPEN (still-awaiting) PR is NOT escalated (rc 1)"
assert_not_contains "$out" "INTENT" "AC2: no escalation intent for an open PR"
assert_eq "$(cat "$STUB_CALLS")" "" "AC2: no adapter writes — the story keeps resting (ABS-270 behavior preserved)"

# AC3 — MERGED is owned by merge_wait_release, so the declined gate no-ops on it.
MODE="live"; FORGE_CMD="stub"; STUB_PR_LINE="MERGED #173"; STUB_DUMP=""
res="$(run_gate merge_wait_declined_gate "ABS-253" "Ready for Merge")"
assert_eq "${res%%$'\n'*}" "1" "AC3: a MERGED PR is not escalated by this gate (merge_wait_release releases it)"
assert_eq "$(cat "$STUB_CALLS")" "" "AC3: no writes on a merged PR"

# AC4 — idempotent: a second sweep over an already-escalated declined story is a no-op.
MODE="live"; FORGE_CMD="stub"; STUB_PR_LINE="DECLINED #173"
STUB_DUMP="$(printf '%s\n' '### 2026-07-24T10:00:00Z | kind: notification | actor: orchestrator' 'MERGE-WAIT DECLINED: the implementation PR #173 for this story was DECLINED')"
res="$(run_gate merge_wait_declined_gate "ABS-253" "Ready for Merge")"
assert_eq "${res%%$'\n'*}" "1" "AC4: a second sweep over an already-escalated declined story is a no-op (rc 1)"
assert_eq "$(cat "$STUB_CALLS")" "" "AC4: no duplicate notification is emitted on re-invocation"

# Scoping: out-of-gate status and placeholder (no forge) never escalate.
MODE="live"; FORGE_CMD="stub"; STUB_PR_LINE="DECLINED #173"; STUB_DUMP=""
res="$(run_gate merge_wait_declined_gate "ABS-253" "In Test")"
assert_eq "${res%%$'\n'*}" "1" "a declined PR on a ticket NOT at the merge gate is never escalated"
FORGE_CMD=""
res="$(run_gate merge_wait_declined_gate "ABS-253" "Ready for Merge")"
assert_eq "${res%%$'\n'*}" "1" "no \$FORGE_CMD (placeholder) -> no DECLINED signal, no escalation"
assert_eq "$(cat "$STUB_CALLS")" "" "placeholder case makes no adapter writes"
FORGE_CMD="stub"

# Dry-run reports the escalation intent but performs NO adapter writes.
MODE="dry-run"; FORGE_CMD="stub"; STUB_PR_LINE="DECLINED #173"; STUB_DUMP=""
res="$(run_gate merge_wait_declined_gate "ABS-253" "Ready for Merge")"; rc="${res%%$'\n'*}"; out="${res#*$'\n'}"
assert_eq "$rc" "0" "dry-run still reports the declined-escalation intent (rc 0)"
assert_contains "$out" "INTENT MERGE-WAIT-DECLINED ticket=ABS-253" "dry-run logs the escalation intent"
assert_eq "$(cat "$STUB_CALLS")" "" "dry-run makes NO tracker comment calls"
MODE="live"; STUB_DUMP=""

# =============================================================================
echo -e "\n${CYAN}Scoping — the gate only touches the state it owns${NC}"
# =============================================================================
MODE="live"; FORGE_CMD="stub"; STUB_IN=0
STUB_PR_LINE="MERGED #173"
res="$(run_gate docs_pr_gate "ABS-1" "Docs")"; assert_eq "${res%%$'\n'*}" "1" "merged PR -> no park (the normal Docs path is unchanged)"
STUB_PR_LINE="NONE"
res="$(run_gate docs_pr_gate "ABS-2" "Docs")"; assert_eq "${res%%$'\n'*}" "1" "no PR (direct-to-branch) -> fail-OPEN, Docs proceeds"
STUB_PR_LINE="OPEN #9"
FORGE_CMD=""
res="$(run_gate docs_pr_gate "ABS-3" "Docs")"; assert_eq "${res%%$'\n'*}" "1" "no \$FORGE_CMD (boilerplate placeholder) -> fail-OPEN, Docs proceeds"
assert_eq "$(cat "$STUB_CALLS")" "" "placeholder case makes no adapter writes"
FORGE_CMD="stub"; STUB_PR_LINE="OPEN #9"
res="$(run_gate docs_pr_gate "ABS-4" "In Test")"; assert_eq "${res%%$'\n'*}" "1" "to != Docs -> no-op (only the Docs landing is guarded)"
STUB_IN=1
res="$(run_gate docs_pr_gate "ABS-5" "Docs")"; assert_eq "${res%%$'\n'*}" "1" "ticket already moved on -> no-op, no stale write"
assert_eq "$(cat "$STUB_CALLS")" "" "no writes once the ticket has left Docs"
STUB_IN=0

# ABS-537 arming invariant: entry into `Ready for Merge` arms the wait posture
# no matter over which path (v3-pilot #3 retro finding #7: the MERGE-TOKEN-RELEASE
# path never armed the old Docs/Merging origin filter). A MERGED probe releases
# EVERY resting ticket at the gate: docs_pr_gate park (above), Merging-origin
# rest (PILOT-2 stall), Path-A RfHA origin, and dumps with no transition trail.
STUB_PR_LINE="MERGED #173"
STUB_DUMP="$(printf '%s\n' 'Transition: Merging -> Ready for Merge. Reason: ABS-133 human-gate rest')"
res="$(run_gate merge_wait_release "ABS-6" "Ready for Merge")"; rc="${res%%$'\n'*}"; out="${res#*$'\n'}"
assert_eq "$rc" "0" "PILOT-4: Merging-origin rest with a MERGED PR IS released -> Docs (posture 2, PILOT-2 stall)"
assert_contains "$out" "INTENT MERGE-WAIT-RELEASE ticket=ABS-6 role=- to=Docs" "posture 2: advances the Merging-origin rest to the Docs seat"
assert_contains "$(cat "$STUB_CALLS")" "TRANSITION ABS-6 Docs" "posture 2: transitions Ready for Merge -> Docs (no operator step)"
STUB_DUMP="$(printf '%s\n' 'Transition: Ready for Human Acceptance -> Ready for Merge. Reason: PO accepted')"
res="$(run_gate merge_wait_release "ABS-7" "Ready for Merge")"
assert_eq "${res%%$'\n'*}" "0" "ABS-537: Path-A (RfHA origin) with a MERGED PR IS released — RfM entry arms the posture on every path"
STUB_DUMP=""
res="$(run_gate merge_wait_release "ABS-7b" "Ready for Merge")"
assert_eq "${res%%$'\n'*}" "0" "ABS-537: a dump with NO transition trail (seeded/foreign entry) is still released when MERGED"
STUB_DUMP="$PARKED_DUMP"
res="$(run_gate merge_wait_release "ABS-8" "In Test")"
assert_eq "${res%%$'\n'*}" "1" "a ticket that is not at the merge gate is never touched by the sweep hook"
assert_eq "$(cat "$STUB_CALLS")" "" "no adapter writes in any of the out-of-scope cases"

# =============================================================================
echo -e "\n${CYAN}Dry-run logs the intent but performs NO adapter writes${NC}"
# =============================================================================
MODE="dry-run"; FORGE_CMD="stub"; STUB_IN=0; STUB_PR_LINE="OPEN #173"
res="$(run_gate docs_pr_gate "ABS-9" "Docs")"; rc="${res%%$'\n'*}"; out="${res#*$'\n'}"
assert_eq "$rc" "0" "dry-run still reports the park intent (rc 0)"
assert_contains "$out" "INTENT MERGE-WAIT ticket=ABS-9 role=- to=Ready for Merge" "dry-run logs the park intent"
assert_eq "$(cat "$STUB_CALLS")" "" "dry-run makes NO tracker comment/transition calls"
STUB_PR_LINE="MERGED #173"; STUB_DUMP="$PARKED_DUMP"
res="$(run_gate merge_wait_release "ABS-9" "Ready for Merge")"
assert_eq "${res%%$'\n'*}" "0" "dry-run still reports the release intent (rc 0)"
assert_eq "$(cat "$STUB_CALLS")" "" "dry-run makes NO writes on the release either"
MODE="live"

# =============================================================================
echo -e "\n${CYAN}ABS-267 — the merge-wait park burns no rework unit${NC}"
# =============================================================================
# The park is applied as --actor orchestrator (runner bookkeeping, not a seat
# rejecting the work), so rework_count must ignore it — otherwise a story waiting
# on a human merge would spend a third of its rework budget on doing so.
mw_dump="$(cat <<'EOF'
### 2026-07-13T10:00:00Z | kind: transition-reason | actor: qas
Transition: In Test -> In Progress. Reason: rework: test fail
### 2026-07-13T11:00:00Z | kind: transition-reason | actor: orchestrator
Transition: Docs -> Ready for Merge. Reason: MERGE-WAIT: implementation PR #173 not merged (OPEN) — waiting on human merge (ABS-270)
EOF
)"
assert_eq "$(rework_count "$mw_dump")" "1" "the park burns NO rework unit; the genuine qas bounce still counts"

# =============================================================================
echo -e "\n${CYAN}Status machine — the park and release edges are LEGAL in the real adapter${NC}"
# =============================================================================
# A transition the adapter rejects would make the gate a silent no-op in
# production, so both edges are driven through the REAL mock tracker (which
# validates against profiles/neutral/adapters/statuses.yaml) on a temp ticket.
unset -f tracker forge   # from here on: the real adapter, no stubs
MW_DIR="$(mktemp -d /tmp/mw-tickets-XXXXXX)"
cat > "$MW_DIR/ABS-270-fixture.md" <<'EOF'
---
id: ABS-270-fixture
type: ticket
title: merge-wait edge fixture
status: Docs
parent: ABS-278
role: tech-writer
labels: []
depends_on: []
links: []
---

# merge-wait edge fixture
EOF
MT() { MOCK_TRACKER_TICKETS_DIR="$MW_DIR" bash "$REPO_ROOT/scripts/mock-tracker.sh" "$@"; }
mw_reason="$(mktemp /tmp/mw-reason-XXXXXX)"; printf '%s\n' "merge-wait edge test" > "$mw_reason"

rc=0; MT transition ABS-270-fixture "Ready for Merge" --actor orchestrator --reason-file "$mw_reason" >/dev/null 2>&1 || rc=$?
assert_eq "$rc" "0" "statuses.yaml: the park edge Docs -> Ready for Merge is accepted by the adapter"
assert_eq "$(MT get ABS-270-fixture | awk -F': ' '/^status: /{print $2; exit}')" "Ready for Merge" "the parked story really rests at the human-owned merge gate"

rc=0; MT transition ABS-270-fixture "Docs" --actor orchestrator --reason-file "$mw_reason" --expect-from "Ready for Merge" >/dev/null 2>&1 || rc=$?
assert_eq "$rc" "0" "statuses.yaml: the release edge Ready for Merge -> Docs is accepted by the adapter"
assert_eq "$(MT get ABS-270-fixture | awk -F': ' '/^status: /{print $2; exit}')" "Docs" "AC4: the released story is back at the Docs seat"

# ABS-537: the old parked_at_merge_gate origin-marker parse is gone — the release
# arms on ANY entry into `Ready for Merge` (the probe, not the arrival path, is
# the gate), so no dump-marker readability assertion remains here.
MT transition ABS-270-fixture "Ready for Merge" --actor orchestrator --reason-file "$mw_reason" >/dev/null 2>&1 || true

# AC3, at the ADAPTER level. done_pr_gate has redirected an unmerged-PR Done back
# to `Merging` since ABS-211 — but statuses.yaml had no Done -> Merging edge, so the
# adapter REJECTED that redirect: the gate posted its comment and the story stayed
# in Done, leaving the epic JOIN free to fire on the false signal (the very ABS-192 /
# ABS-202 defect the gate exists to stop). Found by driving the gate end-to-end for
# ABS-270; the edge is now in statuses.yaml and pinned here, because a gate whose
# transition the adapter rejects is a gate that only LOOKS closed.
MT transition ABS-270-fixture "Done" --actor human --reason-file "$mw_reason" >/dev/null 2>&1 || true
rc=0; MT transition ABS-270-fixture "Merging" --actor orchestrator --reason-file "$mw_reason" >/dev/null 2>&1 || rc=$?
assert_eq "$rc" "0" "AC3: statuses.yaml has the ABS-211 done-gate edge Done -> Merging (the redirect the adapter used to reject)"
assert_eq "$(MT get ABS-270-fixture | awk -F': ' '/^status: /{print $2; exit}')" "Merging" "AC3: an unmerged-PR Done really lands back in Merging — it does NOT stay in Done"

rm -rf "$MW_DIR" "$mw_reason" 2>/dev/null || true
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
