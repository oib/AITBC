#!/bin/bash
# =============================================================================
# Test: Orchestrator State-Dir Marker Allowlist Freeze (ABS-522 / epic ABS-514)
# =============================================================================
# ADR-A-0026 names the filesystem-marker surface under $ORCH_STATE_DIR as the
# prose-reconstruction substrate to migrate into typed backend state. This
# test FREEZES that surface: every `$ORCH_STATE_DIR/<marker>` literal in
# scripts/*.sh must belong to a known, classified marker class, and every
# class must be documented in docs/sop/ORCHESTRATOR_STATE_MARKERS.md. A NEW
# marker type in scripts/ turns this red until it is added to BOTH the
# allowlist below and the inventory doc (a deliberate, reviewed act).
#
# Fixture override: MARKER_SCRIPTS_DIR (dir whose *.sh are scanned).
# Run from repo root: bash tests/tooling/test-orchestrator-marker-allowlist.sh
# =============================================================================

set -u
# PILOT-46: strip inherited backend/tracker env before any fixture runs (tests/sandbox-guard.sh).
# shellcheck source=tests/sandbox-guard.sh
. "$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)/sandbox-guard.sh"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
SCRIPTS="${MARKER_SCRIPTS_DIR:-$REPO_ROOT/scripts}"
DOC="$REPO_ROOT/docs/sop/ORCHESTRATOR_STATE_MARKERS.md"

PASS=0
FAIL=0
TOTAL=0
GREEN='\033[0;32m'; RED='\033[0;31m'; CYAN='\033[0;36m'; NC='\033[0m'

check() { # check <ok:0|1> <label> [detail]
    TOTAL=$((TOTAL + 1))
    if [ "$1" -eq 0 ]; then
        echo -e "  ${GREEN}PASS${NC} $2"; PASS=$((PASS + 1))
    else
        echo -e "  ${RED}FAIL${NC} $2${3:+ ($3)}"; FAIL=$((FAIL + 1))
    fi
}

# The frozen marker surface. `<name>-` entries are prefix families
# (per-ticket/per-day); everything else matches exactly.
ALLOW="budget-restart-count followup-budget spawn-ledger- escalation- escalation-workcredit- ops-sweep-last
locks worktree.lock probe-inflight claim-warn-
blocker- backoff- wtfail- halt- outage stuck-state standstill-state standstill-episode local-main-drift fastfail
run.log telemetry packets ops-sweep-reports sessions instance-id .claude-account shipper-cursor shipper-executed-commands fastlane-bundle- spawn-pid-ledger"

# extract_markers — every $ORCH_STATE_DIR/<token> literal, variable suffixes
# stripped to the class prefix, trailing separators normalized.
extract_markers() {
    grep -ohE '\$ORCH_STATE_DIR/[A-Za-z0-9._$-]+' "$SCRIPTS"/*.sh 2>/dev/null \
        | sed -E 's|^\$ORCH_STATE_DIR/||; s/\$.*$//; s/\.+$//' \
        | sed -E '/-$/!s/$//' | sort -u | grep -v '^$'
}

allowed() { # allowed <marker> -> 0 when covered by the allowlist
    local m="$1" a
    for a in $ALLOW; do
        case "$a" in
            *-) case "$m" in "$a"*|"${a%-}") return 0 ;; esac ;;
            *)  [ "$m" = "$a" ] && return 0 ;;
        esac
    done
    return 1
}

echo -e "${CYAN}=== Orchestrator marker allowlist freeze (ABS-522) ===${NC}\n"

# --- every marker read/written in scripts/ is a known class --------------------
echo -e "${CYAN}Scripts surface vs allowlist${NC}"
unknown=""
while IFS= read -r m; do
    [ -n "$m" ] || continue
    allowed "$m" || unknown="$unknown $m"
done < <(extract_markers)
check "$([ -z "$unknown" ]; echo $?)" "no unclassified \$ORCH_STATE_DIR marker in scripts/" "new:$unknown"

# --- every allowlist class is documented in the inventory doc ------------------
echo -e "\n${CYAN}Allowlist vs inventory doc${NC}"
if [ -f "$DOC" ]; then
    undoc=""
    for a in $ALLOW; do
        # Directory classes are documented with a trailing slash (`locks/`).
        grep -qF -- "\`$a\`" "$DOC" || grep -qF -- "\`$a/\`" "$DOC" || undoc="$undoc $a"
    done
    check "$([ -z "$undoc" ]; echo $?)" "every allowlist class appears in ORCHESTRATOR_STATE_MARKERS.md" "missing:$undoc"
else
    check 1 "inventory doc exists" "$DOC missing"
fi

# --- fixture: a NOVEL marker write turns the freeze red ------------------------
echo -e "\n${CYAN}Novel marker fixture -> red${NC}"
TMP=$(mktemp -d "${TMPDIR:-/tmp}/marker-freeze-test-XXXXXX")
trap 'rm -rf "$TMP"' EXIT
printf '#!/bin/bash\ntouch "$ORCH_STATE_DIR/frobnication-cache"\n' > "$TMP/new.sh"
novel="$(MARKER_SCRIPTS_DIR="$TMP" SCRIPTS="$TMP" grep -ohE '\$ORCH_STATE_DIR/[A-Za-z0-9._$-]+' "$TMP"/*.sh | sed -E 's|^\$ORCH_STATE_DIR/||')"
nv_ok=1
allowed "$novel" || nv_ok=0
check "$([ "$nv_ok" -eq 0 ]; echo $?)" "novel marker 'frobnication-cache' is NOT allowed (freeze holds)"

# =============================================================================
echo -e "\n${CYAN}=== Test Results ===${NC}\n"
echo -e "  Total:  $TOTAL"
echo -e "  ${GREEN}Passed: $PASS${NC}"
if [ "$FAIL" -gt 0 ]; then
    echo -e "  ${RED}Failed: $FAIL${NC}"; exit 1
else
    echo -e "  Failed: 0"; echo -e "\n  ${GREEN}ALL TESTS PASSED${NC}\n"; exit 0
fi
