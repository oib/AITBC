#!/usr/bin/env bash
# =============================================================================
# Test: seat-independent merge chokepoint (PILOT-11 / twin ABS-513)
# =============================================================================
# harness/claude/hooks/pre-bash-merge-guard.sh is a PreToolUse Bash guard that
# routes EVERY seat `bb pr merge` / `glab mr merge` through
# scripts/merge-target-guard.sh BEFORE the merge reaches the git host — so a seat
# that skips the rte duty-step can no longer self-merge onto main (the MR !150
# defect class). This suite pins the AC contract:
#   AC1: a merge to main issued on the SKIP path (the seat never ran the duty-step)
#        is still REFUSED before the git host — the hook exits 2 (tool blocked, so
#        no merge call runs) and surfaces the guard's
#        `MERGE-GUARD-REFUSE … action=hitl-handoff` intent line.
#   AC2: a legit story-MR merge onto an epic branch (epic/*) with ORCH_AUTOMERGE=1
#        still succeeds through the chokepoint (hook exit 0, no false-positive).
#
# The hook resolves the MR/PR target via ORCH_MERGE_GUARD_TARGET_CMD (the
# host-agnostic test seam), so this suite needs no live bb/glab. bash 3.2 + BSD
# tools. Run from repo root: bash tests/test-merge-guard-chokepoint.sh
# =============================================================================
set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
HOOK="$REPO_ROOT/harness/claude/hooks/pre-bash-merge-guard.sh"

PASS=0; FAIL=0; TOTAL=0
GREEN='\033[0;32m'; RED='\033[0;31m'; CYAN='\033[0;36m'; NC='\033[0m'

# Resolver stubs (ignore the id arg, print a fixed target) — the injected test seam.
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT
printf '#!/usr/bin/env bash\necho main\n'                > "$TMP/resolve-main.sh"
printf '#!/usr/bin/env bash\necho epic/PILOT-11-guard\n' > "$TMP/resolve-epic.sh"
printf '#!/usr/bin/env bash\necho ""\n'                  > "$TMP/resolve-empty.sh"
chmod +x "$TMP"/resolve-*.sh

# Every run is a SEAT (ORCH_SEAT) with the guard reachable via CLAUDE_PROJECT_DIR.
seat_env() { echo "ORCH_SEAT=1 ORCH_ROLE=rte ORCH_TICKET=PILOT-11 CLAUDE_PROJECT_DIR=$REPO_ROOT"; }

