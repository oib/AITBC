#!/bin/bash
# =============================================================================
# Test: One-Click Fastlane Confirm Control (ABS-321, epic ABS-314 v3 fastlane)
# =============================================================================
# Drives scripts/fastlane-confirm.sh against an isolated mock-tracker store and
# asserts the acceptance criteria of ABS-321:
#   AC1  eligible=yes -> `view` renders the proposal + an ENABLED confirm control
#   AC2  `confirm` sets lane=fastlane via the adapter; the refreshed view shows it
#   AC3  eligible=no  -> reasons visible, confirm DISABLED; refused w/o --override
#   AC4  `revert` returns the ticket to lane=normal
#   AC5  no lane change without an explicit confirm click (view/refused-confirm)
# plus: --override promotes a 'no' verdict; live fallback when no annotation;
#       invalid action/args are rejected.
#
# Run from repo root: bash tests/tooling/test-fastlane-confirm.sh
# bash 3.2 / BSD-tool safe.
# =============================================================================

set -u
# PILOT-46: strip inherited backend/tracker env before any fixture runs (tests/sandbox-guard.sh).
# shellcheck source=tests/sandbox-guard.sh
. "$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)/sandbox-guard.sh"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
CONF="$REPO_ROOT/scripts/fastlane-confirm.sh"
ELIG="$REPO_ROOT/scripts/fastlane-eligibility.sh"
MOCK="$REPO_ROOT/scripts/mock-tracker.sh"

TEST_DIR=$(mktemp -d /tmp/fastlane-confirm-test-XXXXXX)
trap 'rm -rf "$TEST_DIR"' EXIT

export MOCK_TRACKER_TICKETS_DIR="$TEST_DIR/work/tickets"
export MOCK_TRACKER_STATUSES="$REPO_ROOT/profiles/neutral/adapters/statuses.yaml"
export TRACKER_CMD="$MOCK"

# both scripts write draft files to work/scratch relative to CWD; run isolated.
cd "$TEST_DIR" || exit 1

GREEN='\033[0;32m'; RED='\033[0;31m'; CYAN='\033[0;36m'; NC='\033[0m'
PASS=0; FAIL=0; TOTAL=0
ok()  { PASS=$((PASS+1)); TOTAL=$((TOTAL+1)); echo -e "  ${GREEN}PASS${NC} $1"; }
bad() { FAIL=$((FAIL+1)); TOTAL=$((TOTAL+1)); echo -e "  ${RED}FAIL${NC} $1"; }
expect() { if [ "$1" = "$2" ]; then ok "$3"; else bad "$3 (expected '$2', got '$1')"; fi; }

mock()  { bash "$MOCK" "$@"; }
conf()  { bash "$CONF" "$@"; }
elig()  { bash "$ELIG" "$@"; }
newid() { mock create "$@" | tail -1; }
lane_of() { mock get "$1" | grep -E '^lane:' | head -1 | sed -E 's/^lane:[[:space:]]*//'; }
# grep a fixed line in `conf <args>` combined output
has_line() { # <label> <pattern> <args...>
    local label="$1" pat="$2"; shift 2
    if conf "$@" 2>&1 | grep -qF -- "$pat"; then ok "$label"; else
        bad "$label (missing '$pat')"; echo "    got:"; conf "$@" 2>&1 | sed 's/^/      /'
    fi
}

echo -e "${CYAN}One-Click Fastlane Confirm Control (ABS-321)${NC}"

EPIC=$(newid --type epic --title "epic 314")

# --- AC1: eligible=yes -> proposal rendered + confirm ENABLED ----------------
echo "AC1: eligible ticket renders proposal + enabled control"
T_YES=$(newid --type ticket --title "clean" --parent "$EPIC")
elig "$T_YES" >/dev/null                      # record the yes proposal
has_line "AC1 proposal verdict shown"   "fastlane-eligible: yes" view "$T_YES"
has_line "AC1 per-rule reason shown"    "rule.diff_surface: pass" view "$T_YES"
has_line "AC1 confirm control ENABLED"  "confirm-control: enabled" view "$T_YES"
expect "$(lane_of "$T_YES")" "normal" "AC1 view did not change lane"

# --- AC2: confirm -> lane=fastlane via adapter; refreshed view reflects it ---
echo "AC2: one-click confirm promotes to fastlane"
conf confirm "$T_YES" >/dev/null
expect "$(lane_of "$T_YES")" "fastlane" "AC2 adapter set lane=fastlane"
has_line "AC2 refreshed view shows fastlane state" "lane: fastlane" view "$T_YES"
has_line "AC2 control now already-fastlane"        "confirm-control: already-fastlane" view "$T_YES"

# --- AC4: revert -> lane=normal ---------------------------------------------
echo "AC4: revert returns to normal"
conf revert "$T_YES" >/dev/null
expect "$(lane_of "$T_YES")" "normal" "AC4 revert set lane=normal"
has_line "AC4 control re-enabled after revert" "confirm-control: enabled" view "$T_YES"

# --- AC3 + AC5: eligible=no -> disabled, refused, lane untouched -------------
echo "AC3/AC5: ineligible ticket -> disabled control, refused without override"
T_NO=$(newid --type ticket --title "schema" --parent "$EPIC" --flag data)
elig "$T_NO" >/dev/null
has_line "AC3 failing reason visible" "rule.schema_security: fail" view "$T_NO"
has_line "AC3 confirm control DISABLED" "confirm-control: disabled" view "$T_NO"
conf confirm "$T_NO" >/dev/null 2>&1; rc=$?
expect "$rc" "3" "AC3 confirm refused (exit 3) without override"
expect "$(lane_of "$T_NO")" "normal" "AC5 refused confirm left lane=normal (no auto-promotion)"

# --- override: explicit human --override promotes a 'no' verdict -------------
echo "override: --override promotes despite 'no' verdict"
conf confirm "$T_NO" --override >/dev/null
expect "$(lane_of "$T_NO")" "fastlane" "override set lane=fastlane"

# --- AC5: view never mutates lane (fresh normal ticket) ---------------------
echo "AC5: view is read-only"
T_V=$(newid --type ticket --title "viewonly" --parent "$EPIC")
elig "$T_V" >/dev/null
conf view "$T_V" >/dev/null
expect "$(lane_of "$T_V")" "normal" "AC5 view left lane=normal"

# --- fallback: no recorded annotation -> control computes it live -----------
echo "fallback: no annotation -> computed live"
T_F=$(newid --type ticket --title "noannotation" --parent "$EPIC")
has_line "fallback computes proposal live" "computed live" view "$T_F"
has_line "fallback still yields a verdict"  "fastlane-eligible: yes" view "$T_F"

# --- guardrail: invalid action / missing id are rejected --------------------
echo "guardrail: invalid input rejected"
conf bogus "$T_YES" >/dev/null 2>&1; expect "$?" "2" "unknown action rejected (exit 2)"
conf view >/dev/null 2>&1;           expect "$?" "2" "missing ticket-id rejected (exit 2)"

# --- summary ----------------------------------------------------------------
echo ""
echo -e "${CYAN}Results:${NC} $PASS/$TOTAL passed"
[ "$FAIL" -eq 0 ] || { echo -e "${RED}$FAIL failed${NC}"; exit 1; }
echo -e "${GREEN}All ABS-321 acceptance criteria verified.${NC}"
