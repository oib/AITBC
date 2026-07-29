#!/bin/bash
# =============================================================================
# Pre-Release Validation Script
# =============================================================================
#
# Automates the verifiable checks from docs/release/PRE-RELEASE-CHECKLIST.md
# Run this BEFORE creating any release tag.
#
# Usage:
#   ./scripts/pre-release-check.sh [version]
#
# Example:
#   ./scripts/pre-release-check.sh v2.8.1
# =============================================================================

set -euo pipefail

VERSION="${1:-UNSET}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$PROJECT_ROOT"

# ABS-111 / PILOT-7: no version argument -> resolve the planned next version
# (lowest unreleased) from the version helper bound to the ACTIVE PROFILE's
# task-tracking provider, same profile-first rule as promote-release.
# shellcheck source=lib/version-source.sh
. "$SCRIPT_DIR/lib/version-source.sh"
# PILOT-60: portable per-suite watchdog timeout (bash-native fallback when no
# timeout(1)/gtimeout on the host). A wedged suite is now a NAMED fail, not an
# unbounded hang.
# shellcheck source=lib/run-with-timeout.sh
. "$SCRIPT_DIR/lib/run-with-timeout.sh"
# ABS-603: pure budget-classification policy (reserve sensor + operational-vs-test
# distinction), shared with tests/test-suite-budget.sh so both agree.
# shellcheck source=lib/suite-budget.sh
. "$SCRIPT_DIR/lib/suite-budget.sh"
_version_script="$(resolve_version_script)"
if [ "$VERSION" = "UNSET" ] && [ -n "$_version_script" ]; then
    _next="$(bash "$SCRIPT_DIR/$_version_script" next 2>/dev/null || true)"
    if [ -n "$_next" ]; then
        VERSION="$_next"
        echo "pre-release-check: resolved next version from ${_version_script%-version.sh}: $VERSION"
    fi
    unset _next
fi
unset _version_script

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[0;33m'
CYAN='\033[0;36m'
NC='\033[0m'

PASS=0
FAIL=0
WARN=0
OPS=0

check_pass() { PASS=$((PASS + 1)); echo -e "  ${GREEN}✓${NC} $1"; }
check_fail() { FAIL=$((FAIL + 1)); echo -e "  ${RED}✗${NC} $1"; }
check_warn() { WARN=$((WARN + 1)); echo -e "  ${YELLOW}⚠${NC} $1"; }
# ABS-603 AC3: a budget OVERRUN is an OPERATIONAL finding, not a test finding —
# the same infra-vs-test distinction ABS-595 draws for a stalled pipeline. A
# suite that merely ran out of wall-clock (a slow host, a parallel seat) is NOT
# a broken product; conflating it with a real ✗ paints the gate red on green
# code (Pilot 8: a concurrent RTE run pushed the 790 s tentpole past 900 s and
# false-red the release). Tracked separately (OPS) and does NOT block the
# release; a genuine test failure (below) still exits non-zero.
check_ops()  { OPS=$((OPS + 1));   echo -e "  ${CYAN}◑${NC} $1"; }

# Per-suite wall-clock budget (PILOT-60). A suite that overruns is a NAMED
# operational finding (exit 124), never an unbounded hang — a SIGTERM-swallowing
# child once hung this gate for an hour. run_with_timeout
# (scripts/lib/run-with-timeout.sh) is bash-native, so the budget holds even on
# stock macOS where neither timeout(1) nor gtimeout exists.
#
# ABS-603: the tentpole (tests/test-orchestrator.sh) measures ~790 s ISOLATED and
# exceeds 900 s under one concurrent seat, and it GROWS with every epic that adds
# a tests/orchestrator.d fixture. The budget therefore carries real headroom
# (see docs/release/SUITE-BUDGET.md for the measured rationale), and the reserve
# sensor below flags shrinking headroom BEFORE it reaches the budget.
# Override with PRE_RELEASE_SUITE_TIMEOUT.
SUITE_TIMEOUT="${PRE_RELEASE_SUITE_TIMEOUT:-1800}"
case "$SUITE_TIMEOUT" in ''|*[!0-9]*) SUITE_TIMEOUT=1800 ;; esac

