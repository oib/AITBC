#!/bin/bash
# =============================================================================
# Test: docs-identifier-check default-on + scope refinements (ABS-517)
# =============================================================================
# Pins the ABS-517 behavior changes of scripts/docs-identifier-check.sh:
#   * gate is ON by default (ORCH_DOCS_IDENTIFIER_CHECK=0 is the kill-switch)
#   * docs/agent-outputs|archive|releases are work product/history: not gated
#   * `docs-identifier-check: skip-file` marker opts a template doc out
#   * path tokens need a left word boundary (backend/scripts/x.sh is NOT a
#     claim about scripts/x.sh) and glob-prefix tokens (trailing -) are skipped
#   * fabricated identifiers still fail
# Auto-discovered by the CI / pre-release tests/test-*.sh loops.
#
# Run from repo root: bash tests/test-docs-identifier-check.sh
# =============================================================================

set -u

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
CHECK="$REPO_ROOT/scripts/docs-identifier-check.sh"

PASS=0
FAIL=0
TOTAL=0
GREEN='\033[0;32m'; RED='\033[0;31m'; CYAN='\033[0;36m'; NC='\033[0m'

assert_exit() {
    local actual="$1" expected="$2" label="$3"
    TOTAL=$((TOTAL + 1))
    if [ "$actual" = "$expected" ]; then
        echo -e "  ${GREEN}PASS${NC} $label"; PASS=$((PASS + 1))
    else
        echo -e "  ${RED}FAIL${NC} $label (expected exit $expected, got $actual)"; FAIL=$((FAIL + 1))
    fi
}

run_check() { # run_check <env...> -- <files...> ; echoes exit code
    local ec=0
    "$@" >/dev/null 2>&1 || ec=$?
    echo "$ec"
}

echo -e "${CYAN}=== docs-identifier-check (ABS-517) ===${NC}\n"

TMP=$(mktemp -d "${TMPDIR:-/tmp}/docs-idcheck-test-XXXXXX")
trap 'rm -rf "$TMP"' EXIT
# The checker gates by repo-relative path segment, so fixture files live under
# a docs/ segment inside TMP (is_docs_path matches */docs/*).
mkdir -p "$TMP/docs/guides" "$TMP/docs/agent-outputs"

# A doc with a token class the repo cannot satisfy: a scripts/ path that does
# not exist. (Never spell a fabricated ORCH_ token literally in a test file
# that lives in the repo — this file is in tests/, not docs/, but the checker
# header's self-satisfy warning still applies to git grep over scripts/.)
printf 'run `scripts/does-not-exist-xyz.sh` now\n' > "$TMP/docs/guides/bad.md"
printf 'see backend/scripts/sandbox-guard.sh and scripts/orchestrator-*.sh prose\n' > "$TMP/docs/guides/boundary.md"
# A doc citing a REAL test-only knob (defined in tests/sandbox-guard.sh, not in
# scripts/) must pass: tests/ is a legitimate source of implementer-facing knobs
# an SOP documents (PILOT-62). Safe to spell literally — it is git-grep-real.
printf 'set the escape hatch `ORCH_TEST_ALLOW_BACKEND=1` before sourcing\n' > "$TMP/docs/guides/testknob.md"
printf 'run `scripts/does-not-exist-xyz.sh` now\n' > "$TMP/docs/agent-outputs/old-run.md"
{ printf '# T\n\n<!-- docs-identifier-check: skip-file -->\n'; printf 'run `scripts/does-not-exist-xyz.sh` now\n'; } > "$TMP/docs/guides/template.md"

echo -e "${CYAN}Default-on + kill-switch${NC}"
assert_exit "$(run_check bash "$CHECK" "$TMP/docs/guides/bad.md")" 1 "fabricated path fails WITHOUT setting the env (default on)"
assert_exit "$(run_check env ORCH_DOCS_IDENTIFIER_CHECK=0 bash "$CHECK" "$TMP/docs/guides/bad.md")" 0 "kill-switch =0 -> clean no-op"

echo -e "\n${CYAN}Scope refinements${NC}"
assert_exit "$(run_check bash "$CHECK" "$TMP/docs/agent-outputs/old-run.md")" 0 "agent-outputs run artifact is not gated"
assert_exit "$(run_check bash "$CHECK" "$TMP/docs/guides/template.md")" 0 "skip-file marker opts the template doc out"
assert_exit "$(run_check bash "$CHECK" "$TMP/docs/guides/boundary.md")" 0 "backend/scripts/... + glob-prefix tokens are not path claims"
assert_exit "$(run_check bash "$CHECK" "$TMP/docs/guides/testknob.md")" 0 "real test-only ORCH_ knob (defined in tests/) is not a fabrication"

echo -e "\n${CYAN}Real corpus${NC}"
corpus_ec=0
cd "$REPO_ROOT" || exit 2
# shellcheck disable=SC2046
bash "$CHECK" $(git ls-files 'docs/*.md' 'work/improvement-proposals/*.md') >/dev/null 2>&1 || corpus_ec=$?
assert_exit "$corpus_ec" 0 "tracked docs corpus passes with the gate on"

# =============================================================================
echo -e "\n${CYAN}=== Test Results ===${NC}\n"
echo -e "  Total:  $TOTAL"
echo -e "  ${GREEN}Passed: $PASS${NC}"
if [ "$FAIL" -gt 0 ]; then
    echo -e "  ${RED}Failed: $FAIL${NC}"; exit 1
else
    echo -e "  Failed: 0"; echo -e "\n  ${GREEN}ALL TESTS PASSED${NC}\n"; exit 0
fi