# Feed a Bash command to the hook as a PreToolUse JSON payload. Extra leading
# KEY=VAL tokens set env for this invocation only. Captures stderr for intent-line
# assertions; returns the hook's exit code.
HOOK_OUT=""
run_hook() {
    local env_kv=() cmd
    while [ $# -gt 1 ]; do env_kv+=("$1"); shift; done
    cmd="$1"
    local payload; payload=$(jq -nc --arg c "$cmd" '{tool_input:{command:$c}}')
    local rc=0
    # seat_env is INTENTIONALLY word-split into multiple KEY=VAL tokens for env.
    # shellcheck disable=SC2046
    HOOK_OUT="$(printf '%s' "$payload" | env $(seat_env) "${env_kv[@]}" bash "$HOOK" 2>&1)" || rc=$?
    return $rc
}

assert_rc() {
    local expected="$1" label="$2"; shift 2
    local rc=0; run_hook "$@" || rc=$?
    TOTAL=$((TOTAL + 1))
    if [ "$rc" = "$expected" ]; then echo -e "  ${GREEN}PASS${NC} $label"; PASS=$((PASS + 1))
    else echo -e "  ${RED}FAIL${NC} $label (expected exit '$expected', got '$rc'; out: $HOOK_OUT)"; FAIL=$((FAIL + 1)); fi
}

assert_intent_line() {
    local label="$1"; shift
    run_hook "$@" || true
    TOTAL=$((TOTAL + 1))
    if printf '%s' "$HOOK_OUT" | grep -q 'MERGE-GUARD-REFUSE .*action=hitl-handoff'; then
        echo -e "  ${GREEN}PASS${NC} $label"; PASS=$((PASS + 1))
    else echo -e "  ${RED}FAIL${NC} $label (no MERGE-GUARD-REFUSE intent line; out: $HOOK_OUT)"; FAIL=$((FAIL + 1)); fi
}

echo -e "${CYAN}=== PILOT-11 merge chokepoint (pre-bash-merge-guard.sh) ===${NC}\n"

# =============================================================================
echo -e "${CYAN}A. AC1 — skip path: a main-targeted merge is BLOCKED before the git host${NC}"
# =============================================================================
# The seat never ran `merge-target-guard.sh` itself; the chokepoint runs it anyway.
assert_rc 2 "bb pr merge -> main -> BLOCK (exit 2, no merge call)" \
    "ORCH_MERGE_GUARD_TARGET_CMD=$TMP/resolve-main.sh" "bb pr merge 150"
assert_intent_line "bb pr merge -> main -> surfaces MERGE-GUARD-REFUSE … action=hitl-handoff" \
    "ORCH_MERGE_GUARD_TARGET_CMD=$TMP/resolve-main.sh" "bb pr merge 150"
assert_rc 2 "glab mr merge -> main -> BLOCK (exit 2, no merge call)" \
    "ORCH_MERGE_GUARD_TARGET_CMD=$TMP/resolve-main.sh" "glab mr merge 150"
assert_intent_line "glab mr merge -> main -> surfaces MERGE-GUARD-REFUSE … action=hitl-handoff" \
    "ORCH_MERGE_GUARD_TARGET_CMD=$TMP/resolve-main.sh" "glab mr merge 150"
# The MR !150 form verbatim: a raw self-merge to main is stopped.
assert_rc 2 "glab mr merge 150 (the MR !150 form) -> BLOCK" \
    "ORCH_MERGE_GUARD_TARGET_CMD=$TMP/resolve-main.sh" "glab mr merge 150 --yes"

# =============================================================================
echo -e "\n${CYAN}B. AC2 — legit epic merge with ORCH_AUTOMERGE=1 passes the chokepoint${NC}"
# =============================================================================
assert_rc 0 "glab mr merge -> epic/* + ORCH_AUTOMERGE=1 -> ALLOW (exit 0)" \
    "ORCH_MERGE_GUARD_TARGET_CMD=$TMP/resolve-epic.sh" "ORCH_AUTOMERGE=1" "glab mr merge 42"
assert_rc 0 "bb pr merge -> epic/* + ORCH_AUTOMERGE=1 -> ALLOW (exit 0)" \
    "ORCH_MERGE_GUARD_TARGET_CMD=$TMP/resolve-epic.sh" "ORCH_AUTOMERGE=1" "bb pr merge 42"

# =============================================================================
echo -e "\n${CYAN}C. Invariance — the ORCH_AUTOMERGE knob never changes the decision${NC}"
# =============================================================================
# main stays REFUSED in every knob state; a knob claim never buys a main merge.
assert_rc 2 "main, ORCH_AUTOMERGE=1 -> BLOCK" \
    "ORCH_MERGE_GUARD_TARGET_CMD=$TMP/resolve-main.sh" "ORCH_AUTOMERGE=1" "glab mr merge 1"
assert_rc 2 "main, ORCH_AUTOMERGE=0 -> BLOCK" \
    "ORCH_MERGE_GUARD_TARGET_CMD=$TMP/resolve-main.sh" "ORCH_AUTOMERGE=0" "glab mr merge 1"
# epic stays ALLOWED even with the knob unset.
assert_rc 0 "epic/*, ORCH_AUTOMERGE unset -> ALLOW" \
    "ORCH_MERGE_GUARD_TARGET_CMD=$TMP/resolve-epic.sh" "glab mr merge 1"

# =============================================================================
echo -e "\n${CYAN}D. Scope — only the merge subcommand is intercepted${NC}"
# =============================================================================
# A resolver that would say 'main' is present, but these are NOT merge calls.
assert_rc 0 "bb pr view (not a merge) -> ALLOW untouched" \
    "ORCH_MERGE_GUARD_TARGET_CMD=$TMP/resolve-main.sh" "bb pr view 150"
assert_rc 0 "glab mr create (not a merge) -> ALLOW untouched" \
    "ORCH_MERGE_GUARD_TARGET_CMD=$TMP/resolve-main.sh" "glab mr create --fill"
assert_rc 0 "git status (not a merge) -> ALLOW untouched" \
    "ORCH_MERGE_GUARD_TARGET_CMD=$TMP/resolve-main.sh" "git status --short"

# =============================================================================
echo -e "\n${CYAN}E. Context + fail-closed + kill switch${NC}"
# =============================================================================
# Human shell (no seat markers) is NEVER guarded — full operator authority.
TOTAL=$((TOTAL + 1))
rc=0
printf '%s' "$(jq -nc '{tool_input:{command:"glab mr merge 1"}}')" \
    | env -u ORCH_SEAT -u ORCH_TICKET -u ORCH_ROLE \
        "ORCH_MERGE_GUARD_TARGET_CMD=$TMP/resolve-main.sh" CLAUDE_PROJECT_DIR="$REPO_ROOT" \
        bash "$HOOK" >/dev/null 2>&1 || rc=$?
if [ "$rc" = "0" ]; then echo -e "  ${GREEN}PASS${NC} human shell (no ORCH_SEAT) -> never guarded (exit 0)"; PASS=$((PASS + 1))
else echo -e "  ${RED}FAIL${NC} human shell -> expected exit 0, got '$rc'"; FAIL=$((FAIL + 1)); fi

# Unresolvable target -> fail CLOSED on the merge boundary.
assert_rc 2 "merge with UNRESOLVABLE target -> fail closed (exit 2)" \
    "ORCH_MERGE_GUARD_TARGET_CMD=$TMP/resolve-empty.sh" "glab mr merge 9"
# Kill switch drops the guard entirely.
assert_rc 0 "ORCH_MERGE_GUARD=0 -> merge to main allowed (legacy, exit 0)" \
    "ORCH_MERGE_GUARD=0" "ORCH_MERGE_GUARD_TARGET_CMD=$TMP/resolve-main.sh" "glab mr merge 1"

# =============================================================================
echo -e "\n${CYAN}=== Results ===${NC}"
echo -e "  Total:  $TOTAL"
echo -e "  ${GREEN}Passed: $PASS${NC}"
[ "$FAIL" -gt 0 ] && echo -e "  ${RED}Failed: $FAIL${NC}" || echo -e "  Failed: 0"
[ "$FAIL" -eq 0 ] || exit 1
echo -e "\n${GREEN}All merge-guard chokepoint tests passed.${NC}"
