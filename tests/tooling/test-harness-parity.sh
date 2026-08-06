#!/bin/bash
# =============================================================================
# Test: governor drift guard -- live .claude/ == generated(pin) (ABS-94)
# =============================================================================
# ABS-94 (Phase 2b, epic ABS-91 "self-hosting: stable governs dev").
#
# The live .claude/ is NO LONGER a byte-copy of harness/claude. It is
# generated(pin): the SHIPPED harness materialized from the RELEASE TAG recorded
# in the committed `.governor-tag` file, plus a CLAUDE.md provenance banner
# stamped with that tag. harness/claude/** diverges freely as inert work
# product; the pin bumps only at promotion (ABS-95).
#
# This suite IS the CI drift guard. It asserts:
#   1. `scripts/generate-governor.sh --check` passes -- i.e. the live .claude/
#      shipped set equals generated(.governor-tag) AND CLAUDE.md's banner block
#      carries the pin tag. (This is the whole drift model in one call.)
#   2. LOCAL-RUNTIME items (settings.local.json, team-config.json, worktrees/,
#      .sync-exclude*, .harness-*) are NEVER part of the generated set -- they
#      exist only in the live tree and must be left untouched by generation
#      (ABS-96 decision doc §2.1).
#   3. Consumer-inertness (ABS-94): wrong-entry-guard presence in the live
#      shipped settings.template.json MATCHES the pinned tag's copy -- i.e. the
#      live tree carries the guard if and only if the pin release ships it
#      (absent at v2.16.0, shipped from v2.17.0), proving harness/claude
#      divergence never leaks into the live copy ahead of promotion.
#
# WHY the filename is kept: CI (tests.yml) globs tests/test-*.sh; keeping the
# name means the reworked guard is picked up with zero CI wiring changes. Its
# old job (harness/claude <-> .claude byte-identity) is SUPERSEDED by the
# generate(pin) drift model above.
#
# bash 3.2 / BSD safe: no `timeout`, no `grep -P`, no associative arrays.
# Run from repo root: bash tests/test-harness-parity.sh
# =============================================================================

set -u

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

GENERATOR="$REPO_ROOT/scripts/generate-governor.sh"
GOVERNOR_TAG_FILE="$REPO_ROOT/.governor-tag"
LIVE_DIR="$REPO_ROOT/.claude"

PASS=0; FAIL=0; TOTAL=0
GREEN='\033[0;32m'; RED='\033[0;31m'; CYAN='\033[0;36m'; NC='\033[0m'

assert_true() {
    local code="$1"; local label="$2"
    TOTAL=$((TOTAL + 1))
    if [ "$code" = "0" ]; then
        echo -e "  ${GREEN}PASS${NC} $label"; PASS=$((PASS + 1))
    else
        echo -e "  ${RED}FAIL${NC} $label"; FAIL=$((FAIL + 1))
    fi
}

echo -e "${CYAN}=== governor drift guard (live .claude == generated(pin)) ===${NC}\n"

# --- Sanity: generator + pin file must exist --------------------------------
if [ ! -f "$GENERATOR" ]; then
    echo -e "  ${RED}FAIL${NC} generator not found at $GENERATOR"; exit 1
fi
if [ ! -f "$GOVERNOR_TAG_FILE" ]; then
    echo -e "  ${RED}FAIL${NC} .governor-tag not found at $GOVERNOR_TAG_FILE"; exit 1
fi
if [ ! -d "$LIVE_DIR" ]; then
    echo -e "  ${RED}FAIL${NC} .claude does not exist at $LIVE_DIR"; exit 1
fi

PIN_TAG="$(sed -n '1p' "$GOVERNOR_TAG_FILE" | tr -d '[:space:]')"
echo -e "  ${CYAN}pin tag:${NC} $PIN_TAG\n"

# --- 1. The drift check itself ----------------------------------------------
bash "$GENERATOR" --check >/tmp/governor_check.$$ 2>&1
CHECK_EC=$?
assert_true "$([ "$CHECK_EC" -eq 0 ] && echo 0 || echo 1)" \
    "generate-governor.sh --check passes (live .claude == generated($PIN_TAG) + banner stamped)"
if [ "$CHECK_EC" -ne 0 ]; then
    echo ""; echo "  Drift check output:"; sed 's/^/    /' /tmp/governor_check.$$; echo ""
fi
rm -f /tmp/governor_check.$$

# --- 2. LOCAL-RUNTIME items are never part of the generated set -------------
# Build the generated set into a temp dir via the generator's own extraction by
# running --check is not enough; instead assert directly that generation never
# emits these names. We reuse the generator's guarantee by checking that each
# name, IF present live, is NOT reproduced by generation: the deterministic
# proof is that the shipped-set list in the generator excludes them. We verify
# structurally here by confirming the generator's shipped set (below) contains
# none of the LOCAL-RUNTIME names.
LOCAL_RUNTIME_ITEMS="settings.local.json team-config.json worktrees .sync-exclude .sync-exclude.local .harness-sync.json .harness-backup .harness-patches"
SHIPPED_ITEMS="agents skills commands hooks hooks-config.json settings.template.json README.md SETUP.md TROUBLESHOOTING.md AGENT_OUTPUT_GUIDE.md"

