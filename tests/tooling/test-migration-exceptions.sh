#!/usr/bin/env bash
# =============================================================================
# Test: migration-driver exception honoring in the delegated .claude sync (ABS-264)
# =============================================================================
# ABS-264 unions project_owned_exceptions from SOURCE ownership.yaml with a
# consumer's TARGET/.agentic/upgrade/ownership.local.yaml, and hands the unioned
# list to sync-claude-harness.sh — which migrate-project.sh delegates the
# `.claude/` domain to — via the MIGRATE_EXCEPTIONS env var.
#
# This test closes the LATENT GAP (AC4): before ABS-264 the sync did NOT read the
# exception list (zero references), so a `.claude/**` exception the fork budget
# graded was still clobbered by the delegated sync — the exact report/classifier
# divergence ABS-259 otherwise eliminates. Here we drive do_sync end-to-end
# (network stubbed: fetch_upstream -> a local upstream dir) and assert the
# exception file is PRESERVED, a non-exception file is still synced, and a
# control run WITHOUT the exception list DOES overwrite the file (proving the
# honoring is load-bearing).
#
# Bash 3.2 / BSD-safe. Run from repo root: bash tests/tooling/test-migration-exceptions.sh
# =============================================================================

set -u

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
SYNC_SCRIPT="$REPO_ROOT/scripts/sync-claude-harness.sh"

TEST_DIR=$(mktemp -d "${TMPDIR:-/tmp}/migration-exceptions-test.XXXXXX")
trap 'rm -rf "$TEST_DIR"' EXIT

GREEN='\033[0;32m'; RED='\033[0;31m'; CYAN='\033[0;36m'; NC='\033[0m'
PASS=0; FAIL=0; TOTAL=0

assert_eq() {
    TOTAL=$((TOTAL + 1))
    if [ "$1" = "$2" ]; then
        echo -e "  ${GREEN}PASS${NC} $3"; PASS=$((PASS + 1))
    else
        echo -e "  ${RED}FAIL${NC} $3 (expected '$2', got '$1')"; FAIL=$((FAIL + 1))
    fi
}
assert_contains() {
    TOTAL=$((TOTAL + 1))
    if printf '%s' "$1" | grep -qF -- "$2"; then
        echo -e "  ${GREEN}PASS${NC} $3"; PASS=$((PASS + 1))
    else
        echo -e "  ${RED}FAIL${NC} $3 (expected to find: $2)"; FAIL=$((FAIL + 1))
    fi
}

# Build a consumer project carrying the sync script + a minimal v1.0 manifest.
setup_project() {
    local proj_dir="$TEST_DIR/project-$1"
    mkdir -p "$proj_dir/.claude/agents" "$proj_dir/scripts"
    cp "$SYNC_SCRIPT" "$proj_dir/scripts/sync-claude-harness.sh"
    chmod +x "$proj_dir/scripts/sync-claude-harness.sh"
    cat > "$proj_dir/.harness-manifest.yml" <<'YAML'
manifest_version: "1.0"
identity:
  PROJECT_NAME: "TestProject"
  PROJECT_REPO: "test-project"
  PROJECT_SHORT: "TST"
  GITHUB_ORG: "test-org"
  TICKET_PREFIX: "TST"
  MAIN_BRANCH: "main"
YAML
    echo "$proj_dir"
}

