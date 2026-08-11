#!/usr/bin/env bash
# =============================================================================
# AITBC-65 — the Devin CLI spawn seam honors the provider-seam contract
# =============================================================================
# scripts/orchestrator-spawn-devin.sh is the Devin binding of the §3.1 provider
# seam. It has to reproduce the parts of the Claude binding that are LOAD-BEARING
# for the workflow, not just launch a binary:
#
#   - ABS-174 commons: _common-rules.md is prepended to every role body, so
#     cross-seat rules live exactly once instead of in every def. A missing
#     prepend silently drops rules the Claude seats all receive.
#   - ABS-174 fragment guard: `_common-rules` is NOT a spawnable role.
#   - ABS-258 overlay: <role>.append.md is APPENDED after the role body so a
#     project can refine a def without forking it.
#   - ABS-535 skill-path rewrite: stable-harness references point at the LIVE
#     skills dir, otherwise the seat loads an inert shipped copy.
#   - ABS-57 separation of duties: a WRITE-FREE ORCH_TOOLS override must leave
#     the seat unable to edit the code under review. On Devin the mechanical
#     gate is `--permission-mode auto` (measured: in -p mode a write is rejected
#     as "requires confirmation"). `--agent-config` allowed-tools/permissions.deny
#     were measured NOT to block the write tool, so they are not relied on.
#   - ABS-92 / ABS-111 C9: cwd is ORCH_SPAWN_CWD, else ORCH_TARGET_REPO.
#   - Model aliases pass through untouched, so `opus` keeps meaning the CURRENT
#     Opus family instead of being pinned to an older version.
#
# The seam is exercised FOR REAL (not reimplemented): a stub `devin` handed via
# ORCH_DEVIN_BIN records the argv and the composed prompt file. No real spawn.
# Same harness/project split + recorder pattern as tests/test-spawn-tmpdir.sh.
#
# Bash 3.2 / BSD-safe. Run from repo root: bash tests/tooling/test-spawn-devin.sh
# =============================================================================
set -u

# ABS-285: scrub ambient ORCH_* so the result is a function of the commit, not
# of the seat that ran the suite. This test sets everything it needs below.
unset "${!ORCH_@}"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
SEAM="$REPO_ROOT/scripts/orchestrator-spawn-devin.sh"

TEST_DIR=$(mktemp -d "${TMPDIR:-/tmp}/spawn-devin-test.XXXXXX")
trap 'rm -rf "$TEST_DIR"' EXIT

GREEN='\033[0;32m'; RED='\033[0;31m'; CYAN='\033[0;36m'; NC='\033[0m'
PASS=0; FAIL=0; TOTAL=0

assert_contains() {
    TOTAL=$((TOTAL + 1))
    if printf '%s' "$1" | grep -qF -- "$2"; then
        echo -e "  ${GREEN}PASS${NC} $3"; PASS=$((PASS + 1))
    else
        echo -e "  ${RED}FAIL${NC} $3 (missing '$2')"; FAIL=$((FAIL + 1))
    fi
}
assert_not_contains() {
    TOTAL=$((TOTAL + 1))
    if printf '%s' "$1" | grep -qF -- "$2"; then
        echo -e "  ${RED}FAIL${NC} $3 (unexpectedly found '$2')"; FAIL=$((FAIL + 1))
    else
        echo -e "  ${GREEN}PASS${NC} $3"; PASS=$((PASS + 1))
    fi
}
assert_exit() {
    TOTAL=$((TOTAL + 1))
    if [ "$1" = "$2" ]; then
        echo -e "  ${GREEN}PASS${NC} $3"; PASS=$((PASS + 1))
    else
        echo -e "  ${RED}FAIL${NC} $3 (expected exit $2, got $1)"; FAIL=$((FAIL + 1))
    fi
}

# --- fixture: a harness with commons + one role, and a live skills dir --------
HARNESS="$TEST_DIR/harness-home"
mkdir -p "$HARNESS/.claude/agents" "$HARNESS/.claude/skills/ponytail"
echo "# ponytail" > "$HARNESS/.claude/skills/ponytail/SKILL.md"

cat > "$HARNESS/.claude/agents/_common-rules.md" <<'EOF'
---
name: _common-rules
description: shared fragment
---
COMMONS_MARKER_present_in_every_seat
EOF

cat > "$HARNESS/.claude/agents/qas.md" <<'EOF'
---
name: qas
description: Quality Assurance Specialist
tools: [Read, Bash, Grep]
model: sonnet
---
ROLE_BODY_MARKER for the qas seat.
Apply the rules in `harness/claude/skills/ponytail` verbatim.
EOF