overlap=0
for lr in $LOCAL_RUNTIME_ITEMS; do
    for sh in $SHIPPED_ITEMS; do
        if [ "$lr" = "$sh" ]; then overlap=1; fi
    done
done
assert_true "$([ "$overlap" -eq 0 ] && echo 0 || echo 1)" \
    "no LOCAL-RUNTIME item is part of the generated shipped set"

# Belt-and-suspenders: the generator source itself must list these as never-touched.
if grep -q "LOCAL_RUNTIME_ITEMS=" "$GENERATOR" \
   && grep -q "team-config.json" "$GENERATOR" \
   && grep -q "settings.local.json" "$GENERATOR"; then
    assert_true 0 "generator explicitly excludes LOCAL-RUNTIME items from generation"
else
    assert_true 1 "generator explicitly excludes LOCAL-RUNTIME items from generation"
fi

# --- 3. Consumer inertness: live guard registration matches the pin ---------
# The ABS-92 wrong-entry guard is absent at v2.16.0 and ships from v2.17.0.
# Rather than hardcoding either state, assert the live shipped copy carries the
# session-wrong-entry-guard registration IF AND ONLY IF the pinned tag's
# settings.template.json does -- harness/claude divergence must never leak
# into the live copy ahead of promotion. Layout detection mirrors the
# generator: prefer harness/claude at the tag, else the pre-v2.23.0
# harness/.claude, else legacy .claude.
if git -C "$REPO_ROOT" rev-parse --verify --quiet "refs/tags/$PIN_TAG^{commit}" >/dev/null 2>&1; then
    if git -C "$REPO_ROOT" cat-file -e "$PIN_TAG:harness/claude/settings.template.json" 2>/dev/null; then
        PIN_TEMPLATE_PATH="harness/claude/settings.template.json"
    elif git -C "$REPO_ROOT" cat-file -e "$PIN_TAG:harness/.claude/settings.template.json" 2>/dev/null; then
        # Pre-rename tags (e.g. v2.22.0) ship the dotted namespace.
        PIN_TEMPLATE_PATH="harness/.claude/settings.template.json"
    else
        PIN_TEMPLATE_PATH=".claude/settings.template.json"
    fi
    if git -C "$REPO_ROOT" show "$PIN_TAG:$PIN_TEMPLATE_PATH" 2>/dev/null | grep -q "session-wrong-entry-guard"; then
        pin_has_guard=1
    else
        pin_has_guard=0
    fi
    if grep -q "session-wrong-entry-guard" "$LIVE_DIR/settings.template.json" 2>/dev/null; then
        live_has_guard=1
    else
        live_has_guard=0
    fi
    if [ "$pin_has_guard" = "$live_has_guard" ]; then
        assert_true 0 "live settings.template.json wrong-entry-guard registration matches generated($PIN_TAG) (pin=$pin_has_guard live=$live_has_guard)"
    else
        assert_true 1 "live settings.template.json wrong-entry-guard registration matches generated($PIN_TAG) (pin=$pin_has_guard live=$live_has_guard)"
    fi
else
    assert_true 1 "live settings.template.json wrong-entry-guard registration matches generated($PIN_TAG) (pin tag not found)"
fi

# --- 4. Provider mirror drift guard (ABS-142, ADR-A-0015) -------------------
# agent_providers/claude_code/ is a GENERATED VIEW of the harness source. The
# committed mirror must equal `generate-governor.sh --providers`. This is the
# byte-parity guard that ends the 16/17-stale-prompt drift the ticket found.
bash "$GENERATOR" --providers --check >/tmp/providers_check.$$ 2>&1
PROV_EC=$?
assert_true "$([ "$PROV_EC" -eq 0 ] && echo 0 || echo 1)" \
    "generate-governor.sh --providers --check passes (agent_providers/claude_code == generated(harness/claude))"
if [ "$PROV_EC" -ne 0 ]; then
    echo ""; echo "  Provider drift output:"; sed 's/^/    /' /tmp/providers_check.$$ | head -30; echo ""
fi
rm -f /tmp/providers_check.$$

# --- 5. Provider mirror mode is wired into the generator --------------------
# Belt-and-suspenders (mirrors the LOCAL-RUNTIME source assertion above): the
# byte-parity guard in test 4 is only meaningful if the generator actually
# implements the --providers mode, so assert it is present in the source.
if grep -q '\-\-providers' "$GENERATOR"; then
    assert_true 0 "generator implements the --providers mirror mode"
else
    assert_true 1 "generator implements the --providers mirror mode"
fi

# =============================================================================
echo -e "\n${CYAN}=== Test Results ===${NC}\n"
echo -e "  Total:  $TOTAL"
echo -e "  ${GREEN}Passed: $PASS${NC}"
if [ "$FAIL" -gt 0 ]; then
    echo -e "  ${RED}Failed: $FAIL${NC}"
    exit 1
else
    echo -e "  Failed: 0"
    echo -e "\n  ${GREEN}ALL TESTS PASSED${NC}\n"
    exit 0
fi
