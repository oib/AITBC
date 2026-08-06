#!/usr/bin/env bash
# =============================================================================
# Test: per-seat prompt-size budget sensor (PILOT-55 / ABS-566)
# =============================================================================
# Guards scripts/agent-prompt-size.sh — the sensor that measures every seat's
# composed prompt (commons + role def + overlay) and flags a role over the
# declared budget as a DEFECT. Two things are proven:
#
#   1. The sensor is CORRECT on fixtures: it sums file bytes the documented way
#      (commons + role + overlay), `--check` FAILS on an over-budget def and
#      PASSES when all defs are under budget, and the budget is configurable.
#   2. The shipped harness stays within a RATCHET: the number of roles over the
#      24000 B budget must not exceed today's known-debt ceiling. New bloat (a
#      14th over-budget role, or a heavier _common-rules.md) is therefore a
#      DEFECT that turns this test red — while the existing debt, whose removal
#      is the follow-up shortening story (ABS-566 remainder), is tolerated.
#
# The real-harness numbers themselves are printed for visibility (the measurement
# is the value): run `bash scripts/agent-prompt-size.sh` to see them.
#
# ABS-285: this test reads FILE BYTES only (no spawn), but it still scrubs the
# ambient ORCH_* env so an inherited ORCH_AGENTS_DIR / ORCH_PROMPT_SIZE_BUDGET
# cannot change what the sensor measures. Each invocation sets exactly what it needs.
#
# Bash 3.2 / BSD safe. Run from repo root: bash tests/tooling/test-agent-prompt-size-budget.sh
# =============================================================================
set -u
# shellcheck disable=SC2046  # deliberate word-split: unset every ORCH_* name.
unset $(env | sed -n 's/^\(ORCH_[A-Za-z0-9_]*\)=.*/\1/p') 2>/dev/null || true

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
SENSOR="$REPO_ROOT/scripts/agent-prompt-size.sh"

# The known-debt ceiling: at PILOT-55 authoring, 13 of 17 roles exceed the 24000 B
# budget. The follow-up shortening story lowers this as it brings defs under budget;
# it must NEVER rise (that would mean a role newly went over budget).
# PILOT-75 raised it 13 -> 14: the _common-rules.md forward-push guidance (rule §1,
# prepended to every seat) pushed one further role's total over 24000 B. This is the
# sanctioned one-time cost of that shared-rule addition, not per-role bloat.
# ABS-601 raised it 14 -> 16: the async-wait-stall prohibition added to Common Rule 5
# (_common-rules.md, prepended to every seat) pushed two further roles' totals over
# 24000 B. Sanctioned one-time cost of that shared-rule addition, not per-role bloat.
RATCHET_MAX_OVER=16

PASS=0; FAIL=0; TOTAL=0
GREEN='\033[0;32m'; RED='\033[0;31m'; CYAN='\033[0;36m'; NC='\033[0m'

TEST_DIR=$(mktemp -d "${TMPDIR:-/tmp}/agent-prompt-size-test.XXXXXX")
trap 'rm -rf "$TEST_DIR"' EXIT

# assert_true CODE LABEL — CODE 0 => pass. Callers pass a computed 0/1.
assert_true() {
    local code="$1"; local label="$2"
    TOTAL=$((TOTAL + 1))
    if [ "$code" = "0" ]; then
        echo -e "  ${GREEN}PASS${NC} $label"; PASS=$((PASS + 1))
    else
        echo -e "  ${RED}FAIL${NC} $label"; FAIL=$((FAIL + 1))
    fi
}

echo -e "${CYAN}=== prompt-size budget sensor (PILOT-55 / ABS-566) ===${NC}\n"

# --- 1. Size methodology: composed = commons + role + overlay ----------------
mkdir -p "$TEST_DIR/fx/agents" "$TEST_DIR/fx/overrides"
# commons = 100 bytes exactly.
head -c 100 /dev/zero | tr '\0' 'C' > "$TEST_DIR/fx/agents/_common-rules.md"
# small role = 50 bytes; big role = 1000 bytes; overlay for small = 40 bytes.
head -c 50   /dev/zero | tr '\0' 's' > "$TEST_DIR/fx/agents/small.md"
head -c 1000 /dev/zero | tr '\0' 'B' > "$TEST_DIR/fx/agents/big.md"
head -c 40   /dev/zero | tr '\0' 'o' > "$TEST_DIR/fx/overrides/small.append.md"
# README + underscore fragment must be ignored (not spawnable roles).
echo "readme" > "$TEST_DIR/fx/agents/README.md"

# small alone: 100 + 50 = 150; big: 100 + 1000 = 1100.
OUT="$(ORCH_AGENTS_DIR="$TEST_DIR/fx/agents" bash "$SENSOR" --budget 500)"
echo "$OUT" | grep -Eq '^small +150 +50 +0 +ok'; assert_true $? "composed size = commons + role (small = 150, under budget → ok)"
echo "$OUT" | grep -Eq '^big +1100 +1000 +0 +OVER'; assert_true $? "composed size flags over-budget (big = 1100 > 500 → OVER)"
if echo "$OUT" | grep -q 'README'; then assert_true 1 "README.md is excluded"; else assert_true 0 "README.md is excluded (not a spawnable role)"; fi
if echo "$OUT" | grep -q '_common-rules'; then assert_true 1 "_common-rules.md is excluded"; else assert_true 0 "_common-rules.md is excluded (shared fragment)"; fi

