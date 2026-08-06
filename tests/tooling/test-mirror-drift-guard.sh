#!/bin/bash
# =============================================================================
# Test: harness->provider mirror-drift pre-commit guard (ABS-317)
#        scripts/hooks/pre-commit-mirror-drift-guard.sh
# =============================================================================
# Drives the guard inside a throwaway git repo with a STUB generate-governor.sh
# so the parity verdict is controllable and the real tree is never touched.
#   - no harness path staged                 => exit 0 (nothing to check)
#   - harness staged, mirror in sync          => exit 0
#   - harness staged, mirror DRIFTED          => exit 1 (fix line printed)
#   - harness staged, regen output UNSTAGED   => exit 1
#   - kill switch ORCH_MIRROR_GUARD=0         => exit 0 even on drift
#
# Run from repo root: bash tests/tooling/test-mirror-drift-guard.sh
# bash 3.2 + BSD tools only.
# =============================================================================

set -u

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
GUARD="$REPO_ROOT/scripts/hooks/pre-commit-mirror-drift-guard.sh"

GREEN='\033[0;32m'; RED='\033[0;31m'; CYAN='\033[0;36m'; NC='\033[0m'
PASS=0; FAIL=0; TOTAL=0
ok()  { PASS=$((PASS+1)); TOTAL=$((TOTAL+1)); echo -e "  ${GREEN}✓${NC} $1"; }
bad() { FAIL=$((FAIL+1)); TOTAL=$((TOTAL+1)); echo -e "  ${RED}✗${NC} $1"; }

echo -e "${CYAN}Mirror-Drift pre-commit guard (ABS-317)${NC}"

# --- build a throwaway repo with a controllable stub generator --------------
mk_repo() { # echoes the repo path; $1 = stub --check rc
    local repo; repo="$(mktemp -d)"
    (
        cd "$repo"
        git init -q .; git config user.email t@t; git config user.name t
        mkdir -p scripts/hooks harness/claude/agents agent_providers/claude_code/prompts
        cat > scripts/generate-governor.sh <<EOF
#!/bin/bash
case "\$*" in
  *"--providers --check"*) exit ${1} ;;
esac
exit 0
EOF
        chmod +x scripts/generate-governor.sh
        printf 'agent def\n' > harness/claude/agents/foo.md
        printf 'mirror\n'    > agent_providers/claude_code/prompts/foo.md
        git add -A; git commit -q -m base
    ) >/dev/null 2>&1
    printf '%s\n' "$repo"
}

run_guard() { # <repo> <staged> [env assignments...] ; sets $rc / $out
    local repo="$1" staged="$2"; shift 2
    out="$(cd "$repo" && env ORCH_MIRROR_GUARD_STAGED="$staged" "$@" bash "$GUARD" 2>&1)"; rc=$?
}

# --- Case 1: no harness path staged -> exit 0 --------------------------------
R="$(mk_repo 1)"      # generator would report drift, but nothing harness staged
run_guard "$R" "agent_providers/claude_code/prompts/foo.md"
if [ "$rc" -eq 0 ]; then ok "no harness staged -> allow"; else bad "no harness staged: rc=$rc out=[$out]"; fi
rm -rf "$R"

# --- Case 2: harness staged, mirror in sync -> exit 0 ------------------------
R="$(mk_repo 0)"      # stub --check passes; no unstaged mirror change
run_guard "$R" "harness/claude/agents/foo.md"
if [ "$rc" -eq 0 ]; then ok "harness staged + mirror in sync -> allow"; else bad "in sync: rc=$rc out=[$out]"; fi
rm -rf "$R"

# --- Case 3: harness staged, mirror drifted -> exit 1 -----------------------
R="$(mk_repo 1)"      # stub --check reports drift
run_guard "$R" "harness/claude/agents/foo.md"
if [ "$rc" -eq 1 ] && printf '%s' "$out" | grep -q 'generate-governor.sh --providers'; then
    ok "harness staged + drift -> block with fix line"
else bad "drift: rc=$rc out=[$out]"; fi
rm -rf "$R"

# --- Case 4: mirror in sync on disk but regen output left UNSTAGED -> exit 1 --
R="$(mk_repo 0)"      # --check passes, but we dirty the mirror without staging
printf 'regenerated but not added\n' >> "$R/agent_providers/claude_code/prompts/foo.md"
run_guard "$R" "harness/claude/agents/foo.md"
if [ "$rc" -eq 1 ] && printf '%s' "$out" | grep -q 'UNSTAGED'; then
    ok "unstaged regen output -> block"
else bad "unstaged: rc=$rc out=[$out]"; fi
rm -rf "$R"

# --- Case 5: kill switch off -> allow even on drift -------------------------
R="$(mk_repo 1)"
run_guard "$R" "harness/claude/agents/foo.md" ORCH_MIRROR_GUARD=0
if [ "$rc" -eq 0 ]; then ok "ORCH_MIRROR_GUARD=0 -> guard bypassed"; else bad "kill switch: rc=$rc out=[$out]"; fi
rm -rf "$R"

echo ""
echo -e "${CYAN}Passed: ${PASS}  Failed: ${FAIL}  Total: ${TOTAL}${NC}"
[ "$FAIL" -eq 0 ] || exit 1
exit 0
