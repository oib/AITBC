#!/bin/bash
# =============================================================================
# Test: Claude Code hooks — BEHAVIORAL (ABS-32 / ABS-45)
# =============================================================================
# Unlike test-hooks-config.sh (which greps the annotated source-of-record),
# this suite extracts each hook command FROM .claude/settings.template.json
# (the file Claude Code actually auto-loads) with jq, pipes realistic Claude
# Code hook JSON payloads to it, and asserts exit codes + key output.
#
# It also fails if anyone reverts matchers to the old command-in-matcher style.
#
# Runs from repo root: bash tests/test-hooks-behavioral.sh
# Must pass on macOS bash 3.2 + BSD userland. jq is required (as it is for the
# hooks themselves); the suite skips with a clear message if jq is absent.
# =============================================================================

set -e
# PILOT-46: strip inherited backend/tracker env before any fixture runs (tests/sandbox-guard.sh).
# shellcheck source=tests/sandbox-guard.sh
. "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/sandbox-guard.sh"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
SETTINGS="$REPO_ROOT/.claude/settings.template.json"

GREEN='\033[0;32m'; RED='\033[0;31m'; CYAN='\033[0;36m'; YELLOW='\033[1;33m'; NC='\033[0m'
PASS=0; FAIL=0; TOTAL=0

if ! command -v jq >/dev/null 2>&1; then
    echo "SKIP: jq not installed — behavioral hook tests require jq"; exit 0
fi

# The hooks call scripts via ${CLAUDE_PROJECT_DIR:-.}; point it at the repo root
# and run everything from there so relative fallbacks resolve.
export CLAUDE_PROJECT_DIR="$REPO_ROOT"
cd "$REPO_ROOT"

# Test isolation (ABS-177): neutralize any inherited TRACKER_CMD /
# ITERATION_GUARD_ADAPTER so the iteration-guard cases resolve against the
# isolated mock-tracker fixture below (its default fallback) rather than a live
# adapter exported in the operator shell — which would make the guard fail open
# on the fixture tickets instead of blocking.
unset TRACKER_CMD ITERATION_GUARD_ADAPTER

# Isolated tracker fixture for the iteration-guard cases.
TEST_DIR=$(mktemp -d /tmp/hooks-behavioral-XXXXXX)
trap 'rm -rf "$TEST_DIR"' EXIT
export MOCK_TRACKER_TICKETS_DIR="$TEST_DIR/work/tickets"
export MOCK_TRACKER_STATUSES="$REPO_ROOT/profiles/neutral/adapters/statuses.yaml"
TRACKER="$REPO_ROOT/scripts/mock-tracker.sh"
tracker() { bash "$TRACKER" "$@"; }
bounce()  { tracker comment "$1" --kind gate-results --actor qas --body "$2" >/dev/null; }

