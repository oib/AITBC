#!/usr/bin/env bash
# =============================================================================
# ABS-307 — implementer agent-defs must declare a v3-conformant exit status
# =============================================================================
# be-developer / fe-developer / data-engineer once declared an Exit State of
# "Ready for QAS" — a status that exists in NO v3 pipeline
# (profiles/neutral/adapters/statuses.yaml). Seats then improvised illegal
# transitions (In Progress -> Done, stranding an unmerged branch behind a Done
# status; consumer BUSCH-97, 2026-07-14). This lint anchors the fix: the
# canonical exit status each implementer def declares must be a real
# statuses.yaml name, must be one of the allowed implementer exits
# {In Review, Merging}, and must never be "Ready for QAS", "In Test" or "Done".
# Red on reintroduction of "Ready for QAS".
#
# Scope (ticket ABS-307): the THREE implementer defs only. Design seats
# (ui-ux-design, qas-design) use handoff-label semantics that are out of scope
# here and deliberately not linted.
#
# Bash 3.2 / BSD-safe. Run from repo root: bash tests/tooling/test-agent-def-exit-state.sh
# =============================================================================
set -u

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
STATUSES="$REPO_ROOT/profiles/neutral/adapters/statuses.yaml"

GREEN='\033[0;32m'; RED='\033[0;31m'; CYAN='\033[0;36m'; NC='\033[0m'
PASS=0; FAIL=0; TOTAL=0
assert_eq() {
    TOTAL=$((TOTAL + 1))
    if [ "$1" = "$2" ]; then echo -e "  ${GREEN}PASS${NC} $3"; PASS=$((PASS + 1))
    else echo -e "  ${RED}FAIL${NC} $3\n    expected: $2\n    got:      $1"; FAIL=$((FAIL + 1)); fi
}

# The def dirs that ship the implementer roles: the harness SOURCE and the
# claude_code provider mirror. Both must stay v3-conformant (mirror parity).
DEF_DIRS="$REPO_ROOT/harness/claude/agents $REPO_ROOT/agent_providers/claude_code/prompts"
IMPLEMENTERS="be-developer fe-developer data-engineer"

# Valid status names, one per line, from statuses.yaml (`  - name: X`).
valid_statuses() { sed -n 's/^[[:space:]]*-[[:space:]]*name:[[:space:]]*//p' "$STATUSES"; }
is_valid_status() { valid_statuses | grep -qxF -- "$1"; }

# Extract the FIRST backtick-quoted token from the "Exit status (canonical)"
# line of a def (the declared exit status).
declared_exit_status() {
    grep -m1 'Exit status (canonical)' "$1" 2>/dev/null \
        | sed -n 's/.*Exit status (canonical)[^`]*`\([^`]*\)`.*/\1/p'
}

echo -e "${CYAN}ABS-307 — implementer exit-state declarations are v3-conformant${NC}"

# Sanity: "Ready for QAS" must NOT be a real status (the whole premise).
if is_valid_status "Ready for QAS"; then _rq=1; else _rq=0; fi
assert_eq "$_rq" "0" "ABS-307: 'Ready for QAS' is not a status in statuses.yaml (premise holds)"

for _dir in $DEF_DIRS; do
    for _role in $IMPLEMENTERS; do
        _f="$_dir/$_role.md"
        [ -f "$_f" ] || continue
        _rel="${_f#$REPO_ROOT/}"

        _exit="$(declared_exit_status "$_f")"
        # AC1: a canonical exit status is declared and is a real v3 status.
        if [ -n "$_exit" ] && is_valid_status "$_exit"; then _r=0; else _r=1; fi
        assert_eq "$_r" "0" "$_rel: declares a canonical exit status that exists in statuses.yaml (got: '${_exit:-<none>}')"

        # AC2: it is one of the allowed implementer exits — never Done/In Test/RfQAS.
        case "$_exit" in
            "In Review"|"Merging") _r=0 ;;
            *) _r=1 ;;
        esac
        assert_eq "$_r" "0" "$_rel: canonical exit status is an allowed implementer exit (In Review|Merging)"

        # AC1/AC3 regression shapes: the def must not RE-DECLARE an illegal exit.
        if grep -Eq 'Exit (status \(canonical\)\*\*|State)[^`"]*[`"]Ready for QAS[`"]' "$_f"; then _r=1; else _r=0; fi
        assert_eq "$_r" "0" "$_rel: does NOT declare 'Ready for QAS' as an exit state (ABS-307 regression guard)"
        if grep -Eq 'Exit (status \(canonical\)\*\*|State)[^`"]*[`"]Done[`"]' "$_f"; then _r=1; else _r=0; fi
        assert_eq "$_r" "0" "$_rel: does NOT declare 'Done' as an implementer exit state (ADR-A-0005/ABS-211)"
    done
done

echo -e "\n${CYAN}=== Results ===${NC}"
echo -e "  Total: $TOTAL  ${GREEN}Pass: $PASS${NC}  ${RED}Fail: $FAIL${NC}"
[ "$FAIL" -eq 0 ] && echo -e "  ${GREEN}ALL TESTS PASSED${NC}" || exit 1
