#!/bin/bash
# =============================================================================
# Test: ADR Enforcement-Status Drift Detector — reverse direction
# (scripts/adr-enforced-status-drift.sh) [PILOT-52 / ABS-561]
# =============================================================================
# Verifies the reverse-direction sensor: an ADR whose mechanic is enforced by
# code/sensors (an enforced/derived ledger row names it) but whose file is still
# `status: proposed`.
#   - FALSIFICATION (AC5): fixture ADR proposed + ledger kind:enforced => rot   (exit 1, DRIFT)
#   - derived kind also triggers                                                (exit 1)
#   - accepted ADR + enforced ledger row                              => clean  (exit 0)
#   - proposed ADR named only by an unenforced/informative row        => clean  (exit 0)
#   - proposed ADR not named by any ledger row                        => clean  (exit 0)
#   - --flip-list emits an operator line for the drifting ADR         (exit 1)
#   - real repo tree: sensor runs, output well-formed, ADVISORY       (rc in {0,1})
#
# Run from repo root: bash tests/tooling/test-adr-enforced-status-drift.sh
# All fixtures live in a temp tree; the real adrs/ check is read-only.
# =============================================================================

set -u

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
DETECTOR="$REPO_ROOT/scripts/adr-enforced-status-drift.sh"

TEST_DIR=$(mktemp -d "${TMPDIR:-/tmp}/adr-enforced-drift-test-XXXXXX")
trap 'rm -rf "$TEST_DIR"' EXIT

GREEN='\033[0;32m'; RED='\033[0;31m'; CYAN='\033[0;36m'; NC='\033[0m'
PASS=0; FAIL=0; TOTAL=0
ok()  { PASS=$((PASS+1)); TOTAL=$((TOTAL+1)); echo -e "  ${GREEN}✓${NC} $1"; }
bad() { FAIL=$((FAIL+1)); TOTAL=$((TOTAL+1)); echo -e "  ${RED}✗${NC} $1"; }

echo -e "${CYAN}ADR Enforcement-Status Drift Detector (reverse)${NC}"

mk_adr() { # <path> <id> <status>
    mkdir -p "$(dirname "$1")"
    { echo "---"; echo "id: $2"; echo "title: fixture"; echo "status: $3"
      echo "scope: agentic"; echo "---"; echo ""; echo "body"; } > "$1"
}
# writes a ledger with one row; args: <path> <rowid> <kind> <heading> <sensors>
mk_ledger() {
    mkdir -p "$(dirname "$1")"
    { echo "scope_dirs:"; echo "  - adrs/agentic"; echo "rules:"
      echo "  - id: $2"; echo "    file: docs/sop/ORCHESTRATOR_SOP.md"
      echo "    heading: \"$4\""; echo "    kind: $3"
      echo "    sensors: [$5]"; } > "$1"
}

# --- Case 1: FALSIFICATION (AC5) — proposed ADR + enforced ledger row -------
C1="$TEST_DIR/c1"
mk_adr "$C1/agentic/ADR-A-9001-fix.md" ADR-A-9001 proposed
mk_ledger "$C1/ledger.yaml" R-9001 enforced "The Widget Gate (ADR-A-9001)" "scripts/orchestrator.sh:widget_gate"
out="$(bash "$DETECTOR" "$C1" "$C1/ledger.yaml")"; rc=$?
if [ "$rc" -eq 1 ] && echo "$out" | grep -q 'DRIFT: ADR-A-9001'; then
    ok "AC5 falsification: kind:enforced + status:proposed => sensor rot"
else bad "AC5 falsification: rc=$rc out=[$out]"; fi

