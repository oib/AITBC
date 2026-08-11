#!/bin/bash
# =============================================================================
# Test: skill-mining.sh (ABS-218)
# =============================================================================
# Drives scripts/skill-mining.sh against the fixture run at
# tests/fixtures/skill-mining/ (no live orchestrator, no network) and asserts:
#   - valid syntax + a --help usage block
#   - AC2: per-role report fields (seats, calls median/max vs turn-ceiling,
#     help count, NOMOVE/RESPAWN/CRASH, skill calls, top normalized commands)
#   - AC3: all three SKILL-KANDIDAT paths fire (pattern / help / NOMOVE) and a
#     quiet role is OK
#   - AC4: --proposals writes one ABS-4-shaped skeleton per candidate
#   - AC5: redaction — no secret value reaches the report, <REDACTED> is emitted,
#     and raw commands are normalized (ticket-ids -> ABS-N, first tokens)
#   - graceful degradation on an empty state dir
#   - the fixture tree is byte-for-byte unchanged (read-only guarantee)
#
# Run from repo root: bash tests/tooling/test-skill-mining.sh
# =============================================================================
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
MINER="$REPO_ROOT/scripts/skill-mining.sh"
FIXTURE="$REPO_ROOT/tests/fixtures/skill-mining"
STATE="$FIXTURE/state"
CONFIG="$FIXTURE/config"

# deterministic turn-ceiling regardless of the caller's env
export ORCH_MAX_TURNS=25

TEST_DIR=$(mktemp -d "${TMPDIR:-/tmp}/skill-mining-test.XXXXXX")
trap 'rm -rf "$TEST_DIR"' EXIT

PASS=0; FAIL=0; TOTAL=0
GREEN='\033[0;32m'; RED='\033[0;31m'; CYAN='\033[0;36m'; NC='\033[0m'

assert_contains() {
    local output="$1" expected="$2" label="$3"
    TOTAL=$((TOTAL + 1))
    if echo "$output" | grep -qF -- "$expected"; then
        echo -e "  ${GREEN}PASS${NC} $label"; PASS=$((PASS + 1))
    else
        echo -e "  ${RED}FAIL${NC} $label (expected to find: $expected)"
        echo "$output" | head -40 | sed 's/^/    /'
        FAIL=$((FAIL + 1))
    fi
}
assert_absent() {
    local output="$1" needle="$2" label="$3"
    TOTAL=$((TOTAL + 1))
    if echo "$output" | grep -qF -- "$needle"; then
        echo -e "  ${RED}FAIL${NC} $label (unexpectedly found: $needle)"; FAIL=$((FAIL + 1))
    else
        echo -e "  ${GREEN}PASS${NC} $label"; PASS=$((PASS + 1))
    fi
}
assert_exit_code() {
    local actual="$1" expected="$2" label="$3"
    TOTAL=$((TOTAL + 1))
    if [ "$actual" -eq "$expected" ]; then
        echo -e "  ${GREEN}PASS${NC} $label"; PASS=$((PASS + 1))
    else
        echo -e "  ${RED}FAIL${NC} $label (expected exit $expected, got $actual)"; FAIL=$((FAIL + 1))
    fi
}

# stanza of the report that describes one role (## Role: X up to next ##)
role_block() { echo "$1" | awk -v r="## Role: $2" '$0==r{f=1} f&&/^## Role: /&&$0!=r{exit} f'; }

fixture_checksum() { find "$FIXTURE" -type f -exec md5 {} + | sort; }

# =============================================================================
echo -e "\n${CYAN}=== Test 0: syntax + help (AC1) ===${NC}\n"
# =============================================================================
bash -n "$MINER" 2>&1; assert_exit_code $? 0 "skill-mining.sh has valid bash syntax"
help_out=$(bash "$MINER" --help 2>&1)
assert_contains "$help_out" "--proposals" "help documents --proposals"
assert_contains "$help_out" "--state-dir" "help documents --state-dir"

sum_before=$(fixture_checksum)

