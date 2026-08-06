#!/bin/bash
# =============================================================================
# Test: Run-Status Collector (PILOT-41 / epic PILOT-39, twin ABS-550)
# =============================================================================
# Exercises scripts/run-status-collector.sh — the mechanical, read-only status
# collector behind the `run-status` skill. Covers the story's acceptance
# criteria and the plan's falsifying evals #7/#8:
#   - every facet header is ALWAYS emitted (silence never reads as "all OK")
#   - every waiting human gate is named (board status + open MR into main)
#   - a healthy board still prints humangate.count: 0 (positive "none")
#   - unavailable sources print "unavailable", never nothing / "none"
#   - two runs over changed boards produce a real, minimal progress diff
# Auto-discovered by the CI / pre-release tests/test-*.sh loops.
#
# Run from repo root: bash tests/test-run-status-collector.sh
# =============================================================================

set -u
# PILOT-46: strip inherited backend/tracker env before any fixture runs (tests/sandbox-guard.sh).
# shellcheck source=tests/sandbox-guard.sh
. "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/sandbox-guard.sh"

# ABS-285 / operator guardrail: scrub inherited backend/orchestrator env so the
# collector cannot reach a live backend and the result is a function of the
# fixture alone.
unset "${!BACKEND_@}" 2>/dev/null || true
unset "${!ORCH_@}" 2>/dev/null || true
unset TRACKER_CMD TRACKER_PROJECT ORCH_INSTANCE_ID RUN_STATUS_MR_CMD \
      RUN_STATUS_SENSOR_CMD \
      RUN_STATUS_HUMAN_GATE_STATUSES RUN_STATUS_PROTECTED_BRANCHES 2>/dev/null || true

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
COLLECTOR="$REPO_ROOT/scripts/run-status-collector.sh"
TRACKER="$REPO_ROOT/scripts/mock-tracker.sh"

PASS=0; FAIL=0; TOTAL=0
GREEN='\033[0;32m'; RED='\033[0;31m'; CYAN='\033[0;36m'; NC='\033[0m'

assert_contains() {
    local output="$1" expected="$2" label="$3"; TOTAL=$((TOTAL + 1))
    if printf '%s' "$output" | grep -qF -- "$expected"; then
        echo -e "  ${GREEN}PASS${NC} $label"; PASS=$((PASS + 1))
    else
        echo -e "  ${RED}FAIL${NC} $label (missing: $expected)"; FAIL=$((FAIL + 1))
    fi
}
assert_not_contains() {
    local output="$1" needle="$2" label="$3"; TOTAL=$((TOTAL + 1))
    if printf '%s' "$output" | grep -qF -- "$needle"; then
        echo -e "  ${RED}FAIL${NC} $label (should NOT contain: $needle)"; FAIL=$((FAIL + 1))
    else
        echo -e "  ${GREEN}PASS${NC} $label"; PASS=$((PASS + 1))
    fi
}
assert_eq() {
    local actual="$1" expected="$2" label="$3"; TOTAL=$((TOTAL + 1))
    if [ "$actual" = "$expected" ]; then
        echo -e "  ${GREEN}PASS${NC} $label"; PASS=$((PASS + 1))
    else
        echo -e "  ${RED}FAIL${NC} $label (expected '$expected', got '$actual')"; FAIL=$((FAIL + 1))
    fi
}

FX="$(mktemp -d "${TMPDIR:-/tmp}/run-status-test-XXXXXX")"
trap 'rm -rf "$FX"' EXIT

mkticket() { # <id> <status> <title> <created-sec-digit>
    cat > "$FX/tickets/$1.md" <<EOF
---
id: $1
type: ticket
title: $3
status: $2
priority: normal
created: 2026-07-25T10:00:0${4}Z
---
body
EOF
}

