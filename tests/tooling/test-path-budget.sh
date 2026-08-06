#!/bin/bash
# =============================================================================
# Test: repo-relative path budget (ABS-276)
# =============================================================================
# Windows (Git for Windows) uses the ANSI Win32 API unless `core.longpaths=true`
# is set, so a full path over MAX_PATH (260 chars) SILENTLY fails to check out:
# git reports success, the file never lands, and `git status` shows it as
# deleted. A consumer hit exactly this on a v2.21.2 -> v2.25.0 migration.
#
# The absolute path is what blows the limit, and only part of it is ours:
#
#   C:\...\<clone>\ .claude\worktrees\<TICKET>-auto\ <tracked path>
#   \_ parent (theirs) _/ \_ worktree prefix (ours) _/ \_ budget (ours) _/
#
# Budget derivation (PATH_BUDGET below):
#   260  Windows MAX_PATH
#   - 32  deepest checkout surface WE create: `.claude/worktrees/<TICKET>-auto/`
#         (the orchestrator checks the full tree out again inside each worktree)
#   -128  reserved for the consumer's clone parent, e.g.
#         `C:\Users\<user>\<...>\agentic-development-boilerplate\`
#   = 100  chars available for a repo-relative tracked path
#
# This guard keeps the part we control inside that budget. It does NOT make deep
# parent directories safe — nothing in-repo can — which is why `core.longpaths`
# is documented as a Windows prerequisite in SETUP.md and the migration SOP.
#
# Run from repo root: bash tests/test-path-budget.sh
# =============================================================================
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

PATH_BUDGET="${PATH_BUDGET:-100}"

PASS=0; FAIL=0; TOTAL=0
GREEN='\033[0;32m'; RED='\033[0;31m'; CYAN='\033[0;36m'; NC='\033[0m'

ok()   { echo -e "  ${GREEN}PASS${NC} $1"; PASS=$((PASS + 1)); TOTAL=$((TOTAL + 1)); }
bad()  { echo -e "  ${RED}FAIL${NC} $1"; FAIL=$((FAIL + 1)); TOTAL=$((TOTAL + 1)); }

# The lint itself: read paths on stdin, print every one over $1 chars as
# "<length> <path>". Exits 0 always; callers judge by whether output is empty.
over_budget() { awk -v max="$1" 'length($0) > max { print length($0), $0 }'; }

# n_chars <n> -> a synthetic path of exactly <n> characters
n_chars() { printf '%*s' "$1" '' | tr ' ' a; }

# =============================================================================
echo -e "\n${CYAN}=== Test 1: every tracked path is within the budget ===${NC}\n"
# =============================================================================
# git ls-files == exactly the set of paths a `git checkout` has to materialize.
tracked=$(git -C "$REPO_ROOT" ls-files)
offenders=$(printf '%s\n' "$tracked" | over_budget "$PATH_BUDGET")

if [ -z "$offenders" ]; then
    ok "all tracked paths <= $PATH_BUDGET chars"
else
    bad "tracked paths exceed the $PATH_BUDGET-char budget:"
    echo "$offenders" | sort -rn | sed 's/^/    /'
    echo "    -> shorten the path, or raise PATH_BUDGET in this file with a new derivation."
fi

# Report the current worst path + headroom (signal, not an assertion).
worst=$(printf '%s\n' "$tracked" | awk '{ print length($0), $0 }' | sort -rn | head -1)
worst_len=${worst%% *}
echo -e "\n  longest tracked path: ${worst_len} chars (budget ${PATH_BUDGET}, headroom $((PATH_BUDGET - worst_len)))"
echo "    ${worst#* }"

# =============================================================================
echo -e "\n${CYAN}=== Test 2: the guard actually fires (no always-green lint) ===${NC}\n"
# =============================================================================
# A lint nobody has ever seen fail is indistinguishable from a lint that cannot
# fail. Drive both sides of the boundary through the same code path as Test 1.
at_budget=$(n_chars "$PATH_BUDGET")
over=$(n_chars $((PATH_BUDGET + 1)))

if [ -z "$(printf '%s\n' "$at_budget" | over_budget "$PATH_BUDGET")" ]; then
    ok "a path of exactly $PATH_BUDGET chars is accepted (boundary is inclusive)"
else
    bad "a path of exactly $PATH_BUDGET chars was wrongly flagged"
fi

if [ -n "$(printf '%s\n' "$over" | over_budget "$PATH_BUDGET")" ]; then
    ok "a path of $((PATH_BUDGET + 1)) chars is flagged"
else
    bad "a path of $((PATH_BUDGET + 1)) chars was NOT flagged — the guard is inert"
fi

# =============================================================================
echo -e "\n${CYAN}=== Results ===${NC}"
echo -e "  Total: $TOTAL  ${GREEN}Pass: $PASS${NC}  ${RED}Fail: $FAIL${NC}\n"
if [ "$FAIL" -eq 0 ]; then
    echo -e "${GREEN}PATH BUDGET TESTS PASSED${NC}"; exit 0
else
    echo -e "${RED}PATH BUDGET TESTS FAILED${NC}"; exit 1
fi