# Replace the network functions so do_sync runs fully offline against a local
# upstream tree (same technique as tests/test-protected-files.sh).
create_mocked_script() {
    local proj_dir="$1" mock_upstream_dir="$2"
    local mocked_script="$proj_dir/scripts/sync-claude-harness-mocked.sh"
    node -e "
        const fs = require('fs');
        let src = fs.readFileSync('$proj_dir/scripts/sync-claude-harness.sh', 'utf8');
        src = src.replace(/^fetch_upstream\(\) \{/m,
            'fetch_upstream() {\n    TMP_DIR=\"${mock_upstream_dir}\"\n    return 0\n}\nfetch_upstream_ORIG() {');
        src = src.replace(/^get_upstream_sha\(\) \{/m,
            'get_upstream_sha() { echo \"abc12345\"; }\nget_upstream_sha_ORIG() {');
        src = src.replace(/^get_latest_release\(\) \{/m,
            'get_latest_release() { echo \"v2.6.0\"; }\nget_latest_release_ORIG() {');
        fs.writeFileSync('$mocked_script', src);
    "
    chmod +x "$mocked_script"
    echo "$mocked_script"
}

# A mock upstream .claude tree where every file has CHANGED (so an unhonored
# exception would be overwritten).
make_mock_upstream() {
    local up="$1"
    mkdir -p "$up/.claude/agents"
    echo "UPSTREAM keep"  > "$up/.claude/keep-me.md"
    echo "UPSTREAM other" > "$up/.claude/other.md"
    echo "UPSTREAM agent" > "$up/.claude/agents/pinned.md"
}

# =============================================================================
echo -e "\n${CYAN}=== AC4: delegated sync HONORS the driver exception list (preserve) ===${NC}\n"
# =============================================================================
PROJ=$(setup_project "honor-exception")
"$PROJ/scripts/sync-claude-harness.sh" init >/dev/null 2>&1
echo "LOCAL FORK"  > "$PROJ/.claude/keep-me.md"
echo "local old"   > "$PROJ/.claude/other.md"
echo "LOCAL AGENT" > "$PROJ/.claude/agents/pinned.md"
MOCK_UP="$TEST_DIR/mock-upstream"
make_mock_upstream "$MOCK_UP"
MOCKED=$(create_mocked_script "$PROJ" "$MOCK_UP")

# The driver exports the unioned list this way: a single-file exception + a
# directory-subtree exception, both repo-root-relative (as the ownership map is).
output=$(MIGRATE_EXCEPTIONS=".claude/keep-me.md
.claude/agents/" "$MOCKED" sync 2>&1 || true)

assert_eq "$(cat "$PROJ/.claude/keep-me.md")" "LOCAL FORK" \
    "AC4: a .claude/** file exception is PRESERVED through the delegated sync (not overwritten)"
assert_eq "$(cat "$PROJ/.claude/agents/pinned.md")" "LOCAL AGENT" \
    "AC4: a .claude/** directory exception preserves the whole subtree"
assert_eq "$(cat "$PROJ/.claude/other.md")" "UPSTREAM other" \
    "AC4: a NON-exception .claude file is still synced (report-only invariant for non-exception paths)"
assert_contains "$output" "Skipping excluded: keep-me.md" \
    "AC4: the sync reports the driver exception as skipped"

# =============================================================================
echo -e "\n${CYAN}=== Control: WITHOUT the exception list the file IS synced ===${NC}\n"
# =============================================================================
# Proves the honoring in AC4 is load-bearing (the file is preserved because of
# MIGRATE_EXCEPTIONS, not because the sync happened to skip it).
PROJ2=$(setup_project "no-exception")
"$PROJ2/scripts/sync-claude-harness.sh" init >/dev/null 2>&1
echo "LOCAL FORK"  > "$PROJ2/.claude/keep-me.md"
echo "local old"   > "$PROJ2/.claude/other.md"
echo "LOCAL AGENT" > "$PROJ2/.claude/agents/pinned.md"
MOCK_UP2="$TEST_DIR/mock-upstream2"
make_mock_upstream "$MOCK_UP2"
MOCKED2=$(create_mocked_script "$PROJ2" "$MOCK_UP2")

output2=$("$MOCKED2" sync 2>&1 || true)   # no MIGRATE_EXCEPTIONS
assert_eq "$(cat "$PROJ2/.claude/keep-me.md")" "UPSTREAM keep" \
    "control: without MIGRATE_EXCEPTIONS the .claude file IS synced (exception honoring is load-bearing)"

# =============================================================================
echo -e "\n${CYAN}=== Test Results ===${NC}\n"
# =============================================================================
echo -e "  Total:  $TOTAL"
echo -e "  ${GREEN}Passed: $PASS${NC}"
if [ "$FAIL" -gt 0 ]; then
    echo -e "  ${RED}Failed: $FAIL${NC}\n"
    exit 1
else
    echo -e "  Failed: 0\n  ${GREEN}ALL TESTS PASSED${NC}\n"
    exit 0
fi
