#!/bin/bash
# =============================================================================
# Test: backend TS status-literal drift guard (ABS-424)
#        scripts/backend-status-literal-drift-guard.sh
# =============================================================================
# Drives the guard against a throwaway sandbox seeded from the REAL tree, so the
# real files are never mutated. Cases:
#   - clean tree (real files)                        => exit 0
#   - a marked literal renamed/removed in the YAML   => exit 1 (rename drift)
#   - a bogus marked literal added to a TS file      => exit 1 (dangling literal)
#   - all markers stripped from every TS file        => exit 1 (anti-rot lock)
#   - adr-lifecycle.yaml union supplies `Proposed`   => exit 0
#
# Run from repo root: bash tests/tooling/test-backend-status-literal-drift.sh
# bash 3.2 + BSD tools only.
# =============================================================================
set -u

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
GUARD="$REPO_ROOT/scripts/backend-status-literal-drift-guard.sh"

GREEN='\033[0;32m'; RED='\033[0;31m'; CYAN='\033[0;36m'; NC='\033[0m'
PASS=0; FAIL=0; TOTAL=0
ok()  { PASS=$((PASS+1)); TOTAL=$((TOTAL+1)); echo -e "  ${GREEN}✓${NC} $1"; }
bad() { FAIL=$((FAIL+1)); TOTAL=$((TOTAL+1)); echo -e "  ${RED}✗${NC} $1"; }

echo -e "${CYAN}Backend TS status-literal drift guard (ABS-424)${NC}"

SRC_YAML="$REPO_ROOT/backend/packages/core/src/workflows/statuses.yaml"
ADR_YAML="$REPO_ROOT/backend/packages/core/src/workflows/adr-lifecycle.yaml"
BOARD="$REPO_ROOT/backend/packages/core/src/board.ts"
INVAR="$REPO_ROOT/backend/packages/core/src/invariants.ts"
TRANS="$REPO_ROOT/backend/packages/core/src/transitions.ts"
DASH="$REPO_ROOT/backend/apps/server/src/routes/dashboard.ts"
UTIL="$REPO_ROOT/backend/apps/web/src/util.ts"

# Seed a sandbox from the real files; echoes the sandbox dir.
mk_sandbox() {
    local d; d="$(mktemp -d)"
    cp "$SRC_YAML" "$d/statuses.yaml"
    # Mirror the real tree: the guard validates against statuses.yaml ∪
    # adr-lifecycle.yaml, and board.ts marks the ADR-only 'Proposed' (ABS-383).
    [ -f "$ADR_YAML" ] && cp "$ADR_YAML" "$d/adr-lifecycle.yaml"
    cp "$BOARD" "$d/board.ts"
    cp "$INVAR" "$d/invariants.ts"
    cp "$TRANS" "$d/transitions.ts"
    cp "$DASH"  "$d/dashboard.ts"
    cp "$UTIL"  "$d/util.ts"
    printf '%s\n' "$d"
}

# Run the guard against a sandbox; sets $rc / $out.
run_guard() { # <sandbox> [extra env assignments...]
    local d="$1"; shift
    out="$(env \
        STATUS_SOURCE_FILE="$d/statuses.yaml" \
        STATUS_ADR_SOURCE_FILE="$d/adr-lifecycle.yaml" \
        STATUS_BOARD_TS_FILE="$d/board.ts" \
        STATUS_INVARIANTS_TS_FILE="$d/invariants.ts" \
        STATUS_TRANSITIONS_TS_FILE="$d/transitions.ts" \
        STATUS_DASHBOARD_TS_FILE="$d/dashboard.ts" \
        STATUS_WEB_UTIL_TS_FILE="$d/util.ts" \
        "$@" bash "$GUARD" 2>&1)"; rc=$?
}

# --- Case 1: clean sandbox -> exit 0 ----------------------------------------
D="$(mk_sandbox)"
run_guard "$D"
if [ "$rc" -eq 0 ]; then ok "clean tree: guard exits 0"; else bad "clean tree should pass (rc=$rc): $out"; fi
rm -rf "$D"

# --- Case 2: rename/remove a status in the YAML -> exit 1 --------------------
# "Merging" is a marked literal in invariants.ts + transitions.ts. Remove it
# from the YAML => the TS literal is now dangling.
D="$(mk_sandbox)"
grep -v '^  - name: Merging$' "$D/statuses.yaml" > "$D/statuses.yaml.tmp" && mv "$D/statuses.yaml.tmp" "$D/statuses.yaml"
run_guard "$D"
if [ "$rc" -eq 1 ] && printf '%s' "$out" | grep -q "Merging"; then
    ok "YAML rename/removal of 'Merging' turns the guard red"
else
    bad "removing 'Merging' from YAML should fail with a Merging drift line (rc=$rc): $out"
fi
rm -rf "$D"

# --- Case 3: bogus marked literal in a TS file -> exit 1 ---------------------
D="$(mk_sandbox)"
printf 'const BOGUS = "Totally Not A Status"; // drift-guard:status-name\n' >> "$D/dashboard.ts"
run_guard "$D"
if [ "$rc" -eq 1 ] && printf '%s' "$out" | grep -q "Totally Not A Status"; then
    ok "bogus marked TS literal turns the guard red"
else
    bad "a bogus marked literal should fail (rc=$rc): $out"
fi
rm -rf "$D"

# --- Case 4: all markers stripped -> exit 1 (anti-rot lock) ------------------
D="$(mk_sandbox)"
for f in board.ts invariants.ts transitions.ts dashboard.ts util.ts; do
    sed 's/ \/\/ drift-guard:status-name.*$//' "$D/$f" > "$D/$f.tmp" && mv "$D/$f.tmp" "$D/$f"
done
run_guard "$D"
if [ "$rc" -eq 1 ] && printf '%s' "$out" | grep -qi "anti-rot"; then
    ok "stripping every marker trips the anti-rot lock"
else
    bad "no markers at all should fail via anti-rot lock (rc=$rc): $out"
fi
rm -rf "$D"

# --- Case 5: adr-lifecycle.yaml union supplies a name -> exit 0 --------------
# A marked literal whose name lives ONLY in adr-lifecycle.yaml (not statuses.yaml)
# must pass when that file is present (the `Proposed` case).
D="$(mk_sandbox)"
printf 'statuses:\n  - name: Proposed\n' > "$D/adr-lifecycle.yaml"
printf 'const ADRISH = "Proposed"; // drift-guard:status-name\n' >> "$D/board.ts"
run_guard "$D"
if [ "$rc" -eq 0 ]; then
    ok "adr-lifecycle.yaml union validates an ADR-only literal ('Proposed')"
else
    bad "a literal valid via adr-lifecycle.yaml should pass (rc=$rc): $out"
fi
rm -rf "$D"

echo ""
echo -e "  ${CYAN}${PASS}/${TOTAL} passed${NC}"
[ "$FAIL" -eq 0 ] || exit 1