# hook_cmd EVENT MATCHER INDEX — extract the INDEX-th command string of the
# matcher group whose .matcher equals MATCHER (use "" for groups with no matcher).
hook_cmd() {
    local event="$1" matcher="$2" idx="$3"
    jq -r --arg ev "$event" --arg m "$matcher" --argjson i "$idx" '
      .hooks[$ev][]
      | select((.matcher // "") == $m)
      | .hooks[$i].command
    ' "$SETTINGS"
}

# run_hook CMD PAYLOAD -> sets globals OUT (stdout+stderr) and EC (exit code).
run_hook() {
    local cmd="$1" payload="$2"
    EC=0
    OUT=$(printf '%s' "$payload" | bash -c "$cmd" 2>&1) || EC=$?
}

assert_exit() {
    local expected="$1" label="$2"
    TOTAL=$((TOTAL + 1))
    if [ "$EC" = "$expected" ]; then
        echo -e "  ${GREEN}PASS${NC} $label"; PASS=$((PASS + 1))
    else
        echo -e "  ${RED}FAIL${NC} $label (expected exit $expected, got $EC)"
        echo -e "  ${YELLOW}  Output:${NC} $OUT"; FAIL=$((FAIL + 1))
    fi
}
assert_contains() {
    local needle="$1" label="$2"
    TOTAL=$((TOTAL + 1))
    if printf '%s' "$OUT" | grep -qF -- "$needle"; then
        echo -e "  ${GREEN}PASS${NC} $label"; PASS=$((PASS + 1))
    else
        echo -e "  ${RED}FAIL${NC} $label (expected output to contain: $needle)"
        echo -e "  ${YELLOW}  Output:${NC} $OUT"; FAIL=$((FAIL + 1))
    fi
}
assert_empty() {
    local label="$1"
    TOTAL=$((TOTAL + 1))
    if [ -z "$OUT" ]; then
        echo -e "  ${GREEN}PASS${NC} $label"; PASS=$((PASS + 1))
    else
        echo -e "  ${RED}FAIL${NC} $label (expected empty, got: $OUT)"; FAIL=$((FAIL + 1))
    fi
}

bash_payload()  { printf '{"tool_name":"Bash","tool_input":{"command":%s}}' "$(printf '%s' "$1" | jq -R .)"; }
edit_payload()  { printf '{"tool_name":"Edit","tool_input":{"file_path":%s}}' "$(printf '%s' "$1" | jq -R .)"; }

echo -e "${CYAN}=== Hooks Behavioral (ABS-32) ===${NC}\n"

# --- 0. Settings template is valid and carries a hooks block -----------------
echo -e "${CYAN}Settings template shape${NC}"
TOTAL=$((TOTAL + 1))
if jq -e '.hooks.PreToolUse and .hooks.PostToolUse' "$SETTINGS" >/dev/null 2>&1; then
    echo -e "  ${GREEN}PASS${NC} settings.template.json has a hooks block"; PASS=$((PASS + 1))
else
    echo -e "  ${RED}FAIL${NC} settings.template.json missing hooks block"; FAIL=$((FAIL + 1))
fi

# --- 1. Matchers are tool-name-only (regression guard against old style) -----
# The old, broken style used matchers like "Bash.*git commit" (a space and/or
# ".*git"). Assert NO matcher in the template contains a space or ".*git".
echo -e "${CYAN}Matcher hygiene (fails if reverted to old command-in-matcher style)${NC}"
BAD_MATCHERS=$(jq -r '
  [ .hooks | to_entries[] | .value[] | (.matcher // "") ]
  | map(select(test(" ") or test("\\.\\*git")))
  | .[]
' "$SETTINGS")
TOTAL=$((TOTAL + 1))
if [ -z "$BAD_MATCHERS" ]; then
    echo -e "  ${GREEN}PASS${NC} no matcher contains a space or '.*git'"; PASS=$((PASS + 1))
else
    echo -e "  ${RED}FAIL${NC} command-in-matcher style detected: $BAD_MATCHERS"; FAIL=$((FAIL + 1))
fi
# Every PreToolUse/PostToolUse matcher must be one of the allowed tool-name forms.
TOTAL=$((TOTAL + 1))
BAD_TOOLNAME=$(jq -r '
  [ .hooks.PreToolUse[]?, .hooks.PostToolUse[]? | (.matcher // "") ]
  | map(select(. as $m | ["Bash","Write|Edit","Edit|Write",""] | index($m) | not))
  | .[]
' "$SETTINGS")
if [ -z "$BAD_TOOLNAME" ]; then
    echo -e "  ${GREEN}PASS${NC} PreToolUse/PostToolUse matchers are tool names only"; PASS=$((PASS + 1))
else
    echo -e "  ${RED}FAIL${NC} unexpected matcher(s): $BAD_TOOLNAME"; FAIL=$((FAIL + 1))
fi
# No $TOOL_INPUT and no grep -oP in any hook command (portability + correctness).
TOTAL=$((TOTAL + 1))
BADCMD=$(jq -r '[ .hooks | to_entries[] | .value[] | .hooks[] | .command ] | .[]' "$SETTINGS" \
    | grep -nE '\$TOOL_INPUT|grep -oP|grep -P' || true)
if [ -z "$BADCMD" ]; then
    echo -e "  ${GREEN}PASS${NC} no \$TOOL_INPUT / grep -oP in any hook command"; PASS=$((PASS + 1))
else
    echo -e "  ${RED}FAIL${NC} forbidden construct in hook command: $BADCMD"; FAIL=$((FAIL + 1))
fi

# --- 2. git push guard (PreToolUse Bash, index 1) ----------------------------
echo -e "${CYAN}git push guard${NC}"
PUSH_CMD=$(hook_cmd PreToolUse Bash 1)

# On main -> block (exit 2). Fake being on main via a stub git on PATH.
FAKE_BIN="$TEST_DIR/bin-main"; mkdir -p "$FAKE_BIN"
cat > "$FAKE_BIN/git" <<'STUB'
#!/bin/bash
case "$1 $2" in
  "branch --show-current") echo main ;;
  "status --porcelain") : ;;      # clean
  *) : ;;
esac
exit 0
STUB
chmod +x "$FAKE_BIN/git"
EC=0; OUT=$(printf '%s' "$(bash_payload 'git push origin main')" | PATH="$FAKE_BIN:$PATH" bash -c "$PUSH_CMD" 2>&1) || EC=$?
assert_exit 2 "git push on main -> exit 2"
assert_contains "BLOCKER" "push-to-main block message"

# On a feature branch, clean, up to date -> exit 0.
FAKE_BIN2="$TEST_DIR/bin-feat"; mkdir -p "$FAKE_BIN2"
cat > "$FAKE_BIN2/git" <<'STUB'
#!/bin/bash
case "$1 $2" in
  "branch --show-current") echo feature-x ;;
  "status --porcelain") : ;;      # clean
  "fetch origin") exit 0 ;;
  "log HEAD..origin/main") : ;;   # not behind
  *) : ;;
