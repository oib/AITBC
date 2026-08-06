#!/usr/bin/env bash
# =============================================================================
# ABS-258 / ADR-A-0022 — agent-def overlays composed at the spawn seam
# =============================================================================
# A project customizes a shipped agent def by ADDING
#   .agentic/overrides/agents/<role>.append.md
# instead of EDITING (forking) the def. The spawn seam
# (scripts/orchestrator-spawn-claude.sh) appends the overlay body AFTER the role
# body when it materializes the --agents JSON; the def file itself is never
# touched, so migration keeps classifying it REPLACE and never CONFLICT.
#
# The seam is exercised FOR REAL (not reimplemented): a stub `claude` binary is
# handed to it via ORCH_CLAUDE_BIN and records the --agents JSON it was invoked
# with. Assertions are made against that recorded JSON.
#
# Bash 3.2 / BSD-safe. Run from repo root: bash tests/tooling/test-agent-def-overlay.sh
# =============================================================================
set -u

# --- ABS-285: scrub ambient ORCH_* before driving the real seam/runner --------
# An agent seat exports ~37 ORCH_* vars. A non-empty one (ORCH_TOOLS bakes the
# seat's tool list into the --agents JSON; ORCH_OVERRIDES_DIR redirects overlay
# lookup) leaks into the code under test and flips assertions — the result would
# be a function of the SEAT that ran the suite, not of the commit, which voids
# every baseline comparison. Prefix-unset, not an enumerated list, so ORCH_*
# added later are covered by construction. This test sets what it needs, below.
unset "${!ORCH_@}"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
SEAM="$REPO_ROOT/scripts/orchestrator-spawn-claude.sh"

TEST_DIR=$(mktemp -d "${TMPDIR:-/tmp}/agent-def-overlay-test.XXXXXX")
trap 'rm -rf "$TEST_DIR"' EXIT

GREEN='\033[0;32m'; RED='\033[0;31m'; CYAN='\033[0;36m'; NC='\033[0m'
PASS=0; FAIL=0; TOTAL=0

assert_eq() {
    TOTAL=$((TOTAL + 1))
    if [ "$1" = "$2" ]; then
        echo -e "  ${GREEN}PASS${NC} $3"; PASS=$((PASS + 1))
    else
        echo -e "  ${RED}FAIL${NC} $3\n    expected: $2\n    got:      $1"; FAIL=$((FAIL + 1))
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
assert_not_contains() {
    TOTAL=$((TOTAL + 1))
    if printf '%s' "$1" | grep -qF -- "$2"; then
        echo -e "  ${RED}FAIL${NC} $3 (unexpectedly found: $2)"; FAIL=$((FAIL + 1))
    else
        echo -e "  ${GREEN}PASS${NC} $3"; PASS=$((PASS + 1))
    fi
}

# -----------------------------------------------------------------------------
# Fixtures: a HARNESS (ships the defs) and a PROJECT (owns the overlay).
# Kept as two separate dirs on purpose — that is the ABS-92 self-hosting split,
# and it is what proves the overlay resolves against the TARGET, not the harness.
# -----------------------------------------------------------------------------
HARNESS="$TEST_DIR/harness"
PROJECT="$TEST_DIR/project"
mkdir -p "$HARNESS/harness/claude/agents" "$PROJECT/.agentic/overrides/agents"

AGENTS_DIR="$HARNESS/harness/claude/agents"
cat > "$AGENTS_DIR/_common-rules.md" <<'EOF'
---
title: common rules
---
COMMONS LINE
EOF
cat > "$AGENTS_DIR/be-developer.md" <<'EOF'
---
name: be-developer
description: test role
tools: [Read, Bash]
---
ROLE BODY MARKER
EOF

OVERLAY="$PROJECT/.agentic/overrides/agents/be-developer.append.md"

# Stub `claude`: records the --agents JSON, then returns a well-formed result.
RECORDER="$TEST_DIR/fake-claude.sh"
AGENTSLOG="$TEST_DIR/agents.json"
cat > "$RECORDER" <<RECBIN
#!/usr/bin/env bash
while [ \$# -gt 0 ]; do
    case "\$1" in
        --agents) printf '%s' "\$2" > "$AGENTSLOG"; shift 2 ;;
        *) shift ;;
    esac