# --- Case 2: derived kind also triggers -------------------------------------
C2="$TEST_DIR/c2"
mk_adr "$C2/agentic/ADR-A-9002-fix.md" ADR-A-9002 proposed
mk_ledger "$C2/ledger.yaml" R-9002 derived "Counters (ADR-A-9002 P4)" "tests/test-x.sh"
out="$(bash "$DETECTOR" "$C2" "$C2/ledger.yaml")"; rc=$?
if [ "$rc" -eq 1 ] && echo "$out" | grep -q 'DRIFT: ADR-A-9002'; then
    ok "kind:derived + proposed => drift"
else bad "derived: rc=$rc out=[$out]"; fi

# --- Case 3: accepted ADR + enforced row => no drift ------------------------
C3="$TEST_DIR/c3"
mk_adr "$C3/agentic/ADR-A-9003-fix.md" ADR-A-9003 accepted
mk_ledger "$C3/ledger.yaml" R-9003 enforced "The Widget Gate (ADR-A-9003)" "scripts/x.sh:g"
out="$(bash "$DETECTOR" "$C3" "$C3/ledger.yaml")"; rc=$?
if [ "$rc" -eq 0 ] && [ -z "$out" ]; then ok "accepted + enforced => no drift"
else bad "accepted: rc=$rc out=[$out]"; fi

# --- Case 4: proposed ADR named only by unenforced row => no drift ----------
C4="$TEST_DIR/c4"
mk_adr "$C4/agentic/ADR-A-9004-fix.md" ADR-A-9004 proposed
mk_ledger "$C4/ledger.yaml" R-9004 unenforced "Some rule (ADR-A-9004)" ""
out="$(bash "$DETECTOR" "$C4" "$C4/ledger.yaml")"; rc=$?
if [ "$rc" -eq 0 ] && [ -z "$out" ]; then ok "proposed + unenforced-only => no drift"
else bad "unenforced-only: rc=$rc out=[$out]"; fi

# --- Case 5: proposed ADR not named by any ledger row => no drift -----------
C5="$TEST_DIR/c5"
mk_adr "$C5/agentic/ADR-A-9005-fix.md" ADR-A-9005 proposed
mk_ledger "$C5/ledger.yaml" R-9005 enforced "Unrelated gate (ABS-999)" "scripts/x.sh:g"
out="$(bash "$DETECTOR" "$C5" "$C5/ledger.yaml")"; rc=$?
if [ "$rc" -eq 0 ] && [ -z "$out" ]; then ok "proposed but unnamed by any enforced row => no drift"
else bad "unnamed: rc=$rc out=[$out]"; fi

# --- Case 6: --flip-list emits an operator line -----------------------------
out="$(bash "$DETECTOR" --flip-list "$C1" "$C1/ledger.yaml")"; rc=$?
if [ "$rc" -eq 1 ] && echo "$out" | grep -q 'ADR-A-9001.*enforced by R-9001.*HUMAN-ONLY'; then
    ok "--flip-list: operator decision line with Belegstelle"
else bad "flip-list: rc=$rc out=[$out]"; fi

# --- Case 7: real repo tree — sensor runs, ADVISORY (rc in {0,1}) -----------
# The live tree is EXPECTED to carry reverse-drift until a human works the
# flip-list (ADR-A-0004), so we assert the sensor executes cleanly (never rc 2 /
# parse error) and every DRIFT line is well-formed — NOT that the tree is clean.
out="$(bash "$DETECTOR" 2>&1)"; rc=$?
malformed="$(echo "$out" | grep '^DRIFT:' | grep -vE 'DRIFT: ADR-A-[0-9]+ status:proposed .* ledger R-[0-9]+' || true)"
if { [ "$rc" -eq 0 ] || [ "$rc" -eq 1 ]; } && [ -z "$malformed" ]; then
    ok "real tree: sensor runs advisory (rc=$rc), DRIFT lines well-formed"
else bad "real tree: rc=$rc malformed=[$malformed]"; fi

echo ""
echo -e "${CYAN}Passed: ${PASS}  Failed: ${FAIL}  Total: ${TOTAL}${NC}"
[ "$FAIL" -eq 0 ] || exit 1
exit 0