esac
exit 0
STUB
chmod +x "$FAKE_BIN2/git"
EC=0; OUT=$(printf '%s' "$(bash_payload 'git push origin feature-x')" | PATH="$FAKE_BIN2:$PATH" bash -c "$PUSH_CMD" 2>&1) || EC=$?
assert_exit 0 "git push on feature branch (clean, current) -> exit 0"

# Non-push command must be ignored by the push guard (exit 0, silent).
run_hook "$PUSH_CMD" "$(bash_payload 'ls -la')"
assert_exit 0 "non-push command -> push guard exits 0"

# --- 3. commit-format reminder (PreToolUse Bash, index 0) --------------------
echo -e "${CYAN}commit-format reminder${NC}"
COMMIT_CMD=$(hook_cmd PreToolUse Bash 0)
run_hook "$COMMIT_CMD" "$(bash_payload 'git commit -m "feat: x"')"
assert_exit 0 "git commit -> reminder exits 0"
assert_contains "conventional format" "commit reminder fires for git commit"
run_hook "$COMMIT_CMD" "$(bash_payload 'git status')"
assert_exit 0 "git status -> no reminder (exit 0)"
assert_empty "commit reminder does NOT fire for non-commit command"

# --- 4. iteration guard (PreToolUse Bash, index 3) --------------------------
echo -e "${CYAN}iteration guard${NC}"
GUARD_CMD=$(hook_cmd PreToolUse Bash 3)

# Real-bounce seeding (ABS-115): marker-bearing gate comment + backward
# transition; the ticket ends back at the In Review gate.
trans() { tracker transition "$1" "$2" --actor test --reason x >/dev/null; }
to_review() { trans "$1" "Ready for Development"; trans "$1" "In Progress"; trans "$1" "In Review"; }
real_bounce() { bounce "$1" "$2"; trans "$1" "In Progress"; trans "$1" "In Review"; }

# Under cap: 1 prior REAL bounce, cap 3 -> the guard proceeds (exit 0).
T=$(tracker create --type ticket --title "under")
to_review "$T"
real_bounce "$T" "Iteration 1 of 3"
BOUNCE_CMD="bash scripts/mock-tracker.sh comment $T --kind gate-results --actor qas --body \"Iteration 2 of 3\""
run_hook "$GUARD_CMD" "$(bash_payload "$BOUNCE_CMD")"
assert_exit 0 "iteration-guard under cap -> exit 0"

