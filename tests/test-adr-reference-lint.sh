#!/bin/bash
# =============================================================================
# Test: ADR Reference Linter (scripts/adr-reference-lint.sh) [ABS-315]
# =============================================================================
# Verifies the dangling-citation guard that closes the renumber-reference gap:
#   - clean tree (every cited id resolves)         => exit 0, no output
#   - a spec cites an id no ADR file defines        => exit 1, DANGLING
#   - an ADR cross-reference to a missing id         => exit 1, DANGLING
#   - README index rows are excluded (no FP)         => exit 0
#   - placeholder prose (ADR-YYY / ADR-A-00NN)       => not matched, exit 0
#   - real repo specs/ + adrs/ tree                  => exit 0 (no live dangler)
#
# Run from repo root: bash tests/test-adr-reference-lint.sh
# All fixtures live in a temp tree; the real-tree check is read-only.
# =============================================================================

set -u

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
LINT="$REPO_ROOT/scripts/adr-reference-lint.sh"

TEST_DIR=$(mktemp -d /tmp/adr-reflint-test-XXXXXX)
trap 'rm -rf "$TEST_DIR"' EXIT

GREEN='\033[0;32m'; RED='\033[0;31m'; CYAN='\033[0;36m'; NC='\033[0m'
PASS=0; FAIL=0; TOTAL=0
ok()  { PASS=$((PASS+1)); TOTAL=$((TOTAL+1)); echo -e "  ${GREEN}✓${NC} $1"; }
bad() { FAIL=$((FAIL+1)); TOTAL=$((TOTAL+1)); echo -e "  ${RED}✗${NC} $1"; }

echo -e "${CYAN}ADR Reference Linter${NC}"

mk_adr() { # <path> <id>
    mkdir -p "$(dirname "$1")"
    printf -- '---\nid: %s\nstatus: proposed\n---\n\nbody\n' "$2" > "$1"
}

# --- Case 1: clean tree — every citation resolves ---------------------------
C1="$TEST_DIR/c1"; mkdir -p "$C1/adrs/agentic" "$C1/specs"
mk_adr "$C1/adrs/agentic/ADR-A-0001-a.md" ADR-A-0001
mk_adr "$C1/adrs/agentic/ADR-A-0002-b.md" ADR-A-0002
printf 'Implements ADR-A-0001; see also ADR-A-0002.\n' > "$C1/specs/ABS-1-spec.md"
out="$(bash "$LINT" "$C1/adrs" "$C1/specs")"; rc=$?
if [ "$rc" -eq 0 ] && [ -z "$out" ]; then ok "clean tree: exit 0, no dangler"; else bad "clean tree: rc=$rc out=[$out]"; fi

# --- Case 2: spec cites an id no file defines (dangling renumber) ------------
C2="$TEST_DIR/c2"; mkdir -p "$C2/adrs/agentic" "$C2/specs"
mk_adr "$C2/adrs/agentic/ADR-A-0017-x.md" ADR-A-0017
printf 'Accepted per ADR-A-0016.\n' > "$C2/specs/ABS-190-spec.md"   # stale pre-renumber id
out="$(bash "$LINT" "$C2/adrs" "$C2/specs")"; rc=$?
if [ "$rc" -eq 1 ] && echo "$out" | grep -q 'DANGLING: ADR-A-0016'; then ok "spec dangling renumber ref -> exit 1"; else bad "spec dangling: rc=$rc out=[$out]"; fi

# --- Case 3: ADR cross-reference to a missing id ----------------------------
C3="$TEST_DIR/c3"; mkdir -p "$C3/adrs/agentic"
mk_adr "$C3/adrs/agentic/ADR-A-0003-c.md" ADR-A-0003
printf 'Superseded by ADR-A-0404.\n' >> "$C3/adrs/agentic/ADR-A-0003-c.md"
out="$(bash "$LINT" "$C3/adrs" "$C3/adrs")"; rc=$?
if [ "$rc" -eq 1 ] && echo "$out" | grep -q 'DANGLING: ADR-A-0404'; then ok "ADR cross-ref to missing id -> exit 1"; else bad "adr cross-ref: rc=$rc out=[$out]"; fi

