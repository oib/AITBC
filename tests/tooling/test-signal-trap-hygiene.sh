#!/usr/bin/env bash
# =============================================================================
# Test: signal-trap hygiene audit (PILOT-60 / ABS-573, AC2)
# =============================================================================
# A signal trap that only cleans up and RETURNS lets bash resume the interrupted
# code instead of terminating — so the process ignores SIGTERM. That is exactly
# how scripts/backend-shipper.sh once swallowed SIGTERM and hung the release
# gate for an hour: `trap '<cleanup>' EXIT INT TERM` with a handler that never
# called `exit`.
#
# This is the standing regression guard for that class. It scans every shell
# script under scripts/ and tests/ and fails when a `trap` statement:
#
#   (a) lists EXIT together with INT/TERM in a SINGLE statement — a handler
#       cannot both `exit` on a signal AND merely return on normal EXIT, so the
#       two concerns MUST be separate traps; or
#   (b) traps INT/TERM but carries no explicit `exit` in the statement — the
#       returning-handler defect itself.
#
# The fix in both cases: split the traps and make the signal handler exit, e.g.
#     trap cleanup EXIT
#     trap 'cleanup; exit 130' INT TERM
# =============================================================================

set -u

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
# This entrypoint names backend-shipper.sh (its motivating incident), so the
# mechanical sandbox-guard-check requires it to source the guard. Harmless here
# (nothing is executed against the backend) — it only strips inherited env.
. "$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)/sandbox-guard.sh"

GREEN='\033[0;32m'; RED='\033[0;31m'; CYAN='\033[0;36m'; NC='\033[0m'
PASS=0; FAIL=0; TOTAL=0

echo -e "${CYAN}=== signal-trap hygiene: no returning INT/TERM handler ===${NC}"

# A signal appears as a bare word after the trap body. Bodies in this repo carry
# `exit`/`kill`/`rm` in lowercase, never the uppercase signal NAMES, so matching
# the uppercase words distinguishes a signal list from a handler body cleanly.
sig_re='(^|[[:space:]])(INT|TERM)([[:space:]]|$)'
exit_sig_re='(^|[[:space:]])EXIT([[:space:]]|$)'

offenders=""
# Only real `trap` STATEMENTS (line begins with optional indent then `trap `),
# which excludes the many comments that quote the antipattern for documentation.
while IFS= read -r hit; do
    [ -z "$hit" ] && continue
    file="${hit%%:*}"; rest="${hit#*:}"; lineno="${rest%%:*}"; content="${rest#*:}"
    rel="${file#"$REPO_ROOT"/}"

    # Not a signal trap -> irrelevant (EXIT-only cleanup traps are correct).
    printf '%s' "$content" | grep -qE "$sig_re" || continue

    if printf '%s' "$content" | grep -qE "$exit_sig_re"; then
        offenders+="  ${rel}:${lineno}  EXIT combined with INT/TERM in one trap — split them"$'\n'
    elif ! printf '%s' "$content" | grep -q 'exit'; then
        offenders+="  ${rel}:${lineno}  INT/TERM handler has no explicit 'exit' — it would only return"$'\n'
    fi
done < <(grep -rnE '^[[:space:]]*trap[[:space:]]' "$REPO_ROOT/scripts" "$REPO_ROOT/tests" --include='*.sh' 2>/dev/null)

TOTAL=$((TOTAL + 1))
if [ -z "$offenders" ]; then
    echo -e "  ${GREEN}PASS${NC} every INT/TERM trap under scripts/ and tests/ exits (and is split from EXIT)"
    PASS=$((PASS + 1))
else
    echo -e "  ${RED}FAIL${NC} returning / combined signal trap(s) found:"
    printf '%s' "$offenders"
    FAIL=$((FAIL + 1))
fi

# Self-check: the guard must actually recognise a bad trap (a green test that can
# never go red is worthless). Feed it a synthetic offending line.
echo -e "${CYAN}=== self-check: the guard catches a known-bad trap ===${NC}"
bad="trap 'rm -f x' EXIT INT TERM"
TOTAL=$((TOTAL + 1))
if printf '%s' "$bad" | grep -qE "$sig_re" && printf '%s' "$bad" | grep -qE "$exit_sig_re"; then
    echo -e "  ${GREEN}PASS${NC} 'trap ... EXIT INT TERM' is recognised as the antipattern"
    PASS=$((PASS + 1))
else
    echo -e "  ${RED}FAIL${NC} guard failed to recognise the antipattern"
    FAIL=$((FAIL + 1))
fi

echo ""
echo -e "${CYAN}=== Test summary ===${NC}"
if [ "$FAIL" -eq 0 ]; then
    echo -e "${GREEN}PASS${NC} $PASS/$TOTAL tests passed"
    exit 0
else
    echo -e "${RED}FAIL${NC} $FAIL/$TOTAL tests failed"
    exit 1
fi