# At cap: 2 prior REAL bounces, cap 3 -> next bounce forbidden -> block (exit 2).
T=$(tracker create --type ticket --title "atcap")
to_review "$T"
real_bounce "$T" "Iteration 1 of 3"; real_bounce "$T" "Iteration 2 of 3"
BOUNCE_CMD="bash scripts/mock-tracker.sh comment $T --kind gate-results --actor qas --body \"Iteration 3 of 3\""
run_hook "$GUARD_CMD" "$(bash_payload "$BOUNCE_CMD")"
assert_exit 2 "iteration-guard at cap -> exit 2"
assert_contains "BLOCK" "at-cap block carries BLOCK label"

# Marker-only history (no backward transitions) must NOT block (ABS-107 fix).
T=$(tracker create --type ticket --title "markeronly")
to_review "$T"
bounce "$T" "Iteration 1 of 3"; bounce "$T" "Iteration 2 of 3"
BOUNCE_CMD="bash scripts/mock-tracker.sh comment $T --kind gate-results --actor qas --body \"Iteration 3 of 3\""
run_hook "$GUARD_CMD" "$(bash_payload "$BOUNCE_CMD")"
assert_exit 0 "iteration-guard: marker-only history -> no false-positive block"

# A command with no marker must be ignored by the guard hook (exit 0).
run_hook "$GUARD_CMD" "$(bash_payload 'git status')"
assert_exit 0 "no marker in command -> guard hook exits 0"

# --- 5. markdown post-edit hook (PostToolUse Write|Edit, index 1) ------------
echo -e "${CYAN}markdown post-edit hook${NC}"
MD_CMD=$(hook_cmd PostToolUse "Write|Edit" 1)
# A .md edit takes the md path (npx may be absent/offline; the hook is fail-open
# so it must still exit 0). We assert exit 0 and that it did not hard-fail.
MDFILE="$TEST_DIR/sample.md"; printf '# hi\n' > "$MDFILE"
run_hook "$MD_CMD" "$(edit_payload "$MDFILE")"
assert_exit 0 "markdown edit -> md hook exits 0"
# A non-md edit must short-circuit before any formatter (exit 0, no formatter output).
run_hook "$MD_CMD" "$(edit_payload "$TEST_DIR/app.ts")"
assert_exit 0 "non-md edit -> md hook exits 0"
assert_empty "non-md edit produces no formatter output"

# --- 6. doc reminder (PostToolUse Write|Edit, index 0) ----------------------
echo -e "${CYAN}doc reminder${NC}"
DOC_CMD=$(hook_cmd PostToolUse "Write|Edit" 0)
run_hook "$DOC_CMD" "$(edit_payload 'CONTRIBUTING.md')"
assert_exit 0 "high-impact edit -> doc reminder exits 0"
assert_contains "High-impact file modified" "doc reminder fires for CONTRIBUTING.md"
run_hook "$DOC_CMD" "$(edit_payload 'src/util.ts')"
assert_empty "doc reminder does NOT fire for ordinary file"

# --- 7. jq-missing graceful degrade -----------------------------------------
# Simulate jq absent by shadowing it with an empty PATH dir. A Bash-command hook
# must fail open (exit 0) with a one-line stderr warning, never hard-block.
echo -e "${CYAN}jq-missing graceful degrade${NC}"
NOJQ_BIN="$TEST_DIR/nojq"; mkdir -p "$NOJQ_BIN"
for t in bash grep git printf cat; do ln -sf "$(command -v $t)" "$NOJQ_BIN/$t" 2>/dev/null || true; done
EC=0; OUT=$(printf '%s' "$(bash_payload 'git push origin main')" | PATH="$NOJQ_BIN" bash -c "$PUSH_CMD" 2>&1) || EC=$?
assert_exit 0 "push guard without jq -> fail-open exit 0"
assert_contains "jq not found" "push guard warns about missing jq"

# =============================================================================
echo -e "\n${CYAN}=== Test Results ===${NC}\n"
echo -e "  Total:  $TOTAL"
echo -e "  ${GREEN}Passed: $PASS${NC}"
if [ "$FAIL" -gt 0 ]; then
    echo -e "  ${RED}Failed: $FAIL${NC}"; exit 1
else
    echo -e "  Failed: 0"; echo -e "\n  ${GREEN}ALL TESTS PASSED${NC}\n"; exit 0
fi