done
echo '{"result": "ok", "session_id": "rec"}'
RECBIN
chmod +x "$RECORDER"

# Drive the real seam once; echo the recorded --agents JSON. stderr -> $STDERRLOG.
STDERRLOG="$TEST_DIR/stderr.log"
spawn() {
    rm -f "$AGENTSLOG" "$STDERRLOG"
    ORCH_HARNESS_HOME="$HARNESS" \
    ORCH_AGENTS_DIR="$AGENTS_DIR" \
    ORCH_SPAWN_CWD="$PROJECT" \
    ORCH_CLAUDE_BIN="$RECORDER" \
        bash "$SEAM" be-developer ABS-258 /dev/null </dev/null >/dev/null 2>"$STDERRLOG"
    cat "$AGENTSLOG" 2>/dev/null || true
}

# The prompt the seam MUST emit with no overlay present — commons body, a blank
# line, then the role body. Asserted verbatim (not "contains"), so any drift in
# the composition is caught, and so the fail-open guarantee is a golden check.
NO_OVERLAY_JSON='{"be-developer": {"description": "test role", "prompt": "COMMONS LINE\n\nROLE BODY MARKER\n", "tools": ["Read", "Bash"]}}'

# =============================================================================
echo -e "\n${CYAN}=== fail-open: no overlay -> emission is byte-identical to pre-overlay ===${NC}\n"
# =============================================================================
rm -f "$OVERLAY"
JSON="$(spawn)"
assert_eq "$JSON" "$NO_OVERLAY_JSON" "no overlay -> --agents JSON is exactly the commons+role emission (fail-open parity)"
assert_not_contains "$(cat "$STDERRLOG")" "overlay" "no overlay -> seam says nothing about overlays"

# An EMPTY overrides dir is the same as no overlay at all (the shipped state of
# every project that never writes one).
JSON="$(ORCH_OVERRIDES_DIR="$PROJECT/.agentic/overrides/agents" spawn)"
assert_eq "$JSON" "$NO_OVERLAY_JSON" "empty overrides dir -> still byte-identical"

# =============================================================================
echo -e "\n${CYAN}=== AC2: base body + overlay body are BOTH present, overlay LAST ===${NC}\n"
# =============================================================================
# The real-world shape: a plain markdown section, no frontmatter.
cat > "$OVERLAY" <<'EOF'
## Project Section

OVERLAY BODY MARKER
EOF
DEF_BEFORE="$TEST_DIR/def.before"; cp "$AGENTS_DIR/be-developer.md" "$DEF_BEFORE"
JSON="$(spawn)"
assert_contains "$JSON" "ROLE BODY MARKER"    "overlay present -> role body still in the prompt"
assert_contains "$JSON" "OVERLAY BODY MARKER" "overlay present -> overlay body in the prompt"
assert_contains "$JSON" "COMMONS LINE"        "overlay present -> commons body still in the prompt (ABS-174 intact)"
assert_contains "$JSON" "## Project Section"  "overlay markdown structure preserved"
# Order matters: later text refines earlier text, so the overlay must come AFTER.
POS_ROLE=$(awk -v s="$JSON" 'BEGIN { print index(s, "ROLE BODY MARKER") }')
POS_OVER=$(awk -v s="$JSON" 'BEGIN { print index(s, "OVERLAY BODY MARKER") }')
TOTAL=$((TOTAL + 1))
if [ "$POS_OVER" -gt "$POS_ROLE" ] && [ "$POS_ROLE" -gt 0 ]; then
    echo -e "  ${GREEN}PASS${NC} overlay body is appended AFTER the role body"; PASS=$((PASS + 1))
else
    echo -e "  ${RED}FAIL${NC} overlay body is appended AFTER the role body (role@$POS_ROLE overlay@$POS_OVER)"; FAIL=$((FAIL + 1))
fi
# Frontmatter still comes from the ROLE DEF, even though it is no longer the last file.
assert_contains "$JSON" '"description": "test role"' "role def still supplies description when an overlay follows it"
assert_contains "$JSON" '"tools": ["Read", "Bash"]'  "role def still supplies tools when an overlay follows it"
assert_contains "$(cat "$STDERRLOG")" "overlay applied" "seam announces the applied overlay on stderr"