# ABS-603 AC4: warn when a PASSING suite leaves less than this % of its budget as
# reserve, so fixture growth is visible BEFORE it turns the gate red. Override
# with SUITE_RESERVE_WARN_PCT.
RESERVE_WARN_PCT="${SUITE_RESERVE_WARN_PCT:-25}"
case "$RESERVE_WARN_PCT" in ''|*[!0-9]*) RESERVE_WARN_PCT=25 ;; esac

# Run one test suite under the per-suite budget, echoing its combined output; the
# caller reads the exit code via `$?` (124 == the suite exceeded its budget).
run_test_suite() {
    run_with_timeout "$SUITE_TIMEOUT" bash "$1" 2>&1
}

echo -e "${CYAN}════════════════════════════════════════════════════${NC}"
echo -e "${CYAN}  Pre-Release Validation: ${VERSION}${NC}"
echo -e "${CYAN}════════════════════════════════════════════════════${NC}"
echo ""

# ─── 1. Code Quality ────────────────────────────────────────────────────────

echo -e "${CYAN}1. Code Quality Gates${NC}"

# Syntax check
if bash -n scripts/sync-claude-harness.sh 2>/dev/null; then
    check_pass "sync-claude-harness.sh syntax OK"
else
    check_fail "sync-claude-harness.sh syntax FAILED"
fi

# Merge conflict markers
# Anchored to REAL marker shape (7 chars at line start + space/EOL) so tests that
# grep for markers as string literals (e.g. test-epic-end-scenario.sh) don't trip it.
CONFLICTS=$(grep -rlE '^<{7}( |$)' . --include='*.sh' --include='*.md' --include='*.json' --include='*.toml' --include='*.yml' --include='*.mdc' 2>/dev/null | grep -v node_modules | grep -v .git | grep -v '.claude/worktrees/' | grep -v '.harness-backup' | grep -v pre-release | grep -v PRE-RELEASE || true)
if [ -z "$CONFLICTS" ]; then
    check_pass "No merge conflict markers"
else
    check_fail "Merge conflict markers found in: $CONFLICTS"
fi

# Test suites — each under a per-suite watchdog budget (PILOT-60).
TOTAL_TESTS=0
TOTAL_PASS=0
for test_file in tests/test-*.sh; do
    if [ -f "$test_file" ]; then
        test_name=$(basename "$test_file" .sh)
        # Exit code is authoritative (ABS-99): a suite passes iff it exits 0.
        # `&& rc=0 || rc=$?` keeps set -e from aborting on a failing suite.
        _suite_start=$(date +%s)
        output=$(run_test_suite "$test_file") && rc=0 || rc=$?
        _suite_elapsed=$(( $(date +%s) - _suite_start ))
        # ABS-603: one shared policy classifies the run (scripts/lib/suite-budget.sh).
        _reserve_pct="$(suite_reserve_pct "$_suite_elapsed" "$SUITE_TIMEOUT")"
        _verdict="$(classify_suite "$rc" "$_suite_elapsed" "$SUITE_TIMEOUT" "$RESERVE_WARN_PCT")"
        case "$_verdict" in
        pass|pass-low-reserve)
            # AC4 reserve sensor: warn a PASSING suite that is running close to
            # its budget, so fixture growth surfaces before it red-lines.
            if [ "$_verdict" = pass-low-reserve ]; then
                check_warn "$test_name: LOW RESERVE — ${_suite_elapsed}s of ${SUITE_TIMEOUT}s budget (${_reserve_pct}% left, < ${RESERVE_WARN_PCT}% threshold); see docs/release/SUITE-BUDGET.md"
            fi
            # Human-readable count (fallback signal only). Accept both summary
            # forms: standard suites print "Passed: N"; a few end with a
            # terminal "PASS: <name>" line and expose no count. POSIX grep only
            # (no GNU -P): match either shape, then take the first integer.
            # `|| true`: with `set -o pipefail`, a suite that reports no numeric
            # summary (terminal "PASS:" form) makes grep exit 1, which would
            # otherwise trip set -e on this assignment.
            count=$(printf '%s\n' "$output" \
                | grep -Eo 'Passed:[[:space:]]*[0-9]+|[0-9]+/[0-9]+ PASS' \
                | grep -Eo '[0-9]+' | head -1 || true)
            if [ -n "$count" ]; then
                check_pass "$test_name: ${count} tests (${_suite_elapsed}s, ${_reserve_pct}% reserve)"
                TOTAL_TESTS=$((TOTAL_TESTS + count))
                TOTAL_PASS=$((TOTAL_PASS + count))
            else
                check_pass "$test_name: passed (${_suite_elapsed}s, ${_reserve_pct}% reserve)"
            fi
            ;;
        ops-overbudget)
            # AC3: a budget overrun is OPERATIONAL, not a test failure — named and
            # loud, but it does NOT block the release (an unbounded hang is still
            # impossible: the suite was killed at the budget).
            check_ops "$test_name: OVER BUDGET (exceeded ${SUITE_TIMEOUT}s) — operational/load, not a test failure; run the tentpole via tests/staged-suite.sh, raise PRE_RELEASE_SUITE_TIMEOUT, or reduce concurrency"
            ;;
        *)
            check_fail "$test_name: FAILED (exit $rc)"
            ;;
        esac
    fi
