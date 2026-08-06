#!/bin/bash
# =============================================================================
# Test: Shadow Dual-Write Tracker Shim (epic ABS-326, story ABS-327)
# =============================================================================
# Offline test for scripts/shadow-tracker.sh against STUB primary/mirror
# adapters (no Jira, no backend, no docker): asserts the shim's whole
# contract —
#   1. byte-identical stdout + exit-code passthrough of the primary adapter
#      (success and failure),
#   2. mutating ops are mirrored verbatim, read ops and `events` are not,
#   3. a failed primary op is never mirrored,
#   4. a dead/failing mirror changes NOTHING for the caller and lands in the
#      mirror log in replay format (AC: blast radius zero),
#   5. the replay line round-trips: eval'ing the text after " -- " reproduces
#      the exact argv, including multi-line bodies (%q quoting),
#   6. create key parity: a mirror key mismatch is logged, a match is not.
#
# Run from repo root: bash tests/tooling/test-shadow-tracker.sh
# =============================================================================

set -u

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
SHIM="$REPO_ROOT/scripts/shadow-tracker.sh"

TEST_DIR=$(mktemp -d /tmp/shadow-tracker-test-XXXXXX)
trap 'rm -rf "$TEST_DIR"' EXIT

PASS=0; FAIL=0; TOTAL=0
GREEN='\033[0;32m'; RED='\033[0;31m'; CYAN='\033[0;36m'; NC='\033[0m'

assert_eq() {
    local actual="$1" expected="$2" label="$3"
    TOTAL=$((TOTAL + 1))
    if [ "$actual" = "$expected" ]; then
        echo -e "  ${GREEN}PASS${NC} $label"; PASS=$((PASS + 1))
    else
        echo -e "  ${RED}FAIL${NC} $label"
        echo "        expected: $(printf '%q' "$expected")"
        echo "        actual:   $(printf '%q' "$actual")"
        FAIL=$((FAIL + 1))
    fi
}

assert_true() {
    local code="$1" label="$2"
    TOTAL=$((TOTAL + 1))
    if [ "$code" = "0" ]; then
        echo -e "  ${GREEN}PASS${NC} $label"; PASS=$((PASS + 1))
    else
        echo -e "  ${RED}FAIL${NC} $label"; FAIL=$((FAIL + 1))
    fi
}

# --- Stub adapters ------------------------------------------------------------
# Primary: prints a canned multi-line body (trailing-newline-sensitive), a
# stderr line, exits with $STUB_PRIMARY_RC; records its argv %q-quoted.
PRIMARY="$TEST_DIR/stub-primary.sh"
cat > "$PRIMARY" <<'EOF'
#!/bin/bash
{ for a in "$@"; do printf '%q ' "$a"; done; echo; } >> "$STUB_PRIMARY_CALLS"
if [ "${1:-}" = "create" ]; then
    printf '%s\n' "$STUB_PRIMARY_CREATE_KEY"
else
    printf 'line-1 of %s\nline-2\tand a tab\n' "${1:-}"
fi
echo "primary-stderr-marker" >&2
exit "${STUB_PRIMARY_RC:-0}"
EOF
chmod +x "$PRIMARY"

# Mirror: records argv, prints $STUB_MIRROR_CREATE_KEY on create, exits with
# $STUB_MIRROR_RC (writing a diagnostic to stderr when failing).
MIRROR="$TEST_DIR/stub-mirror.sh"
cat > "$MIRROR" <<'EOF'
#!/bin/bash
{ for a in "$@"; do printf '%q ' "$a"; done; echo; } >> "$STUB_MIRROR_CALLS"
[ "${1:-}" != "create" ] || printf '%s\n' "${STUB_MIRROR_CREATE_KEY:-}"
if [ "${STUB_MIRROR_RC:-0}" != "0" ]; then
    echo "mirror-diagnostic: backend unreachable" >&2
fi
exit "${STUB_MIRROR_RC:-0}"
EOF
chmod +x "$MIRROR"

export SHADOW_PRIMARY_CMD="$PRIMARY"
export SHADOW_MIRROR_CMD="$MIRROR"
export SHADOW_MIRROR_LOG="$TEST_DIR/mirror.log"
export STUB_PRIMARY_CALLS="$TEST_DIR/primary-calls.txt"
export STUB_MIRROR_CALLS="$TEST_DIR/mirror-calls.txt"
export STUB_PRIMARY_CREATE_KEY="ABS-901"
export STUB_MIRROR_CREATE_KEY="ABS-901"
export STUB_PRIMARY_RC=0
export STUB_MIRROR_RC=0

reset_state() {
    : > "$STUB_PRIMARY_CALLS"; : > "$STUB_MIRROR_CALLS"; rm -f "$SHADOW_MIRROR_LOG"
    export STUB_PRIMARY_RC=0 STUB_MIRROR_RC=0
    export STUB_PRIMARY_CREATE_KEY="ABS-901" STUB_MIRROR_CREATE_KEY="ABS-901"
}

mirror_calls() { [ -f "$STUB_MIRROR_CALLS" ] && wc -l < "$STUB_MIRROR_CALLS" | tr -d ' ' || echo 0; }

echo -e "${CYAN}=== shadow-tracker.sh — dual-write shim (ABS-327) ===${NC}\n"