# collector <extra-env...> — runs the collector against the fixture board+state.
collector() {
    env MOCK_TRACKER_TICKETS_DIR="$FX/tickets" \
        ORCH_STATE_DIR="$FX/state" \
        TRACKER_CMD="$TRACKER" \
        "$@" bash "$COLLECTOR"
}

echo -e "${CYAN}=== Run-Status Collector (PILOT-41) ===${NC}\n"

# --- Case 1: mixed board with two human gates (PO decision + MR into main) ----
echo -e "${CYAN}Case 1: board + MR human gates${NC}"
mkdir -p "$FX/tickets" "$FX/state/locks/PILOT-1" "$FX/state/sessions"
touch "$FX/state/sessions/PILOT-1.be-developer.In_Progress"
printf 'a\nb\nc\n' > "$FX/state/spawn-ledger-20260725"
mkticket PILOT-1 "In Progress" "impl a" 1
mkticket PILOT-2 "Done" "done b" 2
mkticket PILOT-3 "Needs PO Decision" "decide c" 3
mkticket PILOT-4 "Ready for Development" "ready d" 4
out1="$(collector RUN_STATUS_MR_CMD='printf "%s\n" "77 main" "9 feature-x"')"

assert_contains "$out1" "# run-status " "header present"
assert_contains "$out1" "board.In Progress: 1" "board counts by status"
assert_contains "$out1" "board.Needs PO Decision: 1" "multi-word status counted"
assert_contains "$out1" "board.total: 4" "board total"
assert_contains "$out1" "spawns.total: 3" "spawn count from ledger"
assert_contains "$out1" "inflight.PILOT-1: role=be-developer" "in-flight seat w/ role"
assert_contains "$out1" "inflight.count: 1" "in-flight count"
assert_contains "$out1" "mr.77: target=main gate=yes" "MR into main flagged as gate"
assert_contains "$out1" "mr.9: target=feature-x gate=no" "MR into feature branch not a gate"
assert_contains "$out1" "humangate.1: ticket PILOT-3" "PO-decision ticket named as gate"
assert_contains "$out1" "awaiting human merge into main" "MR-into-main named as gate"
assert_contains "$out1" "humangate.count: 2" "both human gates counted"
assert_contains "$out1" "next: handoff from PILOT-1" "next event derived from in-flight"
# Positive sensor path (PILOT-40): sibling ops-sweep-sensors.sh autodetected ->
# a count line, never "unavailable" (AC2, guards the PILOT-40 integration).
assert_contains "$out1" "sensors.count:" "present sensor script -> sensors count emitted"
assert_not_contains "$out1" "sensors.status: unavailable" "present sensor script -> not unavailable"