# --- Case 4: README index rows excluded (range tables never FP) -------------
C4="$TEST_DIR/c4"; mkdir -p "$C4/adrs/agentic"
mk_adr "$C4/adrs/agentic/ADR-A-0005-e.md" ADR-A-0005
printf '| ADR | x |\n| ADR-A-0005 | ok |\n| ADR-A-0999 | archived-elsewhere |\n' > "$C4/adrs/agentic/README.md"
out="$(bash "$LINT" "$C4/adrs" "$C4/adrs")"; rc=$?
if [ "$rc" -eq 0 ] && [ -z "$out" ]; then ok "README index rows excluded -> no FP"; else bad "readme exclude: rc=$rc out=[$out]"; fi

# --- Case 5: placeholder prose not matched by the strict id shape -----------
C5="$TEST_DIR/c5"; mkdir -p "$C5/adrs/agentic" "$C5/specs"
mk_adr "$C5/adrs/agentic/ADR-A-0006-f.md" ADR-A-0006
printf 'Template: name it ADR-YYY or ADR-A-00NN; real ref ADR-A-0006.\n' > "$C5/specs/ABS-2-spec.md"
out="$(bash "$LINT" "$C5/adrs" "$C5/specs")"; rc=$?
if [ "$rc" -eq 0 ] && [ -z "$out" ]; then ok "placeholder prose not matched -> no FP"; else bad "placeholder: rc=$rc out=[$out]"; fi

# --- Case 6: real repo specs/ + adrs/ has no live dangling reference ---------
out="$(bash "$LINT")"; rc=$?
if [ "$rc" -eq 0 ] && [ -z "$out" ]; then ok "real specs/ + adrs/ tree: no live dangling reference"; else bad "real tree: rc=$rc out=[$out]"; fi

# =============================================================================
# PILOT-56: concurrency-safe file-walk. The linter flaked RED under the -P4
# `pool` stage when the tree it walks was mutated mid-scan. Cases 7-9 pin the
# fix. ID_RE mirrors the linter's strict id shape (used by the AC1 witness).
# =============================================================================
ID_RE='ADR-[ACP]-[0-9]{4}'

# Concurrent-mutation scenario shared by AC1 (witness) and AC2 (fix): a cited ADR
# file flickers out of and back into the defined set — models a read starved by
# -P4 resource contention, which drops a real id and dangles its citation.
mk_race_tree() { # <dir>
    mkdir -p "$1/adrs/agentic" "$1/specs"
    mk_adr "$1/adrs/agentic/ADR-A-0001-a.md" ADR-A-0001
    printf 'Implements ADR-A-0001.\n' > "$1/specs/ABS-1-spec.md"
}
start_flicker() { # <dir> -> sets FLICKER_PID
    # Rare, brief miss (present ~3ms, absent only the sub-ms rm->write window) —
    # models an occasional -P4 read-miss, not a 50%-duty flicker. The pre-fix walk
    # still catches it within the witness's 300 tries; the fixed linter's confirm
    # loop reliably re-reads the file present and drops the transient.
    ( for _ in $(seq 1 30000); do
        rm -f "$1/adrs/agentic/ADR-A-0001-a.md"
        printf -- '---\nid: ADR-A-0001\nstatus: proposed\n---\nbody\n' > "$1/adrs/agentic/ADR-A-0001-a.md"
        sleep 0.003
      done ) >/dev/null 2>&1 &
    FLICKER_PID=$!
}
stop_flicker() { kill "$FLICKER_PID" 2>/dev/null; wait "$FLICKER_PID" 2>/dev/null; }