# =============================================================================
echo -e "\n${CYAN}=== Test 1: per-role report fields (AC2) ===${NC}\n"
# =============================================================================
report=$(bash "$MINER" --state-dir "$STATE" --config-dir "$CONFIG" 2>/dev/null)
bd=$(role_block "$report" "be-developer")
assert_contains "$bd" "Seats (spawns): 3" "be-developer seat count == 3"
assert_contains "$bd" "turn-ceiling: 25" "turn-ceiling rendered"
assert_contains "$bd" "median" "call median/max line present"
assert_contains "$bd" "Skill calls per seat" "skill calls per seat present"
assert_contains "$bd" "Escalations — NOMOVE:" "NOMOVE/RESPAWN/CRASH counters present"
assert_contains "$bd" "Top normalized commands" "top normalized commands section present"

# =============================================================================
echo -e "\n${CYAN}=== Test 2: SKILL-KANDIDAT verdicts (AC3) ===${NC}\n"
# =============================================================================
assert_contains "$bd" "Verdict: SKILL-KANDIDAT" "be-developer is a candidate (pattern path)"
assert_contains "$bd" "git status --short" "be-developer names the recurring pattern"
sa=$(role_block "$report" "system-architect")
assert_contains "$sa" "Verdict: SKILL-KANDIDAT" "system-architect is a candidate (help path)"
assert_contains "$sa" "help invocations 3" "system-architect verdict cites help>=3"
bsa=$(role_block "$report" "bsa")
assert_contains "$bsa" "Verdict: SKILL-KANDIDAT" "bsa is a candidate (NOMOVE path)"
assert_contains "$bsa" "NOMOVE+RESPAWN 2" "bsa verdict cites NOMOVE+RESPAWN>=2"
qas=$(role_block "$report" "qas")
assert_contains "$qas" "Verdict: OK" "quiet role qas is OK (below all thresholds)"

# =============================================================================
echo -e "\n${CYAN}=== Test 3: normalization + redaction (AC5) ===${NC}\n"
# =============================================================================
# make the secret command visible in the Top list, then prove it is redacted
vis=$(THRESH_TOP_CMD=1 bash "$MINER" --state-dir "$STATE" --config-dir "$CONFIG" 2>/dev/null)
assert_absent "$vis" "supersecret" "no secret value reaches the report"
assert_contains "$vis" "<REDACTED>" "secret value replaced with <REDACTED>"
assert_contains "$vis" "git status --short" "raw command normalized to first tokens"
assert_absent "$report" "ABS-101-foo-spec.md" "ticket-id path not carried verbatim (normalized)"

# =============================================================================
echo -e "\n${CYAN}=== Test 4: --proposals skeletons (AC4) ===${NC}\n"
# =============================================================================
PDIR="$TEST_DIR/proposals"
PROPOSALS_DIR="$PDIR" bash "$MINER" --state-dir "$STATE" --config-dir "$CONFIG" \
    --proposals --out "$TEST_DIR/report.md" 2>/dev/null