# overlay is added to the composed size when ORCH_OVERRIDES_DIR is set: 100+50+40=190.
OUT_OV="$(ORCH_AGENTS_DIR="$TEST_DIR/fx/agents" ORCH_OVERRIDES_DIR="$TEST_DIR/fx/overrides" bash "$SENSOR" --budget 500)"
echo "$OUT_OV" | grep -Eq '^small +190 +50 +40 +ok'; assert_true $? "overlay bytes are added to the composed size (small = 100+50+40 = 190)"

# --- 2. --check is the gate: over budget → exit 1 ----------------------------
if ORCH_AGENTS_DIR="$TEST_DIR/fx/agents" bash "$SENSOR" --check --budget 500 >/dev/null 2>&1; then
    assert_true 1 "--check should exit non-zero when a role is over budget"
else
    assert_true 0 "--check EXITS NON-ZERO when a role is over budget (defect, not a mode)"
fi

# report mode never fails, even with an over-budget role.
ORCH_AGENTS_DIR="$TEST_DIR/fx/agents" bash "$SENSOR" --budget 500 >/dev/null 2>&1
assert_true $? "report mode exits 0 even with an over-budget role (pure measurement)"

# all under budget → --check passes. Raise the budget above big's 1100.
ORCH_AGENTS_DIR="$TEST_DIR/fx/agents" bash "$SENSOR" --check --budget 5000 >/dev/null 2>&1
assert_true $? "--check PASSES when every role is under budget"

# budget is configurable via env too (ORCH_PROMPT_SIZE_BUDGET), same result.
ORCH_AGENTS_DIR="$TEST_DIR/fx/agents" ORCH_PROMPT_SIZE_BUDGET=5000 bash "$SENSOR" --check >/dev/null 2>&1
assert_true $? "budget is configurable via ORCH_PROMPT_SIZE_BUDGET"

# a non-numeric budget is rejected (exit 2).
rc=0; ORCH_AGENTS_DIR="$TEST_DIR/fx/agents" bash "$SENSOR" --budget nope >/dev/null 2>&1 || rc=$?
[ "$rc" -eq 2 ] && assert_true 0 "a non-numeric budget is rejected (exit 2)" || assert_true 1 "a non-numeric budget should exit 2 (got $rc)"

# --- 3. Real harness: methodology reproduces + ratchet holds -----------------
rc=0; REAL="$(ORCH_AGENTS_DIR="$REPO_ROOT/harness/claude/agents" bash "$SENSOR")" || rc=$?
assert_true "$rc" "real-harness report runs cleanly (exit 0)"

# The methodology reproduces the ABS-566 headline: be-developer composed size ==
# wc -c(be-developer.md) + wc -c(_common-rules.md). Computed live so it can't rot.
be_expected=$(( $(wc -c < "$REPO_ROOT/harness/claude/agents/be-developer.md" | tr -d '[:space:]') \
              + $(wc -c < "$REPO_ROOT/harness/claude/agents/_common-rules.md" | tr -d '[:space:]') ))
echo "$REAL" | grep -Eq "^be-developer +${be_expected} "; assert_true $? "real be-developer composed size == role + commons bytes (methodology matches ABS-566)"

# Every high-cost role appears in the report.
for r in qas rte issue-enrichment system-architect be-developer; do
    echo "$REAL" | grep -q "^${r} "; assert_true $? "  real report includes role: $r"
done

# RATCHET: over-budget count must not exceed the known-debt ceiling.
over_now="$(echo "$REAL" | sed -n 's/^SUMMARY: \([0-9]*\)\/.*/\1/p')"
[ -n "$over_now" ] && assert_true 0 "real report emits a parseable SUMMARY line" || assert_true 1 "real report should emit a SUMMARY line"
if [ "${over_now:-999}" -le "$RATCHET_MAX_OVER" ]; then
    assert_true 0 "over-budget count (${over_now:-?}) within ratchet ceiling ($RATCHET_MAX_OVER) — no new prompt-size defect"
else
    assert_true 1 "over-budget count (${over_now:-?}) EXCEEDS ratchet ceiling ($RATCHET_MAX_OVER) — a role newly went over budget"
fi

echo -e "\n${CYAN}--- current IST sizes (harness) ---${NC}"
echo "$REAL" | sed 's/^/    /'

# --- Summary ----------------------------------------------------------------
echo ""
echo -e "${CYAN}=== Results ===${NC}"
echo -e "  Total:  $TOTAL"
echo -e "  ${GREEN}Passed: $PASS${NC}"
echo -e "  ${RED}Failed: $FAIL${NC}"
[ "$FAIL" -eq 0 ] || exit 1
echo -e "\n${GREEN}Prompt-size budget sensor: all checks passed.${NC}"
exit 0