done
echo -e "  ${CYAN}Total: ${TOTAL_PASS}/${TOTAL_TESTS} counted tests${NC}"

echo ""

# ─── 2. Documentation ───────────────────────────────────────────────────────

echo -e "${CYAN}2. Documentation Completeness${NC}"

REQUIRED_DOCS=(
    "README.md"
    "docs/HARNESS_SYNC_GUIDE.md"
    "docs/HARNESS_MANIFEST_SCHEMA.md"
    "docs/guides/GETTING-STARTED.md"
    "docs/guides/WORKSPACE-ADOPTION-GUIDE.md"
)

for doc in "${REQUIRED_DOCS[@]}"; do
    if [ -f "$doc" ]; then
        check_pass "$doc exists"
    else
        check_fail "$doc MISSING"
    fi
done

# Provider-specific docs
for provider_doc in .claude/README.md .codex/README.md .cursor/rules/README.md .gemini/README.md; do
    if [ -f "$provider_doc" ]; then
        check_pass "$provider_doc exists"
    else
        check_warn "$provider_doc not found (optional)"
    fi
done

# Stale references
STALE=$(grep -rl 'CODEX\.md' docs/ README.md .claude/ .codex/ .cursor/ .gemini/ 2>/dev/null | grep -v CHANGELOG | grep -v PRE-RELEASE | grep -v 'qa-validations/' | grep -v '.codex/README.md' | grep -v '.claude/worktrees/' | grep -v '.harness-backup' || true)
if [ -z "$STALE" ]; then
    check_pass "No stale CODEX.md references"
else
    check_fail "Stale CODEX.md references in: $STALE"
fi

echo ""

# ─── 3. Template Compatibility ──────────────────────────────────────────────

echo -e "${CYAN}3. Template Compatibility${NC}"

# Check for hardcoded project values in template files (excluding examples/)
HARDCODED=$(grep -rl 'ByBren-LLC\|rendertrust\|cheddarfox' .claude/ .codex/ .cursor/ .gemini/ 2>/dev/null | grep -v examples/ | grep -v node_modules | grep -v '.claude/worktrees/' | grep -v '.harness-backup' || true)
if [ -z "$HARDCODED" ]; then
    check_pass "No hardcoded project values in harness files"
else
    check_warn "Possible hardcoded values in: $HARDCODED"
fi

# Check setup-template.sh exists
if [ -f "scripts/setup-template.sh" ]; then
    check_pass "setup-template.sh exists"
else
    check_fail "setup-template.sh MISSING"
fi

echo ""

# ─── 4. Backward Compatibility ──────────────────────────────────────────────

echo -e "${CYAN}4. Backward Compatibility${NC}"

# Check manifest schema exists
if [ -f ".harness-manifest.schema.json" ]; then
    check_pass ".harness-manifest.schema.json exists"
else
    check_warn ".harness-manifest.schema.json not found"
fi

