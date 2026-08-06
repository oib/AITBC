#!/usr/bin/env bash
# =============================================================================
# ABS-599 — repo-relative tool paths resolve against the TARGET repo (the seat
#           cwd), never against the governing/harness checkout
# =============================================================================
# Origin (Pilot 8, Epic-Integration of PILOT-71, 2026-07-27): the RTE seat tried
# to Read `/Users/sahan/boilerplate-stable/tests/staged-suite.sh` — the HARNESS
# checkout, OUTSIDE its sandbox — instead of its own `tests/staged-suite.sh` in
# the target repo it was `cd`'d into. The read was denied and (pre-ABS-598) the
# denial poisoned the whole RTE session at the epic gate. The seat had generalized
# the harness prefix it legitimately sees on ABS-535-rewritten skill paths onto a
# repo-relative tool path. This is the SOURCE side of the defect (ABS-598 fixes
# the poison heuristic; ABS-599 stops the misresolution).
#
# The fix is guidance the two gate seats (rte, qas) carry at their staged-suite
# blocks — repo-relative paths run VERBATIM from cwd, never with a harness prefix.
# Scoped to the gate seats (not commons) on purpose: they are the roles that invoke
# repo-relative TEST tools; SOP-read poisoning of tech-writer/qas is ABS-535/ABS-598.
#
# AC2 (spawn seam, real defs): with the harness and the target checkout in DIFFERENT
#      directories (the self-hosting norm), a gate seat (rte) is `cd`'d into the
#      TARGET repo, finds `tests/staged-suite.sh` there, and carries the rule-13
#      anchor in its composed prompt — no harness-absolute path to the tool.
# AC3 (static lint): no agent-def / skill SOURCE text names a machine-absolute
#      checkout path (`/Users/…`, `/home/<user>/…`). A grep-guard, analogous to the
#      existing #EXPORT_CRITICAL-style content asserts.
#
# The seam is exercised FOR REAL via a stub `claude` (ORCH_CLAUDE_BIN) that records
# its cwd + the composed seat material — no real model spawn. Same shape as
# tests/test-spawn-skill-path.sh.
#
# Bash 3.2 / BSD-safe. Run from repo root: bash tests/tooling/test-seat-repo-path.sh
# =============================================================================
set -u

# ABS-285: scrub ambient ORCH_* so the result is a function of the commit, not of
# the seat that ran the suite. This test sets everything it needs below.
unset "${!ORCH_@}"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
SEAM="$REPO_ROOT/scripts/orchestrator-spawn-claude.sh"

TEST_DIR=$(mktemp -d "${TMPDIR:-/tmp}/seat-repo-path-test.XXXXXX")
trap 'rm -rf "$TEST_DIR"' EXIT

GREEN='\033[0;32m'; RED='\033[0;31m'; CYAN='\033[0;36m'; NC='\033[0m'
PASS=0; FAIL=0; TOTAL=0

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
assert_true() {
    TOTAL=$((TOTAL + 1))
    if [ "$1" = "0" ]; then
        echo -e "  ${GREEN}PASS${NC} $2"; PASS=$((PASS + 1))
    else
        echo -e "  ${RED}FAIL${NC} $2"; FAIL=$((FAIL + 1))
    fi
}

# =============================================================================
echo -e "${CYAN}=== ABS-599: repo-relative tool paths resolve against the target repo ===${NC}\n"
echo -e "${CYAN}AC2 — a gate seat is cd'd into the target repo and finds tests/staged-suite.sh there${NC}"
# =============================================================================
# The HARNESS is this real repo (ships the real rte.md + _common-rules.md). The
# PROJECT is a SEPARATE directory carrying its OWN tests/staged-suite.sh — this is
# exactly the self-hosting split (harness checkout != target checkout) in which the
# defect fired. A distinct marker in each staged-suite proves which one the seat sees.
HARNESS="$REPO_ROOT"
PROJECT="$TEST_DIR/project"
mkdir -p "$PROJECT/tests"
printf '#!/usr/bin/env bash\necho TARGET-REPO-STAGED-SUITE\n' > "$PROJECT/tests/staged-suite.sh"
chmod +x "$PROJECT/tests/staged-suite.sh"