cat > "$HARNESS/.claude/agents/be-developer.md" <<'EOF'
---
name: be-developer
description: Backend Developer
tools: [Read, Write, Edit, Bash]
model: opus
---
ROLE_BODY_MARKER for the be-developer seat.
EOF

PACKET="$TEST_DIR/packet.md"
printf 'TICKET: AITBC-999\nTASK: do the thing.\n\n## Handoff\nrequired.\n' > "$PACKET"

# --- recorder stub: writes argv + the composed prompt to files ----------------
STUB_DIR="$TEST_DIR/bin"
mkdir -p "$STUB_DIR"
cat > "$STUB_DIR/devin" <<'EOF'
#!/usr/bin/env bash
echo "$*" > "$RECORD_ARGV"
prev=""
for a in "$@"; do
    if [ "$prev" = "--prompt-file" ]; then cp "$a" "$RECORD_PROMPT"; fi
    prev="$a"
done
EOF
chmod +x "$STUB_DIR/devin"

RECORD_ARGV="$TEST_DIR/argv.txt"
RECORD_PROMPT="$TEST_DIR/prompt.md"
export RECORD_ARGV RECORD_PROMPT

run_seam() {
    # usage: run_seam <role> [env assignments...]
    rm -f "$RECORD_ARGV" "$RECORD_PROMPT"
    local role="$1"; shift
    env "$@" \
        ORCH_HARNESS_HOME="$HARNESS" \
        ORCH_DEVIN_BIN="$STUB_DIR/devin" \
        RECORD_ARGV="$RECORD_ARGV" RECORD_PROMPT="$RECORD_PROMPT" \
        bash "$SEAM" "$role" AITBC-999 "$PACKET" < "$PACKET" >/dev/null 2>&1
    echo $?
}

echo ""
echo -e "${CYAN}=== AITBC-65: Devin spawn seam contract ===${NC}"

echo ""
echo -e "${CYAN}AC1 — ABS-174 commons are prepended to the role body${NC}"
rc=$(run_seam qas)
prompt=$(cat "$RECORD_PROMPT" 2>/dev/null || echo "")
assert_exit "$rc" 0 "seam exits 0 on a well-formed spawn"
assert_contains "$prompt" "COMMONS_MARKER_present_in_every_seat" "commons body reached the seat prompt"
assert_contains "$prompt" "ROLE_BODY_MARKER for the qas seat" "role body reached the seat prompt"
assert_not_contains "$prompt" "name: _common-rules" "commons frontmatter was stripped, not injected"

echo ""
echo -e "${CYAN}AC2 — ABS-535 skill references point at the LIVE skills dir${NC}"
assert_contains "$prompt" "$HARNESS/.claude/skills/ponytail" "reference rewritten to the live skills dir"
assert_not_contains "$prompt" "harness/claude/skills/ponytail" "no inert shipped-harness LOAD path remains"

echo ""
echo -e "${CYAN}AC3 — the packet and the handoff instruction reach the seat${NC}"
assert_contains "$prompt" "TICKET: AITBC-999" "packet body reached the seat prompt"
assert_contains "$prompt" "## Handoff" "handoff instruction present"

echo ""
echo -e "${CYAN}AC4 — ABS-174 a shared fragment is NOT a spawnable role${NC}"
rc=$(run_seam _common-rules)
assert_exit "$rc" 1 "the seam refuses to spawn _common-rules as a role"

echo ""
echo -e "${CYAN}AC5 — ABS-57 a write-free ORCH_TOOLS override forces read-only${NC}"
rc=$(run_seam be-developer ORCH_TOOLS="Read, Grep, Bash")
argv=$(cat "$RECORD_ARGV" 2>/dev/null || echo "")
assert_contains "$argv" "--permission-mode auto" "write-free override forces read-only, even for a writer role"
rc=$(run_seam be-developer ORCH_TOOLS="Read, Write, Edit, Bash")
argv=$(cat "$RECORD_ARGV" 2>/dev/null || echo "")
assert_contains "$argv" "--permission-mode accept-edits" "a write-granting override keeps edit rights"

echo ""
echo -e "${CYAN}AC6 — read-only-by-charter roles default to read-only${NC}"
rc=$(run_seam qas)
argv=$(cat "$RECORD_ARGV" 2>/dev/null || echo "")
assert_contains "$argv" "--permission-mode auto" "qas defaults to read-only without any override"
rc=$(run_seam be-developer)
argv=$(cat "$RECORD_ARGV" 2>/dev/null || echo "")
assert_contains "$argv" "--permission-mode accept-edits" "be-developer keeps edit rights without any override"

