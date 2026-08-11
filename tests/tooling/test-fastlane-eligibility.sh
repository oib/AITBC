#!/bin/bash
# =============================================================================
# Test: Fastlane Eligibility Proposal (ABS-320, epic ABS-314 v3 fastlane)
# =============================================================================
# Drives scripts/fastlane-eligibility.sh against an isolated mock-tracker store
# and asserts the acceptance criteria of ABS-320:
#   AC1  all four rules pass -> fastlane-eligible: yes, all rules shown passing
#   AC2  any single rule violated -> fastlane-eligible: no, failing rule named
#        (one case per rule: a diff_surface, b schema_security, d inflight)
#   AC3  a depends_on link -> always fail on rule (c)
#   AC4  the proposal NEVER mutates lane (stays normal after recording)
#   AC5  the annotation shape is machine-readable (stable `key: value` lines)
#
# Run from repo root: bash tests/tooling/test-fastlane-eligibility.sh
# bash 3.2 / BSD-tool safe.
# =============================================================================

set -u
# PILOT-46: strip inherited backend/tracker env before any fixture runs (tests/sandbox-guard.sh).
# shellcheck source=tests/sandbox-guard.sh
. "$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)/sandbox-guard.sh"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
ELIG="$REPO_ROOT/scripts/fastlane-eligibility.sh"
MOCK="$REPO_ROOT/scripts/mock-tracker.sh"

TEST_DIR=$(mktemp -d /tmp/fastlane-elig-test-XXXXXX)
trap 'rm -rf "$TEST_DIR"' EXIT

export MOCK_TRACKER_TICKETS_DIR="$TEST_DIR/work/tickets"
export MOCK_TRACKER_STATUSES="$REPO_ROOT/profiles/neutral/adapters/statuses.yaml"
export TRACKER_CMD="$MOCK"

# fastlane-eligibility.sh writes its body draft to work/scratch relative to CWD;
# run from the isolated TEST_DIR so nothing lands in the repo.
cd "$TEST_DIR" || exit 1

GREEN='\033[0;32m'; RED='\033[0;31m'; CYAN='\033[0;36m'; NC='\033[0m'
PASS=0; FAIL=0; TOTAL=0

ok()  { PASS=$((PASS+1)); TOTAL=$((TOTAL+1)); echo -e "  ${GREEN}PASS${NC} $1"; }
bad() { FAIL=$((FAIL+1)); TOTAL=$((TOTAL+1)); echo -e "  ${RED}FAIL${NC} $1"; }
expect() { # <actual> <expected> <label>
    if [ "$1" = "$2" ]; then ok "$3"; else bad "$3 (expected '$2', got '$1')"; fi
}

mock()  { bash "$MOCK" "$@"; }
elig()  { bash "$ELIG" "$@"; }
newid() { mock create "$@" | tail -1; }
# assert stdout of `elig <id> --dry-run` contains a fixed line
assert_line() { # <id> <grep-pattern> <label>
    if elig "$1" --dry-run | grep -qF -- "$2"; then ok "$3"; else
        bad "$3 (missing line: '$2')"; echo "    got:"; elig "$1" --dry-run | sed 's/^/      /'
    fi
}

echo -e "${CYAN}Fastlane Eligibility Proposal (ABS-320)${NC}"

EPIC=$(newid --type epic --title "epic 314")
RF="$TEST_DIR/reason.txt"; printf 'test\n' > "$RF"

# --- AC1: clean ticket -> yes, all four rules pass --------------------------
echo "AC1 — all rules pass -> yes"
CLEAN=$(newid --type ticket --parent "$EPIC" --title "small clean change")
assert_line "$CLEAN" "fastlane-eligible: yes"               "AC1 verdict yes"
assert_line "$CLEAN" "rule.diff_surface: pass"             "AC1 rule a passing"
assert_line "$CLEAN" "rule.schema_security: pass"          "AC1 rule b passing"
assert_line "$CLEAN" "rule.depends_on: pass"               "AC1 rule c passing"
assert_line "$CLEAN" "rule.inflight_conflict: pass"        "AC1 rule d passing"

