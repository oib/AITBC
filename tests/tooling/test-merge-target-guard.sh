#!/usr/bin/env bash
# =============================================================================
# Test: mechanical RTE merge-target guard (PILOT-10 / twin ABS-513)
# =============================================================================
# scripts/merge-target-guard.sh refuses ANY merge whose target is a protected
# branch (main), independent of ORCH_AUTOMERGE. Auto-merge stays legitimate ONLY
# for story MRs onto an epic integration branch. This suite pins the AC contract:
#   AC1: target main + ORCH_AUTOMERGE=1 -> REFUSE + HITL + intent line;
#        target epic/* + ORCH_AUTOMERGE=1 -> ALLOW (auto-merge still permitted).
#   AC2: the refuse decision is the SAME whether ORCH_AUTOMERGE is unset, empty,
#        or =1 — a seat's claim about the knob never buys a main merge.
#
# Self-contained (no git repo, no fixed paths). bash 3.2 + BSD tools.
# Run from repo root: bash tests/tooling/test-merge-target-guard.sh
# =============================================================================
set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
GUARD="$REPO_ROOT/scripts/merge-target-guard.sh"

PASS=0; FAIL=0; TOTAL=0
GREEN='\033[0;32m'; RED='\033[0;31m'; CYAN='\033[0;36m'; NC='\033[0m'

# Assert the guard's EXIT CODE (the contract is the exit code). Extra args after
# the label are the command; the caller sets any env inline (e.g. ORCH_AUTOMERGE=1).
assert_rc() {
    local expected="$1" label="$2"; shift 2
    local rc=0
    "$@" >/dev/null 2>&1 || rc=$?
    TOTAL=$((TOTAL + 1))
    if [ "$rc" = "$expected" ]; then echo -e "  ${GREEN}PASS${NC} $label"; PASS=$((PASS + 1))
    else echo -e "  ${RED}FAIL${NC} $label (expected exit '$expected', got '$rc')"; FAIL=$((FAIL + 1)); fi
}

# Assert the guard prints the machine-greppable intent line on refuse.
assert_intent_line() {
    local label="$1"; shift
    local out; out="$("$@" 2>/dev/null || true)"
    TOTAL=$((TOTAL + 1))
    if printf '%s' "$out" | grep -q 'MERGE-GUARD-REFUSE .*action=hitl-handoff'; then
        echo -e "  ${GREEN}PASS${NC} $label"; PASS=$((PASS + 1))
    else echo -e "  ${RED}FAIL${NC} $label (no MERGE-GUARD-REFUSE intent line; got: $out)"; FAIL=$((FAIL + 1)); fi
}

echo -e "${CYAN}=== RTE merge-target guard (PILOT-10) ===${NC}\n"

# =============================================================================
echo -e "${CYAN}A. AC1 — main refused, epic allowed, both with ORCH_AUTOMERGE=1${NC}"
# =============================================================================
assert_rc 1 "target main + ORCH_AUTOMERGE=1 -> REFUSE (exit 1)" \
    env ORCH_AUTOMERGE=1 bash "$GUARD" check main
assert_intent_line "target main -> prints MERGE-GUARD-REFUSE ... action=hitl-handoff (intent line)" \
    env ORCH_AUTOMERGE=1 bash "$GUARD" check main
assert_rc 0 "target epic/PILOT-10-x + ORCH_AUTOMERGE=1 -> ALLOW (exit 0)" \
    env ORCH_AUTOMERGE=1 bash "$GUARD" check "epic/PILOT-10-guard"
# origin/main and refs/heads/main normalise to the bare protected name.
assert_rc 1 "target origin/main -> REFUSE (normalised, exit 1)" \
    env ORCH_AUTOMERGE=1 bash "$GUARD" check origin/main
assert_rc 1 "target refs/heads/main -> REFUSE (normalised, exit 1)" \
    bash "$GUARD" check refs/heads/main
# master is protected by the shared default too.
assert_rc 1 "target master -> REFUSE (default protected set, exit 1)" \
    bash "$GUARD" check master

# =============================================================================
echo -e "\n${CYAN}B. AC2 — refuse is invariant across every ORCH_AUTOMERGE state${NC}"
# =============================================================================
assert_rc 1 "main, ORCH_AUTOMERGE unset -> REFUSE (exit 1)" \
    env -u ORCH_AUTOMERGE bash "$GUARD" check main
assert_rc 1 "main, ORCH_AUTOMERGE='' (empty) -> REFUSE (exit 1)" \
    env ORCH_AUTOMERGE= bash "$GUARD" check main
assert_rc 1 "main, ORCH_AUTOMERGE=1 -> REFUSE (exit 1)" \
    env ORCH_AUTOMERGE=1 bash "$GUARD" check main
assert_rc 1 "main, ORCH_AUTOMERGE=0 -> REFUSE (exit 1)" \
    env ORCH_AUTOMERGE=0 bash "$GUARD" check main
# Symmetric invariance on the allow side: epic target passes in every knob state.
assert_rc 0 "epic/*, ORCH_AUTOMERGE unset -> ALLOW (exit 0)" \
    env -u ORCH_AUTOMERGE bash "$GUARD" check "epic/ABS-000-integration"

# =============================================================================
echo -e "\n${CYAN}C. operator override + bad input${NC}"
# =============================================================================
# Operators can narrow/extend the protected set via the shared knob.
assert_rc 1 "custom ORCH_PROTECTED_BRANCHES catches 'trunk' -> REFUSE (exit 1)" \
    env ORCH_PROTECTED_BRANCHES="main trunk" bash "$GUARD" check trunk
assert_rc 0 "custom set excludes 'master' -> ALLOW (exit 0)" \
    env ORCH_PROTECTED_BRANCHES="main" bash "$GUARD" check master
assert_rc 64 "missing target -> exit 64 (usage, fails closed on bad input)" \
    bash "$GUARD" check
assert_rc 64 "unknown subcommand -> exit 64" \
    bash "$GUARD" bogus

# =============================================================================
echo -e "\n${CYAN}=== Results ===${NC}"
echo -e "  Total:  $TOTAL"
echo -e "  ${GREEN}Passed: $PASS${NC}"
[ "$FAIL" -gt 0 ] && echo -e "  ${RED}Failed: $FAIL${NC}" || echo -e "  Failed: 0"
[ "$FAIL" -eq 0 ] || exit 1
echo -e "\n${GREEN}All merge-target-guard tests passed.${NC}"