# Check example manifests
for example in examples/manifests/rendertrust.harness-manifest.yml examples/manifests/keryk-ai.harness-manifest.yml; do
    if [ -f "$example" ]; then
        check_pass "$example exists"
    else
        check_warn "$example not found"
    fi
done

echo ""

# ─── 5. Git State ───────────────────────────────────────────────────────────

echo -e "${CYAN}5. Git State${NC}"

BRANCH=$(git branch --show-current)
if [ "$BRANCH" = "main" ]; then
    check_pass "On main branch"
else
    check_fail "Not on main branch (on: $BRANCH)"
fi

# Check for uncommitted changes
if git diff --quiet && git diff --cached --quiet; then
    check_pass "Working tree clean"
else
    check_warn "Uncommitted changes present"
fi

# Check for leftover feature branches
SAW_BRANCHES=$(git branch --list 'SAW-*' 2>/dev/null | wc -l)
if [ "$SAW_BRANCHES" -eq 0 ]; then
    check_pass "No leftover SAW feature branches"
else
    check_warn "${SAW_BRANCHES} SAW feature branches remain"
fi

echo ""

# ─── 6. Version Identity ─────────────────────────────────────────────────────
# ABS-139: the version carriers must agree so a release can never ship a stale
# marker (the .boilerplate-version rot that ran v2.10.0 through 11 releases).
# .governor-tag carries the 'v' prefix; .boilerplate-version is the bare semver
# (BOILERPLATE_MIGRATION_SOP §1.2). Compare them modulo the prefix.

echo -e "${CYAN}6. Version Identity${NC}"

if [ -f .governor-tag ] && [ -f .boilerplate-version ]; then
    GOV_TAG="$(grep -v '^#' .governor-tag | grep -v '^[[:space:]]*$' | head -1 | tr -d '[:space:]')"
    BP_VER="$(grep -v '^#' .boilerplate-version | grep -v '^[[:space:]]*$' | head -1 | tr -d '[:space:]')"
    if [ "${GOV_TAG#v}" = "${BP_VER#v}" ]; then
        check_pass ".governor-tag ($GOV_TAG) and .boilerplate-version ($BP_VER) agree"
    else
        check_fail ".governor-tag ($GOV_TAG) and .boilerplate-version ($BP_VER) DISAGREE — a release would ship a stale migration marker"
    fi
    # SOP §1.2: the marker is exactly one line, no comments, no 'v' prefix.
    if grep -q '^#' .boilerplate-version; then
        check_fail ".boilerplate-version contains comment lines (SOP §1.2: one bare semver line only)"
    elif [ "$BP_VER" != "${BP_VER#v}" ]; then
        check_fail ".boilerplate-version carries a 'v' prefix ($BP_VER); SOP §1.2 wants the bare semver"
    else
        check_pass ".boilerplate-version is SOP-conform (bare one-line semver)"
    fi
    # The latest HARNESS_CHANGELOG.yml release entry must match the target too, so
    # setup-template.sh (which prefers the changelog over the marker) agrees.
    if [ -f HARNESS_CHANGELOG.yml ]; then
        CHANGELOG_VER="$(grep -E '^  - version:' HARNESS_CHANGELOG.yml | head -1 | grep -Eo '[0-9]+\.[0-9]+\.[0-9]+')"
        if [ "$CHANGELOG_VER" = "${BP_VER#v}" ]; then
            check_pass "HARNESS_CHANGELOG.yml latest entry ($CHANGELOG_VER) matches the marker"
        else
            check_warn "HARNESS_CHANGELOG.yml latest entry ($CHANGELOG_VER) != marker ($BP_VER) — add the release entry (governor-only patches: a stub entry)"
        fi
    fi
else
    check_warn ".governor-tag or .boilerplate-version absent — not a self-hosted checkout?"
fi

echo ""

# ─── 7. Knowledge Graph Freshness ────────────────────────────────────────────
# ABS-148: graphify-out/ is mandated agent context (ADR-A-0003, "graph before
# grep") but drifted 229 commits stale once because nothing checked it. The
# graph records its source commit in GRAPH_REPORT.md ("Built from commit: <sha>").
# Warn when the graph is more than GRAPH_STALE_MAX_COMMITS behind HEAD so a
# release ships a current graph; regenerate with `graphify update .`.