# --- Case 7 (AC1): falsification witness — the PRE-FIX walk (a live `find|xargs
#     grep` + `grep -r`) CAN emit a false dangling when the tree mutates mid-walk.
#     Proves the scenario genuinely exercises the race. Inconclusive (never FAIL)
#     if the race does not manifest on this host, so the witness is not flaky. ---
C7="$TEST_DIR/c7"; mk_race_tree "$C7"
old_scan() { # reproduces the pre-fix danglers over C7
    local d
    d="$(find "$C7/adrs" -type f -name 'ADR-*.md' 2>/dev/null | xargs grep -h '^id:' 2>/dev/null \
        | sed -E 's/^id:[[:space:]]*//; s/[[:space:]]*$//' | grep -E "^${ID_RE}$" | sort -u || true)"
    grep -rnoE "$ID_RE" "$C7/adrs" "$C7/specs" 2>/dev/null | grep -vE '/README\.md:' \
        | grep -oE "$ID_RE" | sort -u | while read -r id; do
            printf '%s\n' "$d" | grep -qx "$id" || echo "$id"
        done
}
start_flicker "$C7"; witnessed=0
for _ in $(seq 1 300); do if [ -n "$(old_scan)" ]; then witnessed=1; break; fi; done
stop_flicker
if [ "$witnessed" -eq 1 ]; then ok "AC1: pre-fix walk flakes RED on a mid-walk mutation (race reproduced)"
else echo -e "  ${CYAN}~${NC} AC1: race did not manifest on this host (inconclusive, not a failure)"; fi

# --- Case 8 (AC2): the FIXED linter stays green under that SAME mutation across
#     20 back-to-back runs. ---------------------------------------------------
C8="$TEST_DIR/c8"; mk_race_tree "$C8"
start_flicker "$C8"; ac2_red=0
for _ in $(seq 1 20); do
    o="$(bash "$LINT" "$C8/adrs" "$C8/specs" 2>/dev/null)"; r=$?
    if [ "$r" -ne 0 ] || printf '%s' "$o" | grep -q DANGLING; then ac2_red=$((ac2_red+1)); fi
done
stop_flicker
if [ "$ac2_red" -eq 0 ]; then ok "AC2: fixed linter green across 20 runs under concurrent mutation"; else bad "AC2: $ac2_red/20 runs falsely RED under mutation"; fi

# --- Case 9 (AC5): a path enumerated but unreadable at read time (proxy for a
#     path that vanished between enumeration and read) neither aborts the scan
#     nor marks the tree dirty. Skipped as root (chmod 000 is still readable). --
if [ "$(id -u)" -eq 0 ]; then
    echo -e "  ${CYAN}~${NC} AC5: skipped (running as root — 000 perms do not deny root)"
else
    C9="$TEST_DIR/c9"; mkdir -p "$C9/adrs/agentic" "$C9/specs"
    mk_adr "$C9/adrs/agentic/ADR-A-0001-a.md" ADR-A-0001
    printf 'Implements ADR-A-0001.\n' > "$C9/specs/ABS-1-spec.md"
    printf 'ghost ref ADR-A-9999\n' > "$C9/specs/unreadable.md"   # cites an UNDEFINED id
    chmod 000 "$C9/specs/unreadable.md"                           # read fails at scan time
    out="$(bash "$LINT" "$C9/adrs" "$C9/specs" 2>/dev/null)"; rc=$?
    chmod 644 "$C9/specs/unreadable.md"                           # restore so trap-cleanup works
    if [ "$rc" -eq 0 ] && [ -z "$out" ]; then ok "AC5: unreadable enumerated path is skipped — no abort, no false dangling"; else bad "AC5: rc=$rc out=[$out]"; fi
fi

echo ""
echo -e "${CYAN}Passed: ${PASS}  Failed: ${FAIL}  Total: ${TOTAL}${NC}"
[ "$FAIL" -eq 0 ] || exit 1
exit 0