# Stub `claude`: record the cwd it was exec'd in, the --agents JSON, and (on the
# PILOT-23 argv-size fallback) the plugin-materialized def.
RECORDER="$TEST_DIR/fake-claude.sh"
CWDLOG="$TEST_DIR/cwd.log"
AGENTSLOG="$TEST_DIR/agents.json"
DEFLOG="$TEST_DIR/fallback-def.md"
cat > "$RECORDER" <<RECBIN
#!/usr/bin/env bash
pwd -P > "$CWDLOG"
while [ \$# -gt 0 ]; do
    case "\$1" in
        --agents) printf '%s' "\$2" > "$AGENTSLOG"; shift 2 ;;
        --plugin-dir) cat "\$2"/agents/*.md > "$DEFLOG" 2>/dev/null; shift 2 ;;
        *) shift ;;
    esac
done
echo '{"result": "ok", "session_id": "rec"}'
RECBIN
chmod +x "$RECORDER"

rm -f "$CWDLOG" "$AGENTSLOG" "$DEFLOG"
ORCH_HARNESS_HOME="$HARNESS" \
ORCH_SPAWN_CWD="$PROJECT" \
ORCH_SEAT="rte" \
ORCH_CLAUDE_BIN="$RECORDER" \
    bash "$SEAM" rte ABS-599 /dev/null </dev/null >/dev/null 2>&1

SEAT_CWD="$(cat "$CWDLOG" 2>/dev/null || true)"
SEATTEXT="$(cat "$AGENTSLOG" 2>/dev/null || true)$(cat "$DEFLOG" 2>/dev/null || true)"
PROJECT_P="$(cd "$PROJECT" && pwd -P)"

# Precondition: the two checkouts really are different directories.
[ "$PROJECT_P" != "$HARNESS" ]; assert_true "$?" \
    "harness and target checkout are different directories (self-hosting split)"

# The seat is cd'd into the TARGET repo, not the harness.
[ "$SEAT_CWD" = "$PROJECT_P" ]; assert_true "$?" \
    "seat cwd is the target repo ($SEAT_CWD)"
[ "$SEAT_CWD" != "$HARNESS" ]; assert_true "$?" \
    "seat cwd is NOT the harness checkout"

# From that cwd, the repo-relative tool path resolves to the target repo's copy.
[ -f "$SEAT_CWD/tests/staged-suite.sh" ]; assert_true "$?" \
    "tests/staged-suite.sh is findable from the seat cwd (the target repo)"

# The composed seat prompt carries the relative invocation and the rule-13 anchor,
# and never a harness-absolute path to the tool.
assert_contains "$SEATTEXT" "tests/staged-suite.sh" \
    "rte prompt keeps the repo-relative staged-suite invocation"
assert_contains "$SEATTEXT" "it resolves against YOUR working" \
    "rte staged-suite block carries the path-resolution anchor (ABS-599)"
assert_not_contains "$SEATTEXT" "$HARNESS/tests/staged-suite.sh" \
    "no harness-absolute path to staged-suite in the seat prompt"

# =============================================================================
echo -e "\n${CYAN}AC3 — no seat SOURCE text names a machine-absolute checkout path${NC}"
# =============================================================================
# Grep-guard over agent-def + skill SOURCE (analogous to the #EXPORT_CRITICAL-style
# content asserts): a hardcoded /Users/... or /home/<user>/... path is a
# machine-specific checkout reference — exactly the class that let a seat resolve
# tests/staged-suite.sh against the harness. Portable seat text must never carry one.
SCAN_DIRS=""
[ -d "$REPO_ROOT/harness/claude/agents" ] && SCAN_DIRS="$SCAN_DIRS $REPO_ROOT/harness/claude/agents"
[ -d "$REPO_ROOT/harness/claude/skills" ] && SCAN_DIRS="$SCAN_DIRS $REPO_ROOT/harness/claude/skills"

HITS="$(grep -rnE '/(Users|home)/[A-Za-z0-9_.-]+/' $SCAN_DIRS 2>/dev/null || true)"
if [ -n "$HITS" ]; then
    echo "$HITS"
fi
[ -z "$HITS" ]; assert_true "$?" \
    "no agent-def / skill source names a machine-absolute checkout path (/Users|/home)"

# The guard is real: an injected offender is caught.
OFFENDER="$TEST_DIR/offender-agents"
mkdir -p "$OFFENDER"
printf 'Run bash /Users/someone/boilerplate-stable/tests/staged-suite.sh\n' > "$OFFENDER/bad.md"
BADHITS="$(grep -rnE '/(Users|home)/[A-Za-z0-9_.-]+/' "$OFFENDER" 2>/dev/null || true)"
[ -n "$BADHITS" ]; assert_true "$?" \
    "guard catches an injected machine-absolute harness path"

# =============================================================================
echo ""
echo -e "${CYAN}=== Results: $PASS/$TOTAL passed ===${NC}"
if [ "$FAIL" -gt 0 ]; then
    echo -e "${RED}$FAIL test(s) failed${NC}"
    exit 1
fi
echo -e "${GREEN}All tests passed${NC}"
exit 0