echo ""
echo -e "${CYAN}AC7 — model aliases pass through untouched (no silent downgrade)${NC}"
rc=$(run_seam qas ORCH_MODEL="opus")
argv=$(cat "$RECORD_ARGV" 2>/dev/null || echo "")
assert_contains "$argv" "--model opus" "the 'opus' alias is not pinned to an older version"
rc=$(run_seam qas)
argv=$(cat "$RECORD_ARGV" 2>/dev/null || echo "")
assert_not_contains "$argv" "--model" "no --model flag when no model is configured (CLI default stands)"

echo ""
echo -e "${CYAN}AC8 — ABS-258 a project overlay is APPENDED after the role body${NC}"
OVERLAY="$TEST_DIR/overrides/agents"
mkdir -p "$OVERLAY"
echo "OVERLAY_MARKER refines the role." > "$OVERLAY/qas.append.md"
rc=$(run_seam qas ORCH_OVERRIDES_DIR="$OVERLAY")
prompt=$(cat "$RECORD_PROMPT" 2>/dev/null || echo "")
assert_contains "$prompt" "OVERLAY_MARKER refines the role." "overlay body reached the seat prompt"
# Order matters: later text refines earlier text (commons -> role -> overlay).
order=$(printf '%s' "$prompt" | grep -n -E 'COMMONS_MARKER|ROLE_BODY_MARKER for the qas|OVERLAY_MARKER' | cut -d: -f2- | tr '\n' '|')
assert_contains "$order" "COMMONS_MARKER" "composition order recorded"
TOTAL=$((TOTAL + 1))
if [ "$(printf '%s' "$order" | sed -n 's/.*\(COMMONS_MARKER\).*\(ROLE_BODY_MARKER\).*\(OVERLAY_MARKER\).*/ok/p')" = "ok" ]; then
    echo -e "  ${GREEN}PASS${NC} order is commons -> role def -> overlay"; PASS=$((PASS + 1))
else
    echo -e "  ${RED}FAIL${NC} order is commons -> role def -> overlay (got '$order')"; FAIL=$((FAIL + 1))
fi

echo ""
echo -e "${CYAN}AC9 — ABS-92 cwd falls back to ORCH_TARGET_REPO${NC}"
TARGET="$TEST_DIR/target-repo"
WORKTREE="$TEST_DIR/worktree"
mkdir -p "$TARGET" "$WORKTREE"
cat > "$STUB_DIR/devin" <<'EOF'
#!/usr/bin/env bash
pwd > "$RECORD_ARGV"
EOF
chmod +x "$STUB_DIR/devin"
rc=$(run_seam qas ORCH_TARGET_REPO="$TARGET")
assert_contains "$(cat "$RECORD_ARGV" 2>/dev/null || echo "")" "$TARGET" "seat cwd is ORCH_TARGET_REPO when no worktree is set"
rc=$(run_seam qas ORCH_TARGET_REPO="$TARGET" ORCH_SPAWN_CWD="$WORKTREE")
assert_contains "$(cat "$RECORD_ARGV" 2>/dev/null || echo "")" "$WORKTREE" "ORCH_SPAWN_CWD takes precedence over ORCH_TARGET_REPO"

echo ""
echo -e "${CYAN}AC10 — SQLite database-lock retry with exponential backoff${NC}"
# Stub devin that fails with "database is locked" on first call, succeeds on second.
# Records call count to verify retry happened.
CALL_COUNT_FILE="$TEST_DIR/devin-call-count"
: > "$CALL_COUNT_FILE"
cat > "$STUB_DIR/devin" <<'EOF'
#!/usr/bin/env bash
COUNT_FILE="${CALL_COUNT_FILE:-/dev/null}"
n=$(cat "$COUNT_FILE" 2>/dev/null || echo 0)
n=$((n + 1))
echo "$n" > "$COUNT_FILE"
if [ "$n" -eq 1 ]; then
    echo "Error: database is locked" >&2
    exit 1
fi
echo "## Handoff"
echo "- role: qas"
echo "- status: Done"
echo "- summary: succeeded on retry"
EOF
chmod +x "$STUB_DIR/devin"
rc=$(run_seam qas ORCH_TARGET_REPO="$TARGET" ORCH_DEVIN_DB_LOCK_RETRIES=3 ORCH_DEVIN_DB_LOCK_BASE_DELAY=1 ORCH_DEVIN_DB_LOCK_MAX_DELAY=2 CALL_COUNT_FILE="$CALL_COUNT_FILE")
# The stub should have been called twice (1 fail + 1 success)
calls=$(cat "$CALL_COUNT_FILE" 2>/dev/null || echo 0)
TOTAL=$((TOTAL + 1))
if [ "$calls" -ge 2 ]; then
    echo -e "  ${GREEN}PASS${NC} devin retried after database-locked error ($calls calls)"; PASS=$((PASS + 1))