# D1, the load-bearing property: the seam composes at RUNTIME and never writes
# the def. The def keeping upstream bytes is exactly what makes migration
# classify it REPLACE instead of CONFLICT (asserted end-to-end in
# tests/test-migrate-project.sh).
TOTAL=$((TOTAL + 1))
if cmp -s "$DEF_BEFORE" "$AGENTS_DIR/be-developer.md"; then
    echo -e "  ${GREEN}PASS${NC} the on-disk agent def is byte-unchanged by the spawn (stays upstream-pure)"; PASS=$((PASS + 1))
else
    echo -e "  ${RED}FAIL${NC} the on-disk agent def is byte-unchanged by the spawn (stays upstream-pure)"; FAIL=$((FAIL + 1))
fi

# =============================================================================
echo -e "\n${CYAN}=== AC1/D2: an overlay cannot widen the seat's privilege grant ===${NC}\n"
# =============================================================================
# An overlay carrying frontmatter (tools/model/name) must have it STRIPPED: the
# toolset is the seat's privilege grant, and a project-owned file that migration
# never inspects must not be able to widen a security boundary.
cat > "$OVERLAY" <<'EOF'
---
name: hijacked
description: hijacked description
tools: [Read, Bash, Write, Edit, WebFetch]
model: opus
---
OVERLAY BODY MARKER
EOF
JSON="$(spawn)"
assert_contains "$JSON" '"tools": ["Read", "Bash"]' "overlay tools: does NOT widen the emitted toolset"
assert_not_contains "$JSON" "Write"   "overlay cannot add the Write tool"
assert_not_contains "$JSON" "WebFetch" "overlay cannot add the WebFetch tool"
assert_not_contains "$JSON" "hijacked" "overlay cannot rename the seat or hijack its description"
assert_contains "$JSON" '"be-developer"' "seat name still comes from the role def"
assert_contains "$JSON" "OVERLAY BODY MARKER" "overlay BODY is still appended (only frontmatter is stripped)"
assert_not_contains "$JSON" "model: opus" "overlay frontmatter is not leaked into the prompt body"
assert_contains "$(cat "$STDERRLOG")" "carries frontmatter" "seam NOTICEs that overlay frontmatter was stripped"

# =============================================================================
echo -e "\n${CYAN}=== D3: the overlay resolves against the TARGET, not the harness ===${NC}\n"
# =============================================================================
# Under the ABS-92 split the defs come from the harness but the overlay is a
# PROJECT artifact. A decoy overlay planted in the harness must never apply.
rm -f "$OVERLAY"
mkdir -p "$HARNESS/.agentic/overrides/agents"
printf 'HARNESS DECOY OVERLAY\n' > "$HARNESS/.agentic/overrides/agents/be-developer.append.md"
JSON="$(spawn)"
assert_not_contains "$JSON" "HARNESS DECOY" "an overlay in the HARNESS is ignored (overlay is a project artifact)"
assert_eq "$JSON" "$NO_OVERLAY_JSON" "harness decoy -> emission still byte-identical to no-overlay"

# ORCH_OVERRIDES_DIR points the lookup somewhere else entirely (escape hatch).
ELSEWHERE="$TEST_DIR/elsewhere"
mkdir -p "$ELSEWHERE"
printf 'ELSEWHERE OVERLAY MARKER\n' > "$ELSEWHERE/be-developer.append.md"
JSON="$(ORCH_OVERRIDES_DIR="$ELSEWHERE" spawn)"
assert_contains "$JSON" "ELSEWHERE OVERLAY MARKER" "ORCH_OVERRIDES_DIR overrides where the overlay is read from"

# An overlay for a DIFFERENT role must not bleed into this seat.
rm -f "$ELSEWHERE/be-developer.append.md"
printf 'QAS OVERLAY MARKER\n' > "$ELSEWHERE/qas.append.md"
JSON="$(ORCH_OVERRIDES_DIR="$ELSEWHERE" spawn)"
assert_not_contains "$JSON" "QAS OVERLAY MARKER" "an overlay for another role is not applied to this seat"

# =============================================================================
echo -e "\n${CYAN}=== Summary ===${NC}"
# =============================================================================
echo -e "  Total: $TOTAL  ${GREEN}Passed: $PASS${NC}  ${RED}Failed: $FAIL${NC}\n"
[ "$FAIL" -eq 0 ] || exit 1
echo -e "${GREEN}All agent-def overlay tests passed.${NC}"
