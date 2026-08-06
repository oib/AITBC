#!/usr/bin/env bash
# =============================================================================
# Test: per-suite watchdog timeout for the release gate (PILOT-60 / ABS-573)
# =============================================================================
# A SIGTERM-swallowing shipper child once hung the pre-release check for an HOUR
# because neither scripts/pre-release-check.sh nor tests/run-all.sh imposed a
# per-suite time budget ("no timeout/gtimeout found — running suites without a
# per-suite timeout" had stood as a warning for months). The fix is a
# bash-native watchdog (scripts/lib/run-with-timeout.sh) that both scripts use,
# so a wedged suite is a NAMED fail (exit 124) within budget, not an unbounded
# hang — and its whole process tree is reaped, leaving no survivor.
#
#   AC1: run_with_timeout returns the command's OWN exit code when it finishes
#        in time, and 124 when it overruns — within budget + grace, host has no
#        timeout(1)/gtimeout (the release host's condition).
#   AC2: a timed-out command leaves NO surviving descendant (the incident's
#        exact failure: a live child outliving its killed parent).
#   AC3 (falsification): tests/run-all.sh reports a deliberately hanging fixture
#        BY NAME as a timeout FAIL within budget, exits non-zero, no survivor.
#        scripts/pre-release-check.sh is structurally pinned to the same helper
#        (it is a ~20-min full release gate — not run end-to-end here; the shared
#        watchdog it calls is proven by AC1/AC2 above).
# =============================================================================

set -u
# PILOT-46: strip inherited backend/tracker env before any fixture runs.
# shellcheck source=tests/sandbox-guard.sh
. "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/sandbox-guard.sh"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
# shellcheck source=scripts/lib/run-with-timeout.sh
. "$REPO_ROOT/scripts/lib/run-with-timeout.sh"

GREEN='\033[0;32m'; RED='\033[0;31m'; CYAN='\033[0;36m'; NC='\033[0m'
PASS=0; FAIL=0; TOTAL=0

assert_eq() {
    TOTAL=$((TOTAL + 1))
    if [ "$1" = "$2" ]; then echo -e "  ${GREEN}PASS${NC} $3"; PASS=$((PASS + 1))
    else echo -e "  ${RED}FAIL${NC} $3 (expected: '$2', got: '$1')"; FAIL=$((FAIL + 1)); fi
}
assert_le() {
    TOTAL=$((TOTAL + 1))
    if [ "$1" -le "$2" ]; then echo -e "  ${GREEN}PASS${NC} $3 ($1 <= $2)"; PASS=$((PASS + 1))
    else echo -e "  ${RED}FAIL${NC} $3 (got $1 > $2)"; FAIL=$((FAIL + 1)); fi
}
assert_contains() {
    TOTAL=$((TOTAL + 1))
    if printf '%s' "$1" | grep -qF "$2"; then echo -e "  ${GREEN}PASS${NC} $3"; PASS=$((PASS + 1))
    else echo -e "  ${RED}FAIL${NC} $3 (missing: '$2')"; FAIL=$((FAIL + 1)); fi
}

WORK="$(mktemp -d "${TMPDIR:-/tmp}/pilot60-XXXXXX")"
cleanup() { rm -rf "$WORK"; }
trap cleanup EXIT
trap 'cleanup; exit 130' INT TERM

# ---------------------------------------------------------------------------
echo -e "${CYAN}=== AC1: run_with_timeout — own rc in time, 124 on overrun ===${NC}"
# ---------------------------------------------------------------------------
run_with_timeout 5 bash -c 'exit 7'; rc=$?
assert_eq "$rc" "7" "AC1: passes through the command's own exit code (7)"

run_with_timeout 5 bash -c 'sleep 1; exit 0'; rc=$?
assert_eq "$rc" "0" "AC1: a command that finishes within budget returns 0"

t0=$(date +%s)
run_with_timeout 2 bash -c 'sleep 987'; rc=$?
t1=$(date +%s)
assert_eq "$rc" "124" "AC1: an overrunning command returns 124 (GNU timeout code)"
assert_le "$((t1 - t0))" "15" "AC1: the timeout fires within budget + grace"

