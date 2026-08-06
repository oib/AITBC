#!/bin/bash
# =============================================================================
# Test: tracker-adapter lint -- agent defs resolve the tracker via $TRACKER_CMD
# =============================================================================
# ABS-155 (epic ABS-153). Regression guard for the ABS-130-RC-Run finding:
#
#   A non-implementer seat (po-agent) hardcoded `scripts/mock-tracker.sh` for
#   its comment/transition operations. In a live-Jira run (TRACKER_CMD=
#   scripts/jira-tracker.sh) that wrote to the mock store instead of the real
#   tracker -> writes no-op'd -> the ticket never moved -> HANDOFF-NOMOVE ->
#   respawn -> escalation to Blocked.
#
# ADR-A-0007 (adapter model): EVERY tracker operation of EVERY seat must go
# through the env-resolved adapter `$TRACKER_CMD` (default scripts/mock-tracker.sh),
# never a hardcoded `scripts/mock-tracker.sh <verb>` invocation.
#
# This lint asserts, over harness/claude/agents/*.md:
#   1. No actual-operation hardcode: `scripts/mock-tracker.sh` immediately
#      followed by a canonical tracker verb (get|search|children|create|
#      update|comment|transition|link|parent|child-count|events). The
#      env-parametrized form
#      `"${TRACKER_CMD:-scripts/mock-tracker.sh}" <verb>` does NOT match
#      (the literal `.sh}` is never directly followed by a verb), and prose
#      mentions of the default value (`default \`scripts/mock-tracker.sh\``)
#      are not operations, so they are allowed.
#   2. Positive control: the env-parametrized token IS present -- i.e. the
#      defs actually use `${TRACKER_CMD:-scripts/mock-tracker.sh}` (proves the
#      resolution form is wired, not that the operations were simply deleted).
#
# bash 3.2 / BSD safe: no `grep -P`, no associative arrays.
# Run from repo root: bash tests/tooling/test-tracker-adapter-lint.sh
# =============================================================================

set -u
# PILOT-46: strip inherited backend/tracker env before any fixture runs (tests/sandbox-guard.sh).
# shellcheck source=tests/sandbox-guard.sh
. "$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)/sandbox-guard.sh"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
AGENTS_DIR="$REPO_ROOT/harness/claude/agents"

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

echo -e "${CYAN}=== tracker-adapter lint (ADR-A-0007: ops via \$TRACKER_CMD) ===${NC}\n"

if [ ! -d "$AGENTS_DIR" ]; then
    echo -e "  ${RED}FAIL${NC} agents dir not found at $AGENTS_DIR"; exit 1
fi

# Canonical task-tracking verbs (task-tracking.md operation set; mock-tracker.sh
# dispatch). Covers every seat-usable operation incl. the WRITE op `update`.
# `assign` is orchestrator/runner-side (task-tracking.md) -> intentionally omitted.
VERBS='get|search|children|create|update|comment|transition|link|parent|child-count|events'
FORBIDDEN="scripts/mock-tracker\.sh[[:space:]]+($VERBS)"

# --- 1. No hardcoded operation invocation ------------------------------------
HITS="$(grep -rnE "$FORBIDDEN" "$AGENTS_DIR" 2>/dev/null || true)"
if [ -z "$HITS" ]; then
    assert_true 0 "no hardcoded 'scripts/mock-tracker.sh <verb>' operation in agent defs"
else
    assert_true 1 "no hardcoded 'scripts/mock-tracker.sh <verb>' operation in agent defs"
    echo ""; echo "  Offending lines (use \"\${TRACKER_CMD:-scripts/mock-tracker.sh}\" instead):"
    echo "$HITS" | sed 's/^/    /'
    echo ""
fi

# --- 2. Positive control: env-parametrized token is actually used ------------
if grep -rqF 'TRACKER_CMD:-scripts/mock-tracker.sh' "$AGENTS_DIR" 2>/dev/null; then
    assert_true 0 "agent defs use the env-parametrized token \${TRACKER_CMD:-scripts/mock-tracker.sh}"
else
    assert_true 1 "agent defs use the env-parametrized token \${TRACKER_CMD:-scripts/mock-tracker.sh}"
fi

# --- 3. Backend adapter parity (ABS-237 / spec §7) ---------------------------
# The Agentic-Backend curl shim must be a drop-in for the mock: same canonical
# subcommand surface, callable WITHOUT `help` (tracker-ops skill compat, ABS-222).
BACKEND_ADAPTER="$REPO_ROOT/scripts/backend-tracker.sh"
CONFORMANCE_SUITE="$REPO_ROOT/tests/tooling/test-backend-tracker.sh"