echo -e "${CYAN}7. Knowledge Graph Freshness${NC}"

GRAPH_STALE_MAX_COMMITS="${GRAPH_STALE_MAX_COMMITS:-50}"
GRAPH_REPORT="graphify-out/GRAPH_REPORT.md"
if [ -f "$GRAPH_REPORT" ]; then
    GRAPH_SHA="$(grep -m1 'Built from commit:' "$GRAPH_REPORT" | grep -Eo '[0-9a-f]{7,40}' | head -1)"
    if [ -z "$GRAPH_SHA" ]; then
        check_warn "graphify-out/GRAPH_REPORT.md has no 'Built from commit:' line — cannot assess freshness"
    elif ! git cat-file -e "${GRAPH_SHA}^{commit}" 2>/dev/null; then
        check_warn "graph source commit $GRAPH_SHA is unknown to this repo (rebased/shallow?) — regenerate with 'graphify update .'"
    else
        BEHIND="$(git rev-list --count "${GRAPH_SHA}..HEAD" 2>/dev/null || echo "?")"
        if [ "$BEHIND" = "0" ]; then
            check_pass "graph is built from HEAD (0 commits behind)"
        elif [ "$BEHIND" != "?" ] && [ "$BEHIND" -le "$GRAPH_STALE_MAX_COMMITS" ]; then
            check_pass "graph is ${BEHIND} commit(s) behind HEAD (<= ${GRAPH_STALE_MAX_COMMITS} threshold)"
        else
            check_warn "graph is ${BEHIND} commits behind HEAD (> ${GRAPH_STALE_MAX_COMMITS}) — run 'graphify update .' and commit graphify-out/ before releasing"
        fi
    fi
else
    check_warn "graphify-out/GRAPH_REPORT.md absent — knowledge graph not present"
fi

echo ""

# ─── 8. Provider Mirror Governance ───────────────────────────────────────────
# ABS-142 (ADR-A-0015): hand-maintained provider mirrors drifted for months
# (agent_providers/claude_code/ was 16/17 prompts stale; ABS-38 skills parity
# regressed). Guard the mirrors whose decision is "keep":
#   - agent_providers/claude_code/  -> GENERATED from harness: byte-parity check
#     (failing BLOCKS release; it is regenerated at promotion by promote-release).
#   - .codex/agents/                -> HAND-ADAPTED: roster-parity against the
#     documented 11-role core-delivery subset (failing BLOCKS release).

echo -e "${CYAN}8. Provider Mirror Governance${NC}"

# 8a. agent_providers/claude_code/ byte-parity with the harness source.
if [ -f scripts/generate-governor.sh ]; then
    if bash scripts/generate-governor.sh --providers --check >/tmp/providers_check.$$ 2>&1; then
        check_pass "agent_providers/claude_code/ == generated(harness/claude) (byte-parity)"
    else
        check_fail "agent_providers/claude_code/ has DRIFTED from harness — run 'bash scripts/generate-governor.sh --providers' and commit"
        sed 's/^/      /' /tmp/providers_check.$$ | head -20
    fi
    rm -f /tmp/providers_check.$$
else
    check_fail "scripts/generate-governor.sh missing — cannot verify provider mirror parity"
fi

# 8b. .codex/agents/ roster-parity with the documented core-delivery subset.
# ADR-A-0015 records the 11-role subset as intentional; .codex/README.md documents
# it. If a role is added/removed without updating both, this catches the drift.
CODEX_EXPECTED="be-developer bsa data-engineer data-provisioning-eng fe-developer qas rte security-engineer system-architect tdm tech-writer"
if [ -d .codex/agents ]; then
    CODEX_ACTUAL="$(ls .codex/agents/*.toml 2>/dev/null | xargs -n1 basename 2>/dev/null | sed 's/\.toml$//' | sort | tr '\n' ' ')"
    CODEX_WANT="$(printf '%s\n' $CODEX_EXPECTED | sort | tr '\n' ' ')"
    if [ "$CODEX_ACTUAL" = "$CODEX_WANT" ]; then
        check_pass ".codex/agents/ roster matches the documented 11-role subset (ADR-A-0015)"
    else
        check_fail ".codex/agents/ roster drifted — expected [$CODEX_WANT], got [$CODEX_ACTUAL]; update .codex/README.md + ADR-A-0015 or the roster"
    fi