else
    echo -e "  ${RED}FAIL${NC} devin did not retry after database-locked error ($calls calls)"; FAIL=$((FAIL + 1))
fi
# The seam should exit 0 (success on retry)
assert_exit "$rc" 0 "seam exits 0 after successful retry"

echo ""
echo -e "${CYAN}AC11 — SQLite database-lock retry exhausts and fails${NC}"
# Stub devin that always fails with "database is locked"
: > "$CALL_COUNT_FILE"
cat > "$STUB_DIR/devin" <<'EOF'
#!/usr/bin/env bash
COUNT_FILE="${CALL_COUNT_FILE:-/dev/null}"
n=$(cat "$COUNT_FILE" 2>/dev/null || echo 0)
n=$((n + 1))
echo "$n" > "$COUNT_FILE"
echo "Error: database is locked" >&2
exit 1
EOF
chmod +x "$STUB_DIR/devin"
rc=$(run_seam qas ORCH_TARGET_REPO="$TARGET" ORCH_DEVIN_DB_LOCK_RETRIES=2 ORCH_DEVIN_DB_LOCK_BASE_DELAY=1 ORCH_DEVIN_DB_LOCK_MAX_DELAY=2 CALL_COUNT_FILE="$CALL_COUNT_FILE")
# The stub should have been called 3 times (1 initial + 2 retries)
calls=$(cat "$CALL_COUNT_FILE" 2>/dev/null || echo 0)
TOTAL=$((TOTAL + 1))
if [ "$calls" -ge 3 ]; then
    echo -e "  ${GREEN}PASS${NC} devin exhausted retries ($calls calls, expected 3)"; PASS=$((PASS + 1))
else
    echo -e "  ${RED}FAIL${NC} devin did not exhaust retries ($calls calls, expected 3)"; FAIL=$((FAIL + 1))
fi
# The seam should exit non-zero
TOTAL=$((TOTAL + 1))
if [ "$rc" -ne 0 ]; then
    echo -e "  ${GREEN}PASS${NC} seam exits non-zero after exhausting retries"; PASS=$((PASS + 1))
else
    echo -e "  ${RED}FAIL${NC} seam exits 0 after exhausting retries (expected non-zero)"; FAIL=$((FAIL + 1))
fi

echo ""
echo -e "${CYAN}AC12 — non-database-locked error does NOT retry${NC}"
# Stub devin that fails with a different error
: > "$CALL_COUNT_FILE"
cat > "$STUB_DIR/devin" <<'EOF'
#!/usr/bin/env bash
COUNT_FILE="${CALL_COUNT_FILE:-/dev/null}"
n=$(cat "$COUNT_FILE" 2>/dev/null || echo 0)
n=$((n + 1))
echo "$n" > "$COUNT_FILE"
echo "Error: model not found" >&2
exit 1
EOF
chmod +x "$STUB_DIR/devin"
rc=$(run_seam qas ORCH_TARGET_REPO="$TARGET" ORCH_DEVIN_DB_LOCK_RETRIES=3 ORCH_DEVIN_DB_LOCK_BASE_DELAY=1 ORCH_DEVIN_DB_LOCK_MAX_DELAY=2 CALL_COUNT_FILE="$CALL_COUNT_FILE")
calls=$(cat "$CALL_COUNT_FILE" 2>/dev/null || echo 0)
TOTAL=$((TOTAL + 1))
if [ "$calls" -eq 1 ]; then
    echo -e "  ${GREEN}PASS${NC} non-database-locked error did not retry ($calls calls)"; PASS=$((PASS + 1))
else
    echo -e "  ${RED}FAIL${NC} non-database-locked error retried ($calls calls, expected 1)"; FAIL=$((FAIL + 1))
fi

echo ""
if [ "$FAIL" -eq 0 ]; then
    echo -e "${CYAN}=== Results: $PASS/$TOTAL passed ===${NC}"
    echo -e "${GREEN}All tests passed${NC}"
    exit 0
fi
echo -e "${CYAN}=== Results: $PASS/$TOTAL passed, $FAIL failed ===${NC}"
echo -e "${RED}Tests failed${NC}"
exit 1