# --- AC2: one case per rule violated -> no + names the failing rule ---------
echo "AC2 — each single rule violated -> no"
# (a) diff surface: model:opus label
A=$(newid --type ticket --parent "$EPIC" --title "opus change")
mock update "$A" labels "[model:opus]" >/dev/null
assert_line "$A" "fastlane-eligible: no"                   "AC2(a) verdict no"
assert_line "$A" "rule.diff_surface: fail"                 "AC2(a) names diff_surface"
# (b) schema/security: data flag
B=$(newid --type ticket --parent "$EPIC" --flag data --title "schema change")
assert_line "$B" "fastlane-eligible: no"                   "AC2(b) verdict no"
assert_line "$B" "rule.schema_security: fail"              "AC2(b) names schema_security"
# (b') security flag also trips rule b
BS=$(newid --type ticket --parent "$EPIC" --flag security --title "auth change")
assert_line "$BS" "rule.schema_security: fail"             "AC2(b') security flag names schema_security"
# (d) in-flight conflict: an actively-worked sibling under the same epic
SIB=$(newid --type ticket --parent "$EPIC" --title "in-flight sibling")
mock transition "$SIB" "Ready for Development" --actor t --reason-file "$RF" >/dev/null
mock transition "$SIB" "In Progress" --actor t --reason-file "$RF" >/dev/null
D=$(newid --type ticket --parent "$EPIC" --title "concurrent change")
assert_line "$D" "fastlane-eligible: no"                   "AC2(d) verdict no"
assert_line "$D" "rule.inflight_conflict: fail"            "AC2(d) names inflight_conflict"

# --- AC3: depends_on link -> always fail on rule (c) ------------------------
echo "AC3 — depends_on -> fail rule c"
C=$(newid --type ticket --parent "$EPIC" --title "dependent change")
mock update "$C" depends_on "[$CLEAN]" >/dev/null
assert_line "$C" "rule.depends_on: fail"                   "AC3 depends_on trips rule c"
assert_line "$C" "fastlane-eligible: no"                   "AC3 verdict no"

# --- AC4: recording NEVER mutates lane --------------------------------------
echo "AC4 — proposal never mutates lane"
LANE_BEFORE=$(mock get "$CLEAN" | grep '^lane:' | sed 's/lane:[[:space:]]*//')
elig "$CLEAN" >/dev/null   # non-dry-run: records the decision annotation
LANE_AFTER=$(mock get "$CLEAN" | grep '^lane:' | sed 's/lane:[[:space:]]*//')
expect "$LANE_BEFORE" "normal" "AC4 lane is normal before"
expect "$LANE_AFTER"  "normal" "AC4 lane still normal after recording"
if mock get "$CLEAN" | grep -q "kind: decision"; then ok "AC4 decision annotation recorded"; else bad "AC4 no decision annotation"; fi

# --- AC5: machine-readable field shape --------------------------------------
echo "AC5 — machine-readable shape"
OUT=$(elig "$CLEAN" --dry-run)
# exactly one verdict line + one line per rule, all as parseable 'key: value'
NVERDICT=$(printf '%s\n' "$OUT" | grep -c '^fastlane-eligible: \(yes\|no\)$')
NRULES=$(printf '%s\n' "$OUT" | grep -c '^rule\.[a-z_]*: \(pass\|fail\) - ')
expect "$NVERDICT" "1" "AC5 exactly one verdict line"
expect "$NRULES"   "4" "AC5 four parseable rule lines"

# --- summary ----------------------------------------------------------------
echo ""
echo -e "${CYAN}Results:${NC} ${GREEN}$PASS passed${NC}, ${RED}$FAIL failed${NC} ($TOTAL total)"
[ "$FAIL" -eq 0 ] || exit 1
