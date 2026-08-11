#!/usr/bin/env bash
# =============================================================================
# Test: agent-def / skill content lint -- draft-path + inline-body guard (ABS-268)
# =============================================================================
# ABS-253 fixed a defect class in three implementer defs; ABS-268 found it had
# recurred in four more places (qas-design, bsa, issue-enrichment SKILL) AND in
# the doctrine source itself (tracker-ops SKILL). This lint makes the class
# mechanically unrepeatable.
#
# The class, precisely:
#
#   (a) INLINE --body / --reason on a tracker-adapter call. A `<` or `>` in the
#       value is parsed as shell redirection under `--permission-mode dontAsk`
#       and the call is DENIED (ABS-163). Use --body-file / --reason-file.
#
#   (b) A body/reason DRAFT written to /tmp/ or a bare $(mktemp). Those paths are
#       outside the Write/Edit allowlist (`.claude/settings.template.json` grants
#       exactly `work/scratch/`), so a seat drafting there WITH THE WRITE TOOL is
#       denied, the file never appears, and the adapter then hard-fails on the
#       missing --body-file -- the comment/transition silently never lands
#       (ABS-253).
#
# WHAT IS DELIBERATELY NOT FLAGGED:
#   - `gh pr create --body "..."` -- not a tracker call; gh takes the body inline.
#   - PROSE mentioning /tmp or $(mktemp) (the rules that EXPLAIN the trap). The
#     guard matches the redirect/assignment FORM, not the bare string.
#   - `SB="$(mktemp -d)"` sandbox DIRECTORIES -- not a body draft.
#   - EXEMPT_FILES below (see the justification there).
#
# Bash 3.2 / BSD safe: no `grep -P`, no associative arrays, no `mapfile`.
# Run from repo root: bash tests/tooling/test-agent-def-lint.sh
# =============================================================================
set -u
# PILOT-46: strip inherited backend/tracker env before any fixture runs (tests/sandbox-guard.sh).
# shellcheck source=tests/sandbox-guard.sh
. "$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)/sandbox-guard.sh"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"

PASS=0; FAIL=0; TOTAL=0
GREEN='\033[0;32m'; RED='\033[0;31m'; CYAN='\033[0;36m'; NC='\033[0m'

TEST_DIR=$(mktemp -d "${TMPDIR:-/tmp}/agent-def-lint-test.XXXXXX")
trap 'rm -rf "$TEST_DIR"' EXIT

# Files exempt from rule (b), with justification. spec-creation's snippet writes
# the body via `printf > "$BODY_FILE"` (BASH REDIRECTION, not the Write tool) to
# drive the mock tracker in an executed-AC simulation -- that path genuinely works
# under dontAsk, so flagging it would be a false positive (ABS-268 scope note).
EXEMPT_FILES="harness/claude/skills/spec-creation/SKILL.md"

is_exempt() {
    local rel="$1" e
    for e in $EXEMPT_FILES; do
        [ "$rel" = "$e" ] && return 0
    done
    return 1
}

# --- The linter ------------------------------------------------------------
# lint_tree <root> -> prints "path:line: RULE: text" per violation, exit 1 if any.
lint_tree() {
    local root="$1"
    local violations=0
    local f rel line n pending_tracker this_tracker exempt

    # agents/*.md + skills/**/*.md under the given root
    for f in $(find "$root/agents" -name '*.md' 2>/dev/null | sort) \
             $(find "$root/skills" -name '*.md' 2>/dev/null | sort); do
        rel="${f#$REPO_ROOT/}"
        n=0
        pending_tracker=0
        # rule-B exemption is a per-FILE property -- resolve it once, not per line
        exempt=0
        is_exempt "$rel" && exempt=1

        while IFS= read -r line || [ -n "$line" ]; do
            n=$((n + 1))

            # Does this line (or the tracker command it continues) invoke the adapter?
            case "$line" in
                *TRACKER_CMD*|*mock-tracker.sh*|*jira-tracker.sh*) this_tracker=1 ;;
                *) this_tracker=0 ;;
            esac
            [ "$pending_tracker" = "1" ] && this_tracker=1

            # RULE (a): inline --body "/--reason " on a tracker-adapter call.
            if [ "$this_tracker" = "1" ]; then
                case "$line" in
                    *'--body "'*|*'--reason "'*)
                        echo "$rel:$n: RULE-A inline --body/--reason on a tracker call (use --body-file/--reason-file; ABS-163):$line"
                        violations=$((violations + 1))
                        ;;
                esac
            fi

            # Continuation tracking: a trailing backslash carries the command on.
            case "$line" in
                *\\) [ "$this_tracker" = "1" ] && pending_tracker=1 ;;
                *) pending_tracker=0 ;;
            esac

            [ "$exempt" = "1" ] && continue

            # RULE (b1): redirecting a draft INTO /tmp.
            case "$line" in
                *'> /tmp/'*|*'>/tmp/'*|*'> "/tmp/'*)
                    echo "$rel:$n: RULE-B draft redirected into /tmp (use work/scratch/; ABS-253):$line"
                    violations=$((violations + 1))
                    ;;
            esac

            # RULE (b2): a body/reason draft var assigned a bare mktemp.
            # `$(mktemp -d)` (a sandbox DIR) is intentionally not matched.
            case "$line" in
                *_FILE=*'$(mktemp)'*)
                    echo "$rel:$n: RULE-B body/reason draft in a bare \$(mktemp) (use work/scratch/; ABS-253):$line"
                    violations=$((violations + 1))
                    ;;
            esac
        done < "$f"
    done

    [ "$violations" -eq 0 ] && return 0
    return 1
}

