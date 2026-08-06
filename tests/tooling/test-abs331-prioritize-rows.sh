#!/bin/bash
# =============================================================================
# Test: prioritize_rows consumes the search priority column (ABS-331 AC3)
# =============================================================================
# ABS-331 removes the per-sweep N x `tracker get` cost of priority-aware dispatch
# (ABS-261): the adapter `search` surface now emits the canonical priority as a
# column (id<TAB>type<TAB>status<TAB>priority<TAB>title), so prioritize_rows reads
# priority straight from the row instead of a per-row `tracker get`. This suite
# SOURCES scripts/orchestrator.sh (main is source-guarded, same idiom as
# tests/test-station-guard.sh) and drives prioritize_rows directly with a stubbed
# `ticket_priority` that records every call to a file — the only way to prove the
# get is GONE when the column is present and STILL taken when it is absent.
#
# bash 3.2 + BSD tools only. Run from repo root: bash tests/tooling/test-abs331-prioritize-rows.sh
# =============================================================================

set -euo pipefail

# Scrub ambient ORCH_* so the result is a function of the commit, not the caller
# (same guard as test-station-guard.sh / ABS-285).
unset $(compgen -v | grep '^ORCH_') 2>/dev/null || true

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

# main is source-guarded, so this loads the functions without starting the loop.
source "$REPO_ROOT/scripts/orchestrator.sh" >/dev/null 2>&1

echo -e "${CYAN}=== prioritize_rows: search priority column (ABS-331 AC3) ===${NC}\n"

# Record every ticket_priority (=per-row `tracker get`) call so we can assert the
# count. The function under test runs inside a `while|sort` pipeline subshell, so
# a shell variable would not survive — count via a file instead.
GET_LOG="$(mktemp "${TMPDIR:-/tmp}/abs331-getlog-XXXXXX")"
trap 'rm -f "$GET_LOG"' EXIT
ticket_priority() { echo x >> "$GET_LOG"; printf 'normal'; }
gets() { [ -s "$GET_LOG" ] && wc -l < "$GET_LOG" | tr -d ' ' || echo 0; }

TAB="$(printf '\t')"

# --- AC3: column present => priority read from the row, ZERO per-row gets --------
: > "$GET_LOG"
IN="$(printf 'ID-1\tticket\tBacklog\tlow\tlowtitle\nID-2\tticket\tBacklog\thotfix\thottitle\nID-3\tticket\tBacklog\tnormal\tnormtitle\nID-4\tticket\tBacklog\thigh\thightitle\n')"
order="$(printf '%s\n' "$IN" | prioritize_rows | cut -f1 | tr '\n' ' ')"
assert_eq "$order" "ID-2 ID-4 ID-3 ID-1 " "AC3: rows sort hotfix>high>normal>low from the column"
assert_eq "$(gets)" "0" "AC3: priority read from the search column issues ZERO per-row tracker get"

# --- AC3: each input line is preserved VERBATIM (ignoring callers unaffected) ----
verbatim="$(printf 'ID-9\tticket\tBacklog\thigh\tmy title\n' | prioritize_rows)"
assert_eq "$verbatim" "$(printf 'ID-9\tticket\tBacklog\thigh\tmy title')" "AC3: the 5-column row round-trips byte-for-byte"

# --- AC3: an empty title still counts as a present column (5 fields) -------------
: > "$GET_LOG"
printf 'ID-5\tticket\tBacklog\tnormal\t\n' | prioritize_rows >/dev/null
assert_eq "$(gets)" "0" "AC3: a present column with an empty title still skips the get"

# --- AC3 fallback: legacy 4-column adapter => per-row get, one per row -----------
: > "$GET_LOG"
printf 'X-1\tticket\tBacklog\ttitleone\nX-2\tticket\tBacklog\ttitletwo\n' | prioritize_rows >/dev/null
assert_eq "$(gets)" "2" "AC3 fallback: a legacy 4-column row reads priority per-row (one get each)"

# --- AC3 fallback: no false-positive when a legacy title equals a priority word --
# `...\thigh` with NO 5th field is a title, not a column — must still fall back.
: > "$GET_LOG"
out="$(printf 'Z-1\tticket\tBacklog\thigh\n' | prioritize_rows)"
assert_eq "$(gets)" "1" "AC3 fallback: a 4-column title of 'high' is not mistaken for the column"
assert_eq "$out" "$(printf 'Z-1\tticket\tBacklog\thigh')" "AC3 fallback: the legacy row is preserved verbatim"

# --- stable tiebreak within a band: input (age-ASC) order is kept ----------------
tie="$(printf 'A\tticket\tBacklog\tnormal\tt\nB\tticket\tBacklog\tnormal\tt\nC\tticket\tBacklog\tnormal\tt\n' | prioritize_rows | cut -f1 | tr '\n' ' ')"
assert_eq "$tie" "A B C " "AC3: equal-priority rows keep their stable (age-ASC) input order"

# --- unmapped column value defaults to normal (defensive) -----------------------
: > "$GET_LOG"
umap="$(printf 'U-1\tticket\tBacklog\tbogus\tt\nU-2\tticket\tBacklog\thotfix\tt\n' | prioritize_rows | cut -f1 | tr '\n' ' ')"
assert_eq "$umap" "U-2 U-1 " "AC3: an unmapped column value is treated as normal (hotfix still sorts first)"
assert_eq "$(gets)" "0" "AC3: an unmapped-but-present column still skips the get"

echo -e "\n${CYAN}=== Results ===${NC}"
echo -e "  Total:  $TOTAL / Passed: ${GREEN}$PASS${NC} / Failed: $([ "$FAIL" -gt 0 ] && echo "${RED}$FAIL${NC}" || echo 0)"
[ "$FAIL" -eq 0 ] || exit 1
echo -e "  ${GREEN}ALL TESTS PASSED${NC}"