n=$(find "$PDIR" -maxdepth 1 -name '*.md' 2>/dev/null | wc -l | tr -d ' ')
assert_exit_code "$([ "$n" -eq 3 ] && echo 0 || echo 1)" 0 "one proposal per candidate (3 written)"
prop=$(cat "$PDIR"/*be-developer*.md 2>/dev/null)
assert_contains "$prop" "**Filed**:" "proposal has ABS-4 Filed field"
assert_contains "$prop" "## Rationale" "proposal has Rationale section"
assert_contains "$prop" "## Issue Body (copy-paste-ready)" "proposal has copy-paste Issue Body"
# a role that is OK gets no proposal
qcount=$(find "$PDIR" -maxdepth 1 -name '*qas*' 2>/dev/null | wc -l | tr -d ' ')
assert_exit_code "$([ "$qcount" -eq 0 ] && echo 0 || echo 1)" 0 "OK role gets no proposal"

# =============================================================================
echo -e "\n${CYAN}=== Test 5: graceful degradation (empty state) ===${NC}\n"
# =============================================================================
empty="$TEST_DIR/empty"; mkdir -p "$empty"
ec=0; deg=$(bash "$MINER" --state-dir "$empty" --config-dir "$empty" 2>/dev/null) || ec=$?
assert_exit_code "$ec" 0 "empty state dir does not crash"
assert_contains "$deg" "nothing to mine" "empty run reports nothing to mine"

# =============================================================================
echo -e "\n${CYAN}=== Test 6: fixture read-only guarantee ===${NC}\n"
# =============================================================================
sum_after=$(fixture_checksum)
assert_exit_code "$([ "$sum_before" = "$sum_after" ] && echo 0 || echo 1)" 0 "fixture tree unchanged"

# =============================================================================
echo -e "\n${CYAN}=== Test 7: applicable-vs-inapplicable split (ABS-318) ===${NC}\n"
# =============================================================================
# Isolated fixture (NOT the shared read-only tree): two fe-developer seats — one
# touches patterns_library/ AND calls stop-slop (product-domain + process), one
# only edits scripts/ (harness/infra, product skills inapplicable).
SM="$TEST_DIR/split"; mkdir -p "$SM/state/sessions" "$SM/config/projects/p"
printf 's900\n' > "$SM/state/sessions/ABS-900.fe-developer.Ready_for_Development"
printf 's901\n' > "$SM/state/sessions/ABS-901.fe-developer.Ready_for_Development"
cat > "$SM/config/projects/p/s900.jsonl" <<'JSONL'
{"message":{"content":[{"type":"tool_use","name":"Bash","input":{"command":"cat patterns_library/api/webhook-handler.md"}}]}}
{"message":{"content":[{"type":"tool_use","name":"Skill","input":{"skill":"stop-slop"}}]}}
JSONL
cat > "$SM/config/projects/p/s901.jsonl" <<'JSONL'
{"message":{"content":[{"type":"tool_use","name":"Bash","input":{"command":"vim scripts/orchestrator.sh"}}]}}
JSONL
split_report=$(bash "$MINER" --state-dir "$SM/state" --config-dir "$SM/config" 2>/dev/null)
fe=$(role_block "$split_report" "fe-developer")
assert_contains "$fe" "Product-domain-touching seats: 1/2" "only the patterns_library/ seat counts as product-domain-applicable"
assert_contains "$fe" "Process-skill calls (stop-slop/verify/simplify — applicable every seat): 1" "process-skill call (stop-slop) counted from the transcript"

# =============================================================================
echo -e "\n${CYAN}=== Test 8: HANDOFF-CLAIM-NOHASH advisory telemetry (PILOT-69 AC2) ===${NC}\n"
# =============================================================================
# ADR-A-0024 (f) promotion criterion needs the advisory MEASURED. Isolated state
# with a run.log carrying INTENT-HANDOFF-CLAIM-NOHASH lines on two roles; assert
# the per-role count, the run-total measure line, and that it is NOT folded into
# the nomove/defect signal (it is advisory, not a verified defect).
NH="$TEST_DIR/nohash"; mkdir -p "$NH/state" "$NH/config"
{
  printf '%s\tINTENT-HANDOFF-CLAIM-NOHASH\tP-1\tbe-developer\tIn Review\t\n' 2026-07-26T00:00:00Z
  printf '%s\tINTENT-HANDOFF-CLAIM-NOHASH\tP-2\tbe-developer\tIn Review\t\n' 2026-07-26T00:01:00Z
  printf '%s\tINTENT-HANDOFF-CLAIM-NOHASH\tP-3\tqas\tIn Test\t\n'           2026-07-26T00:02:00Z
} > "$NH/state/run.log"
nh_report=$(bash "$MINER" --state-dir "$NH/state" --config-dir "$NH/config" 2>/dev/null)
assert_contains "$nh_report" "HANDOFF-CLAIM-NOHASH advisories (run total, ADR-A-0024 f promotion measure): 3" \
    "run-total advisory measure present (PILOT-69 AC2)"
nh_be=$(role_block "$nh_report" "be-developer")
assert_contains "$nh_be" "HANDOFF-CLAIM-NOHASH advisories: 2" "committing seat advisory count is 2"
assert_contains "$nh_be" "Escalations — NOMOVE: 0" "advisory NOT folded into the nomove defect signal"
nh_qas=$(role_block "$nh_report" "qas")
assert_contains "$nh_qas" "HANDOFF-CLAIM-NOHASH advisories: 1" "review seat advisory count is 1 (expected false-positive class)"

# =============================================================================
echo -e "\n${CYAN}=== Results ===${NC}"
echo -e "  Total: $TOTAL  ${GREEN}Pass: $PASS${NC}  ${RED}Fail: $FAIL${NC}\n"
if [ "$FAIL" -eq 0 ]; then
    echo -e "${GREEN}SKILL-MINING TESTS PASSED${NC}"; exit 0
else
    echo -e "${RED}SKILL-MINING TESTS FAILED${NC}"; exit 1
fi