# ---------------------------------------------------------------------------
echo -e "${CYAN}=== AC2: a timed-out command leaves no surviving descendant ===${NC}"
# ---------------------------------------------------------------------------
PIDFILE="$WORK/child.pid"
cat > "$WORK/child.sh" <<EOF
#!/usr/bin/env bash
echo \$\$ > "$PIDFILE"
sleep 987
EOF
run_with_timeout 2 bash "$WORK/child.sh"; rc=$?
assert_eq "$rc" "124" "AC2: the hanging child run returns 124"
CHILD_PID="$(cat "$PIDFILE" 2>/dev/null || true)"
sleep 1  # let the KILL grace elapse
if [ -n "$CHILD_PID" ] && kill -0 "$CHILD_PID" 2>/dev/null; then
    survivor=1; kill -KILL "$CHILD_PID" 2>/dev/null || true
else
    survivor=0
fi
assert_eq "$survivor" "0" "AC2: no descendant survives the timeout (tree reaped)"

# ---------------------------------------------------------------------------
echo -e "${CYAN}=== AC3: run-all.sh names a hanging fixture as a timeout FAIL ===${NC}"
# ---------------------------------------------------------------------------
FX_DIR="$WORK/fx"; mkdir -p "$FX_DIR"
FX="$FX_DIR/test-hang-fixture.sh"
FX_PID="$WORK/fx.pid"
cat > "$FX" <<EOF
#!/usr/bin/env bash
# Deliberately wedged suite: writes its pid, then blocks forever.
echo \$\$ > "$FX_PID"
sleep 987
EOF

t0=$(date +%s)
out="$(RUN_ALL_SUITE_TIMEOUT=2 bash "$REPO_ROOT/tests/run-all.sh" "$FX" 2>&1)"; rc=$?
t1=$(date +%s)

# Non-zero exit: a hanging suite fails the run instead of hanging it.
TOTAL=$((TOTAL + 1))
if [ "$rc" -ne 0 ]; then echo -e "  ${GREEN}PASS${NC} AC3: run-all exits non-zero on a hanging suite (rc=$rc)"; PASS=$((PASS + 1))
else echo -e "  ${RED}FAIL${NC} AC3: run-all should exit non-zero on a hanging suite (rc=$rc)"; FAIL=$((FAIL + 1)); fi

assert_contains "$out" "test-hang-fixture.sh" "AC3: run-all names the offending suite"
assert_contains "$out" "TIMED OUT" "AC3: run-all labels the overrun as a timeout"
assert_le "$((t1 - t0))" "20" "AC3: run-all completes within budget + grace (no hang)"

FX_CHILD="$(cat "$FX_PID" 2>/dev/null || true)"
sleep 1
if [ -n "$FX_CHILD" ] && kill -0 "$FX_CHILD" 2>/dev/null; then
    fx_survivor=1; kill -KILL "$FX_CHILD" 2>/dev/null || true
else
    fx_survivor=0
fi
assert_eq "$fx_survivor" "0" "AC3: run-all leaves no surviving suite process"

# ---------------------------------------------------------------------------
echo -e "${CYAN}=== AC3: pre-release-check.sh is pinned to the shared watchdog ===${NC}"
# ---------------------------------------------------------------------------
PRC="$REPO_ROOT/scripts/pre-release-check.sh"
assert_contains "$(cat "$PRC")" "lib/run-with-timeout.sh" "AC3: pre-release-check sources the watchdog helper"
assert_contains "$(cat "$PRC")" "run_with_timeout \"\$SUITE_TIMEOUT\"" "AC3: pre-release-check runs suites under the budget"
# The stale "without a per-suite timeout" warning must be gone (the amplifier).
TOTAL=$((TOTAL + 1))
if grep -qF "without a per-suite timeout" "$PRC"; then
    echo -e "  ${RED}FAIL${NC} AC3: stale 'without a per-suite timeout' warning still present"; FAIL=$((FAIL + 1))
else
    echo -e "  ${GREEN}PASS${NC} AC3: the 'no per-suite timeout' warning is gone"; PASS=$((PASS + 1))
fi

# ---------------------------------------------------------------------------
echo ""
echo -e "${CYAN}=== Test summary ===${NC}"
if [ "$FAIL" -eq 0 ]; then
    echo -e "${GREEN}PASS${NC} $PASS/$TOTAL tests passed"
    exit 0
else
    echo -e "${RED}FAIL${NC} $FAIL/$TOTAL tests failed"
    exit 1
fi