if [ -f "$BACKEND_ADAPTER" ]; then
    assert_true 0 "backend adapter present at scripts/backend-tracker.sh"
    bash -n "$BACKEND_ADAPTER" >/dev/null 2>&1
    assert_true $? "backend-tracker.sh has valid bash syntax"

    # Every canonical verb must be dispatched (usable directly, no help needed).
    missing=""
    for verb in get search create update comment transition link children parent child-count events assign; do
        grep -qE "^[[:space:]]*$verb\)" "$BACKEND_ADAPTER" || missing="$missing $verb"
    done
    if [ -z "$missing" ]; then
        assert_true 0 "backend-tracker.sh dispatches every canonical verb (no help-call needed, ABS-222)"
    else
        assert_true 1 "backend-tracker.sh dispatches every canonical verb (missing:$missing)"
    fi
else
    assert_true 1 "backend adapter present at scripts/backend-tracker.sh"
fi

# The conformance suite (Epic acceptance gate) must be registered here.
if [ -f "$CONFORMANCE_SUITE" ]; then
    assert_true 0 "backend conformance suite present at tests/test-backend-tracker.sh"
else
    assert_true 1 "backend conformance suite present at tests/test-backend-tracker.sh"
fi

# --- 4. No adapter request/response payload crosses argv (ABS-250 + ABS-263) --
# A whole Jira JSON (response OR request body) handed to python as an argv
# ARGUMENT dies with "Argument list too long" past the OS argv limit — ~32 KB on
# Windows/MSYS. ABS-250 moved every response parse to stdin; ABS-263 moved the two
# remaining request sites (comment ADF, create description) to stdin. This guard
# makes the argv-payload defect class permanently unrepeatable: no `json.loads(
# sys.argv` may remain in the Jira adapter.
JIRA_ADAPTER="$REPO_ROOT/scripts/jira-tracker.sh"
ARGV_HITS="$(grep -nE 'json\.loads\(sys\.argv' "$JIRA_ADAPTER" 2>/dev/null || true)"
if [ -z "$ARGV_HITS" ]; then
    assert_true 0 "no adapter payload on argv (no 'json.loads(sys.argv' in jira-tracker.sh)"
else
    assert_true 1 "no adapter payload on argv (no 'json.loads(sys.argv' in jira-tracker.sh)"
    echo ""; echo "  Offending lines (stream the payload over stdin instead):"
    echo "$ARGV_HITS" | sed 's/^/    /'
    echo ""
fi

# --- 5. shell/curl half of the argv-payload class (ABS-292) ------------------
# Check 4 guards only the python half. The shell/curl half — a raw request
# body expanded onto curl's argv (`--data-binary "$body"`) — hits the OS argv
# limit FIRST on Windows/MSYS (E2BIG via curl before python, per ABS-263's own
# context). Request bodies must go through the @file form
# (`--data-binary "@$bodyfile"`), never as an inline "$var" expansion. The
# regex keys on the quote being immediately followed by `$` (inline expansion);
# the legitimate `"@$file"` form starts with `"@` and never matches.
CURL_ARGV_HITS="$(grep -nE -- '--data(-binary|-raw)?[[:space:]]+"\$' "$JIRA_ADAPTER" 2>/dev/null || true)"
if [ -z "$CURL_ARGV_HITS" ]; then
    assert_true 0 "no raw request body on curl argv (no inline '--data-binary \"\$var\"' in jira-tracker.sh)"
else
    assert_true 1 "no raw request body on curl argv (no inline '--data-binary \"\$var\"' in jira-tracker.sh)"
    echo ""; echo "  Offending lines (deliver the body via a temp file: --data-binary \"@\$bodyfile\"):"
    echo "$CURL_ARGV_HITS" | sed 's/^/    /'
    echo ""
fi

# --- 6a. Phase-3 knowledge conformance registration (ABS-384 / ABS-231 S7) ---
# The §10 conformance cases 1–7 (ADR import round-trip, policy resolution matrix,
# human-only rejection guards, export/import lifecycle) must be wired into the
# backend conformance suite and have their golden fixtures on disk.
# Any regression in ADR import, policy resolution, or human-only guards must be a
# release blocker via these checks (AC: "registered in CI and test-tracker-adapter-lint.sh").

echo -e "\n${CYAN}=== Phase-3 knowledge conformance lint (ABS-384: §10 cases 1–7) ===${NC}\n"

PHASE3_GOLDEN_EMPTY="$REPO_ROOT/tests/fixtures/phase3-golden-empty-render.txt"
PHASE3_GOLDEN_MATRIX="$REPO_ROOT/tests/fixtures/phase3-golden-policy-matrix.txt"

# Golden fixture: empty render (§10/Case 3 — empty policy constellation).
if [ -f "$PHASE3_GOLDEN_EMPTY" ]; then
    assert_true 0 "phase3 golden empty-render fixture present at tests/fixtures/phase3-golden-empty-render.txt"
    # Fixture must contain the canonical empty render text (not empty, not obviously wrong).
    if grep -qF '(no applicable policy)' "$PHASE3_GOLDEN_EMPTY"; then
        assert_true 0 "phase3 empty-render fixture contains canonical '(no applicable policy)' text"
    else
        assert_true 1 "phase3 empty-render fixture contains canonical '(no applicable policy)' text (wrong content — deliberately break this file to prove the check bites)"
    fi
