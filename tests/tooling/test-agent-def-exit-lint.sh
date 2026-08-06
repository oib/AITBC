#!/bin/bash
# =============================================================================
# Test: agent-def exit-state lint — exit targets must be REAL statuses (ABS-307)
# =============================================================================
# Regression guard for the consumer Befund (Florian, 2026-07-14 / BUSCH-97):
# the implementer defs shipped `Exit State: "Ready for QAS"` — a status that
# exists in NO v3 pipeline — so seats improvised illegal transitions (observed:
# In Progress -> Done twice, stranding an unmerged branch behind a Done status).
# ABS-253 fixed the three implementer defs; this lint makes the CLASS
# unrepeatable across every agent def:
#
#   1. The ambiguous bare `**Exit State**:` key may not reappear — defs use the
#      split the SOP mandates (AGENT_WORKFLOW_SOP.md "Exit States" table):
#      `**Exit status (canonical)**` (a real status) + `**Handoff label**`
#      (free prose, never a transition target).
#   2. Every literal `transition <id> "X"` target in a def must exist in
#      profiles/neutral/adapters/statuses.yaml.
#   3. Positive control: the three implementer defs carry the canonical exit
#      key and never name `Done` as their transition target (ADR-A-0005:
#      Done comes only from the human PR merge).
#
# bash 3.2 / BSD safe. Run from repo root: bash tests/tooling/test-agent-def-exit-lint.sh
# =============================================================================

set -u
unset "${!ORCH_@}"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
AGENTS_DIR="$REPO_ROOT/harness/claude/agents"
STATUSES="$REPO_ROOT/profiles/neutral/adapters/statuses.yaml"

PASS=0; FAIL=0; TOTAL=0
GREEN='\033[0;32m'; RED='\033[0;31m'; CYAN='\033[0;36m'; NC='\033[0m'

assert_true() {
    local code="$1" label="$2" detail="${3:-}"
    TOTAL=$((TOTAL + 1))
    if [ "$code" = "0" ]; then
        echo -e "  ${GREEN}PASS${NC} $label"; PASS=$((PASS + 1))
    else
        echo -e "  ${RED}FAIL${NC} $label"; FAIL=$((FAIL + 1))
        [ -n "$detail" ] && printf '%s\n' "$detail" | sed 's/^/    /'
    fi
}

echo -e "${CYAN}=== agent-def exit lint (ABS-307: exit targets are real statuses) ===${NC}\n"

[ -d "$AGENTS_DIR" ] || { echo "FAIL: agents dir not found at $AGENTS_DIR"; exit 1; }
[ -f "$STATUSES" ]   || { echo "FAIL: statuses.yaml not found at $STATUSES"; exit 1; }

# Canonical status registry: the `- name:` entries of statuses.yaml.
KNOWN_STATUSES="$(grep -E '^  - name: ' "$STATUSES" | sed 's/^  - name: //')"

# --- 1. The ambiguous bare `Exit State` key is gone ---------------------------
HITS="$(grep -rnE '\*\*Exit State' "$AGENTS_DIR" 2>/dev/null || true)"
if [ -z "$HITS" ]; then
    assert_true 0 "no def carries the ambiguous '**Exit State**' key (use 'Exit status (canonical)' + 'Handoff label')"
else
    assert_true 1 "no def carries the ambiguous '**Exit State**' key (use 'Exit status (canonical)' + 'Handoff label')" "$HITS"
fi

# --- 2. Every literal transition target in a def is a real status -------------
# Matches the recipe form the defs ship: `transition <ticket-id> "X"` (and any
# `transition ABS-XXX "X"` example). The target must appear in statuses.yaml.
BAD_TARGETS=""
while IFS= read -r line; do
    [ -n "$line" ] || continue
    target="$(printf '%s' "$line" | sed -E 's/.*transition[[:space:]]+[^[:space:]]+[[:space:]]+"([^"]+)".*/\1/')"
    [ -n "$target" ] || continue
    # A `<placeholder>` target (e.g. "<pre-blocked status>") is a recipe
    # variable, not a literal status — the seat fills it at runtime.
    case "$target" in "<"*">") continue ;; esac
    if ! printf '%s\n' "$KNOWN_STATUSES" | grep -qxF "$target"; then
        BAD_TARGETS="${BAD_TARGETS}${line}
"
    fi
done <<EOF
$(grep -rhoE 'transition[[:space:]]+[^[:space:]]+[[:space:]]+"[^"]+"' "$AGENTS_DIR" 2>/dev/null || true)
EOF
if [ -z "$BAD_TARGETS" ]; then
    assert_true 0 "every literal transition target in the defs exists in statuses.yaml"
else
    assert_true 1 "every literal transition target in the defs exists in statuses.yaml" "$BAD_TARGETS"
fi

# --- 3. Positive controls ------------------------------------------------------
for def in be-developer fe-developer data-engineer; do
    if grep -q 'Exit status (canonical)' "$AGENTS_DIR/$def.md" 2>/dev/null; then
        assert_true 0 "$def.md declares the canonical exit status key"
    else
        assert_true 1 "$def.md declares the canonical exit status key"
    fi
    # ADR-A-0005 / ABS-211: an implementer may never transition to Done — that
    # is the exact improvisation observed on BUSCH-97.
    if grep -E 'transition[[:space:]]+[^[:space:]]+[[:space:]]+"Done"' "$AGENTS_DIR/$def.md" >/dev/null 2>&1; then
        assert_true 1 "$def.md never targets 'Done' in a transition recipe"
    else
        assert_true 0 "$def.md never targets 'Done' in a transition recipe"
    fi
done

# --- 4. Self-test: the lint CATCHES the original defect shape -----------------
# Mutation proof against a scratch file — a lint that cannot go red is no lint.
SCRATCH="$(mktemp -d /tmp/exit-lint-XXXXXX)"
printf '%s\n' '**Exit State**: "Ready for QAS"' > "$SCRATCH/evil.md"
if grep -rnE '\*\*Exit State' "$SCRATCH" >/dev/null 2>&1; then
    assert_true 0 "self-test: the reintroduced 'Exit State: \"Ready for QAS\"' shape IS caught"
else
    assert_true 1 "self-test: the reintroduced 'Exit State: \"Ready for QAS\"' shape IS caught"
fi
rm -rf "$SCRATCH"

# =============================================================================
echo -e "\n${CYAN}=== Test Results ===${NC}\n"
echo -e "  Total:  $TOTAL"
echo -e "  ${GREEN}Passed: $PASS${NC}"
if [ "$FAIL" -gt 0 ]; then
    echo -e "  ${RED}Failed: $FAIL${NC}\n  ${RED}TESTS FAILED${NC}\n"; exit 1
else
    echo -e "  Failed: $FAIL\n  ${GREEN}ALL TESTS PASSED${NC}\n"; exit 0
fi