# --- Case 2: healthy board, NO gates -> count is 0, never silent --------------
echo -e "\n${CYAN}Case 2: healthy board, no gates (positive 'none')${NC}"
rm -f "$FX"/tickets/*.md; rm -rf "$FX/state/locks/PILOT-1"
mkticket PILOT-1 "In Progress" "impl a" 1
mkticket PILOT-2 "Done" "done b" 2
out2="$(collector RUN_STATUS_MR_CMD='printf "%s\n" "9 feature-x"')"
assert_contains "$out2" "humangate.count: 0" "zero gates stated positively"
assert_contains "$out2" "run.health: ok" "run health ok"

# --- Case 3: unavailable sources are labelled, never silent -------------------
echo -e "\n${CYAN}Case 3: unavailable sources labelled (not silent, not 'none')${NC}"
# RUN_STATUS_SENSOR_CMD points at a path that does not exist, so the "sensors
# absent" branch is reachable even though PILOT-40 ships the real script beside
# the collector (epic PILOT-39 integration fix).
out3="$(MOCK_TRACKER_TICKETS_DIR="$FX/tickets" TRACKER_CMD="$TRACKER" \
        RUN_STATUS_SENSOR_CMD="$FX/no-such-sensor.sh" bash "$COLLECTOR")"
assert_contains "$out3" "spawns.status: unavailable" "no state dir -> spawns unavailable"
assert_contains "$out3" "mr.status: unavailable" "no MR cmd -> MRs unavailable"
assert_contains "$out3" "sensors.status: unavailable" "missing sensor path -> sensors unavailable"
assert_contains "$out3" "run.health: unavailable" "no state dir -> health unavailable (not silent)"

# --- Case 4: run-health markers are read by CONTENT, not existence (PILOT-74) --
# The collector must inspect a marker's VALUE: fastfail is a burst counter the
# orchestrator resets to "0" in place while it keeps spawning, so a "0"/empty
# marker is NOT a human gate — only a real value is.
echo -e "\n${CYAN}Case 4: run-health markers read by content, not existence (PILOT-74)${NC}"
for m in fastfail halt outage; do
    # 4a: content "0" -> NOT a pause, NOT a gate (the misfire this ticket fixes).
    printf '0\n' > "$FX/state/$m"
    o0="$(collector)"
    assert_contains "$o0" "run.health: ok" "$m marker content '0' -> health ok"
    assert_not_contains "$o0" "run — paused" "$m marker content '0' -> no human gate"

    # 4b: empty marker (e.g. mid-write) -> NOT a pause either.
    : > "$FX/state/$m"
    oe="$(collector)"
    assert_contains "$oe" "run.health: ok" "$m empty marker -> health ok"

    # 4c: a REAL value -> paused AND raised as a human gate.
    printf '3\n' > "$FX/state/$m"
    or="$(collector)"
    assert_contains "$or" "run.health: paused" "$m marker with real value -> paused"
    assert_contains "$or" "run — paused ($m marker=3" "$m real value -> human gate names marker+value"
    rm -f "$FX/state/$m"
done

# --- Case 4d: honesty preserved (AC3) — unknown state stays explicit ----------
# Removing the state dir must still yield an explicit "unavailable", never a
# silent OK and never an invented alarm.
o_unknown="$(MOCK_TRACKER_TICKETS_DIR="$FX/tickets" TRACKER_CMD="$TRACKER" bash "$COLLECTOR")"
assert_contains "$o_unknown" "run.health: unavailable" "no state dir -> health unavailable (honesty, not silent/invented)"
assert_not_contains "$o_unknown" "run — paused" "no state dir -> no invented pause alarm"

# --- Case 5: real progress diff between two runs ------------------------------
echo -e "\n${CYAN}Case 5: two runs -> real progress diff${NC}"
rm -f "$FX"/tickets/*.md
mkticket PILOT-1 "In Progress" "impl a" 1
mkticket PILOT-2 "In Progress" "impl b" 2
a="$(collector RUN_STATUS_MR_CMD='true' | grep '^board\.')"
# advance: PILOT-1 finished
mkticket PILOT-1 "Done" "impl a" 1
b="$(collector RUN_STATUS_MR_CMD='true' | grep '^board\.')"
d="$(diff <(printf '%s\n' "$a") <(printf '%s\n' "$b") || true)"
assert_contains "$d" "board.Done: 1" "diff shows the newly-done ticket"
[ -n "$d" ] && dne=1 || dne=0
assert_eq "$dne" "1" "diff is non-empty on real progress"
# no spurious churn: an unchanged board diffs to empty
c="$(collector RUN_STATUS_MR_CMD='true' | grep '^board\.')"
same="$(diff <(printf '%s\n' "$b") <(printf '%s\n' "$c") || true)"
assert_eq "${same:-EMPTY}" "EMPTY" "identical board -> empty diff (no ordering noise)"

# --- summary -----------------------------------------------------------------
echo ""
echo -e "${CYAN}=== $PASS/$TOTAL passed ===${NC}"
[ "$FAIL" -eq 0 ] || { echo -e "${RED}$FAIL FAILED${NC}"; exit 1; }
echo -e "${GREEN}ALL PASS${NC}"
