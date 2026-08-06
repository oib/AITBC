#!/usr/bin/env bash
# =============================================================================
# PILOT-76 — a seat's TMPDIR is pinned INSIDE its own worktree
# =============================================================================
# Origin (v3-pilots #4/#6/#7): the RTE Epic-Integration gate ran the test suite
# from a `mktemp` scratch dir under the default $TMPDIR (/var/folders on macOS,
# /tmp on Linux). Under --permission-mode dontAsk a seat may Read/Write only
# within its cwd/worktree tree, so that scratch sat OUTSIDE the seat's Read
# allowlist: the seat could RUN the suite but was DENIED reading its own test
# artefacts → never assembled a pass/fail → 2×NOMOVE → respawn-limit → Needs PO
# Decision, three distinct pilots running (PILOT-39 the sharpest read-denial,
# PILOT-58 the "nothing to integrate" case that STILL could not produce a
# verdict). The fix (scripts/orchestrator-spawn-claude.sh): export a per-seat
# TMPDIR=<worktree>/tmp before exec, so every mktemp the seat and the harness it
# spawns makes lands under the already-allowlisted cwd.
#
# The seam is exercised FOR REAL (not reimplemented): a stub `claude` handed via
# ORCH_CLAUDE_BIN records the TMPDIR it was exec'd with. No real Claude spawn.
# Same harness/project split + recorder pattern as tests/test-spawn-skill-path.sh.
#
# Bash 3.2 / BSD-safe. Run from repo root: bash tests/tooling/test-spawn-tmpdir.sh
# =============================================================================
set -u

# ABS-285: scrub ambient ORCH_* so the result is a function of the commit, not
# of the seat that ran the suite. This test sets everything it needs below.
unset "${!ORCH_@}"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
SEAM="$REPO_ROOT/scripts/orchestrator-spawn-claude.sh"

TEST_DIR=$(mktemp -d "${TMPDIR:-/tmp}/spawn-tmpdir-test.XXXXXX")
trap 'rm -rf "$TEST_DIR"' EXIT

GREEN='\033[0;32m'; RED='\033[0;31m'; CYAN='\033[0;36m'; NC='\033[0m'
PASS=0; FAIL=0; TOTAL=0

assert_eq() {
    TOTAL=$((TOTAL + 1))
    if [ "$1" = "$2" ]; then
        echo -e "  ${GREEN}PASS${NC} $3"; PASS=$((PASS + 1))
    else
        echo -e "  ${RED}FAIL${NC} $3 (expected '$2', got '$1')"; FAIL=$((FAIL + 1))
    fi
}
assert_dir() {
    TOTAL=$((TOTAL + 1))
    if [ -d "$1" ]; then
        echo -e "  ${GREEN}PASS${NC} $2"; PASS=$((PASS + 1))
    else
        echo -e "  ${RED}FAIL${NC} $2 (dir not found: $1)"; FAIL=$((FAIL + 1))
    fi
}

# -----------------------------------------------------------------------------
# Fixtures: a HARNESS (ships the agent defs) and a PROJECT (the seat's cwd /
# worktree). Separate dirs — the ABS-92 self-hosting split.
# -----------------------------------------------------------------------------
HARNESS="$TEST_DIR/harness"
PROJECT="$TEST_DIR/project"
AGENTS_DIR="$HARNESS/harness/claude/agents"
mkdir -p "$AGENTS_DIR" "$PROJECT"

cat > "$AGENTS_DIR/_common-rules.md" <<'EOF'
---
title: common rules
---
COMMONS.
EOF

cat > "$AGENTS_DIR/rte.md" <<'EOF'
---
name: rte
description: gate seat
tools: [Read, Bash]
---
Run the suite at the Epic-Integration gate.
EOF

# Stub `claude`: records the TMPDIR it was exec'd with, then returns a
# well-formed result. Never talks to a real model.
RECORDER="$TEST_DIR/fake-claude.sh"
TMPDIRLOG="$TEST_DIR/tmpdir.log"
cat > "$RECORDER" <<RECBIN
#!/usr/bin/env bash
printf '%s' "\${TMPDIR:-UNSET}" > "$TMPDIRLOG"
echo '{"result": "ok", "session_id": "rec"}'
RECBIN
chmod +x "$RECORDER"

echo -e "${CYAN}=== PILOT-76: seat TMPDIR pinned inside the worktree ===${NC}\n"

# =============================================================================
echo -e "${CYAN}AC — a worktree-provisioned seat gets TMPDIR=<worktree>/tmp${NC}"
# =============================================================================
rm -f "$TMPDIRLOG"
ORCH_HARNESS_HOME="$HARNESS" \
ORCH_SPAWN_CWD="$PROJECT" \
ORCH_CLAUDE_BIN="$RECORDER" \
    bash "$SEAM" rte PILOT-76 /dev/null </dev/null >/dev/null 2>&1
SEEN="$(cat "$TMPDIRLOG" 2>/dev/null || true)"
# Canonicalize the expected path the same way the seam does (cd normalizes any
# double slash a trailing-slash system $TMPDIR left in the mktemp'd fixture path).
assert_eq "$SEEN" "$(cd "$PROJECT" && pwd)/tmp" \
    "seat exec'd with TMPDIR pointing inside its ORCH_SPAWN_CWD worktree"
assert_dir "$PROJECT/tmp" \
    "the tmp dir was actually created (mktemp targets land there, readable at the gate)"

# =============================================================================
echo -e "\n${CYAN}AC — TMPDIR follows ORCH_TARGET_REPO when no worktree is set${NC}"
# =============================================================================
# In self-hosting without a per-ticket worktree the cwd is ORCH_TARGET_REPO;
# scratch must still land inside that already-allowlisted target, never /tmp.
TARGET="$TEST_DIR/target"
mkdir -p "$TARGET"
rm -f "$TMPDIRLOG"
ORCH_HARNESS_HOME="$HARNESS" \
ORCH_TARGET_REPO="$TARGET" \
ORCH_CLAUDE_BIN="$RECORDER" \
    bash "$SEAM" rte PILOT-76 /dev/null </dev/null >/dev/null 2>&1
SEEN="$(cat "$TMPDIRLOG" 2>/dev/null || true)"
assert_eq "$SEEN" "$(cd "$TARGET" && pwd)/tmp" \
    "seat exec'd with TMPDIR pointing inside its ORCH_TARGET_REPO cwd"
assert_dir "$TARGET/tmp" \
    "the tmp dir was created inside the target repo"

# =============================================================================
echo ""
echo -e "${CYAN}=== Results: $PASS/$TOTAL passed ===${NC}"
if [ "$FAIL" -gt 0 ]; then
    echo -e "${RED}$FAIL test(s) failed${NC}"
    exit 1
fi
echo -e "${GREEN}All tests passed${NC}"
exit 0
