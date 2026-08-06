#!/bin/bash
# =============================================================================
# Test: ADR Acceptance-Closeout Drift Detector (scripts/adr-acceptance-drift.sh)
# [ABS-212]
# =============================================================================
# Verifies the detector that guards the ADR file<->record acceptance closeout:
#   - clean tree (statuses consistent)            => exit 0, no DRIFT
#   - accepted_by present but status: proposed    => exit 1, DRIFT (signal b)
#   - index marks **Accepted**, file proposed     => exit 1, DRIFT (signal a)
#   - index **Accepted** + file accepted          => exit 0 (closed out)
#   - in-text ADR mention in an Accepted row      => NO false positive
#   - real repo adrs/ tree                        => exit 0 (no live drift)
#
# Run from repo root: bash tests/tooling/test-adr-acceptance-closeout.sh
# All fixtures live in a temp tree; the real adrs/ check is read-only.
# =============================================================================

set -u

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
DETECTOR="$REPO_ROOT/scripts/adr-acceptance-drift.sh"

TEST_DIR=$(mktemp -d /tmp/adr-closeout-test-XXXXXX)
trap 'rm -rf "$TEST_DIR"' EXIT

GREEN='\033[0;32m'; RED='\033[0;31m'; CYAN='\033[0;36m'; NC='\033[0m'
PASS=0; FAIL=0; TOTAL=0

ok()   { PASS=$((PASS+1)); TOTAL=$((TOTAL+1)); echo -e "  ${GREEN}✓${NC} $1"; }
bad()  { FAIL=$((FAIL+1)); TOTAL=$((TOTAL+1)); echo -e "  ${RED}✗${NC} $1"; }

echo -e "${CYAN}ADR Acceptance-Closeout Drift Detector${NC}"

# --- fixture helpers ---------------------------------------------------------
mk_adr() { # <path> <status> [accepted_by] [accepted_date]
    local p="$1" st="$2" ab="${3:-}" ad="${4:-}"
    mkdir -p "$(dirname "$p")"
    {
        echo "---"
        echo "id: $(basename "$p" .md | grep -oE '^ADR-[A-Z]-[0-9]+')"
        echo "title: fixture"
        echo "status: $st"
        [ -n "$ab" ] && echo "accepted_by: \"$ab\""
        [ -n "$ad" ] && echo "accepted_date: \"$ad\""
        echo "---"
        echo ""
        echo "body"
    } > "$p"
}

mk_index() { # <path> writes an agentic-style index; rows passed on stdin
    local p="$1"; mkdir -p "$(dirname "$p")"
    { echo "| ADR | Decision |"; echo "|-----|----------|"; cat; } > "$p"
}

# --- Case 1: clean tree -> exit 0, no output --------------------------------
C1="$TEST_DIR/c1"; mkdir -p "$C1/agentic"
mk_adr "$C1/agentic/ADR-A-0001-a.md" proposed
mk_adr "$C1/agentic/ADR-A-0002-b.md" accepted "Human" "2026-01-01"
mk_index "$C1/agentic/README.md" <<'EOF'
| [ADR-A-0001](ADR-A-0001-a.md) | proposed thing |
| [ADR-A-0002](ADR-A-0002-b.md) | done thing — **Accepted** |
EOF
out="$(bash "$DETECTOR" "$C1" "$C1/agentic/README.md")"; rc=$?
if [ "$rc" -eq 0 ] && [ -z "$out" ]; then ok "clean tree: exit 0, no drift"; else bad "clean tree: rc=$rc out=[$out]"; fi

# --- Case 2: accepted_by present but status proposed (signal b) -------------
C2="$TEST_DIR/c2"; mkdir -p "$C2/agentic"
mk_adr "$C2/agentic/ADR-A-0003-c.md" proposed "Human" "2026-02-02"
mk_index "$C2/agentic/README.md" <<'EOF'
| [ADR-A-0003](ADR-A-0003-c.md) | thing |
EOF
out="$(bash "$DETECTOR" "$C2" "$C2/agentic/README.md")"; rc=$?
if [ "$rc" -eq 1 ] && echo "$out" | grep -q 'DRIFT: ADR-A-0003'; then ok "signal b: accepted_by + proposed -> drift"; else bad "signal b: rc=$rc out=[$out]"; fi

# --- Case 3: index Accepted, file proposed (signal a) -----------------------
C3="$TEST_DIR/c3"; mkdir -p "$C3/agentic"
mk_adr "$C3/agentic/ADR-A-0004-d.md" proposed
mk_index "$C3/agentic/README.md" <<'EOF'
| [ADR-A-0004](ADR-A-0004-d.md) | thing — **Accepted** |
EOF
out="$(bash "$DETECTOR" "$C3" "$C3/agentic/README.md")"; rc=$?
if [ "$rc" -eq 1 ] && echo "$out" | grep -q 'DRIFT: ADR-A-0004'; then ok "signal a: index Accepted + proposed -> drift"; else bad "signal a: rc=$rc out=[$out]"; fi

# --- Case 4: index Accepted + file accepted -> closed out -------------------
C4="$TEST_DIR/c4"; mkdir -p "$C4/agentic"
mk_adr "$C4/agentic/ADR-A-0005-e.md" accepted "Human" "2026-03-03"
mk_index "$C4/agentic/README.md" <<'EOF'
| [ADR-A-0005](ADR-A-0005-e.md) | thing — **Accepted** |
EOF
out="$(bash "$DETECTOR" "$C4" "$C4/agentic/README.md")"; rc=$?
if [ "$rc" -eq 0 ] && [ -z "$out" ]; then ok "closed out: index Accepted + file accepted -> no drift"; else bad "closed out: rc=$rc out=[$out]"; fi

# --- Case 5: in-text mention of a proposed ADR inside an Accepted row -------
# The proposed ADR-A-0006 is only mentioned as prose in ADR-A-0007's Accepted
# row; its own row carries no marker. Must NOT false-positive.
C5="$TEST_DIR/c5"; mkdir -p "$C5/agentic"
mk_adr "$C5/agentic/ADR-A-0006-f.md" proposed
mk_adr "$C5/agentic/ADR-A-0007-g.md" accepted "Human" "2026-04-04"
mk_index "$C5/agentic/README.md" <<'EOF'
| [ADR-A-0006](ADR-A-0006-f.md) | pending thing |
| [ADR-A-0007](ADR-A-0007-g.md) | builds on ADR-A-0006/0005 — **Accepted** |
EOF
out="$(bash "$DETECTOR" "$C5" "$C5/agentic/README.md")"; rc=$?
if [ "$rc" -eq 0 ] && [ -z "$out" ]; then ok "no false positive on in-text mention in Accepted row"; else bad "in-text mention: rc=$rc out=[$out]"; fi

# --- Case 6: real repo adrs/ tree has no live drift -------------------------
out="$(bash "$DETECTOR")"; rc=$?
if [ "$rc" -eq 0 ] && [ -z "$out" ]; then ok "real adrs/ tree: no live acceptance drift"; else bad "real adrs/ tree: rc=$rc out=[$out]"; fi

echo ""
echo -e "${CYAN}Passed: ${PASS}  Failed: ${FAIL}  Total: ${TOTAL}${NC}"
[ "$FAIL" -eq 0 ] || exit 1
exit 0