else
    assert_true 1 "phase3 golden empty-render fixture present at tests/fixtures/phase3-golden-empty-render.txt"
fi

# Golden fixture: policy resolution matrix (§10/Case 3 — org+project overlay).
if [ -f "$PHASE3_GOLDEN_MATRIX" ]; then
    assert_true 0 "phase3 golden policy-matrix fixture present at tests/fixtures/phase3-golden-policy-matrix.txt"
    # Must contain at least one '## ' heading (a policy block header).
    if grep -qE '^## ' "$PHASE3_GOLDEN_MATRIX"; then
        assert_true 0 "phase3 policy-matrix fixture contains at least one policy block header (## ...)"
    else
        assert_true 1 "phase3 policy-matrix fixture contains at least one policy block header (## ...) — broken fixture"
    fi
else
    assert_true 1 "phase3 golden policy-matrix fixture present at tests/fixtures/phase3-golden-policy-matrix.txt"
fi

# The conformance suite must contain all seven §10 case markers.
if [ -f "$CONFORMANCE_SUITE" ]; then
    MISSING_CASES=""
    for case_label in \
        "§10/Case 1" "§10/Case 2" "§10/Case 3" \
        "§10/Case 4" "§10/Case 5" \
        "§10/Case 6" "§10/Case 7"; do
        grep -qF "$case_label" "$CONFORMANCE_SUITE" || MISSING_CASES="$MISSING_CASES $case_label"
    done
    if [ -z "$MISSING_CASES" ]; then
        assert_true 0 "conformance suite contains all §10 case markers (Cases 1–7)"
    else
        assert_true 1 "conformance suite contains all §10 case markers (missing:$MISSING_CASES)"
    fi

    # Human-only rejection tests must be present (§10/Case 6 — ADR-accept + policy-write + eligible).
    for marker in \
        "ADR→Accepted → 403" \
        "policy write → 403" \
        "adr→eligible"; do
        if grep -qF "$marker" "$CONFORMANCE_SUITE"; then
            assert_true 0 "conformance suite covers human-only rejection: '$marker'"
        else
            assert_true 1 "conformance suite covers human-only rejection: '$marker'"
        fi
    done
fi

# --- 6. Forge adapter parity (ABS-350 / ABS-230 S3) -------------------------
# The forge CLI adapter (scripts/backend-forge.sh) must exist, parse correctly,
# dispatch the pr-state verb, and have its own conformance test wired here — the
# same structural guarantees as the backend-tracker.sh adapter (§3 above).
FORGE_ADAPTER="$REPO_ROOT/scripts/backend-forge.sh"
FORGE_SUITE="$REPO_ROOT/tests/tooling/test-backend-forge.sh"

echo -e "\n${CYAN}=== forge adapter lint (ABS-350: backend-forge.sh pr-state contract) ===${NC}\n"

if [ -f "$FORGE_ADAPTER" ]; then
    assert_true 0 "forge adapter present at scripts/backend-forge.sh"
    bash -n "$FORGE_ADAPTER" >/dev/null 2>&1
    assert_true $? "backend-forge.sh has valid bash syntax"
    # Must dispatch pr-state so the Done-gate can call it without a help sub-call.
    if grep -qE "^[[:space:]]*pr-state\)" "$FORGE_ADAPTER"; then
        assert_true 0 "backend-forge.sh dispatches the pr-state verb"
    else
        assert_true 1 "backend-forge.sh dispatches the pr-state verb (missing pr-state case)"
    fi
    # Must be executable (FORGE_CMD is invoked via the forge() helper in orchestrator.sh).
    [ -x "$FORGE_ADAPTER" ]
    assert_true $? "backend-forge.sh is executable"
else
    assert_true 1 "forge adapter present at scripts/backend-forge.sh"
fi

# Conformance suite (stdout-contract fixture tests) must be registered here.
if [ -f "$FORGE_SUITE" ]; then
    assert_true 0 "forge conformance suite present at tests/test-backend-forge.sh"
else
    assert_true 1 "forge conformance suite present at tests/test-backend-forge.sh"
fi

# =============================================================================
echo -e "\n${CYAN}=== Test Results ===${NC}\n"
echo -e "  Total:  $TOTAL"
echo -e "  ${GREEN}Passed: $PASS${NC}"
if [ "$FAIL" -gt 0 ]; then
    echo -e "  ${RED}Failed: $FAIL${NC}"
    echo -e "\n  ${RED}TESTS FAILED${NC}\n"
    exit 1
else
    echo -e "  Failed: $FAIL"
    echo -e "\n  ${GREEN}ALL TESTS PASSED${NC}\n"
    exit 0
fi