# --- 1. Byte-identical passthrough (success) ----------------------------------
echo -e "${CYAN}[1] passthrough byte-identity + exit codes${NC}"
reset_state
direct_out="$("$PRIMARY" get ABS-1 2>/dev/null)"
shim_out="$(bash "$SHIM" get ABS-1 2>"$TEST_DIR/err1")"
ec=$?
assert_eq "$shim_out" "$direct_out" "get stdout byte-identical to the primary adapter"
assert_eq "$ec" 0 "get exit code 0 passed through"
assert_eq "$(cat "$TEST_DIR/err1")" "primary-stderr-marker" "primary stderr passes through untouched"

reset_state
export STUB_PRIMARY_RC=3
bash "$SHIM" search --status Backlog >/dev/null 2>&1
assert_eq "$?" 3 "non-zero primary exit code passed through unchanged"

# --- 2. Mutating ops mirrored, read ops not ------------------------------------
echo -e "\n${CYAN}[2] mirror routing: mutating vs read ops${NC}"
reset_state
bash "$SHIM" comment ABS-1 --kind gate-results --actor qas --body "all green" >/dev/null 2>&1
assert_eq "$(mirror_calls)" 1 "comment (mutating) reaches the mirror"
assert_eq "$(tail -n1 "$STUB_MIRROR_CALLS")" "$(tail -n1 "$STUB_PRIMARY_CALLS")" \
    "mirror receives the verbatim primary argv"

reset_state
for op in get search children parent child-count events; do
    bash "$SHIM" "$op" ABS-1 >/dev/null 2>&1
done
assert_eq "$(mirror_calls)" 0 "read ops + events are NOT mirrored"

reset_state
export STUB_PRIMARY_RC=1
bash "$SHIM" transition ABS-1 Doing --actor dev --reason go >/dev/null 2>&1
assert_eq "$(mirror_calls)" 0 "failed primary op is never mirrored"

# --- 3. Dead mirror: blast radius zero + replay log -----------------------------
echo -e "\n${CYAN}[3] mirror failure: caller unaffected, replay log written${NC}"
reset_state
export STUB_MIRROR_RC=7
direct_out="$(STUB_PRIMARY_CALLS=/dev/null "$PRIMARY" comment ABS-2 --kind handoff --actor dev --body ok 2>/dev/null)"
shim_out="$(bash "$SHIM" comment ABS-2 --kind handoff --actor dev --body ok 2>"$TEST_DIR/err3")"
ec=$?
assert_eq "$ec" 0 "exit code unchanged by the failing mirror"
assert_eq "$shim_out" "$direct_out" "stdout unchanged by the failing mirror"
assert_eq "$(cat "$TEST_DIR/err3")" "primary-stderr-marker" "no mirror noise on the caller's stderr"
assert_true "$([ -f "$SHADOW_MIRROR_LOG" ] && grep -q 'rc=7 -- comment ABS-2' "$SHADOW_MIRROR_LOG"; echo $?)" \
    "missed op logged with mirror exit code in replay format"
assert_true "$(grep -q '^#   mirror-diagnostic' "$SHADOW_MIRROR_LOG"; echo $?)" \
    "mirror stderr captured as commented context lines"

# Missing mirror binary: same guarantees.
reset_state
SHADOW_MIRROR_CMD="$TEST_DIR/nonexistent.sh" bash "$SHIM" comment ABS-3 --kind skip --actor po --body x >/dev/null 2>&1
assert_eq "$?" 0 "missing mirror binary: caller still succeeds"
assert_true "$(grep -q 'rc=127 -- comment ABS-3' "$SHADOW_MIRROR_LOG"; echo $?)" \
    "missing mirror binary logged as rc=127"

# --- 4. Replay round-trip (incl. multi-line body) --------------------------------
echo -e "\n${CYAN}[4] replay format round-trips the exact argv${NC}"
reset_state
export STUB_MIRROR_RC=9
body=$'first line\nsecond "quoted" line\ttabbed'
bash "$SHIM" comment ABS-4 --kind decision --actor po --body "$body" >/dev/null 2>&1
missed_argv_line="$(tail -n1 "$STUB_PRIMARY_CALLS")"   # ground truth argv
replay_text="$(grep ' -- comment ABS-4' "$SHADOW_MIRROR_LOG" | sed 's/^.* -- //')"
: > "$STUB_MIRROR_CALLS"
export STUB_MIRROR_RC=0
eval "\"$MIRROR\" $replay_text" >/dev/null 2>&1
assert_eq "$(tail -n1 "$STUB_MIRROR_CALLS")" "$missed_argv_line" \
    "eval of the logged replay text reproduces the exact argv (multi-line body survives)"

# --- 5. create key parity ---------------------------------------------------------
echo -e "\n${CYAN}[5] create key-parity check${NC}"
reset_state
out="$(bash "$SHIM" create --type ticket --title "T" 2>/dev/null)"
assert_eq "$out" "ABS-901" "create passes the primary's new id through"
if [ -f "$SHADOW_MIRROR_LOG" ]; then no_log=1; else no_log=0; fi
assert_true "$no_log" "matching keys: nothing logged"

reset_state
export STUB_MIRROR_CREATE_KEY="ABS-777"
bash "$SHIM" create --type ticket --title "T" >/dev/null 2>&1
assert_true "$(grep -q 'key-mismatch primary=ABS-901 mirror=ABS-777 -- create' "$SHADOW_MIRROR_LOG"; echo $?)" \
    "key mismatch logged with both keys"

# --- Summary --------------------------------------------------------------------
echo ""
if [ "$FAIL" -gt 0 ]; then
    echo -e "${RED}$FAIL of $TOTAL assertions failed${NC} ($PASS passed)"
    exit 1
else
    echo -e "${GREEN}All $TOTAL assertions passed${NC}"
    exit 0
fi