else
    check_warn ".codex/agents/ not found — Codex mirror absent"
fi

echo ""

# ─── 9. ADR Acceptance Closeout ──────────────────────────────────────────────
# ABS-212: a human accepting an ADR (human-only, ADR-A-0004) must flip the ADR
# FILE frontmatter (status/accepted_by/accepted_date) in the same acceptance PR.
# ADR-A-0017 drifted — tracker-accepted 2026-07-11, file stayed 'proposed',
# flagged 3x, never closed, forcing a manual flip at the v2.24.0 release
# (A-0018/A-0019 similar). Warn (not fail) when an ADR is accepted in the record
# but still 'proposed' in its file, so the release closes it out or acknowledges it.

echo -e "${CYAN}9. ADR Acceptance Closeout${NC}"

if [ -f scripts/adr-acceptance-drift.sh ]; then
    DRIFT_OUT="$(bash scripts/adr-acceptance-drift.sh 2>&1)" && DRIFT_RC=0 || DRIFT_RC=$?
    if [ "$DRIFT_RC" -eq 0 ]; then
        check_pass "No ADR file↔record acceptance drift"
    else
        check_warn "ADR acceptance drift — accepted in the record but file frontmatter still 'proposed':"
        printf '%s\n' "$DRIFT_OUT" | grep '^DRIFT:' | sed 's/^/      /'
    fi
else
    check_warn "scripts/adr-acceptance-drift.sh missing — cannot check ADR acceptance closeout"
fi

# 9b. Dangling ADR references (ABS-315). A renumber (A-0016 -> A-0017) left
# citations pointing at ids no ADR file defines; nothing caught it. FAIL when an
# ADR id cited in specs/ or an ADR cross-reference resolves to no existing file.
if [ -f scripts/adr-reference-lint.sh ]; then
    REFLINT_OUT="$(bash scripts/adr-reference-lint.sh 2>&1)" && REFLINT_RC=0 || REFLINT_RC=$?
    if [ "$REFLINT_RC" -eq 0 ]; then
        check_pass "No dangling ADR references in specs/ or adrs/ (every cited id resolves)"
    else
        check_fail "Dangling ADR reference(s) — a renumber left a citation resolving to no file:"
        printf '%s\n' "$REFLINT_OUT" | grep '^DANGLING:' | sed 's/^/      /'
    fi
else
    check_warn "scripts/adr-reference-lint.sh missing — cannot check dangling ADR references"
fi

echo ""

# ─── Summary ────────────────────────────────────────────────────────────────

echo -e "${CYAN}════════════════════════════════════════════════════${NC}"
echo -e "  ${GREEN}Passed: ${PASS}${NC}  ${RED}Failed: ${FAIL}${NC}  ${YELLOW}Warnings: ${WARN}${NC}  ${CYAN}Operational: ${OPS}${NC}"
echo -e "${CYAN}════════════════════════════════════════════════════${NC}"

# ABS-603 AC3: OPERATIONAL findings (budget overruns) are reported distinctly and
# do NOT block the release — only a real test/gate failure does.
if [ "$OPS" -gt 0 ]; then
    echo -e "${CYAN}${OPS} operational finding(s) — a suite ran over its wall-clock budget."
    echo -e "This is a load/infrastructure signal, NOT a broken test; it does not block release.${NC}"
fi

if [ "$FAIL" -gt 0 ]; then
    echo -e "${RED}RELEASE BLOCKED — ${FAIL} check(s) failed${NC}"
    echo "Fix the failures above before creating the release tag."
    exit 1
elif [ "$WARN" -gt 0 ] || [ "$OPS" -gt 0 ]; then
    echo -e "${YELLOW}RELEASE READY WITH WARNINGS — review ${WARN} warning(s) / ${OPS} operational finding(s) above${NC}"
    exit 0
else
    echo -e "${GREEN}ALL CHECKS PASSED — ready to release ${VERSION}${NC}"
    exit 0
fi