assert_true() {
    local code="$1"; local label="$2"
    TOTAL=$((TOTAL + 1))
    if [ "$code" = "0" ]; then
        echo -e "  ${GREEN}PASS${NC} $label"; PASS=$((PASS + 1))
    else
        echo -e "  ${RED}FAIL${NC} $label"; FAIL=$((FAIL + 1))
    fi
}

echo -e "${CYAN}=== agent-def lint: draft-path + inline-body guard (ABS-268) ===${NC}\n"

# --- 1. REGRESSION PROOF: the guard must FAIL on the pre-fix content ---------
# These fixtures are the VERBATIM defective lines this ticket removed (the
# pre-fix qas-design.md, bsa.md and issue-enrichment SKILL.md). If the guard
# ever stops flagging them, it has been hollowed out.
mkdir -p "$TEST_DIR/pre-fix/agents" "$TEST_DIR/pre-fix/skills/issue-enrichment"

cat > "$TEST_DIR/pre-fix/agents/qas-design.md" <<'EOF'
```bash
DESIGN_SYSTEM_ENABLED=true scripts/design-system-check.sh <url> > /tmp/dsc-evidence.md
"${TRACKER_CMD:-scripts/mock-tracker.sh}" comment ABS-XXX \
  --kind gate-results --actor qas-design --body "$(cat /tmp/dsc-evidence.md)"
"${TRACKER_CMD:-scripts/mock-tracker.sh}" comment ABS-XXX \
  --kind gate-results --actor qas-design --body "<design test report>"
```
EOF

cat > "$TEST_DIR/pre-fix/agents/bsa.md" <<'EOF'
```bash
BODY_FILE="$(mktemp)"
"${TRACKER_CMD:-scripts/mock-tracker.sh}" comment <epic-id> --kind handoff --actor bsa --body-file "$BODY_FILE"
```
EOF

cat > "$TEST_DIR/pre-fix/skills/issue-enrichment/SKILL.md" <<'EOF'
```bash
"${TRACKER_CMD:-scripts/mock-tracker.sh}" get "$MATCH" > /tmp/match-current.md
BODY_FILE="$(mktemp)"
```
EOF

PRE_OUT="$TEST_DIR/pre-fix.out"
lint_tree "$TEST_DIR/pre-fix" > "$PRE_OUT" 2>&1
pre_code=$?

[ "$pre_code" -ne 0 ]; assert_true $? "guard FAILS on the pre-fix content (regression proof)"

grep -q 'RULE-A' "$PRE_OUT"; assert_true $? "  detects RULE-A: inline --body on a tracker call"
grep -q 'RULE-B draft redirected into /tmp' "$PRE_OUT"; assert_true $? "  detects RULE-B: draft redirected into /tmp"
grep -q 'RULE-B body/reason draft in a bare' "$PRE_OUT"; assert_true $? "  detects RULE-B: body draft in a bare \$(mktemp)"

# Continuation case: the flag sits on a CONTINUED line, not on the call line.
grep -q 'qas-design.md:4: RULE-A' "$PRE_OUT"; assert_true $? "  detects an inline flag on a backslash-CONTINUED tracker call"

# --- 2. NO FALSE POSITIVES: the sanctioned forms must stay clean -------------
mkdir -p "$TEST_DIR/clean/agents" "$TEST_DIR/clean/skills/release-patterns"

cat > "$TEST_DIR/clean/agents/ok.md" <<'EOF'
Draft reason/body files into `work/scratch/`. `/tmp/` and a bare `$(mktemp)` are
outside that grant: a seat that drafts there with Write/Edit is denied.

```bash
mkdir -p work/scratch
printf '%s\n' "AC/DoD met." > work/scratch/ABS-1-handoff.md
"${TRACKER_CMD:-scripts/mock-tracker.sh}" transition ABS-1 "In Review" --actor be-developer \
  --reason-file work/scratch/ABS-1-handoff.md --expect-from "In Progress"

SB="$(mktemp -d)"; printf 'gate: PASS\n' > "$SB/c.md"
scripts/mock-tracker.sh comment ABS-1 --kind gate-results --actor qas --body-file "$SB/c.md"
```
EOF

cat > "$TEST_DIR/clean/skills/release-patterns/SKILL.md" <<'EOF'
```bash
gh pr create --title "feat(scope): description [ABS-1]" --body "$(cat <<'BODY'
Not a tracker call -- gh takes the body inline.
BODY
)"
```
EOF

CLEAN_OUT="$TEST_DIR/clean.out"
lint_tree "$TEST_DIR/clean" > "$CLEAN_OUT" 2>&1
assert_true $? "no false positives on the sanctioned forms"
if [ -s "$CLEAN_OUT" ]; then
    echo -e "    ${RED}unexpected findings:${NC}"; sed 's/^/      /' "$CLEAN_OUT"
fi

# --- 3. THE REAL GATE: the shipped harness must be clean ---------------------
REAL_OUT="$TEST_DIR/real.out"
lint_tree "$REPO_ROOT/harness/claude" > "$REAL_OUT" 2>&1
assert_true $? "harness/claude agents + skills are clean"
if [ -s "$REAL_OUT" ]; then
    echo -e "    ${RED}violations:${NC}"; sed 's/^/      /' "$REAL_OUT"
fi

# --- Summary ----------------------------------------------------------------
echo ""
echo -e "${CYAN}=== Results ===${NC}"
echo -e "  Total:  $TOTAL"
echo -e "  ${GREEN}Passed: $PASS${NC}"
echo -e "  ${RED}Failed: $FAIL${NC}"
[ "$FAIL" -eq 0 ] || exit 1
echo -e "\n${GREEN}Agent-def lint: all checks passed.${NC}"
exit 0
