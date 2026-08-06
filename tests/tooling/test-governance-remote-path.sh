#!/usr/bin/env bash
# =============================================================================
# Test: governance sensors run on the LIVE remote path (PILOT-59 / epic PILOT-58)
# =============================================================================
# The governance sensors used to run ONLY in GitHub Actions, which never execute
# on the active push remote (GitLab). PILOT-59 wires them into `.gitlab-ci.yml`
# so they gate merges on the remote that actually matters. This test pins that
# wiring and proves the falsification (AC3): a branch that introduces a duplicate
# ADR number turns the WIRED adr-id sensor red, so the branch cannot merge.
#
# It does NOT need a live GitLab pipeline — a pipeline is not reproducible in the
# suite. Instead it asserts (a) every named sensor is wired into `.gitlab-ci.yml`
# and its backing script exists, (b) the pipeline runs on every push and on merge
# requests, and (c) the real ADR-id sensor the pipeline runs actually bites when a
# duplicate ADR number is planted.
#
# bash 3.2 + BSD tools only. Run from repo root: bash tests/tooling/test-governance-remote-path.sh
# =============================================================================

set -u

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
CI="$REPO_ROOT/.gitlab-ci.yml"

GREEN='\033[0;32m'; RED='\033[0;31m'; CYAN='\033[0;36m'; NC='\033[0m'
PASS=0; FAIL=0
pass() { echo -e "  ${GREEN}PASS${NC} $1"; PASS=$((PASS + 1)); }
fail() { echo -e "  ${RED}FAIL${NC} $1"; FAIL=$((FAIL + 1)); }

echo -e "${CYAN}=== governance sensors run on the live-remote path (PILOT-59) ===${NC}\n"

# --- 1. the live-remote CI config exists --------------------------------------
if [ -f "$CI" ]; then
    pass ".gitlab-ci.yml exists (live-remote path)"
else
    fail ".gitlab-ci.yml is missing — no live-remote enforcement path"
    echo -e "\n${CYAN}=== ${GREEN}$PASS passed${NC}, ${RED}$FAIL failed${NC} ===${NC}"
    exit 1
fi

# --- 2. every named fast sensor is wired AND its backing script exists ---------
echo -e "\n${CYAN}each named sensor is wired into .gitlab-ci.yml and its backing script exists${NC}"
# "sensor-label|backing-path"
SENSORS="adr-id-uniqueness|tests/test-adr-id-uniqueness.sh
adr-status|tests/test-adr-status.sh
rule-ledger|scripts/rule-ledger-check.sh
knob-doc-drift|scripts/orch-knob-doc-drift.sh
skills-parity|.github/scripts/check-skills-parity.sh"

while IFS='|' read -r label backing; do
    [ -n "$label" ] || continue
    if grep -qF "$backing" "$CI"; then
        pass "wired: $label -> $backing"
    else
        fail "NOT wired into .gitlab-ci.yml: $label ($backing)"
    fi
    if [ -f "$REPO_ROOT/$backing" ]; then
        pass "backing script present: $backing"
    else
        fail "backing script missing: $backing"
    fi
done <<EOF
$SENSORS
EOF

# --- 3. the pipeline runs on every push AND on merge requests (AC2) -----------
echo -e "\n${CYAN}pipeline fires on every push and on merge requests${NC}"
grep -q 'CI_COMMIT_BRANCH' "$CI" && pass "runs on branch pushes (CI_COMMIT_BRANCH rule)" \
    || fail "no branch-push rule in .gitlab-ci.yml"
grep -q 'merge_request_event' "$CI" && pass "runs on merge requests (merge_request_event rule)" \
    || fail "no merge-request rule in .gitlab-ci.yml"

# --- 4. falsification: a duplicate ADR number turns the WIRED sensor red (AC3) -
# Run a COPY of the wired sensor against a THROWAWAY ADR tree, so the real adrs/
# is never mutated — safe even when the sharded runner runs the real sensor
# concurrently in this same checkout. The sensor resolves its ADR dir as
# <script>/../adrs, so a copy at $tmp/tests/ scans $tmp/adrs/.
echo -e "\n${CYAN}falsification: a duplicate ADR number makes the wired sensor exit non-zero${NC}"
SENSOR="$REPO_ROOT/tests/tooling/test-adr-id-uniqueness.sh"
tmp="$(mktemp -d)"; trap 'rm -rf "$tmp"' EXIT
mkdir -p "$tmp/tests" "$tmp/adrs"
cp "$SENSOR" "$tmp/tests/test-adr-id-uniqueness.sh"

# Clean fixture -> the copied sensor is green (isolates the plant as the cause).
printf -- '---\nid: ADR-A-0001\nstatus: proposed\n---\nbody\n' > "$tmp/adrs/ADR-A-0001-alpha.md"
printf -- '---\nid: ADR-A-0002\nstatus: proposed\n---\nbody\n' > "$tmp/adrs/ADR-A-0002-beta.md"
if bash "$tmp/tests/test-adr-id-uniqueness.sh" >/dev/null 2>&1; then
    pass "wired sensor is green on a clean ADR tree"
else
    fail "wired sensor is red even on a clean ADR tree — cannot attribute the falsification"
fi

# Plant a duplicate ADR number -> the wired sensor must now exit non-zero.
printf -- '---\nid: ADR-A-0001\nstatus: proposed\n---\nbody\n' > "$tmp/adrs/ADR-A-0001-gamma.md"
if bash "$tmp/tests/test-adr-id-uniqueness.sh" >/dev/null 2>&1; then
    fail "duplicate ADR-A-0001 did NOT turn the wired adr-id sensor red"
else
    pass "duplicate ADR-A-0001 turns the wired adr-id sensor red (branch would not merge)"
fi
rm -rf "$tmp"; trap - EXIT

echo ""
echo -e "${CYAN}=== governance live-remote path: ${GREEN}$PASS passed${NC}, ${RED}$FAIL failed${NC} ===${NC}"
[ "$FAIL" -eq 0 ]
